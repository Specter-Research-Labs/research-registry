from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.logs import (
    extract_solution_steps,
    family_index,
    read_json,
    read_json_gz,
)
from prover.k import k_log10_ratio
from prover.providers.base import normalize_tactic, tactic_family


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


def _p_success(reference: dict[str, Any], sig: str, fam_idx: int) -> float | None:
    alpha = reference.get("alpha")
    if not isinstance(alpha, (int, float)) or float(alpha) <= 0:
        return None
    alpha = float(alpha)
    global_entry = reference.get("global", {})
    by_sig = reference.get("by_sig", {})
    if not isinstance(global_entry, dict) or not isinstance(by_sig, dict):
        return None

    def _get_counts(entry: dict[str, Any]) -> tuple[int, int] | None:
        a = entry.get("attempts")
        s = entry.get("successes")
        if not isinstance(a, list) or not isinstance(s, list):
            return None
        if fam_idx < 0 or fam_idx >= len(a) or fam_idx >= len(s):
            return None
        att = a[fam_idx]
        suc = s[fam_idx]
        if not isinstance(att, int) or not isinstance(suc, int):
            return None
        return att, suc

    entry = by_sig.get(sig)
    counts = _get_counts(entry) if isinstance(entry, dict) else None
    if counts is None or counts[0] <= 0:
        counts = _get_counts(global_entry) if isinstance(global_entry, dict) else None
    if counts is None:
        return None
    attempts, successes = counts
    return (successes + alpha) / (attempts + 2 * alpha)


def compute_k_reference_from_variant(
    *,
    theorem_dir: Path,
    variant: str,
    goal_cache: dict[str, Any] | None,
    reference: dict[str, Any],
) -> dict[str, Any]:
    mvar_to_sig = None
    if isinstance(goal_cache, dict):
        mts = goal_cache.get("mvar_to_sig")
        mvar_to_sig = mts if isinstance(mts, dict) else None

    ext = extract_solution_steps(
        theorem_dir=theorem_dir,
        variant=variant,
        mvar_to_sig=mvar_to_sig,
    )
    if not ext.valid:
        return {
            "schema_version": 1,
            "valid": False,
            "validity_notes": ext.validity_notes,
        }

    notes = list(ext.validity_notes)
    assert ext.tau_agent is not None
    tau_agent = ext.tau_agent
    step_specs = ext.step_specs
    expected_steps = ext.expected_steps
    dropped_steps = ext.dropped_steps
    candidates_by_iter = ext.candidates_by_iter

    def _mean(values: list[float]) -> float | None:
        return (sum(values) / len(values)) if values else None

    def compute_totals(*, metric: str) -> tuple[float | None, list[str]]:
        tau_blind = 0.0
        local_notes: list[str] = []
        for spec in step_specs:
            it = spec["iteration"]
            sig = spec["goal_sig"]
            used_fam = spec["tactic_family"]
            candidates = candidates_by_iter.get(it)
            if not candidates:
                local_notes.append(f"missing_candidates: iteration={it}")
                return None, local_notes
            fams = [tactic_family(normalize_tactic(c)) for c in candidates]
            if not fams:
                local_notes.append(f"empty_candidates: iteration={it}")
                return None, local_notes

            probs = []
            for fam in fams:
                p = _p_success(reference, sig, family_index(fam))
                if p is None:
                    continue
                probs.append(p)
            p_step = _mean(probs)
            if metric == "used_operator":
                used_count = sum(1 for fam in fams if fam == used_fam)
                if used_count <= 0:
                    local_notes.append(f"used_family_missing_from_candidates: iteration={it}")
                    return None, local_notes
                p_used = _p_success(reference, sig, family_index(used_fam))
                if p_used is None:
                    local_notes.append(f"missing_used_family_prob: iteration={it}")
                    return None, local_notes
                p_step = (used_count / len(fams)) * p_used

            if p_step is None or p_step <= 0:
                local_notes.append(f"invalid_step_probability: iteration={it} p={p_step!r}")
                return None, local_notes
            tau_blind += 1.0 / p_step
        return tau_blind, local_notes

    variants: dict[str, dict[str, dict[str, Any]]] = {"any_success": {}, "used_operator": {}}
    for metric in ("any_success", "used_operator"):
        tau_blind, local_notes = compute_totals(metric=metric)
        if tau_blind is None:
            variants[metric]["blind_uniform_candidate"] = {
                "tau_blind": None,
                "K": None,
                "valid": False,
                "validity_notes": local_notes,
            }
            continue
        k_value = k_log10_ratio(tau_blind=tau_blind, tau_agent=tau_agent)
        variants[metric]["blind_uniform_candidate"] = {
            "tau_blind": round(float(tau_blind), 6),
            "K": round(float(k_value), 6) if k_value is not None else None,
            "valid": k_value is not None,
            "validity_notes": local_notes,
        }

    primary = variants["any_success"]["blind_uniform_candidate"]
    complete = expected_steps == len(step_specs)
    return {
        "schema_version": 1,
        "valid": bool(primary.get("valid")) and complete,
        "validity_notes": notes,
        "reference_kind": "goal_outcomes",
        "w_unit": "tactic_attempt",
        "tau_agent": int(tau_agent),
        "primary": {
            "metric": "any_success",
            "null_model": "blind_uniform_candidate",
            "tau_blind": primary.get("tau_blind"),
            "K": primary.get("K"),
        },
        "variants": variants,
        "steps": {
            "count": len(step_specs),
            "expected": expected_steps,
            "dropped": dropped_steps,
        },
    }


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

    goal_cache = None
    try:
        gz = run_dir / "goal_cache.json.gz"
        plain = run_dir / "goal_cache.json"
        if gz.exists():
            goal_cache = read_json_gz(gz)
        elif plain.exists():
            goal_cache = read_json(plain)
    except Exception:
        goal_cache = None

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
            goal_cache=goal_cache,
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
                goal_cache=goal_cache,
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
    primary = entry.get("primary") if isinstance(entry.get("primary"), dict) else {}
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
