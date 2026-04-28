from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.lake.db import resolve_lake_paths, utc_timestamp
from prover.mcts import TACTIC_FAMILIES


def _stable_ref_id(kind: str, payload: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(kind.encode("utf-8"))
    h.update(b"\0")
    h.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


def _in_clause(values: list[str]) -> tuple[str, list[str]]:
    if not values:
        raise ValueError("values cannot be empty")
    return "(" + ",".join("?" for _ in values) + ")", values


@dataclass(frozen=True)
class BuildReferenceReport:
    ref_id: str
    artifact_path: Path
    members: int
    sigs: int


def build_goal_outcomes_reference(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_keys: list[str],
    alpha: float = 1.0,
    artifacts_dir: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> BuildReferenceReport:
    """Build a cross-run reference table for p(success | goal_sig, tactic_family)."""

    if not run_keys:
        raise ValueError("run_keys is empty")
    if alpha <= 0:
        raise ValueError("alpha must be > 0")

    payload = {
        "run_keys": sorted(run_keys),
        "alpha": float(alpha),
        "families": list(TACTIC_FAMILIES),
    }
    if meta:
        payload["meta"] = meta
    ref_id = _stable_ref_id("goal_outcomes", payload)

    lake_paths = resolve_lake_paths(artifacts_dir=artifacts_dir)
    out_dir = lake_paths.root / "reference" / "goal_outcomes" / ref_id
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "reference_goal_outcomes.json.gz"

    clause, params = _in_clause(run_keys)

    global_rows = conn.execute(
        f"""
        SELECT family_idx, sum(attempts) AS attempts, sum(successes) AS successes
        FROM goal_outcome_global_family
        WHERE run_key IN {clause}
        GROUP BY family_idx
        ORDER BY family_idx
        """,
        params,
    ).fetchall()
    n_fam = len(TACTIC_FAMILIES)
    global_attempts = [0] * n_fam
    global_successes = [0] * n_fam
    for fam_idx, attempts, successes in global_rows:
        if not isinstance(fam_idx, int):
            continue
        if fam_idx < 0 or fam_idx >= n_fam:
            continue
        global_attempts[fam_idx] = int(attempts)
        global_successes[fam_idx] = int(successes)

    sig_rows = conn.execute(
        f"""
        SELECT goal_sig, family_idx, sum(attempts) AS attempts, sum(successes) AS successes
        FROM goal_outcome_sig_family
        WHERE run_key IN {clause}
        GROUP BY goal_sig, family_idx
        ORDER BY goal_sig, family_idx
        """,
        params,
    ).fetchall()

    by_sig: dict[str, dict[str, list[int]]] = {}
    for sig, fam_idx, attempts, successes in sig_rows:
        if not isinstance(sig, str) or not isinstance(fam_idx, int):
            continue
        if fam_idx < 0 or fam_idx >= n_fam:
            continue
        row = by_sig.get(sig)
        if row is None:
            row = {"attempts": [0] * n_fam, "successes": [0] * n_fam}
            by_sig[sig] = row
        row["attempts"][fam_idx] = int(attempts)
        row["successes"][fam_idx] = int(successes)

    artifact = {
        "schema_version": 1,
        "kind": "goal_outcomes",
        "created_at": utc_timestamp(),
        "alpha": float(alpha),
        "tactic_families": list(TACTIC_FAMILIES),
        "members": sorted(run_keys),
        "global": {"attempts": global_attempts, "successes": global_successes},
        "by_sig": by_sig,
        "meta": meta or {},
    }

    with gzip.open(artifact_path, "wt") as f:
        json.dump(artifact, f)

    # Upsert reference rows.
    exists = conn.execute(
        "SELECT 1 FROM lake_references WHERE ref_id = ? LIMIT 1",
        [ref_id],
    ).fetchone()
    if exists is None:
        conn.execute(
            "INSERT INTO lake_references(ref_id, kind, meta, artifact_path) VALUES (?, ?, ?, ?)",
            [ref_id, "goal_outcomes", json.dumps(meta or {}), str(artifact_path)],
        )

    conn.execute("DELETE FROM lake_reference_members WHERE ref_id = ?", [ref_id])
    for rk in run_keys:
        conn.execute(
            "INSERT INTO lake_reference_members(ref_id, run_key) VALUES (?, ?)",
            [ref_id, rk],
        )

    return BuildReferenceReport(
        ref_id=ref_id,
        artifact_path=artifact_path,
        members=len(run_keys),
        sigs=len(by_sig),
    )
