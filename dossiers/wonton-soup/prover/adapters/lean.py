import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from leantree.core.lean import LeanGoal
from leantree.core.project import LeanProject
from leantree.metavar_graph import MetavarGraph
from leantree.repl_adapter.interaction import (
    LeanEnvironmentCheckpoint,
    LeanInteractionException,
    LeanProcessException,
    LeanProofBranch,
)

from prover.assembly import ProofAssemblyTrace
from prover.expr import ExprDAG, PartialProofTerm
from prover.tactic_ir import (
    CONTINUATION_KIND_BRANCH,
    CONTINUATION_KIND_CHAIN,
    CONTINUATION_KIND_REFINE,
    CONTINUATION_KIND_SOLVE,
    EFFECT_BRANCHES_GOALS,
    EFFECT_CLOSES_GOALS,
    EFFECT_COMPLETES_TERM,
    EFFECT_COUPLES_GOALS,
    EFFECT_OPENS_GOALS,
    EFFECT_REFINES_TERM,
    EFFECT_SPAWNS_GOALS,
    EFFECT_SPLITS_INDEPENDENT_GOALS,
    EFFECT_USES_HYPOTHESES,
    GOAL_COUPLING_COUPLED,
    GOAL_COUPLING_INDEPENDENT,
    GOAL_COUPLING_NONE,
    GOAL_COUPLING_UNKNOWN,
    ordered_effect_flags,
    stable_unique_strings,
)

logger = logging.getLogger(__name__)

LEAN_STARTUP_IMPORTS = "import Mathlib\nopen BigOperators Real Nat Topology"
LEAN_STARTUP_TIMEOUT_S = 120.0


@dataclass
class ProofState:
    mvar_id: str
    branch: LeanProofBranch
    checkpoint: LeanEnvironmentCheckpoint
    checkpoint_id: int


