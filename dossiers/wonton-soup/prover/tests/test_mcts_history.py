import asyncio
import math
from dataclasses import dataclass

import pytest

from experiments.distributed_mcts import DistributedMCTSConfig, distributed_mcts_search
from prover.adapters.lean import TacticPreview
from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory, TacticOutcome
from prover.mcts import BackpropStrategy, mcts_search
from prover.proof import ProofGraph


@dataclass
class FakeHypothesis:
    type: str
    type_expr: dict | None = None


@dataclass
class FakeGoal:
    mvar_id: str | None
    type: str
    type_expr: dict | None
    hypotheses: list[FakeHypothesis]


class DedupAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        root = FakeGoal(
            mvar_id="root",
            type="P",
            type_expr=None,
            hypotheses=[],
        )
        self._goals = {"root": root}
        return ["root"]

    def get_goal(self, mvar_id: str) -> FakeGoal | None:
        return self._goals.get(mvar_id)

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id != "root" or tactic != "split":
            return None

        child1 = FakeGoal(mvar_id="c1", type="Q", type_expr=None, hypotheses=[])
        child2 = FakeGoal(mvar_id="c2", type="P", type_expr=None, hypotheses=[])
        return TacticPreview(
            tactic=tactic,
            parent_mvar_id=mvar_id,
            child_mvar_ids=["c1", "c2"],
            child_goals=[child1, child2],
            partial_term_before=None,
            partial_term_after=None,
            completed_proof_term=None,
            goals_before=["P"],
            goals_after=["Q", "P"],
            checkpoint=None,
            checkpoint_id=0,
            branches=[],
        )

    def commit_tactic(self, preview: TacticPreview) -> None:
        for goal in preview.child_goals:
            if goal.mvar_id is None:
                raise ValueError("Missing mvar_id")
            self._goals[goal.mvar_id] = goal


class DedupProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("split", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


class BranchDedupAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        root = FakeGoal(
            mvar_id="root",
            type="P",
            type_expr=None,
            hypotheses=[],
        )
        self._goals = {"root": root}
        return ["root"]

    def get_goal(self, mvar_id: str) -> FakeGoal | None:
        return self._goals.get(mvar_id)

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id == "root" and tactic == "split":
            child1 = FakeGoal(mvar_id="c1", type="Q", type_expr=None, hypotheses=[])
            child2 = FakeGoal(mvar_id="c2", type="R", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["c1", "c2"],
                child_goals=[child1, child2],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["P"],
                goals_after=["Q", "R"],
                checkpoint=None,
                checkpoint_id=0,
                branches=[],
            )
        if mvar_id == "c1" and tactic == "to_s":
            child = FakeGoal(mvar_id="s1", type="S", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["s1"],
                child_goals=[child],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["Q"],
                goals_after=["S"],
                checkpoint=None,
                checkpoint_id=0,
                branches=[],
            )
        if mvar_id == "c2" and tactic == "to_s":
            child = FakeGoal(mvar_id="s2", type="S", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["s2"],
                child_goals=[child],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["R"],
                goals_after=["S"],
                checkpoint=None,
                checkpoint_id=0,
                branches=[],
            )
        return None

    def commit_tactic(self, preview: TacticPreview) -> None:
        for goal in preview.child_goals:
            if goal.mvar_id is None:
                raise ValueError("Missing mvar_id")
            self._goals[goal.mvar_id] = goal


class BranchDedupProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("split", 1.0)]
        if mvar_id in ("c1", "c2"):
            return [("to_s", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


def _search(kind: str, adapter, provider, graph: ProofGraph, history: ExplorationHistory):
    goal_sig_config = GoalSignatureConfig(scheme="text")
    if kind == "centralized":
        return asyncio.run(
            mcts_search(
                "theorem",
                adapter,
                provider,
                graph=graph,
                history=history,
                max_iterations=1,
                goal_sig_config=goal_sig_config,
            )
        )
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=1,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
    )
    return asyncio.run(
        distributed_mcts_search(
            "theorem",
            adapter,
            provider,
            graph,
            history,
            goal_sig_config=goal_sig_config,
            config=config,
        )
    )


@pytest.mark.parametrize("kind", ["centralized", "distributed"])
def test_tactic_with_cyclic_child_is_not_expanded(kind: str):
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    tree = _search(kind, DedupAdapter(), DedupProvider(), graph, history)

    # c2 repeats the root goal. Dropping it would let c1 alone close a proof that
    # still owes c2, so the whole tactic is rejected rather than half expanded.
    root = tree.nodes_by_mvar["root"]
    assert "split" not in root.children
    split_attempts = [
        a
        for a in history.iterations[0].attempts
        if a.node_mvar_id == "root" and a.tactic == "split"
    ]
    assert [(a.outcome, a.child_mvar_ids) for a in split_attempts] == [
        (TacticOutcome.SUCCESS, ["c1", "c2"])
    ]
    assert list(graph.graph.successors("root")) == []


class TwinGoalAdapter(DedupAdapter):
    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        preview = await super().preview_tactic(mvar_id, tactic)
        if preview is None:
            return None
        preview.child_goals[1] = FakeGoal(mvar_id="c2", type="Q", type_expr=None, hypotheses=[])
        return preview


@pytest.mark.parametrize("kind", ["centralized", "distributed"])
def test_sibling_obligations_with_equal_goals_are_both_kept(kind: str):
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    tree = _search(kind, TwinGoalAdapter(), DedupProvider(), graph, history)
    root = tree.nodes_by_mvar["root"]
    assert [n.mvar_id for n in root.children["split"]] == ["c1", "c2"]


def test_goal_dedup_is_branch_local_not_global():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = BranchDedupAdapter()
    provider = BranchDedupProvider()

    tree = asyncio.run(
        mcts_search(
            "theorem",
            adapter,
            provider,
            max_iterations=3,
            goal_sig_config=goal_sig_config,
        )
    )

    assert "s1" in tree.nodes_by_mvar
    assert "s2" in tree.nodes_by_mvar
    assert tree.nodes_by_mvar["s1"].goal_sig == tree.nodes_by_mvar["s2"].goal_sig
