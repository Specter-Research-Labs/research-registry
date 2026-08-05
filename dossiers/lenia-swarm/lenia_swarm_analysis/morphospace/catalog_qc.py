from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

POLICY_ID = "shape_behavior_qc_v1"


def _json_array(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


def _json_object(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def ensure_catalog_qc_schema(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(creatures)")
    }
    if "catalog_status" not in columns:
        connection.execute(
            "ALTER TABLE creatures ADD COLUMN catalog_status TEXT NOT NULL DEFAULT 'active'"
        )
    if "quality_flags_json" not in columns:
        connection.execute(
            "ALTER TABLE creatures ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '[]'"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS creature_qc_events (
            id TEXT PRIMARY KEY,
            creature_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            metrics_snapshot_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS creatures_catalog_status ON creatures(catalog_status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS creature_qc_events_creature ON creature_qc_events(creature_id)"
    )


def _attach_audit(connection: sqlite3.Connection, audit_db: Path | None) -> bool:
    if audit_db is None:
        return False
    connection.execute("ATTACH DATABASE ? AS qc_audit", (str(audit_db),))
    return True


def apply_shape_behavior_qc(
    *,
    compendium_path: Path,
    audit_db: Path | None = None,
    policy_id: str = POLICY_ID,
) -> dict[str, Any]:
    connection = sqlite3.connect(compendium_path)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            ensure_catalog_qc_schema(connection)
            has_audit = _attach_audit(connection, audit_db)
            now = datetime.now(UTC).isoformat()

            base_join = (
                "JOIN qc_audit.creature_audit ca ON ca.creature_id = c.id"
                if has_audit
                else ""
            )
            eligible_where = (
                "ca.processing_status = 'complete' AND ca.replay_material_status != 'none'"
                if has_audit
                else "c.metrics_json IS NOT NULL AND json_valid(c.metrics_json) = 1"
            )
            strict_expr = (
                "ca.quality_bucket = 'strict-garbage-candidate'"
                if has_audit
                else "0"
            )

            connection.execute("DROP TABLE IF EXISTS temp.qc_candidates")
            connection.execute(
                f"""
                CREATE TEMP TABLE qc_candidates AS
                SELECT
                    c.id AS creature_id,
                    c.catalog_status AS old_status,
                    c.source_mode,
                    c.taxonomy_method,
                    c.taxonomy_family_id,
                    c.speed_mean,
                    c.path_length,
                    c.score,
                    json_extract(c.metrics_json, '$.largest_component_anisotropy') AS anisotropy,
                    json_extract(c.metrics_json, '$.moment_density') AS density,
                    ({strict_expr}) AS strict_garbage,
                    (
                        json_extract(c.metrics_json, '$.largest_component_anisotropy') >= 0.80
                        AND json_extract(c.metrics_json, '$.moment_density') <= 0.25
                        AND c.speed_mean <= 0.002
                    ) AS severe_stringy_slow,
                    (
                        c.speed_mean <= 0.0015
                        AND c.path_length <= 1.0
                    ) AS low_motion_low_path,
                    (
                        lower(COALESCE(c.taxonomy_method, '')) LIKE '%section2%'
                        OR COALESCE(c.source_mode, '') = 'chakazul-section2'
                        OR COALESCE(c.source_mode, '') LIKE 'track1-named-family%'
                        OR COALESCE(c.taxonomy_family_id, '') LIKE 'section2:%'
                    ) AS protected_named
                FROM creatures c
                {base_join}
                WHERE {eligible_where}
                """
            )

            changed_protected = list(
                connection.execute(
                    """
                    SELECT creature_id, old_status
                    FROM qc_candidates
                    WHERE protected_named
                      AND old_status NOT IN ('protected', 'rejected')
                    """
                )
            )
            changed_quarantine = list(
                connection.execute(
                    """
                    SELECT creature_id, old_status, strict_garbage, severe_stringy_slow,
                           low_motion_low_path, anisotropy, density, speed_mean,
                           path_length, score
                    FROM qc_candidates
                    WHERE NOT protected_named
                      AND old_status NOT IN ('quarantine', 'protected', 'rejected')
                      AND (strict_garbage OR severe_stringy_slow OR low_motion_low_path)
                    """
                )
            )

            connection.executemany(
                """
                INSERT INTO creature_qc_events (
                    id, creature_id, old_status, new_status, policy_id,
                    reasons_json, metrics_snapshot_json, created_at
                ) VALUES (?, ?, ?, 'protected', ?, ?, NULL, ?)
                """,
                [
                    (
                        str(uuid4()),
                        row["creature_id"],
                        row["old_status"],
                        policy_id,
                        _json_array(["named_section2"]),
                        now,
                    )
                    for row in changed_protected
                ],
            )
            connection.executemany(
                """
                INSERT INTO creature_qc_events (
                    id, creature_id, old_status, new_status, policy_id,
                    reasons_json, metrics_snapshot_json, created_at
                ) VALUES (?, ?, ?, 'quarantine', ?, ?, ?, ?)
                """,
                [
                    (
                        str(uuid4()),
                        row["creature_id"],
                        row["old_status"],
                        policy_id,
                        _json_array(_quarantine_reasons(row)),
                        _json_object(
                            {
                                "anisotropy": row["anisotropy"],
                                "density": row["density"],
                                "speedMean": row["speed_mean"],
                                "pathLength": row["path_length"],
                                "score": row["score"],
                            }
                        ),
                        now,
                    )
                    for row in changed_quarantine
                ],
            )

            connection.execute(
                """
                UPDATE creatures
                SET catalog_status = 'protected',
                    quality_flags_json = ?
                WHERE id IN (
                    SELECT creature_id
                    FROM qc_candidates
                    WHERE protected_named
                      AND old_status NOT IN ('rejected')
                )
                """,
                (_json_array(["named_section2"]),),
            )
            for row in changed_quarantine:
                connection.execute(
                    """
                    UPDATE creatures
                    SET catalog_status = 'quarantine',
                        quality_flags_json = ?
                    WHERE id = ?
                    """,
                    (_json_array(_quarantine_reasons(row)), row["creature_id"]),
                )

            schema_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'compendium_meta'"
            ).fetchone()
            if schema_row is not None:
                connection.execute("UPDATE compendium_meta SET schema_version = MAX(schema_version, 15)")

            summary = {
                "compendiumPath": str(compendium_path),
                "auditDb": str(audit_db) if audit_db is not None else None,
                "policyId": policy_id,
                "protectedChanged": len(changed_protected),
                "quarantineChanged": len(changed_quarantine),
                "statusCounts": {
                    row["catalog_status"]: row["n"]
                    for row in connection.execute(
                        """
                        SELECT catalog_status, COUNT(*) AS n
                        FROM creatures
                        GROUP BY catalog_status
                        ORDER BY catalog_status
                        """
                    )
                },
                "quarantineReasonCounts": _reason_counts(connection),
            }
            return summary
    finally:
        connection.close()


def _quarantine_reasons(row: sqlite3.Row) -> list[str]:
    reasons: list[str] = []
    if row["strict_garbage"]:
        reasons.append("strict_garbage")
    if row["severe_stringy_slow"]:
        reasons.append("severe_stringy_slow")
    if row["low_motion_low_path"]:
        reasons.append("low_motion_low_path")
    return reasons or ["quarantine"]


def _reason_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in connection.execute(
        """
        SELECT quality_flags_json, COUNT(*) AS n
        FROM creatures
        WHERE catalog_status = 'quarantine'
        GROUP BY quality_flags_json
        """
    ):
        try:
            reasons = json.loads(row["quality_flags_json"])
        except json.JSONDecodeError:
            reasons = ["invalid_flags_json"]
        for reason in reasons:
            counts[str(reason)] = counts.get(str(reason), 0) + int(row["n"])
    return counts
