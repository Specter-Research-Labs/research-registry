from __future__ import annotations

from pathlib import Path
from typing import Any

from analysis.logs import ged_value, read_json_auto


def _ged_family_value(intervention: Any, key: str) -> float | None:
    if not isinstance(intervention, dict):
        return None
    return ged_value(intervention.get(key))


def build_theorem_details(
    theorems: list[dict[str, Any]],
    run_dir: Path,
    *,
    max_history_steps: int = 80,
    max_tree_nodes: int = 400,
) -> list[dict[str, Any]]:
    if not theorems:
        return []

    ged_lookup = _load_ged_matrices(run_dir)
    details = []

    for entry in theorems:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        wild = entry.get("wild_type", {})
        metrics = wild.get("metrics", {}) if isinstance(wild, dict) else {}

        detail: dict[str, Any] = {"name": name}

        solved = wild.get("solved") if isinstance(wild, dict) else None
        if isinstance(solved, bool):
            detail["status"] = "Solved" if solved else "Failed"

        iterations = wild.get("iterations") if isinstance(wild, dict) else None
        if not isinstance(iterations, (int, float)):
            trajectory = metrics.get("trajectory", {}) if isinstance(metrics, dict) else {}
            iterations = trajectory.get("total_iterations")
        if isinstance(iterations, (int, float)):
            detail["iterations"] = iterations

        mean_ged_search = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_search_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )
        mean_ged_proof = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_proof_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )
        mean_ged_trace = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_trace_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )
        if mean_ged_search is not None:
            detail["mean_ged"] = mean_ged_search
        detail["mean_ged_search_graph"] = _optional_float(mean_ged_search)
        detail["mean_ged_proof_graph"] = _optional_float(mean_ged_proof)
        detail["mean_ged_trace_graph"] = _optional_float(mean_ged_trace)

        matrix_entry = ged_lookup.get(name)
        if matrix_entry:
            variants = matrix_entry.get("variants")
            if isinstance(variants, list):
                detail["variants"] = variants
            matrix = matrix_entry.get("ged_matrix")
            if isinstance(variants, list):
                normalized = _normalize_ged_matrix(variants, matrix)
                if normalized is not None:
                    detail["ged_matrix"] = normalized
        else:
            matrix_path = run_dir / name / "ged_matrix.json"
            if matrix_path.exists():
                matrix_data = read_json_auto(matrix_path)
                if isinstance(matrix_data, dict):
                    variants = matrix_data.get("variants")
                    if isinstance(variants, list):
                        detail["variants"] = variants
                    matrix = matrix_data.get("ged_matrix")
                    if isinstance(variants, list):
                        normalized = _normalize_ged_matrix(variants, matrix)
                        if normalized is not None:
                            detail["ged_matrix"] = normalized

        history_path = run_dir / name / "wild_type_history.json"
        history_steps = _load_history_steps(history_path, max_history_steps)
        if history_steps:
            detail["history"] = history_steps

        proof_term = metrics.get("proof_term") if isinstance(metrics, dict) else None
        proof_stats = _proof_term_stats(proof_term)
        if proof_stats:
            detail["proof_term_stats"] = proof_stats

        tree_path = run_dir / name / "wild_type_mcts_tree.json"
        tree_data = _load_mcts_tree(tree_path, max_tree_nodes)
        if tree_data is not None:
            detail["mcts_tree"] = tree_data

        details.append(detail)

    return details


def build_provider_deep_dive(run_dir: Path) -> dict[str, Any] | None:
    summary_path = run_dir / "providers_summary.json"
    providers_summary = read_json_auto(summary_path) if summary_path.exists() else None
    providers = _build_provider_summaries(providers_summary)

    interventions_path = run_dir / "providers_theorem_summary.json"
    interventions_data = (
        read_json_auto(interventions_path) if interventions_path.exists() else None
    )
    interventions = _build_provider_interventions(interventions_data)
    theorem_summary = None
    if isinstance(interventions_data, dict) and isinstance(
        interventions_data.get("theorems"), list
    ):
        theorem_summary = interventions_data

    if not providers and not interventions and theorem_summary is None:
        return None
    return {
        "providers": providers,
        "interventions": interventions,
        "theorem_summary": theorem_summary,
    }


