from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from duckdb import DuckDBPyConnection

from .warehouse import (
    ingest_json_object_artifact,
    register_artifact,
    register_study,
    upsert_morphospace_source,
)

SOURCE_ID = "external_morphospace_reference_bundles"


def _bundle_files(bundle_root: Path) -> list[Path]:
    root = bundle_root.resolve()
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(root)
    return sorted(path.resolve() for path in root.rglob("*") if path.is_file())


def _json_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _npy_metadata(path: Path) -> dict[str, Any]:
    array = np.load(path, mmap_mode="r")
    return {
        "arrayShape": [int(value) for value in array.shape],
        "arrayDtype": str(array.dtype),
    }


def _artifact_metadata(path: Path, bundle_root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(bundle_root) if bundle_root.is_dir() else Path(path.name)
    suffix = path.suffix.lower()
    metadata: dict[str, Any] = {
        "sourceId": SOURCE_ID,
        "relativePath": relative_path.as_posix(),
    }
    if suffix == ".npy":
        metadata.update(_npy_metadata(path))
    return metadata


def import_reference_bundle(
    connection: DuckDBPyConnection,
    *,
    bundle_root: Path,
    label: str | None = None,
) -> dict[str, Any]:
    root = bundle_root.resolve()
    files = _bundle_files(root)
    if not files:
        raise ValueError(f"{root}: no files found")

    study_id = register_study(
        connection,
        study_kind="morphospace_reference_bundle",
        label=label or root.name,
        metadata_json={
            "sourceId": SOURCE_ID,
            "bundleRoot": str(root),
            "artifactCount": len(files),
        },
    )
    upsert_morphospace_source(
        connection,
        source_id=SOURCE_ID,
        source_kind="external_reference_bundle",
        label="External morphospace reference bundles",
        version_label="v1",
        metadata_json={"bundleRoot": str(root)},
    )

    json_object_count = 0
    npy_array_count = 0
    artifact_kinds: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower()
        artifact_kind = f"reference_{suffix.lstrip('.') or 'file'}"
        artifact_kinds[artifact_kind] = artifact_kinds.get(artifact_kind, 0) + 1
        if suffix == ".npy":
            npy_array_count += 1
        artifact_id = register_artifact(
            connection,
            study_id=study_id,
            artifact_kind=artifact_kind,
            path=path,
            metadata_json=_artifact_metadata(path, root),
        )
        if suffix == ".json":
            ingest_json_object_artifact(
                connection,
                artifact_id=artifact_id,
                object_kind="reference_json",
                object_key=path.relative_to(root).as_posix() if root.is_dir() else path.name,
                payload=_json_payload(path),
            )
            json_object_count += 1

    return {
        "studyId": study_id,
        "sourceId": SOURCE_ID,
        "bundleRoot": str(root),
        "artifactCount": len(files),
        "jsonObjectCount": json_object_count,
        "npyArrayCount": npy_array_count,
        "artifactKinds": dict(sorted(artifact_kinds.items())),
    }
