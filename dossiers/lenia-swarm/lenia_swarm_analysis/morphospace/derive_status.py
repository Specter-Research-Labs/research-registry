from __future__ import annotations

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import DEVELOPMENTAL_AXIS_IDS, TERMINAL_AXIS_IDS


def derive_status(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        specimen_rows = connection.execute(
            """
            SELECT specimen_id, results_path, export_dir
            FROM specimens
            ORDER BY specimen_id
            """
        ).fetchall()
    else:
        specimen_rows = connection.execute(
            """
            SELECT specimens.specimen_id, specimens.results_path, specimens.export_dir
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            WHERE study_specimens.study_id = ?
            ORDER BY specimen_id
            """,
            [study_id],
        ).fetchall()
    updated = 0
    for specimen_id, results_path, export_dir in specimen_rows:
        terminal_count_row = connection.execute(
            """
            SELECT COUNT(*) FROM specimen_axes
            WHERE specimen_id = ? AND axis_family = 'terminal' AND raw_value IS NOT NULL
            """,
            [specimen_id],
        ).fetchone()
        developmental_count_row = connection.execute(
            """
            SELECT COUNT(*) FROM specimen_axes
            WHERE specimen_id = ? AND axis_family = 'developmental'
            """,
            [specimen_id],
        ).fetchone()
        sample_count_row = connection.execute(
            "SELECT COUNT(*) FROM development_samples WHERE specimen_id = ?",
            [specimen_id],
        ).fetchone()
        if (
            terminal_count_row is None
            or developmental_count_row is None
            or sample_count_row is None
        ):
            raise AssertionError(f"{specimen_id}: count query returned no rows")
        terminal_count = int(terminal_count_row[0])
        developmental_count = int(developmental_count_row[0])
        sample_count = int(sample_count_row[0])
        has_export = bool(results_path or export_dir)
        has_replay = sample_count > 0
        valid_terminal_fingerprint = terminal_count >= len(TERMINAL_AXIS_IDS)
        valid_development_trace = developmental_count >= len(DEVELOPMENTAL_AXIS_IDS)
        atlas_eligible = has_replay and valid_terminal_fingerprint and valid_development_trace
        focal_eligible = atlas_eligible
        reasons = []
        if not has_export:
            reasons.append("missing export")
        if not has_replay:
            reasons.append("missing replay")
        if not valid_terminal_fingerprint:
            reasons.append("missing terminal axes")
        if not valid_development_trace:
            reasons.append("missing developmental axes")
        connection.execute(
            """
            INSERT OR REPLACE INTO specimen_status (
                specimen_id, has_export, has_replay, valid_terminal_fingerprint,
                valid_development_trace, atlas_eligible, focal_eligible, status_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                specimen_id,
                has_export,
                has_replay,
                valid_terminal_fingerprint,
                valid_development_trace,
                atlas_eligible,
                focal_eligible,
                "; ".join(reasons),
            ],
        )
        updated += 1
    return updated
