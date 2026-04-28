from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.lake.db import connect, ensure_schema
from analysis.lake.index import index_logs


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def test_index_logs_records_unreadable_json(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    run_dir = logs_root / "corpus-1"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Invalid JSON payload (parse error).
    (run_dir / "run_config.json").write_text("{", encoding="utf-8")
    _write_json_gz(
        run_dir / "summary.json.gz",
        {"run_id": "corpus-1", "goal_sig_scheme": "text", "theorems": [], "aggregates": {}},
    )

    conn = connect(tmp_path / "lake.duckdb")
    try:
        ensure_schema(conn)
        rep = index_logs(conn, logs_dirs=[logs_root])
        assert rep.runs_indexed == 1
        assert any("run_config.json" in e for e in rep.errors)
    finally:
        conn.close()

