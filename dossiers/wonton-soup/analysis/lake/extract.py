from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.logs import inspect_run_artifacts, read_json, read_json_auto, read_json_gz
from prover.providers.base import tactic_family


def _read_summary(run_dir: Path, *, summary_path: Path | None = None) -> dict[str, Any]:
    resolved_summary_path = summary_path
    if resolved_summary_path is None:
        resolved_summary_path = inspect_run_artifacts(run_dir).summary_path
    if resolved_summary_path is None:
        raise FileNotFoundError(f"No summary.json(.gz) in {run_dir}")
    data = read_json_auto(resolved_summary_path)
    if not isinstance(data, dict):
        raise ValueError("summary must be a dict")
    return data


def _as_bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    return int(v) if isinstance(v, int) else None


def _as_float(v: Any) -> float | None:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return float(v)


def _ged_value(entry: Any) -> tuple[float | None, float | None]:
    if not isinstance(entry, dict):
        return None, None
    value = entry.get("value")
    norm = entry.get("normalized")
    v = float(value) if isinstance(value, (int, float)) else None
    n = float(norm) if isinstance(norm, (int, float)) else None
    return v, n


def _ged_detail(entry: Any) -> tuple[
    float | None,
    float | None,
    bool | None,
    str | None,
    str | None,
]:
    if not isinstance(entry, dict):
        return None, None, None, None, None
    value, norm = _ged_value(entry)
    valid = _as_bool(entry.get("valid"))
    trace_source = entry.get("trace_source") if isinstance(entry.get("trace_source"), str) else None
    trace_comp = (
        entry.get("trace_completeness")
        if isinstance(entry.get("trace_completeness"), str)
        else None
    )
    return value, norm, valid, trace_source, trace_comp


def _k_primary(
    entry: Any,
) -> tuple[bool | None, str | None, int | None, float | None, float | None]:
    if not isinstance(entry, dict):
        return None, None, None, None, None
    valid = entry.get("valid")
    primary = entry.get("primary")
    if not isinstance(primary, dict):
        return _as_bool(valid), None, _as_int(entry.get("tau_agent")), None, None
    null_model = primary.get("null_model") if isinstance(primary.get("null_model"), str) else None
    tau_agent = _as_int(entry.get("tau_agent"))
    tau_blind = primary.get("tau_blind")
    K = primary.get("K")
    tb = float(tau_blind) if isinstance(tau_blind, (int, float)) else None
    kk = float(K) if isinstance(K, (int, float)) else None
    return _as_bool(valid), null_model, tau_agent, tb, kk


@dataclass(frozen=True)
class ExtractReport:
    runs_extracted: int
    wild_rows: int
    intervention_rows: int
    outcome_rows: int
    errors: list[str]


def _delete_summary_tables(
    conn: duckdb.DuckDBPyConnection, *, run_key: str, with_goal_outcomes: bool
) -> None:
    conn.execute("DELETE FROM theorem_wild WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM theorem_intervention WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM theorem_intervention_postprocess WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM theorem_variant_metrics WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM theorem_intervention_comparison WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM run_aggregates WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM goal_type_tactic WHERE run_key = ?", [run_key])
    conn.execute("DELETE FROM run_postprocess WHERE run_key = ?", [run_key])
    if with_goal_outcomes:
        conn.execute("DELETE FROM goal_outcome_global_family WHERE run_key = ?", [run_key])
        conn.execute("DELETE FROM goal_outcome_sig_family WHERE run_key = ?", [run_key])


