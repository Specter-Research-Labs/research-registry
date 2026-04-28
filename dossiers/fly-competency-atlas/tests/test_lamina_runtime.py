from pathlib import Path

from fly_competency_atlas.lamina_runtime import (
    RuntimeArgs,
    default_raw_root,
    default_result_path,
    dry_run_record,
    filter_cases,
)


def test_filter_cases_restricts_to_selected_ids() -> None:
    cases = [
        {"case_id": "a", "family": "f", "metric_slots": []},
        {"case_id": "b", "family": "f", "metric_slots": []},
    ]
    filtered = filter_cases(cases, ("b",))
    assert [case["case_id"] for case in filtered] == ["b"]


def test_default_output_paths_follow_manifest_layout() -> None:
    manifest = Path(
        "/tmp/fly-competency-atlas/lamina_cartridge/manifests/lamina_step_panel_v1.json"
    )
    assert default_result_path(manifest) == Path(
        "/tmp/fly-competency-atlas/lamina_cartridge/results/lamina_step_panel_v1.ndjson"
    )
    assert default_raw_root(manifest) == Path(
        "/tmp/fly-competency-atlas/lamina_cartridge/results/lamina_step_panel_v1"
    )


def test_dry_run_record_preserves_metric_slots() -> None:
    record = dry_run_record(
        {"case_id": "case-a", "family": "fam", "metric_slots": ["lesion_tolerance"]},
        RuntimeArgs(
            manifest=Path("/tmp/manifest.json"),
            processor_url="wss://processor.example/ws",
            dataset="optic_lobe",
            connect_timeout_s=20,
            execute_timeout_s=180,
            dry_run=True,
            case_ids=(),
            keep_going=False,
        ),
    )
    assert record["status"] == "dry_run"
    assert record["metrics"]["lesion_tolerance"] is None