@dataclass
class TacticPreview:
    tactic: str
    parent_mvar_id: str
    child_mvar_ids: list[str]
    child_goals: list[LeanGoal]
    partial_term_before: PartialProofTerm | None
    partial_term_after: PartialProofTerm | None
    completed_proof_term: ExprDAG | None
    goals_before: list[str]
    goals_after: list[str]
    checkpoint: LeanEnvironmentCheckpoint
    checkpoint_id: int
    branches: list[LeanProofBranch]
    mctx_after: MetavarGraph | None = None
    tactic_depends_on: list[str] = field(default_factory=list)
    spawned_goals: list[LeanGoal] = field(default_factory=list)
    proof_step_count: int = 0

    def branch_goal_counts(self) -> list[int]:
        return [len(branch.state.goals) for branch in self.branches if not branch.is_solved]

    def observed_child_goal_count(self) -> int:
        return max(len(self.child_mvar_ids), len(self.child_goals), self.spawned_goal_count())

    def observed_branch_count(self) -> int:
        counts = self.branch_goal_counts()
        if counts:
            return len(counts)
        return 1 if self.observed_child_goal_count() > 0 else 0

    def shared_mvar_count(self) -> int:
        if self.mctx_after is None or len(self.child_goals) <= 1:
            return 0
        return len(self.mctx_after.shared_metavars(self.child_goals))

    def spawned_goal_count(self) -> int:
        return len(self.spawned_goals)

    def goal_coupling(self) -> str:
        observed_child_goal_count = self.observed_child_goal_count()
        if observed_child_goal_count <= 1:
            return GOAL_COUPLING_NONE
        branch_goal_counts = self.branch_goal_counts()
        if self.shared_mvar_count() > 0:
            return GOAL_COUPLING_COUPLED
        if any(count > 1 for count in branch_goal_counts):
            return GOAL_COUPLING_COUPLED
        if len(branch_goal_counts) > 1:
            return GOAL_COUPLING_INDEPENDENT
        return GOAL_COUPLING_UNKNOWN

    def continuation_kind(self) -> str:
        before_hash = (
            self.partial_term_before.structural_hash()
            if self.partial_term_before is not None
            else None
        )
        after_hash = (
            self.partial_term_after.structural_hash()
            if self.partial_term_after is not None
            else None
        )
        observed_child_goal_count = self.observed_child_goal_count()
        if self.completed_proof_term is not None or observed_child_goal_count == 0:
            return CONTINUATION_KIND_SOLVE
        if observed_child_goal_count > 1:
            return CONTINUATION_KIND_BRANCH
        if after_hash is not None and after_hash != before_hash:
            return CONTINUATION_KIND_REFINE
        return CONTINUATION_KIND_CHAIN

    def action_metadata(self, *, expanded_child_count: int | None = None) -> dict[str, object]:
        goals_closed = [goal for goal in self.goals_before if goal not in self.goals_after]
        goals_opened = [goal for goal in self.goals_after if goal not in self.goals_before]
        continuation_kind = self.continuation_kind()
        goal_coupling = self.goal_coupling()
        observed_child_goal_count = self.observed_child_goal_count()
        branch_goal_counts = self.branch_goal_counts()
        branch_count = self.observed_branch_count()
        tactic_depends_on = stable_unique_strings(self.tactic_depends_on)
        effect_flags: list[str] = []
        if observed_child_goal_count > 1:
            effect_flags.append(EFFECT_BRANCHES_GOALS)
        if goals_closed:
            effect_flags.append(EFFECT_CLOSES_GOALS)
        if goals_opened:
            effect_flags.append(EFFECT_OPENS_GOALS)
        if self.spawned_goals:
            effect_flags.append(EFFECT_SPAWNS_GOALS)
        if tactic_depends_on:
            effect_flags.append(EFFECT_USES_HYPOTHESES)
        before_hash = (
            self.partial_term_before.structural_hash()
            if self.partial_term_before is not None
            else None
        )
        after_hash = (
            self.partial_term_after.structural_hash()
            if self.partial_term_after is not None
            else None
        )
        completed_hash = (
            self.completed_proof_term.structural_hash()
            if self.completed_proof_term is not None
            else None
        )
        if continuation_kind == CONTINUATION_KIND_REFINE:
            effect_flags.append(EFFECT_REFINES_TERM)
        if completed_hash is not None:
            effect_flags.append(EFFECT_COMPLETES_TERM)
        if goal_coupling == GOAL_COUPLING_COUPLED:
            effect_flags.append(EFFECT_COUPLES_GOALS)
        if goal_coupling == GOAL_COUPLING_INDEPENDENT:
            effect_flags.append(EFFECT_SPLITS_INDEPENDENT_GOALS)
        return {
            "branch_arity": observed_child_goal_count,
            "expanded_child_count": (
                expanded_child_count
                if expanded_child_count is not None
                else observed_child_goal_count
            ),
            "branch_count": branch_count,
            "branch_goal_counts": branch_goal_counts,
            "goal_coupling": goal_coupling,
            "has_goal_coupling": goal_coupling == GOAL_COUPLING_COUPLED,
            "shared_mvar_count": self.shared_mvar_count(),
            "spawned_goal_count": self.spawned_goal_count(),
            "tactic_depends_on": tactic_depends_on,
            "depends_on_count": len(tactic_depends_on),
            "proof_step_count": self.proof_step_count,
            "continuation_kind": continuation_kind,
            "goals_closed_count": len(goals_closed),
            "goals_opened_count": len(goals_opened),
            "partial_term_before_hash": before_hash,
            "partial_term_after_hash": after_hash,
            "completed_proof_term_hash": completed_hash,
            "effect_flags": ordered_effect_flags(effect_flags),
        }


@dataclass
class ReplayResult:
    success: bool
    applied_tactics: list[str]
    proof_term: ExprDAG | None = None
    error: str | None = None