def _clear_summary_tables(
    conn: duckdb.DuckDBPyConnection, *, run_key: str, with_goal_outcomes: bool
) -> None:
    conn.begin()
    try:
        _delete_summary_tables(conn, run_key=run_key, with_goal_outcomes=with_goal_outcomes)
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def _iter_goal_outcome_rows(
    goal_cache: dict[str, Any],
) -> tuple[list[tuple[int, int, int]], list[tuple[str, int, int, int]]]:
    """Return (global_rows, sig_rows).

    global_rows: (family_idx, attempts, successes)
    sig_rows: (sig, family_idx, attempts, successes)
    """

    entries = goal_cache.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError("goal_cache.entries must be a dict")

    global_attempts: dict[int, int] = {}
    global_successes: dict[int, int] = {}
    sig_attempts: dict[tuple[str, int], int] = {}
    sig_successes: dict[tuple[str, int], int] = {}

    for sig, entry in entries.items():
        if not isinstance(sig, str) or not isinstance(entry, dict):
            continue
        occurrences = entry.get("occurrences", {})
        if not isinstance(occurrences, dict):
            continue
        for occ in occurrences.values():
            if not isinstance(occ, dict):
                continue
            outcomes = occ.get("outcomes", {})
            if not isinstance(outcomes, dict):
                continue
            for fam_key, vals in outcomes.items():
                try:
                    fam_idx = int(fam_key)
                except (TypeError, ValueError):
                    continue
                if not isinstance(vals, list):
                    continue
                attempts = len(vals)
                if attempts <= 0:
                    continue
                successes = sum(1 for v in vals if v is True)
                global_attempts[fam_idx] = global_attempts.get(fam_idx, 0) + attempts
                global_successes[fam_idx] = global_successes.get(fam_idx, 0) + successes
                key = (sig, fam_idx)
                sig_attempts[key] = sig_attempts.get(key, 0) + attempts
                sig_successes[key] = sig_successes.get(key, 0) + successes

    global_rows: list[tuple[int, int, int]] = []
    for fam_idx in sorted(global_attempts.keys()):
        global_rows.append((fam_idx, global_attempts[fam_idx], global_successes.get(fam_idx, 0)))

    sig_rows: list[tuple[str, int, int, int]] = []
    for (sig, fam_idx), attempts in sorted(sig_attempts.items(), key=lambda t: (t[0][0], t[0][1])):
        sig_rows.append((sig, fam_idx, attempts, sig_successes.get((sig, fam_idx), 0)))

    return global_rows, sig_rows


