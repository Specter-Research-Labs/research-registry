import asyncio
from typing import TYPE_CHECKING, cast

from leantree.core.lean import LeanGoal

from prover.goal_signature import GoalSignatureConfig
from prover.intervention import FilteredTacticProvider
from prover.providers.base import GoalAwareTacticProvider, TacticProvider, tactic_family

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter

_ADAPTER = cast("LeanAdapter", None)


class StaticProvider(TacticProvider):
    def __init__(self, tactics_with_probs: list[tuple[str, float]]):
        self.tactics_with_probs = tactics_with_probs

    async def suggest_tactics_with_probs_async(
        self,
        goal: LeanGoal,
        mvar_id: str,
        adapter,
        n: int = 10,
    ) -> list[tuple[str, float]]:
        return self.tactics_with_probs[:n]


def test_or_goal_generates_left_right_for_textual_or() -> None:
    goal = LeanGoal.from_string("⊢ Or P Q")
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=50)
    )
    tactics = [t for t, _ in tactics_with_probs]
    assert "left" in tactics
    assert "right" in tactics


def test_or_hypothesis_triggers_cases_even_if_goal_is_not_or() -> None:
    goal = LeanGoal.from_string(
        """
h : Or A B
⊢ P
""".strip()
    )
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=50)
    )
    tactics = [t for t, _ in tactics_with_probs]
    assert "cases h" in tactics
    assert "rcases h with h1 | h2" in tactics


def test_does_not_suggest_exact_for_irrelevant_hypotheses() -> None:
    goal = LeanGoal.from_string(
        """
hP : P
hQ : Q
⊢ R
""".strip()
    )
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=50)
    )
    tactics = [t for t, _ in tactics_with_probs]
    assert "exact hP" not in tactics
    assert "exact hQ" not in tactics


def test_eq_goal_prefers_rfl() -> None:
    goal = LeanGoal.from_string("⊢ a = a")
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=10)
    )
    assert tactics_with_probs
    assert tactics_with_probs[0][0] == "rfl"


def test_exact_match_prefers_assumption() -> None:
    goal = LeanGoal.from_string(
        """
hP : P
⊢ P
""".strip()
    )
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=10)
    )
    assert tactics_with_probs
    assert tactics_with_probs[0][0] == "assumption"


def test_tactic_family_folds_numeric_suffix_aliases() -> None:
    assert tactic_family("norm_num1") == "arith"
    assert tactic_family("norm_num2 [h]") == "arith"
    assert tactic_family("simp_all1 [h]") == "simplify"


def test_filtered_provider_blocks_numeric_suffix_aliases() -> None:
    goal = LeanGoal.from_string("⊢ 2 = 2")
    provider = FilteredTacticProvider(
        StaticProvider([("norm_num1", 0.9), ("ring", 0.8)]),
        blocked={"norm_num"},
        goal_sig_config=GoalSignatureConfig(scheme="text"),
    )

    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=_ADAPTER, n=10)
    )

    assert tactics_with_probs == [("ring", 0.8)]
    assert [blocked.tactic for blocked in provider.last_blocked] == ["norm_num1"]
