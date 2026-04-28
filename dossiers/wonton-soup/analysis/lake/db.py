from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb

from analysis.logs import relpath_under, resolve_artifacts_dir
from analysis.logs import utc_timestamp as _utc_timestamp

# Bump when any persisted table schema changes (columns or meanings).
SCHEMA_VERSION = 11


RUN_KEY_TABLE_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "run_files": ("run_key", "file_name"),
    "run_aggregates": ("run_key",),
    "goal_type_tactic": ("run_key", "goal_type", "tactic_norm"),
    "run_postprocess": ("run_key",),
    "goal_outcome_global_family": ("run_key", "family_idx"),
    "goal_outcome_sig_family": ("run_key", "goal_sig", "family_idx"),
    "lake_reference_members": ("ref_id", "run_key"),
    "k_reference_score": ("run_key", "theorem", "variant", "ref_id"),
    "theorem_wild": ("run_key", "theorem"),
    "theorem_intervention": ("run_key", "theorem", "intervention"),
    "theorem_variant_metrics": ("run_key", "theorem", "variant"),
    "theorem_intervention_comparison": ("run_key", "theorem", "intervention"),
    "theorem_intervention_postprocess": ("run_key", "theorem", "intervention"),
    "theorem_artifacts": ("run_key", "theorem", "rel_path"),
    "artifact_extract_state": ("run_key", "rel_path", "extractor"),
    "graph_nodes": ("run_key", "theorem", "rel_path", "node_id"),
    "graph_edges": ("run_key", "theorem", "rel_path", "edge_idx"),
    "mcts_trace_stats": ("run_key", "theorem", "rel_path"),
    "mcts_tree_nodes": ("run_key", "theorem", "rel_path", "mvar_id"),
    "mcts_tree_edges": (
        "run_key",
        "theorem",
        "rel_path",
        "parent_mvar_id",
        "child_mvar_id",
        "tactic",
    ),
    "basin_runs": ("run_key", "theorem"),
    "basin_seed": ("run_key", "theorem", "seed"),
    "basin_structure_counts": ("run_key", "theorem", "structure_hash"),
}

RUN_KEY_TABLES_WITHOUT_PRIMARY_KEYS: tuple[str, ...] = (
    "extract_errors",
    "graph_extract_errors",
)


def _stable_id(*parts: str, n: int = 16) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:n]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
            n += 1
    return n


@dataclass(frozen=True)
class LakePaths:
    root: Path
    db_path: Path
    exports_dir: Path


def resolve_lake_paths(*, artifacts_dir: Path | None = None) -> LakePaths:
    artifacts = artifacts_dir or resolve_artifacts_dir()
    lake_root = artifacts / "lake"
    return LakePaths(
        root=lake_root,
        db_path=lake_root / "lake.duckdb",
        exports_dir=lake_root / "exports",
    )


def root_id_for_path(path: Path) -> str:
    # Store the real path inside the DB (local-only), but the key should be stable.
    return _stable_id(str(path.resolve()))


def run_key_for_run_dir(run_dir: Path) -> str:
    return _stable_id(str(run_dir.resolve()))


def run_key_for(root_id: str, rel_run_dir: str) -> str:
    # Legacy v5 identity helper kept for compatibility with older callers/tests.
    return _stable_id(root_id, rel_run_dir)


def run_dir_where_clause(*, root: Path, column: str = "run_dir") -> tuple[str, list[str]]:
    resolved = str(root.resolve())
    return f"({column} = ? OR {column} LIKE ?)", [resolved, resolved + "/%"]


def utc_timestamp() -> str:
    return _utc_timestamp()


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    # We want deterministic ordering when exporting rows (in addition to ORDER BY).
    conn.execute("PRAGMA threads=1")
    return conn


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    return [str(row[1]) for row in rows if len(row) > 1 and isinstance(row[1], str)]


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _canonical_root_for_run_dir(
    run_dir: Path,
    *,
    roots: list[tuple[str, Path]],
) -> tuple[str, Path]:
    candidates = [(rid, root) for rid, root in roots if _path_is_under(run_dir, root)]
    if not candidates:
        raise RuntimeError(f"No enclosing log root found for run_dir {run_dir}")
    candidates.sort(key=lambda item: (len(item[1].parts), len(str(item[1])), str(item[1])))
    return candidates[0]


