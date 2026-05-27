from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lenia_swarm_analysis.morphospace import track1_monitor


def test_monitor_promotes_before_scanning_warehouse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "track1b-2c10-r7-10-initshift-8192-s1"
    run_root = tmp_path / "runs"
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"count": 8192, "resultsCount": 8192}),
        encoding="utf-8",
    )

    compendium_path = tmp_path / "compendium.sqlite"
    connection = sqlite3.connect(compendium_path)
    try:
        connection.execute("CREATE TABLE results (run_id TEXT NOT NULL)")
        connection.commit()
    finally:
        connection.close()

    def fail_refreshed_runs(*_args, **_kwargs) -> set[str]:
        raise AssertionError("warehouse scan should not run before promotion")

    def fake_promote(**kwargs) -> dict[str, object]:
        assert kwargs["run_id"] == run_id
        return {"runId": run_id, "promotedRows": 8192}

    monkeypatch.setattr(track1_monitor, "refreshed_runs", fail_refreshed_runs)
    monkeypatch.setattr(track1_monitor, "promote", fake_promote)

    outcome = track1_monitor.monitor_once(
        root=tmp_path,
        run_root=run_root,
        compendium_path=compendium_path,
        warehouse_path=tmp_path / "warehouse.duckdb",
        log_path=tmp_path / "monitor.jsonl",
        expected_count=8192,
    )

    assert outcome == "promoted"
    log_row = json.loads((tmp_path / "monitor.jsonl").read_text(encoding="utf-8"))
    assert log_row["event"] == "promoted"
    assert log_row["runId"] == run_id
