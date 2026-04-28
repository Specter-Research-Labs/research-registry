from __future__ import annotations

from typing import cast

from leantree.core.lean import LeanGoal
from leantree.repl_adapter.interaction import LeanEnvironmentCheckpoint

from prover.adapters.lean import TacticPreview
from prover.assembly import ProofAssemblyTrace


def test_tactic_preview_action_metadata_tracks_dependencies_and_spawned_goals() -> None:
    preview = TacticPreview(
        tactic="have h := hp",
        parent_mvar_id="root",
        child_mvar_ids=["child"],
        child_goals=[],
        partial_term_before=None,
        partial_term_after=None,
        completed_proof_term=None,
        goals_before=["root"],
        goals_after=["child"],
        checkpoint=cast(LeanEnvironmentCheckpoint, object()),
        checkpoint_id=1,
        branches=[],
        tactic_depends_on=["hp", "hp"],
        spawned_goals=[LeanGoal(type="P", hypotheses=[], tag=None)],
        proof_step_count=2,
    )

    metadata = preview.action_metadata(expanded_child_count=1)

    assert metadata["depends_on_count"] == 1
    assert metadata["tactic_depends_on"] == ["hp"]
    assert metadata["spawned_goal_count"] == 1
    assert metadata["proof_step_count"] == 2
    assert metadata["continuation_kind"] == "chain"
    assert metadata["effect_flags"] == [
        "closes_goals",
        "opens_goals",
        "spawns_goals",
        "uses_hypotheses",
    ]


def test_tactic_preview_action_metadata_uses_spawned_goal_count_for_branch_arity() -> None:
    preview = TacticPreview(
        tactic="constructor",
        parent_mvar_id="root",
        child_mvar_ids=[],
        child_goals=[],
        partial_term_before=None,
        partial_term_after=None,
        completed_proof_term=None,
        goals_before=["root"],
        goals_after=[],
        checkpoint=cast(LeanEnvironmentCheckpoint, object()),
        checkpoint_id=1,
        branches=[],
        spawned_goals=[
            LeanGoal(type="P", hypotheses=[], tag=None),
            LeanGoal(type="Q", hypotheses=[], tag=None),
        ],
    )

    metadata = preview.action_metadata()

    assert metadata["branch_arity"] == 2
    assert metadata["expanded_child_count"] == 2
    assert metadata["branch_count"] == 1
    assert metadata["continuation_kind"] == "branch"
    assert metadata["goal_coupling"] == "unknown"
    assert metadata["effect_flags"] == [
        "branches_goals",
        "closes_goals",
        "spawns_goals",
    ]


def test_assembly_trace_serializes_action_metadata() -> None:
    trace = ProofAssemblyTrace(theorem="theorem t : True := by\n  sorry", root_mvar_id="root")
    trace.add_step(
        tactic="intro h",
        mvar_id="root",
        partial_term_before=None,
        partial_term_after=None,
        goals_before=["root"],
        goals_after=["child"],
        action_metadata={
            "continuation_kind": "chain",
            "effect_flags": ["opens_binder", "uses_hypotheses"],
            "depends_on_count": 1,
        },
    )

    serialized = trace.serialize()

    assert serialized["steps"][0]["actionMetadata"] == {
        "continuation_kind": "chain",
        "effect_flags": ["opens_binder", "uses_hypotheses"],
        "depends_on_count": 1,
    }
