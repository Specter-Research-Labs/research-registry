import asyncio
import math
from dataclasses import dataclass

from experiments.distributed_mcts import DistributedMCTSConfig, distributed_mcts_search
from experiments.distributed_mcts import core as distributed_core
from prover.adapters.lean import TacticPreview
from prover.goal_cache import GoalCache
from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory, TacticOutcome
from prover.mcts import BackpropStrategy, ExpansionPolicy, MCTSTree, mcts_search
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


class FakeAdapter:
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
        if mvar_id == "root" and tactic == "fail":
            return None
        if mvar_id == "root" and tactic == "split":
            child1 = FakeGoal(
                mvar_id="c1",
                type="Q",
                type_expr=None,
                hypotheses=[],
            )
            child2 = FakeGoal(
                mvar_id="c2",
                type="R",
                type_expr=None,
                hypotheses=[],
            )
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
        if mvar_id in ("c1", "c2") and tactic == "solve":
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=[],
                child_goals=[],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=[self._goals[mvar_id].type],
                goals_after=[],
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


class FakeProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("fail", 0.9), ("split", 0.1)]
        if mvar_id in ("c1", "c2"):
            return [("solve", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


class SiblingAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        root = FakeGoal(mvar_id="root", type="P", type_expr=None, hypotheses=[])
        self._goals = {"root": root}
        return ["root"]

    def get_goal(self, mvar_id: str) -> FakeGoal | None:
        return self._goals.get(mvar_id)

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id == "root" and tactic == "left_branch":
            child = FakeGoal(mvar_id="left", type="L", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["left"],
                child_goals=[child],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["P"],
                goals_after=["L"],
                checkpoint=None,
                checkpoint_id=0,
                branches=[],
            )
        if mvar_id == "root" and tactic == "right_branch":
            child = FakeGoal(mvar_id="right", type="R", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["right"],
                child_goals=[child],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["P"],
                goals_after=["R"],
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


class SiblingProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("left_branch", 0.6), ("right_branch", 0.4)]
        return []

    def describe(self) -> str:
        return "fake"


class DedupHistoryAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        root = FakeGoal(mvar_id="root", type="P", type_expr=None, hypotheses=[])
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


class DedupHistoryProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("split", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


class GoalFeaturesAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        root = FakeGoal(mvar_id="root", type="P", type_expr=None, hypotheses=[])
        self._goals = {"root": root}
        return ["root"]

    def get_goal(self, mvar_id: str) -> FakeGoal | None:
        return self._goals.get(mvar_id)

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id == "root" and tactic == "split":
            child = FakeGoal(mvar_id="c1", type="Q", type_expr=None, hypotheses=[])
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=["c1"],
                child_goals=[child],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["P"],
                goals_after=["Q"],
                checkpoint=None,
                checkpoint_id=0,
                branches=[],
            )
        if mvar_id == "c1" and tactic == "solve":
            return TacticPreview(
                tactic=tactic,
                parent_mvar_id=mvar_id,
                child_mvar_ids=[],
                child_goals=[],
                partial_term_before=None,
                partial_term_after=None,
                completed_proof_term=None,
                goals_before=["Q"],
                goals_after=[],
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


class GoalFeaturesProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("split", 1.0)]
        if mvar_id == "c1":
            return [("solve", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


def _run_centralized(max_iterations: int) -> MCTSTree:
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = FakeAdapter()
    provider = FakeProvider()
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    return asyncio.run(
        mcts_search(
            "theorem",
            adapter,
            provider,
            graph,
            history,
            max_iterations=max_iterations,
            goal_sig_config=goal_sig_config,
        )
    )


def _run_distributed(max_iterations: int) -> MCTSTree:
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = FakeAdapter()
    provider = FakeProvider()
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=max_iterations,
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


def test_distributed_single_agent_matches_centralized():
    centralized = _run_centralized(max_iterations=5)
    distributed = _run_distributed(max_iterations=5)
    assert centralized.serialize() == distributed.serialize()
    assert centralized.is_solved()
    assert distributed.is_solved()


def test_centralized_and_distributed_preserve_successful_sibling_tactics():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=1,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
    )

    centralized = asyncio.run(
        mcts_search(
            "theorem",
            SiblingAdapter(),
            SiblingProvider(),
            max_iterations=1,
            goal_sig_config=goal_sig_config,
        )
    )
    distributed = asyncio.run(
        distributed_mcts_search(
            "theorem",
            SiblingAdapter(),
            SiblingProvider(),
            ProofGraph(),
            ExplorationHistory.create("theorem", None),
            goal_sig_config=goal_sig_config,
            config=config,
        )
    )

    for tree in (centralized, distributed):
        root = tree.nodes_by_mvar["root"]
        assert set(root.children) == {"left_branch", "right_branch"}
        assert [node.mvar_id for node in root.children["left_branch"]] == ["left"]
        assert [node.mvar_id for node in root.children["right_branch"]] == ["right"]


def test_centralized_and_distributed_first_success_reproduces_old_expansion_policy():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=1,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
        expansion_policy=ExpansionPolicy.FIRST_SUCCESS,
    )

    centralized = asyncio.run(
        mcts_search(
            "theorem",
            SiblingAdapter(),
            SiblingProvider(),
            max_iterations=1,
            goal_sig_config=goal_sig_config,
            expansion_policy=ExpansionPolicy.FIRST_SUCCESS,
        )
    )
    distributed = asyncio.run(
        distributed_mcts_search(
            "theorem",
            SiblingAdapter(),
            SiblingProvider(),
            ProofGraph(),
            ExplorationHistory.create("theorem", None),
            goal_sig_config=goal_sig_config,
            config=config,
        )
    )

    for tree in (centralized, distributed):
        root = tree.nodes_by_mvar["root"]
        assert set(root.children) == {"left_branch"}
        assert [node.mvar_id for node in root.children["left_branch"]] == ["left"]


def test_distributed_tie_breaker_agent():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = FakeAdapter()
    provider = FakeProvider()
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=2,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
    )
    calls: list[tuple[int, int]] = []

    def tie_breaker_agent(candidates, iteration: int, agent_id: int):
        calls.append((iteration, agent_id))
        return sorted(candidates, key=lambda item: item[1].mvar_id)[-1]

    tree = asyncio.run(
        distributed_mcts_search(
            "theorem",
            adapter,
            provider,
            graph,
            history,
            goal_sig_config=goal_sig_config,
            tie_breaker_agent=tie_breaker_agent,
            config=config,
        )
    )
    assert calls
    assert calls[0][0] == 1
    assert calls[0][1] == 0
    assert tree.nodes_by_mvar["c2"].visit_count > 0


def test_distributed_history_records_deduped_children_only():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = DedupHistoryAdapter()
    provider = DedupHistoryProvider()
    graph = ProofGraph()
    history = ExplorationHistory.create("theorem", None)
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=1,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
    )

    tree = asyncio.run(
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

    root = tree.nodes_by_mvar["root"]
    expanded_child_ids = [n.mvar_id for n in root.children["split"]]
    assert expanded_child_ids == ["c1"]

    split_attempts = [
        attempt
        for attempt in history.iterations[0].attempts
        if attempt.node_mvar_id == "root"
        and attempt.tactic == "split"
        and attempt.outcome == TacticOutcome.SUCCESS
    ]
    assert len(split_attempts) == 1
    assert split_attempts[0].child_mvar_ids == expanded_child_ids


def test_distributed_ranker_sees_goal_features_for_root_and_children():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = GoalFeaturesAdapter()
    provider = GoalFeaturesProvider()
    goal_cache = GoalCache(goal_sig_config)
    seen_features: dict[str, list[float] | None] = {}
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=2,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
    )

    def tactic_ranker(tactics_with_probs, iteration: int, node):
        seen_features[node.mvar_id] = node.goal_features
        return tactics_with_probs

    asyncio.run(
        distributed_mcts_search(
            "theorem",
            adapter,
            provider,
            goal_cache=goal_cache,
            goal_sig_config=goal_sig_config,
            tactic_ranker=tactic_ranker,
            config=config,
        )
    )

    assert seen_features["root"] is not None
    assert seen_features["c1"] is not None