def extract_facts(
    conn: duckdb.DuckDBPyConnection,
    *,
    root_dir: Path,
    run_rows: list[tuple[str, str]],  # (run_key, rel_run_dir)
    with_goal_outcomes: bool = True,
) -> ExtractReport:
    errors: list[str] = []
    runs_extracted = 0
    wild_rows = 0
    intervention_rows = 0
    outcome_rows = 0

    for run_key, rel in run_rows:
        run_dir = (root_dir / rel).resolve()
        artifacts = inspect_run_artifacts(run_dir)
        try:
            summary = _read_summary(run_dir, summary_path=artifacts.summary_path)
        except Exception as exc:
            _clear_summary_tables(conn, run_key=run_key, with_goal_outcomes=with_goal_outcomes)
            if artifacts.is_basin_only:
                continue
            conn.execute(
                "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                [run_key, "read_summary", f"{type(exc).__name__}: {exc}"],
            )
            errors.append(f"{rel}: read_summary: {type(exc).__name__}: {exc}")
            continue

        aggregates = summary.get("aggregates", {})
        if aggregates is None:
            aggregates = {}
        if not isinstance(aggregates, dict):
            conn.execute(
                "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                [run_key, "schema", "summary.aggregates must be an object"],
            )
            errors.append(f"{rel}: schema: summary.aggregates must be an object")
            aggregates = {}

        theorems = summary.get("theorems", [])
        if not isinstance(theorems, list):
            _clear_summary_tables(conn, run_key=run_key, with_goal_outcomes=with_goal_outcomes)
            conn.execute(
                "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                [run_key, "schema", "summary.theorems must be a list"],
            )
            errors.append(f"{rel}: schema: summary.theorems must be a list")
            continue

        # Atomic upsert: delete+insert in a single transaction to avoid partial state on crash.
        conn.begin()
        _delete_summary_tables(conn, run_key=run_key, with_goal_outcomes=with_goal_outcomes)

        # Run-level aggregates.
        theorem_count = aggregates.get("theorem_count")
        crashed_count = aggregates.get("crashed_count")
        wild_rate = aggregates.get("wild_type_solve_rate")
        inv_count = aggregates.get("intervention_count")
        inv_rate = aggregates.get("intervention_solve_rate")
        ged_validity = aggregates.get("ged_validity")
        conn.execute(
            """
            INSERT INTO run_aggregates(
              run_key, theorem_count, crashed_count,
              wild_type_solve_rate, intervention_count, intervention_solve_rate,
              ged_validity, aggregates_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_key,
                int(theorem_count) if isinstance(theorem_count, int) else None,
                int(crashed_count) if isinstance(crashed_count, int) else None,
                float(wild_rate) if isinstance(wild_rate, (int, float)) else None,
                int(inv_count) if isinstance(inv_count, int) else None,
                float(inv_rate) if isinstance(inv_rate, (int, float)) else None,
                json.dumps(ged_validity) if isinstance(ged_validity, dict) else None,
                json.dumps(aggregates) if aggregates else None,
            ],
        )

        # Goal-type x tactic matrix.
        matrix = aggregates.get("goal_type_tactic_matrix")
        if isinstance(matrix, dict):
            for goal_type, tactics in matrix.items():
                if not isinstance(goal_type, str) or not isinstance(tactics, dict):
                    continue
                for tactic_norm, outcomes in tactics.items():
                    if not isinstance(tactic_norm, str) or not isinstance(outcomes, dict):
                        continue
                    success = outcomes.get("success")
                    failure = outcomes.get("failure")
                    blocked = outcomes.get("blocked")
                    s = int(success) if isinstance(success, int) else 0
                    f = int(failure) if isinstance(failure, int) else 0
                    b = int(blocked) if isinstance(blocked, int) else 0
                    total = s + f + b
                    conn.execute(
                        """
                        INSERT INTO goal_type_tactic(
                          run_key, goal_type, tactic_norm, tactic_family,
                          success, failure, blocked, total
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            run_key,
                            goal_type,
                            tactic_norm,
                            tactic_family(tactic_norm),
                            s,
                            f,
                            b,
                            total,
                        ],
                    )

        # Postprocess report (root-level for multi-provider runs).
        postprocess_path = run_dir / "postprocess_metrics.json"
        if not postprocess_path.exists() and run_dir.name.startswith("provider="):
            postprocess_path = run_dir.parent / "postprocess_metrics.json"
        if postprocess_path.exists():
            try:
                post = read_json(postprocess_path)
            except Exception as exc:
                conn.execute(
                    "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                    [run_key, "read_postprocess", f"{type(exc).__name__}: {exc}"],
                )
                errors.append(f"{rel}: read_postprocess: {type(exc).__name__}: {exc}")
                post = None
            if isinstance(post, dict):
                conn.execute(
                    """
                    INSERT INTO run_postprocess(
                      run_key, valid, computed_at, params, inputs, metrics, runs, report_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_key,
                        _as_bool(post.get("valid")),
                        post.get("computed_at")
                        if isinstance(post.get("computed_at"), str)
                        else None,
                        json.dumps(post.get("params"))
                        if isinstance(post.get("params"), dict)
                        else None,
                        json.dumps(post.get("inputs"))
                        if isinstance(post.get("inputs"), dict)
                        else None,
                        json.dumps(post.get("metrics"))
                        if isinstance(post.get("metrics"), dict)
                        else None,
                        json.dumps(post.get("runs"))
                        if isinstance(post.get("runs"), list)
                        else None,
                        json.dumps(post),
                    ],
                )

        for t in theorems:
            if not isinstance(t, dict):
                continue
            theorem = t.get("name")
            if not isinstance(theorem, str) or not theorem:
                continue
            theorem_dir = run_dir / theorem
            # Variant metrics are stored per theorem directory.
            if theorem_dir.exists():
                inv_names: list[str] = []
                interventions_raw = t.get("interventions", [])
                if isinstance(interventions_raw, list):
                    for inv in interventions_raw:
                        if not isinstance(inv, dict):
                            continue
                        name = inv.get("name")
                        if isinstance(name, str) and name:
                            inv_names.append(name)

                for variant in ["wild_type", *inv_names]:
                    metrics_path = theorem_dir / f"{variant}_metrics.json"
                    if not metrics_path.exists():
                        continue
                    try:
                        metrics = read_json(metrics_path)
                    except Exception as exc:
                        conn.execute(
                            "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                            [run_key, "read_variant_metrics", f"{type(exc).__name__}: {exc}"],
                        )
                        errors.append(
                            f"{rel}: read_variant_metrics: {theorem}/{variant}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        continue
                    if not isinstance(metrics, dict):
                        continue

                    traj = (
                        metrics.get("trajectory")
                        if isinstance(metrics.get("trajectory"), dict)
                        else {}
                    )
                    det = metrics.get("detour") if isinstance(metrics.get("detour"), dict) else {}
                    pt = (
                        metrics.get("proof_term")
                        if isinstance(metrics.get("proof_term"), dict)
                        else {}
                    )
                    solution_path = metrics.get("solution_path")
                    sp_len = len(solution_path) if isinstance(solution_path, list) else None

                    # Avoid storing huge strings (e.g., proof_term_pretty) in the lake.
                    sanitized = dict(metrics)
                    if "proof_term_pretty" in sanitized:
                        sanitized["proof_term_pretty"] = None

                    conn.execute(
                        """
                        INSERT INTO theorem_variant_metrics(
                          run_key, theorem, variant,
                          trajectory_total_iterations,
                          trajectory_backtrack_count,
                          trajectory_max_depth_reached,
                          trajectory_depth_at_solution,
                          trajectory_unique_goals_visited,
                          trajectory_tactic_diversity,
                          detour_total_iterations,
                          detour_total_attempts,
                          detour_success_count,
                          detour_failure_count,
                          detour_blocked_count,
                          detour_failure_ratio,
                          detour_max_depth,
                          detour_depth_at_solution,
                          detour_terminal_iteration,
                          proof_term_node_count,
                          proof_term_depth,
                          proof_term_width,
                          solution_path_len,
                          tactic_fingerprint,
                          root_goal_sigs,
                          metrics_json
                        )
                        VALUES (
                          ?, ?, ?,
                          ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        [
                            run_key,
                            theorem,
                            variant,
                            _as_int(traj.get("total_iterations")),
                            _as_int(traj.get("backtrack_count")),
                            _as_int(traj.get("max_depth_reached")),
                            _as_int(traj.get("depth_at_solution")),
                            _as_int(traj.get("unique_goals_visited")),
                            _as_int(traj.get("tactic_diversity")),
                            _as_int(det.get("total_iterations")),
                            _as_int(det.get("total_attempts")),
                            _as_int(det.get("success_count")),
                            _as_int(det.get("failure_count")),
                            _as_int(det.get("blocked_count")),
                            _as_float(det.get("failure_ratio")),
                            _as_int(det.get("max_depth")),
                            _as_int(det.get("depth_at_solution")),
                            _as_int(det.get("terminal_iteration")),
                            _as_int(pt.get("node_count")),
                            _as_int(pt.get("depth")),
                            _as_int(pt.get("width")),
                            int(sp_len) if isinstance(sp_len, int) else None,
                            metrics.get("tactic_fingerprint")
                            if isinstance(metrics.get("tactic_fingerprint"), str)
                            else None,
                            json.dumps(metrics.get("root_goal_sigs"))
                            if isinstance(metrics.get("root_goal_sigs"), list)
                            else None,
                            json.dumps(sanitized),
                        ],
                    )

            wild = t.get("wild_type")
            if isinstance(wild, dict):
                solved = _as_bool(wild.get("solved"))
                iterations = _as_int(wild.get("iterations"))
                proof_term_raw = wild.get("proof_term_hash")
                proof_term_hash = proof_term_raw if isinstance(proof_term_raw, str) else None
                k_entry = wild.get("k_search_efficiency")
                k_valid, k_null, k_tau_agent, k_tau_blind, k_K = _k_primary(k_entry)
                metrics = wild.get("metrics") if isinstance(wild.get("metrics"), dict) else None
                conn.execute(
                    """
                    INSERT INTO theorem_wild(
                      run_key, theorem, solved, iterations, proof_term_hash,
                      k_valid, k_null_model, k_tau_agent, k_tau_blind, k_K,
                      metrics, k_json, wild_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_key,
                        theorem,
                        solved,
                        iterations,
                        proof_term_hash,
                        k_valid,
                        k_null,
                        k_tau_agent,
                        k_tau_blind,
                        k_K,
                        json.dumps(metrics) if metrics is not None else None,
                        json.dumps(k_entry) if isinstance(k_entry, dict) else None,
                        json.dumps(wild),
                    ],
                )
                wild_rows += 1

            interventions = t.get("interventions", [])
            if not isinstance(interventions, list):
                continue
            for inv in interventions:
                if not isinstance(inv, dict):
                    continue
                name = inv.get("name")
                if not isinstance(name, str) or not name:
                    continue

                # Comparison artifact (optional, but preferred for semantic-ish proxies).
                if theorem_dir.exists():
                    comp_path = theorem_dir / f"{name}_comparison.json"
                    if comp_path.exists():
                        try:
                            comp = read_json(comp_path)
                        except Exception as exc:
                            conn.execute(
                                "INSERT INTO extract_errors(run_key, stage, error) "
                                "VALUES (?, ?, ?)",
                                [run_key, "read_comparison", f"{type(exc).__name__}: {exc}"],
                            )
                            errors.append(
                                f"{rel}: read_comparison: {theorem}/{name}: "
                                f"{type(exc).__name__}: {exc}"
                            )
                            comp = None
                        if isinstance(comp, dict):
                            blocked_list = (
                                comp.get("blocked")
                                if isinstance(comp.get("blocked"), list)
                                else None
                            )
                            td = (
                                comp.get("trajectory_diff")
                                if isinstance(comp.get("trajectory_diff"), dict)
                                else {}
                            )
                            iter_diff = td.get("iteration_diff")
                            bt_diff = td.get("backtrack_diff")
                            ax_delta = comp.get("axiom_delta")
                            ax_removed = comp.get("axiom_removed")

                            (gs_v, gs_n, gs_valid, gs_source, gs_comp) = _ged_detail(
                                comp.get("ged_search_graph")
                            )
                            (gss_v, gss_n, gss_valid, gss_source, gss_comp) = _ged_detail(
                                comp.get("ged_search_graph_soft")
                            )
                            (gp_v, gp_n, gp_valid, gp_source, gp_comp) = _ged_detail(
                                comp.get("ged_proof_graph")
                            )
                            (gt_v, gt_n, gt_valid, gt_source, gt_comp) = _ged_detail(
                                comp.get("ged_trace_graph")
                            )

                            conn.execute(
                                """
                                INSERT INTO theorem_intervention_comparison(
                                  run_key, theorem, intervention,
                                  solved, status, blocked,
                                  wild_type_hash, intervention_hash, hash_mismatch,
                                  axiom_delta_count, axiom_removed_count,
                                  trajectory_iteration_diff, trajectory_backtrack_diff,
                                  ged_search_value, ged_search_norm, ged_search_valid,
                                  ged_search_trace_source, ged_search_trace_completeness,
                                  ged_search_soft_value, ged_search_soft_norm,
                                  ged_search_soft_valid,
                                  ged_search_soft_trace_source, ged_search_soft_trace_completeness,
                                  ged_proof_value, ged_proof_norm, ged_proof_valid,
                                  ged_proof_trace_source, ged_proof_trace_completeness,
                                  ged_trace_value, ged_trace_norm, ged_trace_valid,
                                  ged_trace_trace_source, ged_trace_trace_completeness,
                                  comparison_json
                                ) VALUES (
                                  ?, ?, ?,
                                  ?, ?, ?,
                                  ?, ?, ?,
                                  ?, ?,
                                  ?, ?,
                                  ?, ?, ?, ?, ?,
                                  ?, ?, ?, ?, ?,
                                  ?, ?, ?, ?, ?,
                                  ?, ?, ?, ?, ?,
                                  ?
                                )
                                """,
                                [
                                    run_key,
                                    theorem,
                                    name,
                                    _as_bool(comp.get("solved")),
                                    comp.get("status")
                                    if isinstance(comp.get("status"), str)
                                    else None,
                                    json.dumps(blocked_list) if blocked_list is not None else None,
                                    comp.get("wild_type_hash")
                                    if isinstance(comp.get("wild_type_hash"), str)
                                    else None,
                                    comp.get("intervention_hash")
                                    if isinstance(comp.get("intervention_hash"), str)
                                    else None,
                                    _as_bool(comp.get("hash_mismatch")),
                                    len(ax_delta) if isinstance(ax_delta, list) else None,
                                    len(ax_removed) if isinstance(ax_removed, list) else None,
                                    int(iter_diff) if isinstance(iter_diff, int) else None,
                                    int(bt_diff) if isinstance(bt_diff, int) else None,
                                    gs_v,
                                    gs_n,
                                    gs_valid,
                                    gs_source,
                                    gs_comp,
                                    gss_v,
                                    gss_n,
                                    gss_valid,
                                    gss_source,
                                    gss_comp,
                                    gp_v,
                                    gp_n,
                                    gp_valid,
                                    gp_source,
                                    gp_comp,
                                    gt_v,
                                    gt_n,
                                    gt_valid,
                                    gt_source,
                                    gt_comp,
                                    json.dumps(comp),
                                ],
                            )
                solved = _as_bool(inv.get("solved"))
                status = inv.get("status") if isinstance(inv.get("status"), str) else None
                is_control = _as_bool(inv.get("is_control"))
                baseline_solved = _as_bool(inv.get("baseline_solved"))
                blocked = inv.get("blocked") if isinstance(inv.get("blocked"), list) else None

                ged_search_value, ged_search_norm = _ged_value(inv.get("ged_search_graph"))
                soft_value, soft_norm = _ged_value(inv.get("ged_search_graph_soft"))

                k_entry = inv.get("k_search_efficiency")
                k_valid, k_null, k_tau_agent, k_tau_blind, k_K = _k_primary(k_entry)

                metrics = inv.get("metrics") if isinstance(inv.get("metrics"), dict) else None
                conn.execute(
                    """
                    INSERT INTO theorem_intervention(
                      run_key, theorem, intervention,
                      solved, status, is_control, baseline_solved, blocked,
                      ged_search_value, ged_search_norm,
                      ged_search_soft_value, ged_search_soft_norm,
                      k_valid, k_null_model, k_tau_agent, k_tau_blind, k_K,
                      metrics, k_json, intervention_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_key,
                        theorem,
                        name,
                        solved,
                        status,
                        is_control,
                        baseline_solved,
                        json.dumps(blocked) if blocked is not None else None,
                        ged_search_value,
                        ged_search_norm,
                        soft_value,
                        soft_norm,
                        k_valid,
                        k_null,
                        k_tau_agent,
                        k_tau_blind,
                        k_K,
                        json.dumps(metrics) if metrics is not None else None,
                        json.dumps(k_entry) if isinstance(k_entry, dict) else None,
                        json.dumps(inv),
                    ],
                )
                intervention_rows += 1

                # Postprocess-derived convenience scalars.
                novelty = inv.get("goal_novelty")
                solution_dist = inv.get("solution_path_soft_distance")
                novelty_novel = None
                novelty_dropped = None
                if isinstance(novelty, dict):
                    a = novelty.get("novel_goal_count")
                    d = novelty.get("dropped_goal_count")
                    novelty_novel = int(a) if isinstance(a, int) else None
                    novelty_dropped = int(d) if isinstance(d, int) else None

                sp_value = None
                sp_valid = None
                sp_wild_len = None
                sp_int_len = None
                sp_dp_cells = None
                if isinstance(solution_dist, dict):
                    sp_value_raw = solution_dist.get("value")
                    sp_value = (
                        float(sp_value_raw) if isinstance(sp_value_raw, (int, float)) else None
                    )
                    sp_valid = _as_bool(solution_dist.get("valid"))
                    wl = solution_dist.get("wild_len")
                    il = solution_dist.get("intervention_len")
                    dp = solution_dist.get("dp_cells")
                    sp_wild_len = int(wl) if isinstance(wl, int) else None
                    sp_int_len = int(il) if isinstance(il, int) else None
                    sp_dp_cells = int(dp) if isinstance(dp, int) else None

                if novelty is not None or solution_dist is not None:
                    conn.execute(
                        """
                        INSERT INTO theorem_intervention_postprocess(
                          run_key, theorem, intervention,
                          goal_novelty_novel_goal_count, goal_novelty_dropped_goal_count,
                          solution_path_soft_distance_value, solution_path_soft_distance_valid,
                          solution_path_soft_distance_wild_len,
                          solution_path_soft_distance_intervention_len,
                          solution_path_soft_distance_dp_cells,
                          raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            run_key,
                            theorem,
                            name,
                            novelty_novel,
                            novelty_dropped,
                            sp_value,
                            sp_valid,
                            sp_wild_len,
                            sp_int_len,
                            sp_dp_cells,
                            json.dumps(
                                {
                                    "goal_novelty": novelty,
                                    "solution_path_soft_distance": solution_dist,
                                }
                            ),
                        ],
                    )

        if with_goal_outcomes:
            goal_cache = None
            try:
                if (run_dir / "goal_cache.json.gz").exists():
                    goal_cache = read_json_gz(run_dir / "goal_cache.json.gz")
                elif (run_dir / "goal_cache.json").exists():
                    goal_cache = read_json(run_dir / "goal_cache.json")
            except Exception as exc:
                conn.execute(
                    "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                    [run_key, "read_goal_cache", f"{type(exc).__name__}: {exc}"],
                )
                errors.append(f"{rel}: read_goal_cache: {type(exc).__name__}: {exc}")
                goal_cache = None
            if isinstance(goal_cache, dict):
                try:
                    global_rows, sig_rows = _iter_goal_outcome_rows(goal_cache)
                except Exception as exc:
                    conn.execute(
                        "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                        [run_key, "goal_outcomes", f"{type(exc).__name__}: {exc}"],
                    )
                    errors.append(f"{rel}: goal_outcomes: {type(exc).__name__}: {exc}")
                    global_rows, sig_rows = [], []
                for fam_idx, attempts, successes in global_rows:
                    conn.execute(
                        """
                        INSERT INTO goal_outcome_global_family(
                          run_key, family_idx, attempts, successes
                        ) VALUES (?, ?, ?, ?)
                        """,
                        [run_key, fam_idx, attempts, successes],
                    )
                    outcome_rows += 1
                for sig, fam_idx, attempts, successes in sig_rows:
                    conn.execute(
                        """
                        INSERT INTO goal_outcome_sig_family(
                          run_key, goal_sig, family_idx, attempts, successes
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        [run_key, sig, fam_idx, attempts, successes],
                    )
                    outcome_rows += 1

        conn.commit()
        runs_extracted += 1

    return ExtractReport(
        runs_extracted=runs_extracted,
        wild_rows=wild_rows,
        intervention_rows=intervention_rows,
        outcome_rows=outcome_rows,
        errors=errors,
    )
