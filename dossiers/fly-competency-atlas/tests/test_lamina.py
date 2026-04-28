from pathlib import Path
from typing import cast

from fly_competency_atlas.lamina import (
    AssetRecord,
    CircuitSummary,
    build_manifest,
    default_cases,
    default_input_patterns,
    default_lesions,
    planned_run_records,
)


def test_default_lamina_panel_is_focused() -> None:
    case_ids = {case.case_id for case in default_cases()}
    assert len(case_ids) == 12
    assert "uniform_full_field__disable_L2" in case_ids
    assert "single_r1__tutorial_r1_path_ablation" in case_ids


def test_default_inputs_and_lesions_cover_expected_surface() -> None:
    assert [pattern.slug for pattern in default_input_patterns()] == [
        "uniform_full_field",
        "structured_gradient",
        "shuffled_gradient_seed_11",
        "single_r1",
    ]
    assert [lesion.slug for lesion in default_lesions()] == [
        "none",
        "disable_L2",
        "disable_T1",
        "disable_a1",
        "tutorial_r1_path_ablation",
    ]


def test_manifest_and_planned_records_share_schema() -> None:
    manifest = build_manifest(
        Path("/tmp/lamina"),
        (
            AssetRecord(
                relative_path="upstream/connection.csv",
                source_url="https://example.com/connection.csv",
                sha256="abc",
                bytes=12,
                materialized=False,
            ),
        ),
        CircuitSummary(
            neuron_order=("R1", "R2"),
            neuron_count=2,
            edge_count=1,
            total_synapse_weight=3,
            swc_files=("R1.swc", "R2.swc"),
        ),
    )
    cases = cast(list[dict[str, object]], manifest["cases"])
    records = planned_run_records(cases)
    assert manifest["result_schema_version"] == "lamina_result_v1"
    assert len(records) == len(cases)
    first_metrics = cast(dict[str, object], records[0]["metrics"])
    assert first_metrics["lesion_tolerance"] is None