@dataclass
class LeanAdapter:
    project: LeanProject
    env: Any = None
    states: dict[str, ProofState] = field(default_factory=dict)
    completed_proof_term: ExprDAG | None = None
    assembly_trace: ProofAssemblyTrace | None = None
    _last_partial_term: PartialProofTerm | None = None
    _checkpoint_counter: int = 0

    def _next_checkpoint_id(self) -> int:
        self._checkpoint_counter += 1
        return self._checkpoint_counter

    def _state_id(self, checkpoint_id: int, mvar_id: str) -> str:
        return f"cp{checkpoint_id}:{mvar_id}"

    @classmethod
    async def create(cls, project_path: Path | str) -> "LeanAdapter":
        project = LeanProject(str(project_path))
        adapter = cls(project=project)
        return adapter

    async def __aenter__(self):
        self.env = await self.project.environment().__aenter__()
        try:
            await asyncio.wait_for(
                self.env.send_command_async(LEAN_STARTUP_IMPORTS),
                timeout=LEAN_STARTUP_TIMEOUT_S,
            )
            await asyncio.wait_for(
                self.env.send_command_async("set_option maxRecDepth 2000"),
                timeout=30.0,
            )
            await asyncio.wait_for(
                self.env.send_command_async("set_option maxHeartbeats 200000"),
                timeout=30.0,
            )
        except TimeoutError as exc:
            await self.env.__aexit__(None, None, None)
            self.env = None
            raise LeanProcessException(
                "Lean startup timed out while loading Mathlib into the REPL. "
                "Run `nix develop .#wonton-soup` from dossiers/wonton-soup, "
                'rebuild the venv with `uv sync --python "$(which python)"`, '
                "then warm the Lean project with `uv run python setup_lean.py`."
            ) from exc
        return self

    async def __aexit__(self, *args):
        if self.env:
            await self.env.__aexit__(*args)
            self.env = None

    async def send_imports(self, imports: str):
        await self.env.send_command_async(imports)

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        self.states.clear()
        self.completed_proof_term = None
        self._last_partial_term = None
        self._checkpoint_counter = 0

        branch = await self.env.proof_from_sorry_async(theorem_with_sorry)
        checkpoint = self.env.checkpoint()
        checkpoint_id = self._next_checkpoint_id()

        mvar_ids = []
        for goal in branch.state.goals:
            mvar_id = goal.mvar_id
            if mvar_id is None:
                raise ValueError("Goal has no mvar_id")
            state_id = self._state_id(checkpoint_id, mvar_id)
            self.states[state_id] = ProofState(
                mvar_id=mvar_id,
                branch=branch,
                checkpoint=checkpoint,
                checkpoint_id=checkpoint_id,
            )
            mvar_ids.append(state_id)

        root_mvar_id = mvar_ids[0] if mvar_ids else ""
        self.assembly_trace = ProofAssemblyTrace(
            theorem=theorem_with_sorry,
            root_mvar_id=root_mvar_id,
        )

        return mvar_ids

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id not in self.states:
            raise KeyError(f"Unknown mvar_id: {mvar_id}")

        state = self.states[mvar_id]
        self.env.rollback_to(state.checkpoint)

        goals_before = list(self.states.keys())
        partial_term_before = self._last_partial_term

        result = await state.branch.try_apply_tactic_async(tactic)
        if not result.is_success():
            return None

        new_branches = result.value
        checkpoint = self.env.checkpoint()
        checkpoint_id = self._next_checkpoint_id()

        child_mvar_ids = []
        child_goals = []
        partial_term_after: PartialProofTerm | None = None
        completed_proof_term: ExprDAG | None = None
        mctx_after: MetavarGraph | None = None
        tactic_depends_on: list[str] = []
        spawned_goals: list[LeanGoal] = []
        proof_step_count = 0

        for branch in new_branches:
            if mctx_after is None:
                mctx_after = branch.get_metavar_graph()
            if not tactic_depends_on:
                tactic_depends_on = branch.get_tactic_depends_on()
            if not spawned_goals:
                spawned_goals = branch.get_spawned_goals()
            if proof_step_count <= 0:
                proof_step_count = branch.get_proof_step_count()
            partial_json = branch.get_partial_proof_term_json()
            if partial_json:
                partial_term_after = PartialProofTerm.from_json(partial_json)

            if branch.is_solved:
                proof_term_json = branch.get_proof_term_json()
                if proof_term_json:
                    completed_proof_term = ExprDAG.from_json(proof_term_json)
                continue

            for goal in branch.state.goals:
                child_mvar_id = goal.mvar_id
                if child_mvar_id is None:
                    raise ValueError("Goal has no mvar_id")
                state_id = self._state_id(checkpoint_id, child_mvar_id)
                child_mvar_ids.append(state_id)
                child_goals.append(goal)

        goals_after = [m for m in goals_before if m != mvar_id] + child_mvar_ids

        return TacticPreview(
            tactic=tactic,
            parent_mvar_id=mvar_id,
            child_mvar_ids=child_mvar_ids,
            child_goals=child_goals,
            partial_term_before=partial_term_before,
            partial_term_after=partial_term_after,
            completed_proof_term=completed_proof_term,
            goals_before=goals_before,
            goals_after=goals_after,
            checkpoint=checkpoint,
            checkpoint_id=checkpoint_id,
            branches=new_branches,
            mctx_after=mctx_after,
            tactic_depends_on=tactic_depends_on,
            spawned_goals=spawned_goals,
            proof_step_count=proof_step_count,
        )

    def commit_tactic(self, preview: TacticPreview) -> list[str]:
        if preview.parent_mvar_id in self.states:
            del self.states[preview.parent_mvar_id]

        for branch in preview.branches:
            if branch.is_solved:
                if preview.completed_proof_term:
                    self.completed_proof_term = preview.completed_proof_term
                    if self.assembly_trace:
                        self.assembly_trace.final_term = self.completed_proof_term
                continue

            for goal in branch.state.goals:
                child_mvar_id = goal.mvar_id
                if child_mvar_id is None:
                    raise ValueError(f"Goal has no mvar_id in commit_tactic: {goal.type}")
                state_id = self._state_id(preview.checkpoint_id, child_mvar_id)
                state = ProofState(
                    mvar_id=child_mvar_id,
                    branch=branch,
                    checkpoint=preview.checkpoint,
                    checkpoint_id=preview.checkpoint_id,
                )
                self.states[state_id] = state

        self._last_partial_term = preview.partial_term_after

        if self.assembly_trace:
            self.assembly_trace.add_step(
                tactic=preview.tactic,
                mvar_id=preview.parent_mvar_id,
                partial_term_before=preview.partial_term_before,
                partial_term_after=preview.partial_term_after,
                goals_before=preview.goals_before,
                goals_after=preview.goals_after,
                action_metadata=preview.action_metadata(
                    expanded_child_count=len(preview.child_mvar_ids)
                ),
            )

        return preview.child_mvar_ids

    def is_solved(self, mvar_id: str) -> bool:
        if mvar_id not in self.states:
            raise KeyError(f"Unknown mvar_id: {mvar_id}")
        return self.states[mvar_id].branch.is_solved

    def get_proof_term(self) -> ExprDAG | None:
        return self.completed_proof_term

    async def _replay_solution_path_isolated(
        self,
        theorem_with_sorry: str,
        solution_path: list[dict[str, Any]],
    ) -> ReplayResult:
        if self.project is None or not hasattr(self.project, "path"):
            return await self.replay_solution_path(
                theorem_with_sorry=theorem_with_sorry,
                solution_path=solution_path,
            )
        replay_adapter = await LeanAdapter.create(self.project.path)
        async with replay_adapter:
            return await replay_adapter.replay_solution_path(
                theorem_with_sorry=theorem_with_sorry,
                solution_path=solution_path,
            )

    async def replay_solution_path(
        self,
        theorem_with_sorry: str,
        solution_path: list[dict[str, Any]],
    ) -> ReplayResult:
        unique_suffix = f"_replay_{int(time.time() * 1000)}"
        theorem_with_new_name = re.sub(
            r"(theorem\s+)(\S+)",
            rf"\1\2{unique_suffix}",
            theorem_with_sorry,
            count=1,
        )
        branch = await self.env.proof_from_sorry_async(theorem_with_new_name)

        applied_tactics: list[str] = []
        for i, step in enumerate(solution_path):
            tactic_raw = step.get("tactic")
            if not isinstance(tactic_raw, str) or not tactic_raw.strip():
                return ReplayResult(
                    success=False,
                    applied_tactics=applied_tactics,
                    error=f"solution_path step {i} missing tactic",
                )
            tactic = tactic_raw.strip()
            if branch.is_solved:
                break

            goal_raw = step.get("goal")
            target_goal = goal_raw if isinstance(goal_raw, str) and goal_raw else None
            if target_goal is not None:
                goals = [goal.type for goal in branch.state.goals]
                if target_goal in goals:
                    goal_idx = goals.index(target_goal)
                    if goal_idx > 0:
                        rotate_tactic = f"rotate_left {goal_idx}"
                        rotate_result = await branch.try_apply_tactic_no_branching_async(
                            rotate_tactic
                        )
                        if not rotate_result.is_success():
                            return ReplayResult(
                                success=False,
                                applied_tactics=applied_tactics,
                                error=(
                                    "failed to rotate to target goal at "
                                    f"step {i} ({tactic}): {rotate_result.error}"
                                ),
                            )
                        applied_tactics.append(rotate_tactic)
                        branch = rotate_result.value

            result = await branch.try_apply_tactic_no_branching_async(tactic)
            if not result.is_success():
                return ReplayResult(
                    success=False,
                    applied_tactics=applied_tactics,
                    error=f"tactic failed at step {i} ({tactic}): {result.error}",
                )
            applied_tactics.append(tactic)
            branch = result.value

        if not branch.is_solved:
            return ReplayResult(
                success=False,
                applied_tactics=applied_tactics,
                error="proof not solved after replaying all tactics",
            )

        proof_term_json = branch.get_proof_term_json()
        if proof_term_json is None:
            try:
                response = await branch.inspect_async(include_proof_term=True)
            except (LeanInteractionException, LeanProcessException, AssertionError) as exc:
                logger.debug(
                    "replay_solution_path: proof-term extraction failed after replay: %s",
                    exc,
                )
            else:
                proof_term_json = response.get("proofTerm")
        proof_term = ExprDAG.from_json(proof_term_json) if proof_term_json else None
        return ReplayResult(success=True, applied_tactics=applied_tactics, proof_term=proof_term)

    async def reconstruct_proof_term(
        self,
        solution_path: list[dict[str, Any]] | None = None,
    ) -> ExprDAG | None:
        """
        Reconstruct the proof term by replaying tactics sequentially.

        This is needed when the proof involved multiple independent goals that were
        explored in parallel branches (with sorry masking). The parallel exploration
        contaminates each branch's proof term with sorry, so we replay the tactics
        sequentially using apply_tactic_no_branching_async to get a clean proof term.
        """
        if not self.assembly_trace or not self.assembly_trace.steps:
            logger.debug("reconstruct_proof_term: no assembly trace or steps")
            return None
        if self.completed_proof_term:
            return self.completed_proof_term

        if solution_path:
            replay = await self._replay_solution_path_isolated(
                theorem_with_sorry=self.assembly_trace.theorem,
                solution_path=solution_path,
            )
            if not replay.success:
                logger.debug("reconstruct_proof_term: %s", replay.error)
                return None
            if replay.proof_term is not None:
                self.completed_proof_term = replay.proof_term
                if self.assembly_trace:
                    self.assembly_trace.final_term = self.completed_proof_term
                return self.completed_proof_term
            logger.debug("reconstruct_proof_term: no proof term JSON from solved branch")
            return None

        replay_steps = [{"tactic": step.tactic} for step in self.assembly_trace.steps]
        replay = await self._replay_solution_path_isolated(
            theorem_with_sorry=self.assembly_trace.theorem,
            solution_path=replay_steps,
        )
        if not replay.success:
            logger.debug("reconstruct_proof_term: %s", replay.error)
            return None
        if replay.proof_term:
            self.completed_proof_term = replay.proof_term
            if self.assembly_trace:
                self.assembly_trace.final_term = self.completed_proof_term
            return self.completed_proof_term
        logger.debug("reconstruct_proof_term: no proof term JSON from solved branch")
        return None

    def get_assembly_trace(self) -> ProofAssemblyTrace | None:
        return self.assembly_trace

    def get_goal(self, mvar_id: str) -> LeanGoal | None:
        if mvar_id not in self.states:
            raise KeyError(f"Unknown mvar_id: {mvar_id}")
        state = self.states[mvar_id]
        raw_id = state.mvar_id
        for goal in state.branch.state.goals:
            if goal.mvar_id == raw_id:
                return goal
        return None

    async def check_def_eq_async(self, expr1_dag: dict, expr2_dag: dict) -> bool:
        return await self.env.check_def_eq_async(expr1_dag, expr2_dag)

    async def get_tactic_suggestions(
        self, mvar_id: str, search_tactic: str = "aesop?"
    ) -> list[str]:
        if mvar_id not in self.states:
            raise KeyError(f"Unknown mvar_id: {mvar_id}")

        state = self.states[mvar_id]
        self.env.rollback_to(state.checkpoint)

        response = await state.branch._send_tactic_async(search_tactic, timeout=5000)
        if "messages" not in response:
            raise ValueError(f"Lean response missing messages for {search_tactic}")

        messages = response.get("messages", [])
        suggestions = []

        for msg in messages:
            data = msg.get("data", "")
            if "Try this:" in data:
                parts = data.split("Try this:")
                if len(parts) > 1:
                    suggestion_text = parts[1].strip()
                    if suggestion_text:
                        suggestions.append(suggestion_text)

        return suggestions
