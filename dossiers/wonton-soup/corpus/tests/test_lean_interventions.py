from __future__ import annotations

from corpus.lean.theorems import Theorem
from prover.history import (
    ExplorationHistory,
    IterationRecord,
    TacticAttempt,
    TacticOutcome,
)


def _attempt(iteration: int, tactic: str, outcome: TacticOutcome) -> TacticAttempt:
    return TacticAttempt(
        iteration=iteration,
        node_mvar_id="root",
        tactic=tactic,
        tactic_norm=tactic,
        outcome=outcome,
        child_mvar_ids=[],
        timestamp_ms=0,
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


def test_generate_interventions_adds_path_blocks_and_nonpath_controls() -> None:
    theorem = Theorem("demo_theorem", "theorem {name} : True := by\n  sorry")
    history = ExplorationHistory.create("demo_theorem")
    history.solution_path = [{"tactic": "intro h"}, {"tactic": "assumption"}]
    history.record_iteration(
        IterationRecord(
            iteration=0,
            selected_path=["root"],
            attempts=[
                _attempt(0, "intro h", TacticOutcome.SUCCESS),
                _attempt(0, "simp", TacticOutcome.FAILURE),
                _attempt(0, "omega", TacticOutcome.FAILURE),
                _attempt(0, "assumption", TacticOutcome.SUCCESS),
            ],
            backprop_success=True,
            terminal_reached=True,
        )
    )

    interventions = theorem.generate_interventions(history)
    by_name = {intervention.name: intervention for intervention in interventions}

    assert by_name["block_intro"].blocked == {"intro"}
    assert by_name["block_assumption"].blocked == {"assumption"}
    assert by_name["control_null"].blocked == {"omega"}
    assert by_name["control_null"].is_control is True
    assert by_name["random_nonpath_control"].blocked <= {"omega", "simp"}
    assert by_name["random_nonpath_control"].blocked != {"omega"}
    assert by_name["random_nonpath_control"].is_control is True


def test_generate_interventions_reuses_only_nonpath_control_when_single_unused() -> None:
    theorem = Theorem("demo_theorem", "theorem {name} : True := by\n  sorry")
    history = ExplorationHistory.create("demo_theorem")
    history.solution_path = [{"tactic": "trivial"}]
    history.record_iteration(
        IterationRecord(
            iteration=0,
            selected_path=["root"],
            attempts=[
                _attempt(0, "trivial", TacticOutcome.SUCCESS),
                _attempt(0, "simp", TacticOutcome.FAILURE),
            ],
            backprop_success=True,
            terminal_reached=True,
        )
    )

    interventions = theorem.generate_interventions(history)
    by_name = {intervention.name: intervention for intervention in interventions}

    assert by_name["control_null"].blocked == {"simp"}
    assert by_name["random_nonpath_control"].blocked == {"simp"}
    assert by_name["random_nonpath_control"].is_control is True


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
