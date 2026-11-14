from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.k_metric import BLIND_CANDIDATE, compute_k
from analysis.logs import (
    extract_solution_steps,
    read_json,
    read_json_gz,
)
from prover.providers.base import TACTIC_FAMILIES


def _load_reference(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("reference artifact must be an object")
    if data.get("kind") != "goal_outcomes":
        raise ValueError(f"Unsupported reference kind: {data.get('kind')!r}")
    return data


def _family_counts(entry: dict[str, Any], fam_idx: int) -> tuple[int, int]:
    attempts = entry["attempts"]
    successes = entry["successes"]
    if len(attempts) != len(TACTIC_FAMILIES) or len(successes) != len(TACTIC_FAMILIES):
        raise ValueError(
            f"reference counts cover {len(attempts)} families, expected {len(TACTIC_FAMILIES)}"
        )
    return attempts[fam_idx], successes[fam_idx]


def _p_success(reference: dict[str, Any], sig: str, fam: str) -> float:
    """Smoothed p(success | sig, family) from the reference; the reference-wide
    family rate when the reference never tried the family on this signature."""
    alpha = float(reference["alpha"])
    if alpha <= 0:
        raise ValueError(f"reference alpha must be positive, got {alpha}")
    fam_idx = TACTIC_FAMILIES.index(fam)
    entry = reference["by_sig"].get(sig)
    counts = _family_counts(entry, fam_idx) if entry is not None else None
    if counts is None or counts[0] <= 0:
        counts = _family_counts(reference["global"], fam_idx)
    attempts, successes = counts
    return (successes + alpha) / (attempts + 2 * alpha)


def compute_k_reference_from_variant(
    *,
    theorem_dir: Path,
    variant: str,
    mvar_to_sig: dict[str, str] | None,
    reference: dict[str, Any],
) -> dict[str, Any]:
    ext = extract_solution_steps(
        theorem_dir=theorem_dir,
        variant=variant,
        mvar_to_sig=mvar_to_sig,
    )
    entry = compute_k(
        ext,
        p_success=lambda sig, fam: _p_success(reference, sig, fam),
        null_models=(BLIND_CANDIDATE,),
        observed_families=None,
    )
    if ext.valid:
        entry["reference_kind"] = "goal_outcomes"
    return entry


@dataclass(frozen=True)
class ScoreReport:
    scored: int
    skipped: int


@dataclass(frozen=True)
class ScoreRunEligibility:
    eligible: bool
    reason: str | None = None


def inspect_score_k_run(run_dir: Path) -> ScoreRunEligibility:
    if not run_dir.exists():
        return ScoreRunEligibility(eligible=False, reason="missing_run_dir")
    has_summary = (run_dir / "summary.json.gz").exists() or (run_dir / "summary.json").exists()
    if not has_summary:
        return ScoreRunEligibility(eligible=False, reason="missing_summary")
    return ScoreRunEligibility(eligible=True)


def score_k_for_run(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_key: str,
    run_dir: Path,
    ref_id: str,
) -> ScoreReport:
    ref_row = conn.execute(
        "SELECT artifact_path FROM lake_references WHERE ref_id = ? AND kind = ?",
        [ref_id, "goal_outcomes"],
    ).fetchone()
    if ref_row is None or not isinstance(ref_row[0], str):
        raise ValueError(f"Unknown reference id: {ref_id}")
    reference = _load_reference(Path(ref_row[0]))

    # A goal cache only adds signatures for steps whose trace lacks them, so runs
    # without one are still scored from their traces.
    gz = run_dir / "goal_cache.json.gz"
    plain = run_dir / "goal_cache.json"
    mvar_to_sig: dict[str, str] | None = None
    if gz.exists():
        mvar_to_sig = read_json_gz(gz)["mvar_to_sig"]
    elif plain.exists():
        mvar_to_sig = read_json(plain)["mvar_to_sig"]

    scored = 0
    skipped = 0
    summary_gz = run_dir / "summary.json.gz"
    summary_json = run_dir / "summary.json"
    if summary_gz.exists():
        summary = read_json_gz(summary_gz)
    elif summary_json.exists():
        summary = read_json(summary_json)
    else:
        # Basin-only runs intentionally omit summary files; skip K scoring for those runs.
        return ScoreReport(scored=0, skipped=1)
    theorems = summary.get("theorems", []) if isinstance(summary, dict) else []
    if not isinstance(theorems, list):
        return ScoreReport(scored=0, skipped=0)

    # Replace all scores for this run/reference.
    conn.execute(
        "DELETE FROM k_reference_score WHERE run_key = ? AND ref_id = ?",
        [run_key, ref_id],
    )

    for t in theorems:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not isinstance(name, str) or not name:
            continue
        theorem_dir = run_dir / name
        if not theorem_dir.exists():
            continue

        # Wild type.
        k = compute_k_reference_from_variant(
            theorem_dir=theorem_dir,
            variant="wild_type",
            mvar_to_sig=mvar_to_sig,
            reference=reference,
        )
        _insert_k_score(conn, run_key, name, "wild_type", ref_id, k)
        scored += 1 if k.get("valid") is True else 0
        skipped += 0 if k.get("valid") is True else 1

        interventions = t.get("interventions", [])
        if not isinstance(interventions, list):
            continue
        for inv in interventions:
            if not isinstance(inv, dict):
                continue
            vname = inv.get("name")
            if not isinstance(vname, str) or not vname:
                continue
            k = compute_k_reference_from_variant(
                theorem_dir=theorem_dir,
                variant=vname,
                mvar_to_sig=mvar_to_sig,
                reference=reference,
            )
            _insert_k_score(conn, run_key, name, vname, ref_id, k)
            scored += 1 if k.get("valid") is True else 0
            skipped += 0 if k.get("valid") is True else 1

    return ScoreReport(scored=scored, skipped=skipped)


def _insert_k_score(
    conn: duckdb.DuckDBPyConnection,
    run_key: str,
    theorem: str,
    variant: str,
    ref_id: str,
    entry: dict[str, Any],
) -> None:
    valid = entry.get("valid") if isinstance(entry.get("valid"), bool) else None
    primary_raw = entry.get("primary")
    primary = primary_raw if isinstance(primary_raw, dict) else {}
    null_model = primary.get("null_model") if isinstance(primary.get("null_model"), str) else None
    tau_agent = entry.get("tau_agent") if isinstance(entry.get("tau_agent"), int) else None
    tau_blind = primary.get("tau_blind")
    K = primary.get("K")
    tb = float(tau_blind) if isinstance(tau_blind, (int, float)) else None
    kk = float(K) if isinstance(K, (int, float)) else None

    conn.execute(
        """
        INSERT INTO k_reference_score(
          run_key, theorem, variant, ref_id,
          valid, primary_null_model, tau_agent, tau_blind, K, score_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_key,
            theorem,
            variant,
            ref_id,
            valid,
            null_model,
            tau_agent,
            tb,
            kk,
            json.dumps(entry),
        ],
    )
