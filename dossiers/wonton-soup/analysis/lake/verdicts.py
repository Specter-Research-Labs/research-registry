"""Ingest kernel replay verdicts for archived runs into the lake.

Runs from before the in-run kernel check only know that their search tree
closed. A replay study re-elaborates those proofs offline; its per-variant
verdicts land in `replay_verdict` and feed the checked comparison views.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import get_args

import duckdb

from prover.dependencies import CheckStatus

VERDICT_COLUMNS = (
    "run_key",
    "theorem",
    "variant",
    "status",
    "replay_status",
    "replay_error",
    "premises",
)


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> int:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


def ingest_replay_verdicts(conn: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Upsert every row of a verdict parquet; returns the number of rows ingested."""
    source = str(path)
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    columns = set(conn.read_parquet(source).columns)
    missing = [c for c in VERDICT_COLUMNS if c not in columns]
    if missing:
        raise ValueError(f"{path} lacks verdict columns {missing}")
    duplicated = _scalar(
        conn,
        "SELECT count(*) - count(DISTINCT (run_key, theorem, variant)) FROM read_parquet(?)",
        [source],
    )
    if duplicated:
        raise ValueError(f"{path} has {duplicated} duplicate (run_key, theorem, variant) rows")
    unknown = conn.execute(
        """
        SELECT DISTINCT replay_status FROM read_parquet(?)
        WHERE replay_status IS NOT NULL AND NOT list_contains(?, replay_status)
        """,
        [source, list(get_args(CheckStatus))],
    ).fetchall()
    if unknown:
        raise ValueError(f"{path} has unknown replay statuses {sorted(r[0] for r in unknown)}")

    conn.begin()
    try:
        conn.execute(
            """
            DELETE FROM replay_verdict r USING read_parquet(?) i
            WHERE r.run_key = i.run_key AND r.theorem = i.theorem AND r.variant = i.variant
            """,
            [source],
        )
        conn.execute(
            """
            INSERT INTO replay_verdict(
              run_key, theorem, variant, status, replay_status, replay_error, premises,
              source_sha256
            )
            SELECT run_key, theorem, variant, status, replay_status, replay_error,
                   to_json(premises), ?
            FROM read_parquet(?)
            """,
            [source_sha256, source],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _scalar(conn, "SELECT count(*) FROM read_parquet(?)", [source])
