from corpus.lean.theorems import Theorem
from prover.history import (
    ExplorationHistory,
    IterationRecord,
    TacticAttempt,
    TacticOutcome,
)


def _history_with_attempts(*tactics: str) -> ExplorationHistory:
    history = ExplorationHistory.create("theorem t : True := by\n  sorry")
    history.record_iteration(
        IterationRecord(
            iteration=0,
            selected_path=["root"],
            attempts=[
                TacticAttempt(
                    iteration=0,
                    node_mvar_id="root",
                    tactic=tactic,
                    tactic_norm=tactic,
                    outcome=TacticOutcome.FAILURE,
                    child_mvar_ids=[],
                    timestamp_ms=0,
                )
                for tactic in tactics
            ],
            backprop_success=False,
            terminal_reached=False,
        )
    )
    return history


def test_generate_interventions_skips_invalid_tactic_heads() -> None:
    theorem = Theorem("t", "theorem t : True := by\n  sorry")
    history = _history_with_attempts("])])])])", "rw [h]", "simp [Nat.add_sub_cancel]")

    interventions = theorem.generate_interventions(history)

    assert [intervention.name for intervention in interventions] == ["block_rw", "block_simp"]
    assert [intervention.blocked for intervention in interventions] == [{"rw"}, {"simp"}]


def test_generate_interventions_canonicalizes_numeric_tactic_suffixes() -> None:
    theorem = Theorem("t", "theorem t : True := by\n  sorry")
    history = _history_with_attempts("norm_num1", "simp_all2 [h]")

    interventions = theorem.generate_interventions(history)

    assert [intervention.name for intervention in interventions] == [
        "block_norm_num",
        "block_simp_all",
    ]
    assert [intervention.blocked for intervention in interventions] == [
        {"norm_num"},
        {"simp_all"},
    ]


def test_generate_interventions_returns_empty_for_only_invalid_tactic_heads() -> None:
    theorem = Theorem("t", "theorem t : True := by\n  sorry")
    history = _history_with_attempts("]", "])])])])")

    assert theorem.generate_interventions(history) == []