def _mean(values: list[Any]) -> float | None:
    valid = [v for v in values if isinstance(v, (int, float))]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _load_ged_matrices(run_dir: Path) -> dict[str, dict[str, Any]]:
    matrices_path = run_dir / "all_ged_matrices.json"
    if not matrices_path.exists():
        return {}
    data = read_json_auto(matrices_path)
    if not isinstance(data, list):
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("theorem")
        if isinstance(name, str):
            lookup[name] = entry
    return lookup


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _optional_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _build_histogram(values: list[Any], *, bins: int = 12) -> dict[str, list[float]]:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    if not clean:
        return {"bins": [], "counts": []}
    if len(clean) == 1:
        return {"bins": [clean[0]], "counts": [1.0]}
    min_val = min(clean)
    max_val = max(clean)
    if min_val == max_val:
        return {"bins": [min_val], "counts": [float(len(clean))]}
    width = (max_val - min_val) / bins if bins > 0 else max_val - min_val
    if width <= 0:
        width = 1.0
    counts = [0.0 for _ in range(bins)]
    centers = [min_val + width * (idx + 0.5) for idx in range(bins)]
    for value in clean:
        idx = int((value - min_val) / width)
        if idx >= bins:
            idx = bins - 1
        counts[idx] += 1.0
    return {"bins": centers, "counts": counts}


def _build_goal_tactic_heatmap(
    matrix: dict[str, Any] | None,
    *,
    max_rows: int = 12,
    max_cols: int = 10,
) -> dict[str, Any] | None:
    if not matrix or not isinstance(matrix, dict):
        return None
    goal_totals: dict[str, int] = {}
    tactic_totals: dict[str, int] = {}
    for goal, tactics in matrix.items():
        if not isinstance(goal, str) or not isinstance(tactics, dict):
            continue
        for tactic, counts in tactics.items():
            if not isinstance(tactic, str) or not isinstance(counts, dict):
                continue
            total = 0
            for key in ("success", "failure", "blocked"):
                value = counts.get(key)
                if isinstance(value, int):
                    total += value
            if total == 0:
                continue
            goal_totals[goal] = goal_totals.get(goal, 0) + total
            tactic_totals[tactic] = tactic_totals.get(tactic, 0) + total

    if not goal_totals or not tactic_totals:
        return None

    rows = [
        item[0]
        for item in sorted(goal_totals.items(), key=lambda item: item[1], reverse=True)
    ][:max_rows]
    cols = [
        item[0]
        for item in sorted(tactic_totals.items(), key=lambda item: item[1], reverse=True)
    ][:max_cols]

    heat_rows: list[list[float]] = []
    for goal in rows:
        row_values: list[float] = []
        tactics = matrix.get(goal, {})
        for tactic in cols:
            counts = tactics.get(tactic, {}) if isinstance(tactics, dict) else {}
            success = counts.get("success") if isinstance(counts, dict) else None
            failure = counts.get("failure") if isinstance(counts, dict) else None
            blocked = counts.get("blocked") if isinstance(counts, dict) else None
            total = sum(
                value
                for value in (success, failure, blocked)
                if isinstance(value, (int, float))
            )
            value = (success / total) if isinstance(success, (int, float)) and total else 0.0
            row_values.append(float(value))
        heat_rows.append(row_values)

    return {
        "rows": rows,
        "cols": cols,
        "matrix": heat_rows,
        "metric": "success_rate",
    }