def test_distributed_reroute_blocked_root_falls_back_instead_of_hanging(monkeypatch):
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = FakeAdapter()
    provider = FakeProvider()
    history = ExplorationHistory.create("theorem", None)
    config = DistributedMCTSConfig(
        agents=1,
        max_iterations=1,
        max_inflight_expansions=1,
        c=math.sqrt(2),
        backprop_strategy=BackpropStrategy.UNIFORM,
        virtual_loss=0,
        adapter_mode="single",
        block_policy=distributed_core.DistributedBlockPolicy(
            fraction=0.5,
            duration=20,
            seed=1,
        ),
        reroute_policy=distributed_core.DistributedReroutePolicy(max_attempts=4),
    )

    monkeypatch.setattr(distributed_core.BlockSchedule, "is_blocked", lambda *_args: True)
    monkeypatch.setattr(
        distributed_core.BlockSchedule,
        "block_snapshot",
        lambda *_args: {"until": 20, "remaining": 20, "duration": 20, "immovable": False},
    )

    tree = asyncio.run(
        asyncio.wait_for(
            distributed_mcts_search(
                "theorem",
                adapter,
                provider,
                history=history,
                goal_sig_config=goal_sig_config,
                config=config,
            ),
            timeout=1.0,
        )
    )

    assert not tree.is_solved()
    assert tree.expansion_count == 0
    assert len(history.iterations) == 1
