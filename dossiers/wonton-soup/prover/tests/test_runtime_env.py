from __future__ import annotations

from pathlib import Path

import pytest

import runtime_env
from orchestrator.lean import CorpusProgress


def test_assert_wonton_python_runtime_accepts_expected_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_env.sys, "version_info", (3, 12, 5, "final", 0))
    runtime_env.assert_wonton_python_runtime(
        dossier_root=Path("/tmp/wonton"),
        command_name="wonton.py",
    )


def test_assert_wonton_python_runtime_rejects_wrong_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_env.sys, "version_info", (3, 13, 1, "final", 0))
    monkeypatch.setattr(runtime_env.sys, "version", "3.13.1 test-build")
    monkeypatch.setattr(runtime_env.sys, "executable", "/tmp/python3.13")

    with pytest.raises(SystemExit, match="requires Python 3.12"):
        runtime_env.assert_wonton_python_runtime(
            dossier_root=Path("/tmp/wonton"),
            command_name="wonton.py",
        )


def test_corpus_progress_reports_startup_phase(tmp_path: Path) -> None:
    progress = CorpusProgress(
        total_theorems=1,
        corpus_name="easy",
        provider_label="heuristic",
        provider_desc="heuristic",
        log_dir=tmp_path,
        plain=True,
    )

    progress.start_initializing("lean_repl_imports")

    snapshot = progress._progress_snapshot()
    assert snapshot["current"]["phase"] == "startup:lean_repl_imports"
    assert snapshot["current"]["theorem"] == ""


def test_corpus_progress_reports_parallel_basin_workers(tmp_path: Path) -> None:
    progress = CorpusProgress(
        total_theorems=4,
        corpus_name="easy",
        provider_label="heuristic",
        provider_desc="heuristic",
        log_dir=tmp_path,
        plain=True,
    )

    progress.start_basin_mode(10)
    progress.start_basin_theorem("thm_a", 1, worker_id=0)
    progress.update_basin_seed(0, True, "abc", worker_id=0)
    progress.start_basin_theorem("thm_b", 2, worker_id=1)
    progress.update_basin_seed(3, False, None, worker_id=1)

    snapshot = progress._progress_snapshot()
    basin = snapshot["basin"]
    assert basin["workers_active"] == 2
    assert basin["theorem"] == "thm_a"
    assert basin["theorem_idx"] == 1
    assert basin["seeds_completed"] == 1
    assert basin["seeds_solved"] == 1
    assert len(basin["workers"]) == 2
    assert basin["workers"][1]["worker_id"] == 1
    assert basin["workers"][1]["theorem"] == "thm_b"
    assert basin["workers"][1]["seeds_completed"] == 1
