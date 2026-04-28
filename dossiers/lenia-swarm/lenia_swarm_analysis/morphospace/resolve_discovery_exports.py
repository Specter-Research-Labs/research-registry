from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from .warehouse import upsert_discovery_export_resolution


def _as_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else {}


def _optional_path(raw: Any) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    return Path(raw).expanduser()


def _resolve_export_dir(
    *,
    original_export_dir: Path | None,
    results_path: Path | None,
    search_roots: list[Path],
) -> tuple[Path | None, str]:
    if original_export_dir is not None and original_export_dir.is_absolute():
        if original_export_dir.exists():
            return original_export_dir.resolve(), "absolute_export_dir"
    if original_export_dir is not None and not original_export_dir.is_absolute():
        for root in search_roots:
            candidate = (root / original_export_dir).resolve()
            if candidate.exists():
                return candidate, "search_root"
    if results_path is not None and results_path.exists():
        return results_path.resolve().parent, "results_parent"
    return None, "unresolved"


def resolve_discovery_exports(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None = None,
    search_roots: list[Path] | None = None,
) -> int:
    resolved_roots = [path.expanduser().resolve() for path in (search_roots or [])]
    if study_id is None:
        rows = connection.execute(
            """
            SELECT specimens.specimen_id, study_specimens.study_id, specimens.export_dir,
                   specimens.results_path, specimens.fingerprint_path, specimens.activity_path,
                   specimens.provenance_json
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            JOIN studies ON studies.study_id = study_specimens.study_id
            WHERE studies.study_kind IN ('discovery', 'replay_batch')
            ORDER BY study_specimens.study_id, specimens.specimen_id
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT specimens.specimen_id, study_specimens.study_id, specimens.export_dir,
                   specimens.results_path, specimens.fingerprint_path, specimens.activity_path,
                   specimens.provenance_json
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            WHERE study_specimens.study_id = ?
            ORDER BY specimens.specimen_id
            """,
            [study_id],
        ).fetchall()
    updated = 0
    for (
        specimen_id,
        specimen_study_id,
        export_dir,
        results_path,
        fingerprint_path,
        activity_path,
        provenance_json,
    ) in rows:
        provenance = _as_json(provenance_json)
        original_export_dir = _optional_path(export_dir) or _optional_path(
            provenance.get("sourceExportDir")
        )
        resolved_export_dir, resolution_source = _resolve_export_dir(
            original_export_dir=original_export_dir,
            results_path=_optional_path(results_path),
            search_roots=resolved_roots,
        )
        development_trace_path = _optional_path(provenance.get("developmentTracePath"))
        development_frames_dir = _optional_path(provenance.get("developmentFramesDir"))
        upsert_discovery_export_resolution(
            connection,
            specimen_id=str(specimen_id),
            study_id=str(specimen_study_id),
            original_export_dir=(None if original_export_dir is None else str(original_export_dir)),
            resolved_export_dir=(
                None if resolved_export_dir is None else str(resolved_export_dir)
            ),
            replayable=resolved_export_dir is not None,
            resolution_source=resolution_source,
            metadata_json={
                "resultsPath": results_path,
                "fingerprintPath": fingerprint_path,
                "activityPath": activity_path,
                "developmentTracePath": (
                    None if development_trace_path is None else str(development_trace_path)
                ),
                "developmentFramesDir": (
                    None if development_frames_dir is None else str(development_frames_dir)
                ),
                "mediaOnly": bool(
                    resolved_export_dir is None
                    and (
                        development_trace_path is not None
                        or development_frames_dir is not None
                        or fingerprint_path is not None
                    )
                ),
            },
        )
        updated += 1
    return updated
