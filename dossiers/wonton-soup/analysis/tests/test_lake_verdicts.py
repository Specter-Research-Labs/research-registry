from __future__ import annotations

import gzip
import json
from pathlib import Path

import duckdb
import pytest

from analysis.lake.db import SCHEMA_VERSION, connect, ensure_schema, root_id_for_path
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.verdicts import ingest_replay_verdicts

PROVENANCE = {
    "source": {"vcs": "jj", "base_commit": "c0ffee", "dirty": True},
    "lean": {
        "toolchain": "leanprover/lean4:v4.25.0",
        "mathlib": {"source": "lake-manifest", "rev": "abc123", "dirty": False},
    },
    "python": {"leantree": "1.0.0", "uv_lock_sha256": "0" * 64},
    "tactic_limit": {"kind": "heartbeats", "tactic_heartbeats": 50000},
}


def _check(status: str, premises: list[str]) -> dict:
    return {
        "status": status,
        "error": None,
        "tactics": ["simp"],
        "term_hash": "t" * 64 if status == "checked" else None,
        "premises": premises,
        "self_citation": False,
        "blocked_hits": [] if status == "checked" else premises,
    }


def _write_run(run_dir: Path, run_config: dict, theorems: list[dict]) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.json").write_text(json.dumps(run_config))
    with gzip.open(run_dir / "summary.json.gz", "wt") as f:
        json.dump({"run_id": run_dir.name, "theorems": theorems, "aggregates": {}}, f)


def _checked_run(run_dir: Path) -> None:
    _write_run(
        run_dir,
        {"run_id": "checked", "backend": "lean", "provenance": PROVENANCE},
        [
            {
                "name": "t1",
                "wild_type": {
                    "solved": True,
                    "tree_solved": True,
                    "check_status": "checked",
                    "metrics": {"kernel_check": _check("checked", ["List.append_nil"])},
                },
                "interventions": [
                    {
                        "name": "block_premise_List.append_nil",
                        "blocked": [],
                        "blocked_premises": ["List.append_nil"],
                        "solved": False,
                        "tree_solved": True,
                        "check_status": "blocked_premise",
                        "metrics": {"kernel_check": _check("blocked_premise", ["List.append_nil"])},
                    },
                    {
                        "name": "block_simp",
                        "blocked": ["simp"],
                        "solved": False,
                        "tree_solved": False,
                        "check_status": None,
                        "metrics": {"kernel_check": None},
                    },
                ],
            }
        ],
    )


def _archived_run(run_dir: Path) -> None:
    _write_run(
        run_dir,
        {"run_id": "archived", "backend": "lean"},
        [
            {
                "name": "t2",
                "wild_type": {"solved": True, "metrics": {}},
                "interventions": [
                    {"name": "block_intro", "blocked": ["intro"], "solved": True},
                    {"name": "block_ring", "blocked": ["ring"], "solved": True},
                    {"name": "block_omega", "blocked": ["omega"], "solved": False},
                ],
            }
        ],
    )


