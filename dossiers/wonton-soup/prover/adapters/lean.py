import asyncio
import re
from collections.abc import Awaitable, Callable
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
from prover.dependencies import KernelCheck, PremiseBlocked, check_proof, forbidden_hits
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

LEAN_STARTUP_IMPORTS = "import Mathlib\nopen BigOperators Real Nat Topology"
LEAN_STARTUP_TIMEOUT_S = 120.0

# Tactic budgets are counted in Lean heartbeats (units of 1000, like maxHeartbeats)
# so that a search outcome does not depend on host load. The REPL's own timeout is
# wall-clock; it stays only as a guard against a tactic that never checks
# heartbeats, and hitting it is an infrastructure error, not a tactic failure.
TACTIC_HEARTBEATS = 50_000
TACTIC_WALL_GUARD_MS = 120_000
DECLARATION_MAX_HEARTBEATS = 200_000
MAX_REC_DEPTH = 2000

# `set_option maxHeartbeats N in tac` does not bound a tactic run through the REPL,
# because the option elaborator does not update Core.Context.maxHeartbeats, so the
# limit is installed directly on the context.
HEARTBEAT_LIMIT_TACTIC = """syntax (name := wontonHeartbeatLimit)
  "heartbeat_limit " num " => " tacticSeq : tactic
open Lean Elab Tactic in
@[tactic wontonHeartbeatLimit] def evalWontonHeartbeatLimit : Tactic := fun stx => do
  let some limit := stx[1].isNatLit? | throwUnsupportedSyntax
  let start ← IO.getNumHeartbeats
  withTheReader Core.Context
    (fun ctx => { ctx with maxHeartbeats := limit * 1000, initHeartbeats := start })
    (evalTactic stx[3])"""

# leantree reports the REPL's wall-clock timeout as this LeanInteractionException message.
REPL_TIMEOUT_MESSAGE = "Tactic application timed out."

REPLAY_DECLARATION = "wonton_replay"
CHECK_DECLARATION = "wonton_check"


class TacticWallTimeout(LeanProcessException):
    """A tactic outran the wall-clock guard without exhausting its heartbeats."""


def heartbeat_limited(tactic: str) -> str:
    body = tactic.strip("\n")
    if "\n" not in body:
        return f"heartbeat_limit {TACTIC_HEARTBEATS} => ({body})"
    indented = "\n".join(f"  {line}" for line in body.split("\n"))
    return f"heartbeat_limit {TACTIC_HEARTBEATS} => (\n{indented}\n)"


def rename_declaration(statement: str, name: str) -> str:
    renamed, count = re.subn(r"(theorem\s+)(\S+)", rf"\g<1>{name}", statement, count=1)
    if count != 1:
        raise ValueError(f"statement has no theorem declaration: {statement[:120]!r}")
    return renamed


async def _limited[T](
    branch: LeanProofBranch, tactic: str, apply: Callable[..., Awaitable[T]]
) -> T | None:
    """Apply `tactic` under the heartbeat budget; None means Lean rejected it.

    Masked sibling goals are removed before the tactic runs, so a failure there is
    an infrastructure error and propagates. Search-tactic and `have` checks run on
    the raw tactic because the wrapper would hide its prefix from them.
    """
    try:
        LeanProofBranch._check_tactic(tactic, ban_search_tactics=True)
    except LeanInteractionException:
        return None
    await branch._delete_masked_goals_async()
    try:
        return await apply(heartbeat_limited(tactic), timeout=TACTIC_WALL_GUARD_MS)
    except LeanInteractionException as exc:
        if str(exc) == REPL_TIMEOUT_MESSAGE:
            raise TacticWallTimeout(
                f"{tactic!r} exceeded the {TACTIC_WALL_GUARD_MS} ms wall guard"
            ) from exc
        return None


async def apply_limited(branch: LeanProofBranch, tactic: str) -> list[LeanProofBranch] | None:
    return await _limited(branch, tactic, branch.apply_tactic_async)


