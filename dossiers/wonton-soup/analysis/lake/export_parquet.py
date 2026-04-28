from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from analysis.lake.db import utc_timestamp, write_json
from analysis.lake.job import _materialize_parquet
from analysis.lake.job_config import create_selected_runs_view

DatasetQuery = tuple[str, str]

RUNS_COLS = (
    "run_key",
    "root_id",
    "rel_run_dir",
    "run_dir",
    "run_id",
    "provider",
    "backend",
    "mode",
    "corpus",
    "created_at",
    "goal_sig_scheme",
    "trace_mcts",
    "problem_space",
    "config_whitelist_hash",
    "config_full_hash",
    "indexed_at",
)

RUNS_DASHBOARD_COLS = (
    "run_key",
    "run_id",
    "provider",
    "backend",
    "mode",
    "corpus",
    "created_at",
    "goal_sig_scheme",
    "trace_mcts",
    "config_whitelist_hash",
    "config_full_hash",
)

RUN_AGGREGATES_DASHBOARD_COLS = (
    "run_key",
    "theorem_count",
    "crashed_count",
    "wild_type_solve_rate",
    "intervention_count",
    "intervention_solve_rate",
)

THEOREM_WILD_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "solved",
    "iterations",
    "proof_term_hash",
    "k_valid",
    "k_null_model",
    "k_tau_agent",
    "k_tau_blind",
    "k_K",
)

THEOREM_INTERVENTION_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "intervention",
    "solved",
    "status",
    "is_control",
    "baseline_solved",
    "ged_search_value",
    "ged_search_norm",
    "ged_search_soft_value",
    "ged_search_soft_norm",
    "k_valid",
    "k_null_model",
    "k_tau_agent",
    "k_tau_blind",
    "k_K",
)

THEOREM_INTERVENTION_COMPARISON_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "intervention",
    "solved",
    "status",
    "wild_type_hash",
    "intervention_hash",
    "hash_mismatch",
    "axiom_delta_count",
    "axiom_removed_count",
    "trajectory_iteration_diff",
    "trajectory_backtrack_diff",
    "ged_search_value",
    "ged_search_norm",
    "ged_search_valid",
    "ged_search_soft_value",
    "ged_search_soft_norm",
    "ged_search_soft_valid",
    "ged_proof_value",
    "ged_proof_norm",
    "ged_proof_valid",
    "ged_trace_value",
    "ged_trace_norm",
    "ged_trace_valid",
)

THEOREM_VARIANT_METRICS_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "trajectory_total_iterations",
    "trajectory_backtrack_count",
    "trajectory_max_depth_reached",
    "trajectory_depth_at_solution",
    "trajectory_unique_goals_visited",
    "trajectory_tactic_diversity",
    "detour_total_iterations",
    "detour_total_attempts",
    "detour_success_count",
    "detour_failure_count",
    "detour_blocked_count",
    "detour_failure_ratio",
    "detour_max_depth",
    "detour_depth_at_solution",
    "detour_terminal_iteration",
    "proof_term_node_count",
    "proof_term_depth",
    "proof_term_width",
    "solution_path_len",
    "tactic_fingerprint",
)

GRAPH_NODES_DASHBOARD_SELECT = (
    "t.run_key",
    "t.theorem",
    "t.variant",
    "{graph_kind_expr}",
    "t.node_id",
    "t.goal_sig",
    "t.in_proof",
    "json_extract_string(t.attrs_json, '$.goal_type') AS goal_type",
)

GRAPH_EDGES_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "graph_kind",
    "edge_idx",
    "src_node_id",
    "dst_node_id",
    "tactic",
    "tactic_family",
    "in_proof",
)

GOAL_TYPE_TACTIC_DASHBOARD_COLS = (
    "run_key",
    "goal_type",
    "tactic_norm",
    "tactic_family",
    "success",
    "failure",
    "blocked",
    "total",
)

K_REFERENCE_SCORE_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "ref_id",
    "valid",
    "primary_null_model",
    "tau_agent",
    "tau_blind",
    "K",
)

MCTS_TRACE_STATS_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "line_count",
    "bad_json_lines",
    "event_count",
    "iteration_event_count",
    "tactic_attempt_event_count",
    "max_iteration",
    "unique_mvar_count",
    "candidate_total",
    "candidate_max",
)

MCTS_TREE_NODES_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "mvar_id",
    "goal_type",
    "goal_sig",
    "depth",
    "visit_count",
    "success_count",
    "is_terminal",
    "is_dead",
    "expansion_order",
)

MCTS_TREE_EDGES_DASHBOARD_COLS = (
    "run_key",
    "theorem",
    "variant",
    "parent_mvar_id",
    "child_mvar_id",
    "tactic",
    "edge_order",
)


