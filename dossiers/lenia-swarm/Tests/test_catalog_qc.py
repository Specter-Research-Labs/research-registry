from __future__ import annotations

import json
import sqlite3

from lenia_swarm_analysis.morphospace.catalog_qc import apply_shape_behavior_qc


def test_apply_shape_behavior_qc_marks_protected_and_quarantine(tmp_path):
    compendium = tmp_path / "compendium.sqlite"
    audit = tmp_path / "audit.sqlite"
    con = sqlite3.connect(compendium)
    con.executescript(
        """
        CREATE TABLE compendium_meta(schema_version INTEGER NOT NULL);
        INSERT INTO compendium_meta VALUES (14);
        CREATE TABLE creatures(
            id TEXT PRIMARY KEY,
            source_mode TEXT,
            taxonomy_method TEXT,
            taxonomy_family_id TEXT,
            speed_mean REAL,
            path_length REAL,
            score REAL,
            metrics_json TEXT
        );
        """
    )
    con.executemany(
        """
        INSERT INTO creatures(
            id, source_mode, taxonomy_method, taxonomy_family_id,
            speed_mean, path_length, score, metrics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "active-1",
                "track1-harvest",
                None,
                None,
                0.02,
                4.0,
                5.0,
                json.dumps({"largest_component_anisotropy": 0.2, "moment_density": 0.6}),
            ),
            (
                "quarantine-1",
                "track1-harvest",
                None,
                None,
                0.0005,
                0.2,
                1.0,
                json.dumps({"largest_component_anisotropy": 0.92, "moment_density": 0.14}),
            ),
            (
                "protected-1",
                "track1-named-family",
                None,
                None,
                0.0005,
                0.2,
                1.0,
                json.dumps({"largest_component_anisotropy": 0.92, "moment_density": 0.14}),
            ),
        ],
    )
    con.commit()
    con.close()

    audit_con = sqlite3.connect(audit)
    audit_con.executescript(
        """
        CREATE TABLE creature_audit(
            creature_id TEXT PRIMARY KEY,
            processing_status TEXT NOT NULL,
            replay_material_status TEXT NOT NULL,
            quality_bucket TEXT NOT NULL
        );
        """
    )
    audit_con.executemany(
        "INSERT INTO creature_audit VALUES (?, 'complete', 'export+specimen', 'usable')",
        [("active-1",), ("quarantine-1",), ("protected-1",)],
    )
    audit_con.commit()
    audit_con.close()

    summary = apply_shape_behavior_qc(compendium_path=compendium, audit_db=audit)
    assert summary["statusCounts"] == {
        "active": 1,
        "protected": 1,
        "quarantine": 1,
    }
    assert summary["protectedChanged"] == 1
    assert summary["quarantineChanged"] == 1

    second = apply_shape_behavior_qc(compendium_path=compendium, audit_db=audit)
    assert second["protectedChanged"] == 0
    assert second["quarantineChanged"] == 0

    con = sqlite3.connect(compendium)
    assert con.execute("SELECT schema_version FROM compendium_meta").fetchone()[0] == 15
    assert con.execute("SELECT COUNT(*) FROM creature_qc_events").fetchone()[0] == 2
    visible_ids = {
        row[0]
        for row in con.execute(
            "SELECT id FROM creatures WHERE catalog_status IN ('active', 'protected')"
        )
    }
    assert visible_ids == {"active-1", "protected-1"}
    con.close()
