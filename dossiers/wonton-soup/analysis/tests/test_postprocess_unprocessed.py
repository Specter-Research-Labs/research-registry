from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.logs import sha256_file
from analysis.postprocess_batch import (
    discover_postprocess_run_states,
    inspect_postprocess_run_state,
    postprocess_unprocessed_runs,
)
from analysis.postprocess_metrics import PostprocessParams


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _params_dict(params: PostprocessParams) -> dict[str, object]:
    return {
        "max_soft_ged_nodes": params.max_soft_ged_nodes,
        "max_soft_ged_edges": params.max_soft_ged_edges,
        "soft_ged_timeout_sec": params.soft_ged_timeout_sec,
        "max_novelty_pairs": params.max_novelty_pairs,
        "max_path_dp_cells": params.max_path_dp_cells,
        "max_root_goal_theorems": params.max_root_goal_theorems,
        "max_root_goal_knn_theorems": params.max_root_goal_knn_theorems,
        "root_goal_knn_k": params.root_goal_knn_k,
        "root_goal_knn_sample": params.root_goal_knn_sample,
        "root_goal_sample_size": params.root_goal_sample_size,
        "root_goal_mode": params.root_goal_mode,
        "external_statement_max_full": params.external_statement_max_full,
        "external_statement_max_knn": params.external_statement_max_knn,
        "external_statement_knn_k": params.external_statement_knn_k,
        "external_statement_knn_sample": params.external_statement_knn_sample,
        "external_statement_sample_size": params.external_statement_sample_size,
        "external_statement_mode": params.external_statement_mode,
    }


def _make_eligible_run(
    run_dir: Path,
    *,
    run_id: str,
    created_at: str,
    status: str = "completed",
    partial_results: bool = False,
    with_goal_cache: bool = True,
) -> None:
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": run_id,
            "created_at": created_at,
        },
    )
    _write_json(run_dir / "run_status.json", {"status": status, "partial_results": partial_results})
    _write_json_gz(
        run_dir / "summary.json.gz",
        {"run_id": run_id, "theorems": [], "aggregates": {}},
    )
    if with_goal_cache:
        _write_json_gz(run_dir / "goal_cache.json.gz", {"entries": {}})


def _write_up_to_date_metrics(run_dir: Path, *, params: PostprocessParams) -> None:
    _write_json(
        run_dir / "postprocess_metrics.json",
        {
            "inputs": {
                "summary_sha256": sha256_file(run_dir / "summary.json.gz"),
                "goal_cache_sha256": sha256_file(run_dir / "goal_cache.json.gz"),
            },
            "params": _params_dict(params),
        },
    )


def test_inspect_postprocess_run_state_eligibility_and_reasons(tmp_path: Path) -> None:
    params = PostprocessParams()

    missing_summary = tmp_path / "missing-summary"
    _write_json(missing_summary / "run_config.json", {"run_id": "r1"})
    _write_json(missing_summary / "run_status.json", {"status": "completed"})
    state = inspect_postprocess_run_state(missing_summary, params=params, include_partial=True)
    assert state.reason == "missing_summary"
    assert state.eligible is False

    missing_status = tmp_path / "missing-status"
    _write_json(missing_status / "run_config.json", {"run_id": "r2"})
    _write_json_gz(missing_status / "summary.json.gz", {"theorems": [], "aggregates": {}})
    state = inspect_postprocess_run_state(missing_status, params=params, include_partial=True)
    assert state.reason == "missing_run_status"
    assert state.eligible is False

    invalid_status = tmp_path / "invalid-status"
    _write_json(invalid_status / "run_config.json", {"run_id": "r3"})
    _write_json_gz(invalid_status / "summary.json.gz", {"theorems": [], "aggregates": {}})
    _write_json(invalid_status / "run_status.json", ["not-a-dict"])
    state = inspect_postprocess_run_state(invalid_status, params=params, include_partial=True)
    assert state.reason == "invalid_run_status"
    assert state.eligible is False

    partial = tmp_path / "partial"
    _make_eligible_run(
        partial,
        run_id="r4",
        created_at="2026-01-01T00:00:00Z",
        status="running",
        partial_results=True,
    )
    state = inspect_postprocess_run_state(partial, params=params, include_partial=False)
    assert state.reason == "ineligible_status"
    assert state.eligible is False

    state = inspect_postprocess_run_state(partial, params=params, include_partial=True)
    assert state.reason == "missing_postprocess_metrics"
    assert state.eligible is True
    assert state.needs_processing is True


