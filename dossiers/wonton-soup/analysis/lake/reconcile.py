from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from analysis.lake.db import run_dir_where_clause
from analysis.lake.extract import ExtractReport, extract_facts
from analysis.lake.extract_artifacts import ArtifactExtractReport, extract_artifact_facts
from analysis.lake.extract_basin import BasinExtractReport, extract_basin_facts
from analysis.lake.index import IndexReport, index_logs
from analysis.logs import relpath_under

ALL_RUN_KEY_TABLES = [
    "runs",
    "run_files",
    "extract_errors",
    "run_aggregates",
    "run_postprocess",
    "goal_type_tactic",
    "theorem_wild",
    "theorem_intervention",
    "theorem_variant_metrics",
    "theorem_intervention_comparison",
    "theorem_intervention_postprocess",
    "theorem_artifacts",
    "graph_nodes",
    "graph_edges",
    "graph_extract_errors",
    "artifact_extract_state",
    "mcts_trace_stats",
    "mcts_tree_nodes",
    "mcts_tree_edges",
    "goal_outcome_global_family",
    "goal_outcome_sig_family",
    "k_reference_score",
    "basin_runs",
    "basin_seed",
    "basin_structure_counts",
]


@dataclass(frozen=True)
class ReconcileReport:
    index: IndexReport
    extract: ExtractReport
    artifacts: ArtifactExtractReport
    basin: BasinExtractReport
    stale_run_keys: list[str] = field(default_factory=list)
    pruned: int = 0


def _run_rows_for_logs_root(
    conn: duckdb.DuckDBPyConnection,
    *,
    root_dir: Path,
) -> list[tuple[str, str]]:
    clause, params = run_dir_where_clause(root=root_dir)
    rows = conn.execute(
        f"SELECT run_key, run_dir FROM runs WHERE {clause} ORDER BY run_dir",
        params,
    ).fetchall()
    out: list[tuple[str, str]] = []
    for run_key, run_dir in rows:
        if not isinstance(run_key, str) or not isinstance(run_dir, str):
            continue
        out.append((run_key, relpath_under(root_dir, Path(run_dir))))
    return out


def reconcile(
    conn: duckdb.DuckDBPyConnection,
    *,
    logs_dirs: list[Path],
    prune: bool = False,
) -> ReconcileReport:
    idx_report = index_logs(conn, logs_dirs=logs_dirs)

    resolved_dirs = [d.resolve() for d in logs_dirs]

    ext_report = ExtractReport(
        runs_extracted=0, wild_rows=0, intervention_rows=0, outcome_rows=0, errors=[]
    )
    artifact_report = ArtifactExtractReport(
        runs_scanned=0,
        artifacts_indexed=0,
        graph_files=0,
        graph_nodes=0,
        graph_edges=0,
        trace_files=0,
        trace_rows=0,
        errors=[],
    )
    basin_report = BasinExtractReport(
        basin_run_rows=0, basin_seed_rows=0, basin_structure_rows=0, errors=[]
    )

    for root_dir in resolved_dirs:
        rows = _run_rows_for_logs_root(conn, root_dir=root_dir)
        if not rows:
            continue
        run_keys = [
            run_key for run_key, _ in rows if isinstance(run_key, str) and run_key
        ]
        if run_keys:
            placeholders = ", ".join(["?"] * len(run_keys))
            conn.execute(
                f"DELETE FROM extract_errors WHERE run_key IN ({placeholders})",
                run_keys,
            )

        partial = extract_facts(
            conn, root_dir=root_dir, run_rows=rows, with_goal_outcomes=True
        )
        ext_report = ExtractReport(
            runs_extracted=ext_report.runs_extracted + partial.runs_extracted,
            wild_rows=ext_report.wild_rows + partial.wild_rows,
            intervention_rows=ext_report.intervention_rows + partial.intervention_rows,
            outcome_rows=ext_report.outcome_rows + partial.outcome_rows,
            errors=ext_report.errors + partial.errors,
        )

        partial_artifacts = extract_artifact_facts(conn, root_dir=root_dir, run_rows=rows)
        artifact_report = ArtifactExtractReport(
            runs_scanned=artifact_report.runs_scanned + partial_artifacts.runs_scanned,
            artifacts_indexed=(
                artifact_report.artifacts_indexed + partial_artifacts.artifacts_indexed
            ),
            graph_files=artifact_report.graph_files + partial_artifacts.graph_files,
            graph_nodes=artifact_report.graph_nodes + partial_artifacts.graph_nodes,
            graph_edges=artifact_report.graph_edges + partial_artifacts.graph_edges,
            trace_files=artifact_report.trace_files + partial_artifacts.trace_files,
            trace_rows=artifact_report.trace_rows + partial_artifacts.trace_rows,
            errors=artifact_report.errors + partial_artifacts.errors,
        )

        partial_basin = extract_basin_facts(conn, root_dir=root_dir, run_rows=rows)
        basin_report = BasinExtractReport(
            basin_run_rows=basin_report.basin_run_rows + partial_basin.basin_run_rows,
            basin_seed_rows=basin_report.basin_seed_rows + partial_basin.basin_seed_rows,
            basin_structure_rows=(
                basin_report.basin_structure_rows + partial_basin.basin_structure_rows
            ),
            errors=basin_report.errors + partial_basin.errors,
        )

    stale_run_keys: list[str] = []
    pruned = 0

    for root_dir in resolved_dirs:
        for run_key, rel in _run_rows_for_logs_root(conn, root_dir=root_dir):
            if not (root_dir / rel).exists():
                stale_run_keys.append(run_key)
    stale_run_keys = sorted(set(stale_run_keys))

    if prune and stale_run_keys:
        for table in ALL_RUN_KEY_TABLES:
            placeholders = ", ".join(["?"] * len(stale_run_keys))
            conn.execute(
                f"DELETE FROM {table} WHERE run_key IN ({placeholders})",
                stale_run_keys,
            )
        pruned = len(stale_run_keys)

    return ReconcileReport(
        index=idx_report,
        extract=ext_report,
        artifacts=artifact_report,
        basin=basin_report,
        stale_run_keys=stale_run_keys,
        pruned=pruned,
    )