def _qualified(alias: str, columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{alias}.{column}" for column in columns)


def _dataset_query(
    table: str,
    *,
    select: tuple[str, ...],
    order_by: tuple[str, ...],
    alias: str = "t",
) -> str:
    select_sql = ", ".join(select)
    order_sql = ", ".join(order_by)
    return (
        f"SELECT {select_sql} "
        f"FROM {table} {alias} JOIN selected_runs USING(run_key) "
        f"ORDER BY {order_sql}"
    )


def _all_columns_dataset(name: str, table: str, *order_by: str) -> DatasetQuery:
    alias = "t"
    return (
        name,
        _dataset_query(
            table,
            alias=alias,
            select=(f"{alias}.*",),
            order_by=_qualified(alias, order_by),
        ),
    )


def _selected_columns_dataset(
    name: str,
    table: str,
    columns: tuple[str, ...],
    *order_by: str,
) -> DatasetQuery:
    alias = "t"
    return (
        name,
        _dataset_query(
            table,
            alias=alias,
            select=_qualified(alias, columns),
            order_by=_qualified(alias, order_by),
        ),
    )


def _raw_select_dataset(
    name: str,
    table: str,
    *,
    select: tuple[str, ...],
    order_by: tuple[str, ...],
) -> DatasetQuery:
    return (name, _dataset_query(table, select=select, order_by=order_by))


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = conn.execute(f"DESCRIBE {table}").fetchall()
    return {str(row[0]) for row in rows}


def _graph_kind_select_expr(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    columns = _table_columns(conn, table)
    if "graph_kind" in columns:
        return "t.graph_kind"
    if "graph_family" in columns:
        return "t.graph_family AS graph_kind"
    raise ValueError(f"{table} must have graph_kind or graph_family")


def _graph_kind_order_expr(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    columns = _table_columns(conn, table)
    if "graph_kind" in columns:
        return "t.graph_kind"
    if "graph_family" in columns:
        return "t.graph_family"
    raise ValueError(f"{table} must have graph_kind or graph_family")


def _graph_edges_dashboard_select(conn: duckdb.DuckDBPyConnection) -> tuple[str, ...]:
    graph_kind_expr = _graph_kind_select_expr(conn, "graph_edges")
    return tuple(
        f"t.{column}" if column != "graph_kind" else graph_kind_expr
        for column in GRAPH_EDGES_DASHBOARD_COLS
    )


def _dashboard_datasets(conn: duckdb.DuckDBPyConnection) -> list[DatasetQuery]:
    graph_nodes_select = tuple(
        column.format(graph_kind_expr=_graph_kind_select_expr(conn, "graph_nodes"))
        for column in GRAPH_NODES_DASHBOARD_SELECT
    )
    graph_nodes_order = (
        "t.run_key",
        "t.theorem",
        "t.variant",
        _graph_kind_order_expr(conn, "graph_nodes"),
        "t.node_id",
    )
    graph_edges_order = (
        "t.run_key",
        "t.theorem",
        "t.variant",
        _graph_kind_order_expr(conn, "graph_edges"),
        "t.edge_idx",
    )
    return [
        *DASHBOARD_DATASETS_BEFORE_GRAPHS,
        _raw_select_dataset(
            "graph_nodes",
            "graph_nodes",
            select=graph_nodes_select,
            order_by=graph_nodes_order,
        ),
        _raw_select_dataset(
            "graph_edges",
            "graph_edges",
            select=_graph_edges_dashboard_select(conn),
            order_by=graph_edges_order,
        ),
        *DASHBOARD_DATASETS_AFTER_GRAPHS,
    ]


FULL_DATASETS: list[DatasetQuery] = [
    _selected_columns_dataset("runs", "runs", RUNS_COLS, "indexed_at", "run_key"),
    _all_columns_dataset("run_aggregates", "run_aggregates", "run_key"),
    _all_columns_dataset("theorem_wild", "theorem_wild", "run_key", "theorem"),
    _all_columns_dataset(
        "theorem_intervention",
        "theorem_intervention",
        "run_key",
        "theorem",
        "intervention",
    ),
    _all_columns_dataset(
        "theorem_intervention_comparison",
        "theorem_intervention_comparison",
        "run_key",
        "theorem",
        "intervention",
    ),
    _all_columns_dataset(
        "theorem_variant_metrics",
        "theorem_variant_metrics",
        "run_key",
        "theorem",
        "variant",
    ),
    _all_columns_dataset(
        "goal_type_tactic",
        "goal_type_tactic",
        "run_key",
        "goal_type",
        "tactic_norm",
    ),
    _all_columns_dataset(
        "k_reference_score",
        "k_reference_score",
        "ref_id",
        "run_key",
        "theorem",
        "variant",
    ),
    _all_columns_dataset("run_postprocess", "run_postprocess", "run_key"),
    _all_columns_dataset(
        "theorem_intervention_postprocess",
        "theorem_intervention_postprocess",
        "run_key",
        "theorem",
        "intervention",
    ),
    _all_columns_dataset(
        "theorem_artifacts",
        "theorem_artifacts",
        "run_key",
        "theorem",
        "rel_path",
    ),
    _all_columns_dataset(
        "graph_nodes",
        "graph_nodes",
        "run_key",
        "theorem",
        "rel_path",
        "node_id",
    ),
    _all_columns_dataset(
        "graph_edges",
        "graph_edges",
        "run_key",
        "theorem",
        "rel_path",
        "edge_idx",
    ),
    _all_columns_dataset(
        "graph_extract_errors",
        "graph_extract_errors",
        "recorded_at",
        "run_key",
        "theorem",
        "rel_path",
    ),
    _all_columns_dataset(
        "mcts_trace_stats",
        "mcts_trace_stats",
        "run_key",
        "theorem",
        "rel_path",
    ),
    _all_columns_dataset(
        "mcts_tree_nodes",
        "mcts_tree_nodes",
        "run_key",
        "theorem",
        "variant",
        "depth",
        "mvar_id",
    ),
    _all_columns_dataset(
        "mcts_tree_edges",
        "mcts_tree_edges",
        "run_key",
        "theorem",
        "variant",
        "parent_mvar_id",
        "edge_order",
    ),
    _all_columns_dataset("basin_runs", "basin_runs", "run_key", "theorem"),
    _all_columns_dataset("basin_seed", "basin_seed", "run_key", "theorem", "seed"),
    _all_columns_dataset(
        "basin_structure_counts",
        "basin_structure_counts",
        "run_key",
        "theorem",
        "structure_hash",
    ),
]

DASHBOARD_DATASETS_BEFORE_GRAPHS: list[DatasetQuery] = [
    _selected_columns_dataset("runs", "runs", RUNS_DASHBOARD_COLS, "run_key"),
    _selected_columns_dataset(
        "run_aggregates",
        "run_aggregates",
        RUN_AGGREGATES_DASHBOARD_COLS,
        "run_key",
    ),
    _selected_columns_dataset(
        "theorem_wild",
        "theorem_wild",
        THEOREM_WILD_DASHBOARD_COLS,
        "run_key",
        "theorem",
    ),
    _selected_columns_dataset(
        "theorem_intervention",
        "theorem_intervention",
        THEOREM_INTERVENTION_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "intervention",
    ),
    _selected_columns_dataset(
        "theorem_intervention_comparison",
        "theorem_intervention_comparison",
        THEOREM_INTERVENTION_COMPARISON_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "intervention",
    ),
    _selected_columns_dataset(
        "theorem_variant_metrics",
        "theorem_variant_metrics",
        THEOREM_VARIANT_METRICS_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "variant",
    ),
]

DASHBOARD_DATASETS_AFTER_GRAPHS: list[DatasetQuery] = [
    _selected_columns_dataset(
        "goal_type_tactic",
        "goal_type_tactic",
        GOAL_TYPE_TACTIC_DASHBOARD_COLS,
        "run_key",
        "goal_type",
        "tactic_norm",
    ),
    _selected_columns_dataset(
        "k_reference_score",
        "k_reference_score",
        K_REFERENCE_SCORE_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "variant",
        "ref_id",
    ),
    _selected_columns_dataset(
        "mcts_trace_stats",
        "mcts_trace_stats",
        MCTS_TRACE_STATS_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "variant",
    ),
    _selected_columns_dataset(
        "mcts_tree_nodes",
        "mcts_tree_nodes",
        MCTS_TREE_NODES_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "variant",
        "depth",
        "mvar_id",
    ),
    _selected_columns_dataset(
        "mcts_tree_edges",
        "mcts_tree_edges",
        MCTS_TREE_EDGES_DASHBOARD_COLS,
        "run_key",
        "theorem",
        "variant",
        "parent_mvar_id",
        "edge_order",
    ),
]

DASHBOARD_SELECTION: dict[str, Any] = {
    "backend": "lean",
    "require_completed": True,
    "dedupe_run_id": True,
    "max_runs": 600,
}


def export_parquet(
    conn: duckdb.DuckDBPyConnection,
    *,
    profile: str,
    out_dir: Path,
    release_id: str = "",
    selection_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile == "full":
        datasets = FULL_DATASETS
        selection: dict[str, Any] = {}
    elif profile == "dashboard":
        datasets = _dashboard_datasets(conn)
        selection = dict(DASHBOARD_SELECTION)
    else:
        raise ValueError(f"Unknown profile: {profile!r}")

    if selection_overrides:
        selection.update(selection_overrides)

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = create_selected_runs_view(conn, selection=selection)

    tables: list[dict[str, str]] = []
    for name, query in datasets:
        file_name = f"{name}.parquet"
        _materialize_parquet(conn, query=query, out_path=out_dir / file_name)
        tables.append({"name": name, "file": file_name})

    report_datasets = [
        table for table in tables if table["name"] not in {"mcts_tree_nodes", "mcts_tree_edges"}
    ]

    manifest = {
        "schema_version": 1,
        "format": "parquet",
        "profile": profile,
        "compiled_at": utc_timestamp(),
        "release_id": release_id,
        "selection": selection,
        "selected_runs": selected["count"],
        "tables": tables,
        "datasets": report_datasets,
    }
    write_json(out_dir / "manifest.json", manifest)
    write_json(out_dir / "dashboard_manifest.json", manifest)

    return {
        "profile": profile,
        "out_dir": out_dir,
        "selected_runs": selected["count"],
        "tables": tables,
        "datasets": report_datasets,
    }
