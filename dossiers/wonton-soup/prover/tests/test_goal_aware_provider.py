import asyncio

from leantree.core.lean import LeanGoal

from prover.providers.base import GoalAwareTacticProvider


def test_or_goal_generates_left_right_for_textual_or() -> None:
    goal = LeanGoal.from_string("⊢ Or P Q")
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=None, n=50)
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
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=None, n=50)
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
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=None, n=50)
    )
    tactics = [t for t, _ in tactics_with_probs]
    assert "exact hP" not in tactics
    assert "exact hQ" not in tactics


def test_eq_goal_prefers_rfl() -> None:
    goal = LeanGoal.from_string("⊢ a = a")
    provider = GoalAwareTacticProvider(base_tactics=[])
    tactics_with_probs = asyncio.run(
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=None, n=10)
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
        provider.suggest_tactics_with_probs_async(goal, mvar_id="m0", adapter=None, n=10)
    )
    assert tactics_with_probs
    assert tactics_with_probs[0][0] == "assumption"
