import asyncio
from dataclasses import dataclass

from prover.adapters.lean import TacticPreview
from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory, TacticOutcome
from prover.mcts import mcts_search
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

        # Child c2 duplicates the root goal (same goal signature under scheme="text"),
        # so it should be dropped by goal dedup and not expanded into the tree/graph.
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


def test_history_child_ids_match_tree_and_graph_expansion_under_goal_dedup():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = DedupAdapter()
    provider = DedupProvider()
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)

    tree = asyncio.run(
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

    root = tree.nodes_by_mvar["root"]
    assert "split" in root.children
    expanded_child_ids = [n.mvar_id for n in root.children["split"]]
    assert expanded_child_ids == ["c1"]

    # The recorded attempt should reflect the deduped expansion (not the raw preview list).
    assert len(history.iterations) == 1
    attempts = history.iterations[0].attempts
    split_attempts = [
        a
        for a in attempts
        if a.node_mvar_id == "root"
        and a.tactic == "split"
        and a.outcome == TacticOutcome.SUCCESS
    ]
    assert len(split_attempts) == 1
    assert split_attempts[0].child_mvar_ids == expanded_child_ids

    # Graph expansion should match as well (only one successor).
    assert sorted(graph.graph.successors("root")) == expanded_child_ids


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
