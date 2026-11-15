from __future__ import annotations

import gzip
import json
from pathlib import Path

import duckdb
import pytest

from analysis.lake.checked_outcomes import decode_name, row_outcome, write_outcomes
from analysis.lake.db import connect, ensure_schema, root_id_for_path
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.verdicts import ingest_replay_verdicts

THEOREM = "Nat_x2eadd_x5fcomm"


def _archived_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.json").write_text(json.dumps({"run_id": "a", "backend": "lean"}))
    theorems = [
        {
            "name": THEOREM,
            "wild_type": {"solved": True, "metrics": {}},
            "interventions": [
                {"name": "block_rw", "blocked": ["rw"], "solved": True},
                {"name": "block_omega", "blocked": ["omega"], "solved": True},
                {"name": "block_simp", "blocked": ["simp"], "solved": True},
                {"name": "block_ring", "blocked": ["ring"], "solved": False},
            ],
        }
    ]
    with gzip.open(run_dir / "summary.json.gz", "wt") as f:
        json.dump({"run_id": "a", "theorems": theorems, "aggregates": {}}, f)


@pytest.fixture
def lake(tmp_path: Path):
    logs_root = tmp_path / "logs"
    _archived_run(logs_root / "a")
    conn = connect(tmp_path / "lake.duckdb")
    ensure_schema(conn)
    index_logs(conn, logs_dirs=[logs_root])
    run_rows = conn.execute(
        "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ?", [root_id_for_path(logs_root)]
    ).fetchall()
    extract_facts(conn, root_dir=logs_root, run_rows=run_rows, with_goal_outcomes=False)
    [(run_key,)] = conn.execute("SELECT run_key FROM runs").fetchall()
    verdicts = tmp_path / "verdicts.parquet"
    rows = [
        (run_key, THEOREM, "wild_type", "ok", "checked", None, ["Nat.succ_add"]),
        (run_key, THEOREM, "block_rw", "ok", "checked", None, ["Nat.add_comm"]),
        (run_key, THEOREM, "block_omega", "ok", "replay_failed", "tactic failed", None),
    ]
    staging = duckdb.connect()
    staging.execute(
        "CREATE TABLE v (run_key VARCHAR, theorem VARCHAR, variant VARCHAR, status VARCHAR, "
        "replay_status VARCHAR, replay_error VARCHAR, premises VARCHAR[])"
    )
    staging.executemany("INSERT INTO v VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    staging.execute(f"COPY v TO '{verdicts}' (FORMAT parquet)")
    staging.close()
    ingest_replay_verdicts(conn, verdicts)
    yield conn
    conn.close()


def test_every_row_is_labelled_and_missing_verdicts_stay_visible(lake, tmp_path: Path) -> None:
    out = tmp_path / "outcomes.parquet"
    counts = write_outcomes(lake, out)
    assert counts == {
        "checked": 1,
        "checked_selfcite": 1,
        "failed_check": 1,
        "unverified": 1,
        "unsolved": 1,
    }
    rows = {
        r[0]: r[1:]
        for r in duckdb.sql(
            f"SELECT variant, outcome, solved_raw, solved_checked, solved_checked_nonself "
            f"FROM '{out}'"
        ).fetchall()
    }
    assert rows == {
        "wild_type": ("checked", True, True, True),
        "block_rw": ("checked_selfcite", True, True, False),
        "block_omega": ("failed_check", True, False, False),
        "block_simp": ("unverified", True, False, False),
        "block_ring": ("unsolved", False, False, False),
    }
    assert write_outcomes(lake, out) == counts


def test_decode_name_and_unexpected_status() -> None:
    assert decode_name(THEOREM) == "Nat.add_comm"
    assert decode_name("coq_pair_or_assoc") == "coq_pair_or_assoc"
    assert decode_name("Action_x2eforget_x2082_x5fadditive") == "Action.forget₂_additive"
    assert decode_name("Action_x2eforget_x5f_x03b4") == "Action.forget_δ"
    assert decode_name("Nat_x2eadd_x27") == "Nat.add'"
    with pytest.raises(ValueError, match="0 readings"):
        decode_name("a_x20b")
    with pytest.raises(ValueError, match="blocked_premise"):
        row_outcome("t", True, "blocked_premise", "[]")
    assert row_outcome("t", False, "blocked_premise", "[]") == "unsolved"
