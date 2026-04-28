import asyncio
import logging
from dataclasses import dataclass

from prover.goal_signature import GoalSignatureConfig
from prover.mcts import mcts_search
from prover.providers.base import AesopTacticProvider


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


class MinimalAdapter:
    def __init__(self) -> None:
        self._goals: dict[str, FakeGoal] = {}

    async def initialize(self, theorem_with_sorry: str) -> list[str]:
        _ = theorem_with_sorry
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

    async def preview_tactic(self, mvar_id: str, tactic: str):
        raise AssertionError(f"preview_tactic should not be called: {mvar_id=} {tactic=}")

    def commit_tactic(self, preview) -> None:
        raise AssertionError("commit_tactic should not be called")


class ThrowingProvider:
    provider_id = "throwing"
    last_blocked: list[str] = []

    async def suggest_tactics_with_probs_async(self, goal, mvar_id: str, adapter):
        _ = (goal, mvar_id, adapter)
        raise RuntimeError("boom")

    def describe(self) -> str:
        return "throwing"


def test_mcts_provider_exception_is_contained(caplog):
    goal_sig_config = GoalSignatureConfig(scheme="text")
    adapter = MinimalAdapter()
    provider = ThrowingProvider()

    with caplog.at_level(logging.ERROR, logger="prover.mcts"):
        tree = asyncio.run(
            mcts_search(
                "theorem",
                adapter,
                provider,
                max_iterations=3,
                goal_sig_config=goal_sig_config,
            )
        )

    assert tree.root.is_dead
    assert tree.root.dead_reason == "provider_exception"
    assert any("tactic provider failed" in r.message for r in caplog.records)


class NoSuggestionAdapter:
    async def get_tactic_suggestions(
        self,
        mvar_id: str,
        search_tactic: str = "aesop?",
    ) -> list[str]:
        _ = (mvar_id, search_tactic)
        return []


def test_aesop_provider_returns_empty_on_no_suggestions():
    provider = AesopTacticProvider()
    adapter = NoSuggestionAdapter()
    goal = FakeGoal(mvar_id="root", type="P", type_expr=None, hypotheses=[])
    result = asyncio.run(provider.suggest_tactics_with_probs_async(goal, "root", adapter, n=10))
    assert result == []