def _build_run_key_migration_map(conn: duckdb.DuckDBPyConnection) -> bool:
    root_rows = conn.execute(
        "SELECT root_id, root_path FROM log_roots ORDER BY root_path"
    ).fetchall()
    roots: list[tuple[str, Path]] = []
    for root_id, root_path in root_rows:
        if not isinstance(root_id, str) or not isinstance(root_path, str):
            continue
        roots.append((root_id, Path(root_path).resolve()))
    if not roots:
        return False

    run_rows = conn.execute(
        "SELECT run_key, root_id, rel_run_dir FROM runs ORDER BY run_key"
    ).fetchall()
    if not run_rows:
        return False

    conn.execute("DROP TABLE IF EXISTS run_key_migration_map")
    conn.execute(
        """
        CREATE TEMP TABLE run_key_migration_map (
          source_run_key VARCHAR PRIMARY KEY,
          target_run_key VARCHAR NOT NULL,
          run_dir VARCHAR NOT NULL,
          canonical_root_id VARCHAR NOT NULL,
          canonical_rel_run_dir VARCHAR NOT NULL,
          canonical_rank BIGINT NOT NULL
        )
        """
    )

    rows: list[tuple[str, str, str, str, str, int]] = []
    roots_by_id = {root_id: root_path for root_id, root_path in roots}
    for source_run_key, source_root_id, rel_run_dir in run_rows:
        if not (
            isinstance(source_run_key, str)
            and isinstance(source_root_id, str)
            and isinstance(rel_run_dir, str)
        ):
            continue
        root_path = roots_by_id.get(source_root_id)
        if root_path is None:
            continue
        run_dir = (root_path / rel_run_dir).resolve()
        target_run_key = run_key_for_run_dir(run_dir)
        canonical_root_id, canonical_root_path = _canonical_root_for_run_dir(
            run_dir,
            roots=roots,
        )
        canonical_rel_run_dir = relpath_under(canonical_root_path, run_dir)
        source_rank = (0 if source_root_id == canonical_root_id else 1) * 1000 + len(
            root_path.parts
        )
        rows.append(
            (
                source_run_key,
                target_run_key,
                str(run_dir),
                canonical_root_id,
                canonical_rel_run_dir,
                source_rank,
            )
        )

    if not rows:
        conn.execute("DROP TABLE run_key_migration_map")
        return False

    conn.executemany(
        """
        INSERT INTO run_key_migration_map(
          source_run_key, target_run_key, run_dir,
          canonical_root_id, canonical_rel_run_dir, canonical_rank
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return True


def _remap_runs_table(conn: duckdb.DuckDBPyConnection) -> None:
    cols = _table_columns(conn, "runs")
    data_cols = [
        col
        for col in cols
        if col not in {"run_key", "root_id", "rel_run_dir", "run_dir"}
    ]
    select_cols = [
        "m.target_run_key AS run_key",
        "m.canonical_root_id AS root_id",
        "m.canonical_rel_run_dir AS rel_run_dir",
        "m.run_dir AS run_dir",
    ] + [f"r.{_quote_ident(col)}" for col in data_cols]
    output_cols = ["run_key", "root_id", "rel_run_dir", "run_dir"] + data_cols
    output_cols_sql = ", ".join(_quote_ident(col) for col in output_cols)
    select_cols_sql = ", ".join(select_cols)
    conn.execute("DROP TABLE IF EXISTS runs__v11")
    conn.execute(
        f"""
        CREATE TEMP TABLE runs__v11 AS
        SELECT {output_cols_sql}
        FROM (
          SELECT
            {select_cols_sql},
            row_number() OVER (
              PARTITION BY m.target_run_key
              ORDER BY m.canonical_rank, r.indexed_at DESC NULLS LAST, r.run_key
            ) AS _rn
          FROM runs r
          JOIN run_key_migration_map m ON r.run_key = m.source_run_key
        ) ranked
        WHERE _rn = 1
        """
    )
    conn.execute("DELETE FROM runs")
    conn.execute(
        f"INSERT INTO runs({output_cols_sql}) SELECT {output_cols_sql} FROM runs__v11"
    )
    conn.execute("DROP TABLE runs__v11")


def _remap_run_key_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table: str,
    primary_key: tuple[str, ...] | None,
) -> None:
    cols = _table_columns(conn, table)
    if not cols:
        return
    select_cols = [
        "m.target_run_key AS run_key" if col == "run_key" else f"t.{_quote_ident(col)}"
        for col in cols
    ]
    cols_sql = ", ".join(_quote_ident(col) for col in cols)
    select_cols_sql = ", ".join(select_cols)
    tmp_name = f"{table}__v11"
    conn.execute(f"DROP TABLE IF EXISTS {_quote_ident(tmp_name)}")
    if primary_key:
        partition_cols = ", ".join(
            "m.target_run_key" if col == "run_key" else f"t.{_quote_ident(col)}"
            for col in primary_key
        )
        conn.execute(
            f"""
            CREATE TEMP TABLE {_quote_ident(tmp_name)} AS
            SELECT {cols_sql}
            FROM (
              SELECT
                {select_cols_sql},
                row_number() OVER (
                  PARTITION BY {partition_cols}
                  ORDER BY m.canonical_rank, t.run_key
                ) AS _rn
              FROM {_quote_ident(table)} t
              JOIN run_key_migration_map m ON t.run_key = m.source_run_key
            ) ranked
            WHERE _rn = 1
            """
        )
    else:
        conn.execute(
            f"""
            CREATE TEMP TABLE {_quote_ident(tmp_name)} AS
            SELECT DISTINCT {select_cols_sql}
            FROM {_quote_ident(table)} t
            JOIN run_key_migration_map m ON t.run_key = m.source_run_key
            """
        )
    conn.execute(f"DELETE FROM {_quote_ident(table)}")
    conn.execute(
        f"""
        INSERT INTO {_quote_ident(table)}({cols_sql})
        SELECT {cols_sql} FROM {_quote_ident(tmp_name)}
        """
    )
    conn.execute(f"DROP TABLE {_quote_ident(tmp_name)}")


def _migrate_run_identity_v11(conn: duckdb.DuckDBPyConnection) -> None:
    conn.begin()
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_dir VARCHAR")
        if not _build_run_key_migration_map(conn):
            conn.commit()
            return
        _remap_runs_table(conn)
        for table, pk in RUN_KEY_TABLE_PRIMARY_KEYS.items():
            _remap_run_key_table(conn, table=table, primary_key=pk)
        for table in RUN_KEY_TABLES_WITHOUT_PRIMARY_KEYS:
            _remap_run_key_table(conn, table=table, primary_key=None)
        conn.execute(
            """
            DELETE FROM log_roots
            WHERE root_id NOT IN (SELECT DISTINCT root_id FROM runs)
            """
        )
        conn.execute("DROP TABLE run_key_migration_map")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    # Core registry.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          schema_version INTEGER NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS log_roots (
          root_id VARCHAR PRIMARY KEY,
          root_path VARCHAR NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          run_key VARCHAR PRIMARY KEY,
          root_id VARCHAR NOT NULL,
          rel_run_dir VARCHAR NOT NULL,
          run_dir VARCHAR,
          run_id VARCHAR,
          provider VARCHAR,
          backend VARCHAR,
          mode VARCHAR,
          corpus VARCHAR,
          created_at VARCHAR,
          goal_sig_scheme VARCHAR,
          trace_mcts BOOLEAN,
          problem_space JSON,
          config_whitelist_hash VARCHAR,
          config_full_hash VARCHAR,
          run_config JSON,
          run_status JSON,
          indexed_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    # Backfill schema changes on existing DBs.
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_dir VARCHAR")
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS config_whitelist_hash VARCHAR")
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS config_full_hash VARCHAR")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_run_dir ON runs(run_dir)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_files (
          run_key VARCHAR NOT NULL,
          file_name VARCHAR NOT NULL,
          sha256 VARCHAR,
          bytes BIGINT,
          mtime_epoch BIGINT,
          PRIMARY KEY (run_key, file_name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extract_errors (
          run_key VARCHAR NOT NULL,
          stage VARCHAR NOT NULL,
          error VARCHAR NOT NULL,
          recorded_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )

    # Run-level aggregates extracted from summary.json(.gz).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_aggregates (
          run_key VARCHAR PRIMARY KEY,
          theorem_count BIGINT,
          crashed_count BIGINT,
          wild_type_solve_rate DOUBLE,
          intervention_count BIGINT,
          intervention_solve_rate DOUBLE,
          ged_validity JSON,
          aggregates_json JSON
        )
        """
    )

    # Aggregated goal-type x normalized tactic counts from
    # summary.aggregates.goal_type_tactic_matrix.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_type_tactic (
          run_key VARCHAR NOT NULL,
          goal_type VARCHAR NOT NULL,
          tactic_norm VARCHAR NOT NULL,
          tactic_family VARCHAR,
          success BIGINT NOT NULL,
          failure BIGINT NOT NULL,
          blocked BIGINT NOT NULL,
          total BIGINT NOT NULL,
          PRIMARY KEY (run_key, goal_type, tactic_norm)
        )
        """
    )

    # Postprocess provenance report (postprocess_metrics.json).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_postprocess (
          run_key VARCHAR PRIMARY KEY,
          valid BOOLEAN,
          computed_at VARCHAR,
          params JSON,
          inputs JSON,
          metrics JSON,
          runs JSON,
          report_json JSON
        )
        """
    )

    # Goal-outcome aggregates extracted from goal_cache.json(.gz).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_outcome_global_family (
          run_key VARCHAR NOT NULL,
          family_idx INTEGER NOT NULL,
          attempts BIGINT NOT NULL,
          successes BIGINT NOT NULL,
          PRIMARY KEY (run_key, family_idx)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_outcome_sig_family (
          run_key VARCHAR NOT NULL,
          goal_sig VARCHAR NOT NULL,
          family_idx INTEGER NOT NULL,
          attempts BIGINT NOT NULL,
          successes BIGINT NOT NULL,
          PRIMARY KEY (run_key, goal_sig, family_idx)
        )
        """
    )

    # Avoid reserved identifiers (e.g. "references").
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lake_references (
          ref_id VARCHAR PRIMARY KEY,
          kind VARCHAR NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT now(),
          meta JSON,
          artifact_path VARCHAR NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lake_reference_members (
          ref_id VARCHAR NOT NULL,
          run_key VARCHAR NOT NULL,
          PRIMARY KEY (ref_id, run_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS k_reference_score (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR NOT NULL,
          ref_id VARCHAR NOT NULL,
          valid BOOLEAN,
          primary_null_model VARCHAR,
          tau_agent BIGINT,
          tau_blind DOUBLE,
          K DOUBLE,
          score_json JSON,
          PRIMARY KEY (run_key, theorem, variant, ref_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lake_job_runs (
          job_run_id VARCHAR PRIMARY KEY,
          job_name VARCHAR NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT now(),
          status VARCHAR NOT NULL,
          out_dir VARCHAR NOT NULL,
          logs_root VARCHAR,
          selection JSON,
          reference JSON,
          datasets JSON,
          inputs JSON,
          error VARCHAR
        )
        """
    )

    # Extracted facts (Lean-focused today, but schema is generic enough to tolerate nulls).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_wild (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          solved BOOLEAN,
          iterations BIGINT,
          proof_term_hash VARCHAR,
          k_valid BOOLEAN,
          k_null_model VARCHAR,
          k_tau_agent BIGINT,
          k_tau_blind DOUBLE,
          k_K DOUBLE,
          metrics JSON,
          k_json JSON,
          wild_json JSON,
          PRIMARY KEY (run_key, theorem)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_intervention (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          intervention VARCHAR NOT NULL,
          solved BOOLEAN,
          status VARCHAR,
          is_control BOOLEAN,
          baseline_solved BOOLEAN,
          blocked JSON,
          ged_search_value DOUBLE,
          ged_search_norm DOUBLE,
          ged_search_soft_value DOUBLE,
          ged_search_soft_norm DOUBLE,
          k_valid BOOLEAN,
          k_null_model VARCHAR,
          k_tau_agent BIGINT,
          k_tau_blind DOUBLE,
          k_K DOUBLE,
          metrics JSON,
          k_json JSON,
          intervention_json JSON,
          PRIMARY KEY (run_key, theorem, intervention)
        )
        """
    )

    # Per-variant metrics written by the orchestrator (<variant>_metrics.json).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_variant_metrics (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR NOT NULL,

          trajectory_total_iterations BIGINT,
          trajectory_backtrack_count BIGINT,
          trajectory_max_depth_reached BIGINT,
          trajectory_depth_at_solution BIGINT,
          trajectory_unique_goals_visited BIGINT,
          trajectory_tactic_diversity BIGINT,

          detour_total_iterations BIGINT,
          detour_total_attempts BIGINT,
          detour_success_count BIGINT,
          detour_failure_count BIGINT,
          detour_blocked_count BIGINT,
          detour_failure_ratio DOUBLE,
          detour_max_depth BIGINT,
          detour_depth_at_solution BIGINT,
          detour_terminal_iteration BIGINT,

          proof_term_node_count BIGINT,
          proof_term_depth BIGINT,
          proof_term_width BIGINT,

          solution_path_len BIGINT,
          tactic_fingerprint VARCHAR,
          root_goal_sigs JSON,

          metrics_json JSON,
          PRIMARY KEY (run_key, theorem, variant)
        )
        """
    )

    # Per-intervention comparison artifacts (<intervention>_comparison.json).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_intervention_comparison (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          intervention VARCHAR NOT NULL,

          solved BOOLEAN,
          status VARCHAR,
          blocked JSON,

          wild_type_hash VARCHAR,
          intervention_hash VARCHAR,
          hash_mismatch BOOLEAN,

          axiom_delta_count BIGINT,
          axiom_removed_count BIGINT,

          trajectory_iteration_diff BIGINT,
          trajectory_backtrack_diff BIGINT,

          ged_search_value DOUBLE,
          ged_search_norm DOUBLE,
          ged_search_valid BOOLEAN,
          ged_search_trace_source VARCHAR,
          ged_search_trace_completeness VARCHAR,

          ged_search_soft_value DOUBLE,
          ged_search_soft_norm DOUBLE,
          ged_search_soft_valid BOOLEAN,
          ged_search_soft_trace_source VARCHAR,
          ged_search_soft_trace_completeness VARCHAR,

          ged_proof_value DOUBLE,
          ged_proof_norm DOUBLE,
          ged_proof_valid BOOLEAN,
          ged_proof_trace_source VARCHAR,
          ged_proof_trace_completeness VARCHAR,

          ged_trace_value DOUBLE,
          ged_trace_norm DOUBLE,
          ged_trace_valid BOOLEAN,
          ged_trace_trace_source VARCHAR,
          ged_trace_trace_completeness VARCHAR,

          comparison_json JSON,
          PRIMARY KEY (run_key, theorem, intervention)
        )
        """
    )

    # Postprocess-derived per-intervention scalars that are convenient to query cross-run.
    # Source: summary.json(.gz) intervention entries, which are updated in-place by postprocess.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_intervention_postprocess (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          intervention VARCHAR NOT NULL,
          goal_novelty_novel_goal_count BIGINT,
          goal_novelty_dropped_goal_count BIGINT,
          solution_path_soft_distance_value DOUBLE,
          solution_path_soft_distance_valid BOOLEAN,
          solution_path_soft_distance_wild_len BIGINT,
          solution_path_soft_distance_intervention_len BIGINT,
          solution_path_soft_distance_dp_cells BIGINT,
          raw_json JSON,
          PRIMARY KEY (run_key, theorem, intervention)
        )
        """
    )

    # Per-theorem artifact registry (recursive under theorem dirs).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theorem_artifacts (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          artifact_kind VARCHAR NOT NULL,
          rel_path VARCHAR NOT NULL,
          sha256 VARCHAR,
          bytes BIGINT,
          mtime_epoch BIGINT,
          parse_status VARCHAR,
          indexed_at TIMESTAMP NOT NULL DEFAULT now(),
          PRIMARY KEY (run_key, theorem, rel_path)
        )
        """
    )

    # Source-hash watermarking for expensive extractors.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_extract_state (
          run_key VARCHAR NOT NULL,
          rel_path VARCHAR NOT NULL,
          extractor VARCHAR NOT NULL,
          sha256 VARCHAR NOT NULL,
          parse_ok BOOLEAN NOT NULL,
          extracted_at TIMESTAMP NOT NULL DEFAULT now(),
          PRIMARY KEY (run_key, rel_path, extractor)
        )
        """
    )

    # Extracted graph facts from *_graph.json family artifacts.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          graph_kind VARCHAR NOT NULL,
          rel_path VARCHAR NOT NULL,
          node_id VARCHAR NOT NULL,
          goal_sig VARCHAR,
          in_proof BOOLEAN,
          attrs_json JSON,
          source_sha256 VARCHAR,
          PRIMARY KEY (run_key, theorem, rel_path, node_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_edges (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          graph_kind VARCHAR NOT NULL,
          rel_path VARCHAR NOT NULL,
          edge_idx BIGINT NOT NULL,
          src_node_id VARCHAR NOT NULL,
          dst_node_id VARCHAR NOT NULL,
          tactic VARCHAR,
          tactic_family VARCHAR,
          in_proof BOOLEAN,
          attrs_json JSON,
          source_sha256 VARCHAR,
          PRIMARY KEY (run_key, theorem, rel_path, edge_idx)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_extract_errors (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          rel_path VARCHAR NOT NULL,
          stage VARCHAR NOT NULL,
          error VARCHAR NOT NULL,
          recorded_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )

    # Compact MCTS trace summaries (full trace bodies stay in artifacts).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcts_trace_stats (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          rel_path VARCHAR NOT NULL,
          source_sha256 VARCHAR,
          line_count BIGINT NOT NULL,
          bad_json_lines BIGINT NOT NULL,
          event_count BIGINT NOT NULL,
          iteration_event_count BIGINT NOT NULL,
          tactic_attempt_event_count BIGINT NOT NULL,
          max_iteration BIGINT,
          unique_mvar_count BIGINT NOT NULL,
          candidate_total BIGINT NOT NULL,
          candidate_max BIGINT NOT NULL,
          event_counts_json JSON,
          PRIMARY KEY (run_key, theorem, rel_path)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcts_tree_nodes (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          rel_path VARCHAR NOT NULL,
          mvar_id VARCHAR NOT NULL,
          goal_type VARCHAR,
          goal_sig VARCHAR,
          depth BIGINT NOT NULL,
          visit_count BIGINT NOT NULL,
          success_count BIGINT NOT NULL,
          is_terminal BOOLEAN NOT NULL,
          is_dead BOOLEAN NOT NULL,
          expansion_order BIGINT,
          source_sha256 VARCHAR,
          PRIMARY KEY (run_key, theorem, rel_path, mvar_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mcts_tree_edges (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          variant VARCHAR,
          rel_path VARCHAR NOT NULL,
          parent_mvar_id VARCHAR NOT NULL,
          child_mvar_id VARCHAR NOT NULL,
          tactic VARCHAR NOT NULL,
          edge_order BIGINT NOT NULL,
          source_sha256 VARCHAR,
          PRIMARY KEY (run_key, theorem, rel_path, parent_mvar_id, child_mvar_id, tactic)
        )
        """
    )

    # Basin analysis tables (per-theorem multi-seed convergence data).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS basin_runs (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          seeds_requested INTEGER,
          solve_rate DOUBLE,
          unique_structures INTEGER,
          dominant_structure_frequency DOUBLE,
          blind_solve_rate DOUBLE,
          paper_k DOUBLE,
          PRIMARY KEY (run_key, theorem)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS basin_seed (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          seed INTEGER NOT NULL,
          solved BOOLEAN,
          structure_hash VARCHAR,
          iterations_to_solve INTEGER,
          attempts_total INTEGER,
          blind_solved BOOLEAN,
          blind_structure_hash VARCHAR,
          blind_iterations_to_solve INTEGER,
          blind_attempts_total INTEGER,
          PRIMARY KEY (run_key, theorem, seed)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS basin_structure_counts (
          run_key VARCHAR NOT NULL,
          theorem VARCHAR NOT NULL,
          structure_hash VARCHAR NOT NULL,
          count INTEGER NOT NULL,
          PRIMARY KEY (run_key, theorem, structure_hash)
        )
        """
    )

    row = conn.execute("SELECT max(schema_version) FROM schema_meta").fetchone()
    max_ver = row[0] if row else None
    if max_ver is None:
        conn.execute("INSERT INTO schema_meta(schema_version) VALUES (?)", [SCHEMA_VERSION])
    elif max_ver > SCHEMA_VERSION:
        raise RuntimeError(
            f"Lake schema version mismatch: DB has v{max_ver}, code expects v{SCHEMA_VERSION}. "
            "Delete the lake DB to rebuild, or update the code."
        )
    elif max_ver < SCHEMA_VERSION:
        _migrate_run_identity_v11(conn)
        conn.execute("INSERT INTO schema_meta(schema_version) VALUES (?)", [SCHEMA_VERSION])
