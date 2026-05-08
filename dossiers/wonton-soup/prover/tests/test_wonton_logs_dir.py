from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

import wonton
from runtime_paths import default_persistent_root, local_runtime_logs_root


def test_resolve_logs_dir_env_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SPECTER_LOG_ROOT", raising=False)
    monkeypatch.delenv("SPCTR_LOCAL_LOG_ROOT", raising=False)
    out = wonton.resolve_logs_dir()
    assert out.name == "logs"
    assert out == default_persistent_root() / "logs"

    monkeypatch.setenv("SPECTER_LOG_ROOT", "   ")
    with pytest.raises(ValueError, match="SPECTER_LOG_ROOT is set but empty"):
        wonton.resolve_logs_dir()

    monkeypatch.setenv("SPECTER_LOG_ROOT", str(tmp_path))
    out = wonton.resolve_logs_dir()
    assert out == local_runtime_logs_root()

    monkeypatch.setenv("SPCTR_LOCAL_LOG_ROOT", str(tmp_path / "local"))
    out = wonton.resolve_logs_dir()
    assert out == (tmp_path / "local" / "wonton-soup" / "logs").resolve()


def test_list_runs_discovers_non_corpus_run_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = "2026-r1"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "provider": "demo",
                "corpus": "mini",
                "created_at": "2026-03-02T12:34:56",
            }
        )
    )
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "completed", "goal_id_scheme": "checkpoint"})
    )
    with gzip.open(run_dir / "summary.json.gz", "wt") as f:
        json.dump(
            {
                "theorems": [
                    {"wild_type": {"solved": True}},
                    {"wild_type": {"solved": False}},
                ]
            },
            f,
        )

    monkeypatch.setattr(wonton, "resolve_logs_dir", lambda: tmp_path)

    wonton.list_runs()

    out = capsys.readouterr().out
    assert run_id in out