def _trajectory_series(history_path: Path) -> dict[str, list[float]] | None:
    if not history_path.exists():
        return None
    data = read_json_auto(history_path)
    if not isinstance(data, dict):
        return None
    iterations = data.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        return None
    depth: list[float] = []
    attempts: list[float] = []
    success_ratio: list[float] = []
    for record in iterations:
        if not isinstance(record, dict):
            continue
        selected_path = record.get("selected_path")
        attempt_list = record.get("attempts")
        if not isinstance(selected_path, list) or not isinstance(attempt_list, list):
            continue
        depth.append(float(len(selected_path)))
        attempts.append(float(len(attempt_list)))
        success_count = 0
        for attempt in attempt_list:
            if not isinstance(attempt, dict):
                continue
            if attempt.get("outcome") == "success":
                success_count += 1
        success_ratio.append(
            float(success_count) / float(len(attempt_list)) if attempt_list else 0.0
        )
    if not depth:
        return None
    return {"depth": depth, "attempts": attempts, "success_ratio": success_ratio}


def _build_trajectory_sample(
    theorems: list[dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any] | None:
    for entry in theorems:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        wild_series = _trajectory_series(run_dir / name / "wild_type_history.json")
        if wild_series is None:
            continue
        for intervention in entry.get("interventions", []):
            if not isinstance(intervention, dict):
                continue
            int_name = intervention.get("name")
            if not isinstance(int_name, str):
                continue
            int_series = _trajectory_series(run_dir / name / f"{int_name}_history.json")
            if int_series is None:
                continue
            return {
                "theorem": name,
                "wild": wild_series,
                "intervention": {"name": int_name, **int_series},
            }
    return None


def _build_ged_sample(
    theorems: list[dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any] | None:
    matrix_lookup = _load_ged_matrices(run_dir)
    for entry in theorems:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        matrix_entry = matrix_lookup.get(name)
        if matrix_entry:
            variants = matrix_entry.get("variants")
            matrix = matrix_entry.get("ged_matrix")
            if isinstance(variants, list):
                normalized = _normalize_ged_matrix(variants, matrix)
                if normalized is not None:
                    return {"theorem": name, "variants": variants, "matrix": normalized}
    for entry in theorems:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        path = run_dir / name / "ged_matrix.json"
        if not path.exists():
            continue
        data = read_json_auto(path)
        if not isinstance(data, dict):
            continue
        variants = data.get("variants")
        matrix = data.get("ged_matrix")
        if isinstance(variants, list):
            normalized = _normalize_ged_matrix(variants, matrix)
            if normalized is not None:
                return {"theorem": name, "variants": variants, "matrix": normalized}
    return None


def _normalize_ged_matrix(variants: list[str], matrix: Any) -> list[list[float]] | None:
    if isinstance(matrix, dict):
        values: list[float] = []
        for row in variants:
            row_map = matrix.get(row)
            if not isinstance(row_map, dict):
                continue
            for col in variants:
                value = row_map.get(col)
                if isinstance(value, (int, float)):
                    values.append(float(value))
        max_val = max(values) if values else 1.0
        if max_val <= 0:
            max_val = 1.0
        norm: list[list[float]] = []
        for row in variants:
            row_map = matrix.get(row, {})
            row_values: list[float] = []
            for col in variants:
                value = row_map.get(col) if isinstance(row_map, dict) else None
                if isinstance(value, (int, float)):
                    row_values.append(float(value) / max_val)
                else:
                    row_values.append(1.0)
            norm.append(row_values)
        return norm

    if isinstance(matrix, list):
        rows = []
        max_val = 0.0
        for row in matrix:
            if not isinstance(row, list):
                return None
            row_vals: list[float] = []
            for value in row:
                if isinstance(value, (int, float)):
                    max_val = max(max_val, float(value))
                    row_vals.append(float(value))
                else:
                    row_vals.append(0.0)
            rows.append(row_vals)
        if max_val > 1.0:
            rows = [[value / max_val for value in row] for row in rows]
        return rows

    return None


def _build_overview_points(theorems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overview: list[dict[str, Any]] = []
    for entry in theorems:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        wild = entry.get("wild_type")
        if not isinstance(wild, dict):
            wild = {}
        metrics = wild.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        trajectory = metrics.get("trajectory")
        if not isinstance(trajectory, dict):
            trajectory = {}
        detour = metrics.get("detour")
        if not isinstance(detour, dict):
            detour = {}

        iterations = wild.get("iterations")
        if not isinstance(iterations, (int, float)):
            iterations = trajectory.get("total_iterations", 0)

        mean_ged_search = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_search_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )
        mean_ged_proof = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_proof_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )
        mean_ged_trace = _mean(
            [
                value
                for value in (
                    _ged_family_value(i, "ged_trace_graph")
                    for i in entry.get("interventions", [])
                )
                if isinstance(value, (int, float))
            ]
        )

        overview.append(
            {
                "name": name,
                "solved": bool(wild.get("solved")),
                "iterations": _as_float(iterations),
                "max_depth": _as_float(trajectory.get("max_depth_reached")),
                "backtracks": _as_float(trajectory.get("backtrack_count")),
                "unique_goals": _as_float(trajectory.get("unique_goals_visited")),
                "tactic_diversity": _as_float(trajectory.get("tactic_diversity")),
                "failure_ratio": _as_float(detour.get("failure_ratio")),
                "mean_ged": _optional_float(mean_ged_search),
                "mean_ged_search_graph": _optional_float(mean_ged_search),
                "mean_ged_proof_graph": _optional_float(mean_ged_proof),
                "mean_ged_trace_graph": _optional_float(mean_ged_trace),
            }
        )
    return overview


def _build_intervention_points(
    theorems: list[dict[str, Any]],
    run_dir: Path,
    *,
    include_comparison_files: bool = True,
) -> tuple[list[dict[str, Any]], list[float]]:
    interventions: list[dict[str, Any]] = []
    recovery_values: list[float] = []
    for entry in theorems:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        wild = entry.get("wild_type")
        if not isinstance(wild, dict):
            wild = {}
        metrics = wild.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        trajectory = metrics.get("trajectory")
        if not isinstance(trajectory, dict):
            trajectory = {}

        wild_iterations = _as_float(
            wild.get("iterations")
            if isinstance(wild.get("iterations"), (int, float))
            else trajectory.get("total_iterations")
        )
        wild_max_depth = _as_float(trajectory.get("max_depth_reached"))
        wild_backtracks = _as_float(trajectory.get("backtrack_count"))

        for intervention in entry.get("interventions", []):
            if not isinstance(intervention, dict):
                continue
            int_name = intervention.get("name")
            if not isinstance(int_name, str):
                continue
            int_metrics = intervention.get("metrics")
            if not isinstance(int_metrics, dict):
                int_metrics = {}
            int_trajectory = int_metrics.get("trajectory")
            if not isinstance(int_trajectory, dict):
                int_trajectory = {}

            int_iterations = _as_float(int_trajectory.get("total_iterations"))
            int_max_depth = _as_float(int_trajectory.get("max_depth_reached"))
            int_backtracks = _as_float(int_trajectory.get("backtrack_count"))

            recovery_iterations = None
            if include_comparison_files:
                comparison_path = run_dir / name / f"{int_name}_comparison.json"
                if comparison_path.exists():
                    comparison = read_json_auto(comparison_path)
                    if isinstance(comparison, dict):
                        trajectory_comparison = comparison.get("trajectory_comparison")
                        if isinstance(trajectory_comparison, dict):
                            recovery_iterations = trajectory_comparison.get(
                                "recovery_iterations"
                            )
            if isinstance(recovery_iterations, (int, float)):
                recovery_values.append(float(recovery_iterations))

            ged_search = _ged_family_value(intervention, "ged_search_graph")
            ged_proof = _ged_family_value(intervention, "ged_proof_graph")
            ged_trace = _ged_family_value(intervention, "ged_trace_graph")
            ged_value = ged_search
            interventions.append(
                {
                    "theorem": name,
                    "name": int_name,
                    "ged": _optional_float(ged_value),
                    "ged_family": "ged_search_graph" if ged_value is not None else None,
                    "ged_search_graph": _optional_float(ged_search),
                    "ged_proof_graph": _optional_float(ged_proof),
                    "ged_trace_graph": _optional_float(ged_trace),
                    "solved": bool(intervention.get("solved")),
                    "delta_iterations": int_iterations - wild_iterations,
                    "delta_max_depth": int_max_depth - wild_max_depth,
                    "delta_backtracks": int_backtracks - wild_backtracks,
                    "recovery_iterations": recovery_iterations,
                }
            )

    return interventions, recovery_values


def _build_rescue_matrix_v2(theorems: list[dict[str, Any]]) -> dict[str, Any] | None:
    groups: dict[str, dict[str, int]] = {}
    for entry in theorems:
        if not isinstance(entry, dict):
            continue
        for intervention in entry.get("interventions", []):
            if not isinstance(intervention, dict):
                continue
            name = intervention.get("name")
            if not isinstance(name, str):
                continue
            group = groups.setdefault(
                name,
                {
                    "on_failed": 0,
                    "solved_on_failed": 0,
                    "on_solved": 0,
                    "solved_on_solved": 0,
                },
            )
            baseline_solved = intervention.get("baseline_solved")
            solved = intervention.get("solved")
            if baseline_solved is False:
                group["on_failed"] += 1
                if solved:
                    group["solved_on_failed"] += 1
            elif baseline_solved is True:
                group["on_solved"] += 1
                if solved:
                    group["solved_on_solved"] += 1

    if not groups:
        return None

    rows = []
    matrix = []
    for name, stats in sorted(
        groups.items(),
        key=lambda item: (
            (item[1]["solved_on_failed"] / item[1]["on_failed"])
            if item[1]["on_failed"]
            else -1.0,
            item[1]["on_failed"],
        ),
        reverse=True,
    ):
        rescue_rate = (
            stats["solved_on_failed"] / stats["on_failed"] if stats["on_failed"] else 0.0
        )
        wild_rate = (
            stats["solved_on_solved"] / stats["on_solved"] if stats["on_solved"] else 0.0
        )
        rows.append(name)
        matrix.append([float(rescue_rate), float(wild_rate)])

    return {
        "rows": rows,
        "cols": ["rescue_rate", "wild_solved_rate"],
        "matrix": matrix,
        "metric": "rate",
    }


def build_dashboard_payload_v2(
    summary: dict[str, Any],
    run_dir: Path,
    run_config: dict[str, Any] | None,
    run_status: dict[str, Any] | None,
    *,
    include_file_backed_details: bool = True,
) -> dict[str, Any]:
    theorems = summary.get("theorems", [])
    aggregates = summary.get("aggregates", {})
    crashed = summary.get("crashed", [])

    crashed_entries = []
    for entry in crashed:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        error = entry.get("error")
        if not isinstance(name, str) or not isinstance(error, str):
            continue
        payload_entry = {
            "name": name,
            "error": error,
        }
        error_kind = entry.get("error_kind")
        if isinstance(error_kind, str) and error_kind:
            payload_entry["error_kind"] = error_kind
        error_summary = entry.get("error_summary")
        if isinstance(error_summary, str) and error_summary:
            payload_entry["error_summary"] = error_summary
        repl_messages = entry.get("repl_messages")
        if isinstance(repl_messages, list) and repl_messages:
            payload_entry["repl_messages"] = [
                item for item in repl_messages if isinstance(item, dict)
            ]
        crashed_entries.append(payload_entry)

    overview = _build_overview_points(theorems)
    interventions, recovery_values = _build_intervention_points(
        theorems,
        run_dir,
        include_comparison_files=include_file_backed_details,
    )

    ged_histogram_search = _build_histogram(
        [
            entry.get("ged_search_graph")
            for entry in interventions
            if isinstance(entry.get("ged_search_graph"), (int, float))
        ]
    )
    ged_histogram_proof = _build_histogram(
        [
            entry.get("ged_proof_graph")
            for entry in interventions
            if isinstance(entry.get("ged_proof_graph"), (int, float))
        ]
    )
    ged_histogram_trace = _build_histogram(
        [
            entry.get("ged_trace_graph")
            for entry in interventions
            if isinstance(entry.get("ged_trace_graph"), (int, float))
        ]
    )
    ged_histogram = ged_histogram_search
    recovery_histogram = _build_histogram(recovery_values)

    payload = {
        "run_id": summary.get("run_id") or run_dir.name,
        "theorem_count": _as_int(aggregates.get("theorem_count"), len(theorems)),
        "crashed_count": _as_int(aggregates.get("crashed_count"), len(crashed)),
        "wild_type_solve_rate": _as_float(aggregates.get("wild_type_solve_rate")),
        "intervention_count": _as_int(
            aggregates.get("intervention_count"), len(interventions)
        ),
        "intervention_solve_rate": _as_float(aggregates.get("intervention_solve_rate")),
        "run_config": run_config,
        "run_status": run_status,
        "node_count": None,
        "edge_count": None,
        "goal_count": None,
        "expansion_count": None,
        "crashed": crashed_entries,
        "overview": overview,
        "interventions": interventions,
        "ged_histogram": ged_histogram,
        "ged_histogram_search": ged_histogram_search,
        "ged_histogram_proof": ged_histogram_proof,
        "ged_histogram_trace": ged_histogram_trace,
        "recovery_histogram": recovery_histogram,
    }

    goal_tactic_heatmap = _build_goal_tactic_heatmap(
        aggregates.get("goal_type_tactic_matrix")
    )
    if goal_tactic_heatmap:
        payload["goal_tactic_heatmap"] = goal_tactic_heatmap

    rescue_matrix = _build_rescue_matrix_v2(theorems)
    if rescue_matrix:
        payload["rescue_matrix"] = rescue_matrix

    if include_file_backed_details:
        trajectory_sample = _build_trajectory_sample(theorems, run_dir)
        if trajectory_sample:
            payload["trajectory_sample"] = trajectory_sample

        ged_sample = _build_ged_sample(theorems, run_dir)
        if ged_sample:
            payload["ged_sample"] = ged_sample

        theorem_details = build_theorem_details(theorems, run_dir)
        if theorem_details:
            payload["theorem_details"] = theorem_details

        provider_deep_dive = build_provider_deep_dive(run_dir)
        if provider_deep_dive:
            payload["provider_deep_dive"] = provider_deep_dive

    return payload


def _load_history_steps(path: Path, max_steps: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = read_json_auto(path)
    if not isinstance(data, dict):
        return []
    iterations = data.get("iterations")
    if not isinstance(iterations, list):
        return []
    steps: list[dict[str, Any]] = []
    for iteration in iterations:
        attempts = iteration.get("attempts") if isinstance(iteration, dict) else None
        if not isinstance(attempts, list):
            continue
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            tactic = attempt.get("tactic") or "unknown"
            goal = attempt.get("goal_type")
            if not goal:
                goal = attempt.get("goal_sig_strict") or attempt.get("goal_sig") or "n/a"
            outcome = attempt.get("outcome")
            step = {"tactic": tactic, "goal": goal, "outcome": outcome}
            steps.append(step)
            if len(steps) >= max_steps:
                return steps
    return steps


def _proof_term_stats(proof_term: Any) -> dict[str, Any] | None:
    if not isinstance(proof_term, dict):
        return None
    node_count = proof_term.get("node_count")
    depth = proof_term.get("depth")
    kind_counts: list[dict[str, Any]] = []

    for label, key in (
        ("app", "app_count"),
        ("lam", "lam_count"),
        ("forall", "forall_count"),
        ("unique_consts", "unique_consts"),
    ):
        value = proof_term.get(key)
        if isinstance(value, list):
            value = len(value)
        if isinstance(value, int):
            kind_counts.append({"label": label, "count": value})

    stats: dict[str, Any] = {}
    if isinstance(node_count, int):
        stats["node_count"] = node_count
    if isinstance(depth, int):
        stats["max_depth"] = depth
    if kind_counts:
        stats["kind_counts"] = kind_counts
    return stats or None


def _load_mcts_tree(path: Path, max_nodes: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = read_json_auto(path)
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes")
    if isinstance(nodes, dict) and len(nodes) > max_nodes:
        return None
    return data


def _build_provider_summaries(data: Any) -> list[dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, dict):
        entries = data.get("providers")
    elif isinstance(data, list):
        entries = data
    else:
        return []
    if not isinstance(entries, list):
        return []
    summaries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        provider = entry.get("provider") or entry.get("name")
        if not isinstance(provider, str):
            continue
        total = entry.get("theorem_total")
        solved = entry.get("wild_solved")
        crashed = entry.get("crashed", 0)
        failed = None
        if isinstance(total, int) and isinstance(solved, int):
            failed = max(total - solved - (crashed if isinstance(crashed, int) else 0), 0)
        solve_rate = solved / total if isinstance(solved, int) and total else None
        summaries.append(
            {
                "provider": provider,
                "solved": solved,
                "failed": failed,
                "solve_rate": solve_rate,
                "mean_ged": None,
                "median_ged": None,
                "mean_iterations": entry.get("avg_iters"),
                "median_iterations": None,
            }
        )
    return summaries


def _build_provider_interventions(data: Any) -> list[dict[str, Any]]:
    if not data:
        return []
    entries: list[Any] = []
    if isinstance(data, dict):
        if isinstance(data.get("interventions"), list):
            entries = data.get("interventions")
        elif isinstance(data.get("theorems"), list):
            for theorem in data.get("theorems"):
                if not isinstance(theorem, dict):
                    continue
                theorem_name = theorem.get("theorem") or theorem.get("name")
                items = theorem.get("interventions")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            item = dict(item)
                            if theorem_name:
                                item.setdefault("theorem", theorem_name)
                            entries.append(item)
                    continue
                providers = theorem.get("providers")
                if not isinstance(providers, dict):
                    continue
                for provider_name, provider_entry in providers.items():
                    if not isinstance(provider_entry, dict):
                        continue
                    interventions = provider_entry.get("interventions")
                    if not isinstance(interventions, dict):
                        continue
                    for intervention_name, metrics in interventions.items():
                        if not isinstance(metrics, dict):
                            continue
                        entry = dict(metrics)
                        entry.setdefault("provider", provider_name)
                        entry.setdefault("theorem", theorem_name)
                        entry.setdefault("name", intervention_name)
                        entries.append(entry)
    elif isinstance(data, list):
        entries = data

    interventions = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        provider = entry.get("provider") or entry.get("provider_id")
        theorem = entry.get("theorem") or entry.get("name")
        name = entry.get("intervention") or entry.get("variant") or entry.get("name")
        if (
            not isinstance(provider, str)
            or not isinstance(theorem, str)
            or not isinstance(name, str)
        ):
            continue
        delta_iterations = entry.get("delta_iterations")
        if delta_iterations is None:
            delta_iterations = entry.get("iteration_diff")
        delta_backtracks = entry.get("delta_backtracks")
        if delta_backtracks is None:
            delta_backtracks = entry.get("backtrack_diff")
        interventions.append(
            {
                "provider": provider,
                "theorem": theorem,
                "name": name,
                "ged": entry.get("ged"),
                "delta_iterations": delta_iterations,
                "delta_max_depth": entry.get("delta_max_depth"),
                "delta_backtracks": delta_backtracks,
                "recovery_iterations": entry.get("recovery_iterations"),
            }
        )
    return interventions