def _write_verdict_parquet(path: Path, rows: list[tuple]) -> None:
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE v (run_key VARCHAR, theorem VARCHAR, variant VARCHAR, status VARCHAR, "
        "replay_status VARCHAR, replay_error VARCHAR, premises VARCHAR[])"
    )
    conn.executemany("INSERT INTO v VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    conn.execute(f"COPY v TO '{path}' (FORMAT parquet)")
    conn.close()


@pytest.fixture
def lake(tmp_path: Path):
    logs_root = tmp_path / "logs"
    _checked_run(logs_root / "checked")
    _archived_run(logs_root / "archived")
    conn = connect(tmp_path / "lake.duckdb")
    ensure_schema(conn)
    index_logs(conn, logs_dirs=[logs_root])
    run_rows = conn.execute(
        "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ?",
        [root_id_for_path(logs_root)],
    ).fetchall()
    extract_facts(conn, root_dir=logs_root, run_rows=run_rows, with_goal_outcomes=False)
    keys = dict(conn.execute("SELECT run_id, run_key FROM runs").fetchall())
    yield conn, keys
    conn.close()


def test_kernel_check_and_provenance_columns(lake) -> None:
    conn, keys = lake
    assert conn.execute(
        "SELECT source_commit, source_dirty, lean_toolchain, mathlib_rev FROM runs "
        "WHERE run_key = ?",
        [keys["checked"]],
    ).fetchone() == ("c0ffee", True, "leanprover/lean4:v4.25.0", "abc123")
    assert conn.execute(
        "SELECT source_commit, provenance FROM runs WHERE run_key = ?", [keys["archived"]]
    ).fetchone() == (None, None)

    assert conn.execute(
        "SELECT solved, tree_solved, check_status, self_citation, term_hash, premises "
        "FROM theorem_wild WHERE run_key = ?",
        [keys["checked"]],
    ).fetchone() == (True, True, "checked", False, "t" * 64, '["List.append_nil"]')
    assert conn.execute(
        "SELECT solved, tree_solved, check_status, blocked_premises FROM theorem_intervention "
        "WHERE run_key = ? AND intervention = 'block_premise_List.append_nil'",
        [keys["checked"]],
    ).fetchone() == (False, True, "blocked_premise", '["List.append_nil"]')
    assert conn.execute(
        "SELECT solved, tree_solved, check_status FROM theorem_wild WHERE run_key = ?",
        [keys["archived"]],
    ).fetchone() == (True, None, None)


def test_checked_comparison_needs_a_verdict_for_every_solved_row(lake, tmp_path: Path) -> None:
    conn, keys = lake
    query = (
        "SELECT run_key, intervention, wild_solved, solved, check_status, verdict_source "
        "FROM theorem_intervention_checked ORDER BY run_key, intervention"
    )
    before = conn.execute(query).fetchall()
    assert {row[0] for row in before} == {keys["checked"]}

    verdicts = tmp_path / "verdicts.parquet"
    _write_verdict_parquet(
        verdicts,
        [
            (keys["archived"], "t2", "wild_type", "ok", "checked", None, ["Nat.add_comm"]),
            (keys["archived"], "t2", "block_intro", "ok", "replay_failed", "tactic failed", None),
        ],
    )
    assert ingest_replay_verdicts(conn, verdicts) == 2
    assert ingest_replay_verdicts(conn, verdicts) == 2

    rows = {(r[0], r[1]): r[2:] for r in conn.execute(query).fetchall()}
    archived = keys["archived"]
    checked = keys["checked"]
    assert rows == {
        (archived, "block_intro"): (True, False, "replay_failed", "replay"),
        (archived, "block_omega"): (True, False, None, "replay"),
        (checked, "block_premise_List.append_nil"): (True, False, "blocked_premise", "run"),
        (checked, "block_simp"): (True, False, None, "run"),
    }
    assert conn.execute(
        "SELECT premises FROM theorem_variant_verdict WHERE run_key = ? AND variant = 'wild_type'",
        [archived],
    ).fetchone() == ('["Nat.add_comm"]',)


def test_ingest_rejects_unknown_replay_status(lake, tmp_path: Path) -> None:
    conn, _ = lake
    path = tmp_path / "bad.parquet"
    _write_verdict_parquet(path, [("k", "t", "wild_type", "ok", "proved", None, None)])
    with pytest.raises(ValueError, match="unknown replay statuses"):
        ingest_replay_verdicts(conn, path)


def test_v12_lake_retypes_tactic_fingerprint(tmp_path: Path) -> None:
    conn = connect(tmp_path / "lake.duckdb")
    ensure_schema(conn)
    conn.execute("ALTER TABLE theorem_variant_metrics ALTER COLUMN tactic_fingerprint TYPE VARCHAR")
    conn.execute("DELETE FROM schema_meta")
    conn.execute("INSERT INTO schema_meta(schema_version) VALUES (12)")
    ensure_schema(conn)
    column_type = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'theorem_variant_metrics' AND column_name = 'tactic_fingerprint'"
    ).fetchone()
    assert column_type == ("JSON",)
    assert conn.execute("SELECT max(schema_version) FROM schema_meta").fetchone() == (
        SCHEMA_VERSION,
    )
    conn.close()