async def apply_limited_linear(branch: LeanProofBranch, tactic: str) -> LeanProofBranch | None:
    return await _limited(branch, tactic, branch.apply_tactic_no_branching_async)


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
    forbidden_constants: frozenset[str] = frozenset()

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
                self.env.send_command_async(f"set_option maxRecDepth {MAX_REC_DEPTH}"),
                timeout=30.0,
            )
            await asyncio.wait_for(
                self.env.send_command_async(
                    f"set_option maxHeartbeats {DECLARATION_MAX_HEARTBEATS}"
                ),
                timeout=30.0,
            )
            await asyncio.wait_for(
                self.env.send_command_async(HEARTBEAT_LIMIT_TACTIC),
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

        new_branches = await apply_limited(state.branch, tactic)
        if new_branches is None:
            return None
        if self.forbidden_constants:
            await self._reject_forbidden_constants(tactic, new_branches)
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

    async def _reject_forbidden_constants(
        self, tactic: str, branches: list[LeanProofBranch]
    ) -> None:
        # Masked sibling branches share one REPL proof state, so each state is read once.
        # inspect_proof_state_async is used instead of branch.inspect_async because the
        # latter resets the branch's goal mask.
        proof_states = {branch._proof_state_id for branch in branches}
        for proof_state in sorted(proof_states):
            response = await self.env.inspect_proof_state_async(
                proof_state, include_partial_proof_term=True
            )
            partial = response.get("partialProofTerm")
            if partial is None:
                raise LeanInteractionException(
                    f"REPL returned no partial proof term for proof state {proof_state}"
                )
            names = ExprDAG.from_json(partial["proofTerm"])._const_names()
            hits = forbidden_hits(names, self.forbidden_constants)
            if hits:
                raise PremiseBlocked(tactic, sorted(hits))

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

    async def replay_solution_path(
        self,
        theorem_with_sorry: str,
        solution_path: list[dict[str, Any]],
    ) -> ReplayResult:
        """Replay a goal-ordered solution path as one linear tactic script.

        The declaration is renamed to REPLAY_DECLARATION, so the caller must roll
        the environment back before replaying again. Every step names the goal it
        was found on; a step whose goal is no longer open fails the replay instead
        of being skipped.
        """
        branch = await self.env.proof_from_sorry_async(
            rename_declaration(theorem_with_sorry, REPLAY_DECLARATION)
        )

        applied_tactics: list[str] = []
        for i, step in enumerate(solution_path):
            tactic = step["tactic"].strip()
            target_goal = step["goal"]
            if not tactic or not target_goal:
                raise ValueError(f"solution_path step {i} needs a tactic and a goal: {step!r}")
            if branch.is_solved:
                return ReplayResult(
                    success=False,
                    applied_tactics=applied_tactics,
                    error=f"proof closed before step {i} ({tactic})",
                )

            goals = [goal.type for goal in branch.state.goals]
            if target_goal not in goals:
                return ReplayResult(
                    success=False,
                    applied_tactics=applied_tactics,
                    error=f"goal of step {i} ({tactic}) is not open: {target_goal!r}",
                )
            goal_idx = goals.index(target_goal)
            if goal_idx > 0:
                rotate_tactic = f"rotate_left {goal_idx}"
                rotated = await apply_limited_linear(branch, rotate_tactic)
                if rotated is None:
                    raise LeanInteractionException(
                        f"{rotate_tactic} failed with {len(goals)} open goals at step {i}"
                    )
                applied_tactics.append(rotate_tactic)
                branch = rotated

            result = await apply_limited_linear(branch, tactic)
            if result is None:
                return ReplayResult(
                    success=False,
                    applied_tactics=applied_tactics,
                    error=f"tactic failed at step {i} ({tactic})",
                )
            applied_tactics.append(tactic)
            branch = result

        if not branch.is_solved:
            return ReplayResult(
                success=False,
                applied_tactics=applied_tactics,
                error="proof not solved after replaying all tactics",
            )

        proof_term_json = branch.get_proof_term_json()
        if proof_term_json is None:
            response = await branch.inspect_async(include_proof_term=True)
            proof_term_json = response.get("proofTerm")
        if proof_term_json is None:
            raise LeanInteractionException("REPL returned no proof term for a solved replay")
        return ReplayResult(
            success=True,
            applied_tactics=applied_tactics,
            proof_term=ExprDAG.from_json(proof_term_json),
        )

    async def kernel_check(
        self,
        theorem_with_sorry: str,
        solution_path: list[dict[str, Any]],
        *,
        library_name: str | None,
        blocked_premises: frozenset[str],
    ) -> tuple[KernelCheck, ExprDAG | None]:
        """Replay a tree solution, then elaborate it as a standalone declaration.

        The replay yields the linear script and the proof term; the declaration is
        then elaborated with the raw tactics under Lean's default per-declaration
        heartbeat budget, so a checked proof compiles as ordinary Lean. Both
        declarations use fixed names so auxiliary lemma names, and with them the
        term hash, do not depend on the variant or the run. The environment is
        rolled back afterwards so the names can be reused.
        """
        checkpoint = self.env.checkpoint()
        try:
            replay = await self.replay_solution_path(theorem_with_sorry, solution_path)
            if not replay.success:
                return (
                    KernelCheck(
                        status="replay_failed",
                        error=replay.error,
                        tactics=tuple(replay.applied_tactics),
                        term_hash=None,
                        premises=(),
                        self_citation=None,
                        blocked_hits=(),
                    ),
                    None,
                )
            assert replay.proof_term is not None
            tactics = tuple(replay.applied_tactics)
            term_hash = replay.proof_term.structural_hash()
            check = await check_proof(
                self.env, rename_declaration(theorem_with_sorry, CHECK_DECLARATION), list(tactics)
            )
            if not check.ok:
                return (
                    KernelCheck(
                        status="check_failed",
                        error=check.error,
                        tactics=tactics,
                        term_hash=term_hash,
                        premises=(),
                        self_citation=None,
                        blocked_hits=(),
                    ),
                    replay.proof_term,
                )
            names = {d.premise for d in check.dependencies}
            hits = tuple(
                sorted(forbidden_hits((d.name for d in check.dependencies), blocked_premises))
            )
            return (
                KernelCheck(
                    status="blocked_premise" if hits else "checked",
                    error=f"proof uses blocked premise {', '.join(hits)}" if hits else None,
                    tactics=tactics,
                    term_hash=term_hash,
                    premises=tuple(sorted(check.premises())),
                    self_citation=library_name in names if library_name is not None else None,
                    blocked_hits=hits,
                ),
                replay.proof_term,
            )
        finally:
            self.env.rollback_to(checkpoint)

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

        try:
            response = await state.branch._send_tactic_async(
                heartbeat_limited(search_tactic), timeout=TACTIC_WALL_GUARD_MS
            )
        except LeanInteractionException as exc:
            if str(exc) == REPL_TIMEOUT_MESSAGE:
                raise TacticWallTimeout(
                    f"{search_tactic!r} exceeded the {TACTIC_WALL_GUARD_MS} ms wall guard"
                ) from exc
            raise
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
