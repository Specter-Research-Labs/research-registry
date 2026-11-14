import pytest

from prover.intervention import _runs_blocked_tactic
from prover.providers.base import tactic_families, tactic_family, tactic_heads, tactic_leaves


@pytest.mark.parametrize(
    ("tactic", "heads"),
    [
        ("simp", {"simp"}),
        ("simp <;> first | ring | linarith", {"simp", "ring", "linarith"}),
        ("try (exact (by norm_num))", {"exact", "norm_num"}),
        ("all_goals simp", {"simp"}),
        ("any_goals (rw [h]; ring)", {"rw", "ring"}),
        ("constructor\n· simp\n· linarith", {"constructor", "simp", "linarith"}),
        ("refine ⟨by simp, by omega⟩", {"refine", "simp", "omega"}),
        ("cases h with\n| inl h => exact h\n| inr h => simp at h", {"cases", "exact", "simp"}),
        ("norm_num1", {"norm_num"}),
        ("repeat' constructor", {"constructor"}),
        ("on_goal 2 => ring", {"ring"}),
        ("case succ n ih => simp [ih]", {"simp"}),
    ],
)
def test_tactic_heads_look_through_combinators(tactic: str, heads: set[str]) -> None:
    assert tactic_heads(tactic) == heads


def test_by_inside_identifier_is_not_a_block() -> None:
    assert tactic_leaves("exact Nat.by_contra h") == ["exact Nat.by_contra h"]


def test_families_cover_every_leaf_and_first_leaf_names_the_tactic() -> None:
    assert tactic_families("simp <;> linarith") == {"simplify", "arith"}
    assert tactic_family("try linarith") == "arith"
    assert tactic_family("apply Or.inl") == "split"
    assert tactic_family("apply foo") == "other"


@pytest.mark.parametrize(
    "tactic",
    [
        "norm_num",
        "norm_num1",
        "simp <;> norm_num",
        "first | ring | norm_num [h]",
        "exact (by norm_num)",
        "· norm_num",
        "all_goals norm_num",
    ],
)
def test_blocked_head_is_found_anywhere_in_the_tactic(tactic: str) -> None:
    assert _runs_blocked_tactic(frozenset({"norm_num"}), tactic)


def test_blocked_head_does_not_match_other_heads() -> None:
    assert not _runs_blocked_tactic(frozenset({"norm_num"}), "simp [norm_num_lemma]")
    assert not _runs_blocked_tactic(frozenset({"simp"}), "simp_all")