def test_inspect_postprocess_run_state_staleness_detection(tmp_path: Path) -> None:
    params = PostprocessParams()
    run_dir = tmp_path / "run"
    _make_eligible_run(run_dir, run_id="r1", created_at="2026-01-01T00:00:00Z")

    _write_json(run_dir / "postprocess_metrics.json", {"not": "valid"})
    state = inspect_postprocess_run_state(run_dir, params=params, include_partial=True)
    assert state.reason == "missing_inputs_hashes"
    assert state.needs_processing is True

    _write_json(
        run_dir / "postprocess_metrics.json",
        {
            "inputs": {
                "summary_sha256": "wrong",
                "goal_cache_sha256": "wrong",
            },
            "params": _params_dict(params),
        },
    )
    state = inspect_postprocess_run_state(run_dir, params=params, include_partial=True)
    assert state.reason == "stale_inputs"

    _write_json(
        run_dir / "postprocess_metrics.json",
        {
            "inputs": {
                "summary_sha256": sha256_file(run_dir / "summary.json.gz"),
                "goal_cache_sha256": sha256_file(run_dir / "goal_cache.json.gz"),
            },
        },
    )
    state = inspect_postprocess_run_state(run_dir, params=params, include_partial=True)
    assert state.reason == "missing_params"

    stale_params = _params_dict(params)
    stale_params["max_soft_ged_nodes"] = int(stale_params["max_soft_ged_nodes"]) + 1
    _write_json(
        run_dir / "postprocess_metrics.json",
        {
            "inputs": {
                "summary_sha256": sha256_file(run_dir / "summary.json.gz"),
                "goal_cache_sha256": sha256_file(run_dir / "goal_cache.json.gz"),
            },
            "params": stale_params,
        },
    )
    state = inspect_postprocess_run_state(run_dir, params=params, include_partial=True)
    assert state.reason == "stale_params"

    _write_up_to_date_metrics(run_dir, params=params)
    state = inspect_postprocess_run_state(run_dir, params=params, include_partial=True)
    assert state.reason == "up_to_date"
    assert state.needs_processing is False


def test_discover_postprocess_run_states_orders_oldest_and_skips_provider_subdirs(
    tmp_path: Path,
) -> None:
    params = PostprocessParams()
    logs = tmp_path / "logs"

    run_old = logs / "run-old"
    run_mid = logs / "run-mid"
    run_new = logs / "run-new"
    _make_eligible_run(run_old, run_id="run-old", created_at="2026-01-01T00:00:00Z")
    _make_eligible_run(run_mid, run_id="run-mid", created_at="2026-01-02T00:00:00Z")
    _make_eligible_run(run_new, run_id="run-new", created_at="2026-01-03T00:00:00Z")

    root = logs / "corpus-multi"
    _make_eligible_run(root, run_id="corpus-multi", created_at="2026-01-04T00:00:00Z")
    provider = root / "provider=deepseek"
    _make_eligible_run(provider, run_id="corpus-multi", created_at="2026-01-04T00:00:00Z")

    states = discover_postprocess_run_states(
        [logs],
        params=params,
        include_partial=True,
    )
    names = [s.run_dir.name for s in states]
    assert names == ["run-old", "run-mid", "run-new", "corpus-multi"]
    assert "provider=deepseek" not in names


def test_postprocess_unprocessed_runs_continue_on_error_and_fail_fast(
    tmp_path: Path,
    monkeypatch,
) -> None:
    params = PostprocessParams()
    logs = tmp_path / "logs"
    run_a = logs / "a"
    run_b = logs / "b"
    run_c = logs / "c"
    _make_eligible_run(run_a, run_id="a", created_at="2026-01-01T00:00:00Z")
    _make_eligible_run(run_b, run_id="b", created_at="2026-01-02T00:00:00Z")
    _make_eligible_run(run_c, run_id="c", created_at="2026-01-03T00:00:00Z")

    def fake_postprocess_run(run_dir: Path, *, params: PostprocessParams):
        if run_dir.name == "b":
            raise RuntimeError("boom")
        return {"run_dir": str(run_dir), "inputs": {}, "params": _params_dict(params)}

    monkeypatch.setattr("analysis.postprocess_metrics.postprocess_run", fake_postprocess_run)

    report = postprocess_unprocessed_runs(
        logs_dirs=[logs],
        params=params,
        continue_on_error=True,
    )
    assert report.discovered == 3
    assert report.pending == 3
    assert report.processed == 3
    assert report.succeeded == 2
    assert report.failed == 1
    assert report.skipped == 0
    assert len(report.failures) == 1
    assert (run_a / "postprocess_metrics.json").exists()
    assert not (run_b / "postprocess_metrics.json").exists()
    assert (run_c / "postprocess_metrics.json").exists()

    for run_dir in [run_a, run_b, run_c]:
        if (run_dir / "postprocess_metrics.json").exists():
            (run_dir / "postprocess_metrics.json").unlink()

    report_fail_fast = postprocess_unprocessed_runs(
        logs_dirs=[logs],
        params=params,
        continue_on_error=False,
    )
    assert report_fail_fast.pending == 3
    assert report_fail_fast.processed == 2
    assert report_fail_fast.succeeded == 1
    assert report_fail_fast.failed == 1
    assert report_fail_fast.skipped == 1
