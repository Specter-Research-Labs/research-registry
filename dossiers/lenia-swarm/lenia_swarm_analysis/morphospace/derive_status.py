from __future__ import annotations

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import DEVELOPMENTAL_AXIS_IDS, TERMINAL_AXIS_IDS


def derive_status(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        target_sql = "SELECT specimen_id, results_path, export_dir FROM specimens"
        params: list[str] = []
    else:
        target_sql = """
            SELECT specimens.specimen_id, specimens.results_path, specimens.export_dir
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            WHERE study_specimens.study_id = ?
        """
        params = [study_id]

    updated_row = connection.execute(
        f"SELECT COUNT(*) FROM ({target_sql}) target",
        params,
    ).fetchone()
    if updated_row is None:
        raise AssertionError("status target count query returned no rows")
    updated = int(updated_row[0])

    connection.execute(
        f"""
        INSERT OR REPLACE INTO specimen_status (
            specimen_id, has_export, has_replay, valid_terminal_fingerprint,
            valid_development_trace, atlas_eligible, focal_eligible, status_reason
        )
        WITH target AS ({target_sql}),
        terminal_counts AS (
            SELECT specimen_id, COUNT(*) AS terminal_count
            FROM specimen_axes
            WHERE axis_family = 'terminal' AND raw_value IS NOT NULL
            GROUP BY specimen_id
        ),
        developmental_counts AS (
            SELECT specimen_id, COUNT(*) AS developmental_count
            FROM specimen_axes
            WHERE axis_family = 'developmental'
            GROUP BY specimen_id
        ),
        sample_counts AS (
            SELECT specimen_id, COUNT(*) AS sample_count
            FROM development_samples
            GROUP BY specimen_id
        ),
        status AS (
            SELECT
                target.specimen_id,
                (target.results_path IS NOT NULL OR target.export_dir IS NOT NULL) AS has_export,
                COALESCE(sample_counts.sample_count, 0) > 0 AS has_replay,
                COALESCE(terminal_counts.terminal_count, 0) >= ? AS valid_terminal_fingerprint,
                COALESCE(developmental_counts.developmental_count, 0) >= ?
                    AS valid_development_trace
            FROM target
            LEFT JOIN terminal_counts USING (specimen_id)
            LEFT JOIN developmental_counts USING (specimen_id)
            LEFT JOIN sample_counts USING (specimen_id)
        )
        SELECT
            specimen_id,
            has_export,
            has_replay,
            valid_terminal_fingerprint,
            valid_development_trace,
            has_replay AND valid_terminal_fingerprint AND valid_development_trace AS atlas_eligible,
            has_replay AND valid_terminal_fingerprint AND valid_development_trace AS focal_eligible,
            trim(concat(
                CASE WHEN NOT has_export THEN 'missing export; ' ELSE '' END,
                CASE WHEN NOT has_replay THEN 'missing replay; ' ELSE '' END,
                CASE WHEN NOT valid_terminal_fingerprint THEN 'missing terminal axes; ' ELSE '' END,
                CASE WHEN NOT valid_development_trace
                    THEN 'missing developmental axes; ' ELSE '' END
            ), '; ') AS status_reason
        FROM status
        """,
        [
            *params,
            len(TERMINAL_AXIS_IDS),
            len(DEVELOPMENTAL_AXIS_IDS),
        ],
    )
    return updated
