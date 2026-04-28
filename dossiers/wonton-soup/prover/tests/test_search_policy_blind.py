import asyncio
import random
from dataclasses import dataclass

import pytest

from prover.adapters.lean import TacticPreview
from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory
from prover.mcts import SearchPolicy, mcts_search


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


class TwoLeafAdapter:
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

    def commit_tactic(self, preview: TacticPreview) -> None:
        for goal in preview.child_goals:
            if goal.mvar_id is None:
                raise ValueError("Missing mvar_id")
            self._goals[goal.mvar_id] = goal


class TwoLeafProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("split", 1.0)]
        return []

    def describe(self) -> str:
        return "fake"


class TwoTacticAdapter:
    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        return ["root"]

    def get_goal(self, mvar_id: str) -> FakeGoal | None:
        if mvar_id != "root":
            return None
        return FakeGoal(mvar_id="root", type="P", type_expr=None, hypotheses=[])

    async def preview_tactic(self, mvar_id: str, tactic: str) -> TacticPreview | None:
        if mvar_id != "root":
            return None
        if tactic not in {"t_high", "t_low"}:
            return None
        return TacticPreview(
            tactic=tactic,
            parent_mvar_id=mvar_id,
            child_mvar_ids=[],
            child_goals=[],
            partial_term_before=None,
            partial_term_after=None,
            completed_proof_term=None,
            goals_before=["P"],
            goals_after=[],
            checkpoint=None,
            checkpoint_id=0,
            branches=[],
        )

    def commit_tactic(self, preview: TacticPreview) -> None:
        return None


class TwoTacticProvider:
    provider_id = "fake"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        if mvar_id == "root":
            return [("t_high", 1.0), ("t_low", 0.0)]
        return []

    def describe(self) -> str:
        return "fake"


def test_ucb1_selects_first_child_without_rng():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = TwoLeafAdapter()
    provider = TwoLeafProvider()
    history = ExplorationHistory.create("theorem", None)

    asyncio.run(
        mcts_search(
            "theorem",
            adapter,
            provider,
            history=history,
            max_iterations=2,
            goal_sig_config=goal_sig_config,
            search_policy=SearchPolicy.UCB1,
        )
    )

    assert history.iterations[1].selected_path[-1] == "c1"


def test_blind_uniform_selects_random_leaf_with_rng():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = TwoLeafAdapter()
    provider = TwoLeafProvider()
    history = ExplorationHistory.create("theorem", None)

    asyncio.run(
        mcts_search(
            "theorem",
            adapter,
            provider,
            history=history,
            max_iterations=2,
            goal_sig_config=goal_sig_config,
            rng=random.Random(0),
            search_policy=SearchPolicy.BLIND_UNIFORM,
        )
    )

    assert history.iterations[1].selected_path[-1] == "c2"


def test_blind_uniform_requires_rng():
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = TwoLeafAdapter()
    provider = TwoLeafProvider()
    history = ExplorationHistory.create("theorem", None)

    with pytest.raises(ValueError, match="rng is required"):
        asyncio.run(
            mcts_search(
                "theorem",
                adapter,
                provider,
                history=history,
                max_iterations=1,
                goal_sig_config=goal_sig_config,
                rng=None,
                search_policy=SearchPolicy.BLIND_UNIFORM,
            )
        )


def test_blind_uniform_shuffles_tactic_order():
    goal_sig_config = GoalSignatureConfig(scheme="text")

    history_agent = ExplorationHistory.create("theorem", None)
    asyncio.run(
        mcts_search(
            "theorem",
            TwoTacticAdapter(),
            TwoTacticProvider(),
            history=history_agent,
            max_iterations=1,
            goal_sig_config=goal_sig_config,
            search_policy=SearchPolicy.UCB1,
        )
    )
    assert history_agent.iterations[0].attempts[0].tactic == "t_high"

    history_blind = ExplorationHistory.create("theorem", None)
    asyncio.run(
        mcts_search(
            "theorem",
            TwoTacticAdapter(),
            TwoTacticProvider(),
            history=history_blind,
            max_iterations=1,
            goal_sig_config=goal_sig_config,
            rng=random.Random(1),
            search_policy=SearchPolicy.BLIND_UNIFORM,
        )
    )
    assert history_blind.iterations[0].attempts[0].tactic == "t_low"

