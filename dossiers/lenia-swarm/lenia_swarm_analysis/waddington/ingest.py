"""Ingest replay-with-capture runs into the dedicated study warehouse.

Each config's replay run is ingested as its own study via the existing replay ingest, which writes
development_samples (full per-step terminal descriptor) and development_sample_axes. We record the
config_hash -> study_id mapping so the landscape stage can pull each rule's trajectories. This
targets a dedicated waddington.duckdb rather than the multi-hundred-GB production warehouse.
"""

from __future__ import annotations

import json

from ..morphospace.ingest_replay import ingest_replay_batch
from ..morphospace.warehouse import connect_database
from .study import CONFIGS, STUDY_ROOT, WAREHOUSE_DB, replay_run_path

STUDY_MAP_PATH = STUDY_ROOT / "study_map.json"


def ingest_all() -> dict[str, str]:
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_database(WAREHOUSE_DB)
    mapping: dict[str, str] = {}
    for config in CONFIGS:
        run = replay_run_path(config.config_hash)
        if not run.exists():
            raise SystemExit(f"missing replay run for {config.label}: {run}")
        study_id = ingest_replay_batch(
            conn,
            development_traces_path=run,
            label=f"waddington-{config.label}",
        )
        count = conn.execute(
            """
            SELECT COUNT(DISTINCT ds.specimen_id)
            FROM development_samples ds
            JOIN study_specimens ss USING (specimen_id)
            WHERE ss.study_id = ?
            """,
            [study_id],
        ).fetchone()[0]
        mapping[config.config_hash] = study_id
        print(f"{config.label}: study {study_id}, {count} specimens with traces")
    conn.close()
    STUDY_MAP_PATH.write_text(json.dumps(mapping, indent=2))
    print(f"wrote {STUDY_MAP_PATH}")
    return mapping


if __name__ == "__main__":
    ingest_all()
