from __future__ import annotations

import importlib.util
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import robust_center_scale, zscore

from .warehouse import (
    register_context,
    register_specimen_study,
    register_study,
    replace_feature_axes,
    replace_sparse_feature_values,
    stable_id,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_observation,
    upsert_specimen,
)

SOURCE_ID = "embryomaker_legacy_snapshots"
FEATURE_SPACE_ID = "embryomaker_legacy_snapshot_v1"
FEATURE_SPACE_LABEL = "EmbryoMaker legacy snapshot summaries"
OBSERVATION_KIND = "embryomaker_legacy_snapshot_summary"

AXIS_SPECS: tuple[dict[str, str], ...] = (
    {"id": "node_count", "label": "Node count", "units": "count"},
    {"id": "cell_count", "label": "Cell count", "units": "count"},
    {"id": "gene_count", "label": "Gene count", "units": "count"},
    {
        "id": "max_distance_from_origin",
        "label": "Maximum distance from origin",
        "units": "model_length",
    },
    {
        "id": "mean_distance_from_origin",
        "label": "Mean distance from origin",
        "units": "model_length",
    },
    {"id": "type1_cell_fraction", "label": "Type 1 cell fraction", "units": "fraction"},
    {"id": "type2_cell_fraction", "label": "Type 2 cell fraction", "units": "fraction"},
)
AXIS_IDS = tuple(spec["id"] for spec in AXIS_SPECS)
_SNAPSHOT_SUFFIXES = (".output.dat", ".dat")
_FAMILY_RE = re.compile(r"^(IC\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class EmbryoMakerSnapshotRecord:
    path: Path
    family: str
    run_name: str
    getot: int
    rtime: float
    node_count: int
    cell_count: int
    gene_count: int
    max_distance_from_origin: float
    mean_distance_from_origin: float
    type1_cell_count: int | None
    type2_cell_count: int | None

    @property
    def values(self) -> dict[str, float]:
        cell_count = max(float(self.cell_count), 1.0)
        return {
            "node_count": float(self.node_count),
            "cell_count": float(self.cell_count),
            "gene_count": float(self.gene_count),
            "max_distance_from_origin": self.max_distance_from_origin,
            "mean_distance_from_origin": self.mean_distance_from_origin,
            "type1_cell_fraction": (
                0.0 if self.type1_cell_count is None else self.type1_cell_count / cell_count
            ),
            "type2_cell_fraction": (
                0.0 if self.type2_cell_count is None else self.type2_cell_count / cell_count
            ),
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_legacy_snapshot_module() -> ModuleType:
    module_path = _repo_root() / "addenda/embryomaker-v2/embryomaker_v2/legacy_snapshot.py"
    if not module_path.exists():
        raise FileNotFoundError(
            "EmbryoMaker parser is missing; expected "
            f"{module_path}. Keep the addenda/embryomaker-v2 parser available."
        )
    spec = importlib.util.spec_from_file_location(
        "_specter_embryomaker_legacy_snapshot",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load EmbryoMaker parser from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def iter_embryomaker_snapshot_paths(
    roots: Iterable[Path],
    *,
    limit: int | None = None,
) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        resolved_root = root.resolve()
        if resolved_root.is_file():
            paths.append(resolved_root)
            continue
        if not resolved_root.is_dir():
            raise FileNotFoundError(resolved_root)
        for path in resolved_root.rglob("*"):
            if not path.is_file() or path.name == "name.dat":
                continue
            if any(path.name.endswith(suffix) for suffix in _SNAPSHOT_SUFFIXES):
                paths.append(path.resolve())
    unique_paths = sorted(dict.fromkeys(paths))
    return unique_paths[:limit] if limit is not None else unique_paths


def _family_label(path: Path) -> str:
    for candidate in (path.name, path.parent.name):
        match = _FAMILY_RE.match(candidate)
        if match is not None:
            return match.group(1).upper()
    return path.parent.name


def _cheap_summary(module: ModuleType, path: Path) -> EmbryoMakerSnapshotRecord:
    snapshot = module.parse_legacy_snapshot(path)
    max_distance = 0.0
    distance_sum = 0.0
    for node in snapshot.nodes:
        distance = math.sqrt((node.x * node.x) + (node.y * node.y) + (node.z * node.z))
        max_distance = max(max_distance, distance)
        distance_sum += distance

    type1_cell_count: int | None
    type2_cell_count: int | None
    try:
        cell_types = module.extract_legacy_cell_types(snapshot)
    except ValueError:
        type1_cell_count = None
        type2_cell_count = None
    else:
        type1_cell_count = sum(1 for value in cell_types if value == 1)
        type2_cell_count = sum(1 for value in cell_types if value == 2)

    return EmbryoMakerSnapshotRecord(
        path=path,
        family=_family_label(path),
        run_name=str(snapshot.run_name),
        getot=int(snapshot.getot),
        rtime=float(snapshot.rtime),
        node_count=int(snapshot.node_count),
        cell_count=int(snapshot.cell_count),
        gene_count=int(snapshot.gene_count),
        max_distance_from_origin=max_distance,
        mean_distance_from_origin=distance_sum / max(float(snapshot.node_count), 1.0),
        type1_cell_count=type1_cell_count,
        type2_cell_count=type2_cell_count,
    )


def load_embryomaker_snapshot_record(path: Path) -> EmbryoMakerSnapshotRecord:
    return _cheap_summary(_load_legacy_snapshot_module(), path.resolve())


def load_embryomaker_node_points(path: Path) -> list[tuple[float, float, float]]:
    module = _load_legacy_snapshot_module()
    snapshot = module.parse_legacy_snapshot(path.resolve())
    return [(float(node.x), float(node.y), float(node.z)) for node in snapshot.nodes]


def _axis_stats(records: list[EmbryoMakerSnapshotRecord]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for axis_id in AXIS_IDS:
        values = [record.values[axis_id] for record in records]
        center, scale = robust_center_scale(values)
        stats[axis_id] = {
            "center": center,
            "scale": scale,
            "min": min(values),
            "max": max(values),
        }
    return stats


def _source_root_metadata(snapshot_roots: list[Path]) -> dict[str, Any]:
    return {
        "snapshotRoots": [str(path.resolve()) for path in snapshot_roots],
        "parser": "addenda/embryomaker-v2/embryomaker_v2/legacy_snapshot.py",
    }


def _existing_embryomaker_study(
    connection: DuckDBPyConnection,
) -> tuple[str, str] | None:
    rows = connection.execute(
        """
        SELECT s.study_id, s.label
        FROM studies AS s
        WHERE s.study_kind = 'embryomaker_morphospace'
          AND EXISTS (
              SELECT 1
              FROM observations AS o
              WHERE o.study_id = s.study_id
                AND o.source_id = ?
                AND o.observation_kind = ?
          )
        ORDER BY s.created_at, s.study_id
        """,
        [SOURCE_ID, OBSERVATION_KIND],
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        study_ids = ", ".join(str(row[0]) for row in rows)
        raise ValueError(
            "multiple EmbryoMaker snapshot studies already exist; "
            f"pass --label to select one or clean the duplicate studies: {study_ids}"
        )
    return str(rows[0][0]), str(rows[0][1])


def ingest_embryomaker_snapshots(
    connection: DuckDBPyConnection,
    *,
    snapshot_roots: list[Path],
    label: str | None = None,
    limit: int | None = None,
    skip_invalid: bool = False,
) -> dict[str, Any]:
    if not snapshot_roots:
        raise ValueError("at least one snapshot root is required")
    snapshot_paths = iter_embryomaker_snapshot_paths(snapshot_roots, limit=limit)
    if not snapshot_paths:
        raise ValueError("no EmbryoMaker snapshot files found")

    module = _load_legacy_snapshot_module()
    records: list[EmbryoMakerSnapshotRecord] = []
    skipped: list[dict[str, str]] = []
    for path in snapshot_paths:
        try:
            records.append(_cheap_summary(module, path))
        except Exception as exc:
            if not skip_invalid:
                raise ValueError(f"{path}: failed to parse EmbryoMaker snapshot: {exc}") from exc
            skipped.append({"path": str(path), "error": str(exc)})
    if not records:
        raise ValueError("no parseable EmbryoMaker snapshot files found")
    stats = _axis_stats(records)
    family_counts: dict[str, int] = {}
    for record in records:
        family_counts[record.family] = family_counts.get(record.family, 0) + 1

    existing_study = None if label is not None else _existing_embryomaker_study(connection)
    study_label = (
        label
        if label is not None
        else (
            existing_study[1]
            if existing_study is not None
            else "EmbryoMaker legacy snapshot morphospace"
        )
    )
    study_id = register_study(
        connection,
        study_kind="embryomaker_morphospace",
        label=study_label,
        study_id=None if existing_study is None else existing_study[0],
        metadata_json={
            "sourceId": SOURCE_ID,
            "featureSpaceId": FEATURE_SPACE_ID,
            "snapshotCount": len(records),
            "skippedSnapshotCount": len(skipped),
            "familyCounts": dict(sorted(family_counts.items())),
            "skippedSnapshots": skipped[:20],
            **_source_root_metadata(snapshot_roots),
        },
    )
    upsert_morphospace_source(
        connection,
        source_id=SOURCE_ID,
        source_kind="embryomaker_legacy_snapshot_corpus",
        label="EmbryoMaker legacy artifact morphospace",
        version_label="legacy-output-dat",
        metadata_json=_source_root_metadata(snapshot_roots),
    )
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="embryomaker_native_snapshot_descriptor",
        storage_mode="sparse_values",
        label=FEATURE_SPACE_LABEL,
        version_label="v1",
        coordinate_policy=(
            "raw_value is a cheap snapshot descriptor; normalized_value is robust "
            "z-score across the imported EmbryoMaker snapshot corpus"
        ),
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "sourceId": SOURCE_ID,
            "axisCount": len(AXIS_IDS),
            "familyCounts": dict(sorted(family_counts.items())),
        },
    )
    replace_feature_axes(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        axis_rows=[
            {
                "axis_id": spec["id"],
                "axis_index": index,
                "axis_family": "embryomaker_legacy_snapshot",
                "label": spec["label"],
                "units": spec["units"],
                "metadata_json": {
                    "robustCenter": stats[spec["id"]]["center"],
                    "robustScale": stats[spec["id"]]["scale"],
                    "rawMin": stats[spec["id"]]["min"],
                    "rawMax": stats[spec["id"]]["max"],
                },
            }
            for index, spec in enumerate(AXIS_SPECS)
        ],
    )

    context_id = register_context(
        connection,
        study_id=study_id,
        context_kind="baseline",
        label="legacy_snapshot",
        metadata_json={"sourceId": SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
    )
    for record in records:
        source_ref = str(record.path)
        specimen_id = stable_id(SOURCE_ID, "specimen", source_ref)
        observation_id = stable_id(SOURCE_ID, "observation", study_id, source_ref)
        upsert_specimen(
            connection,
            {
                "specimen_id": specimen_id,
                "source_creature_id": record.path.stem,
                "study_id": study_id,
                "source_kind": "embryomaker",
                "source_mode": record.family,
                "source_algorithm": "legacy_embryomaker",
                "family_kind": "embryomaker_artifact",
                "regime_family": "developmental_artifact",
                "geometry_family": "3d_node_point_cloud",
                "canonical_family": record.family,
                "results_path": source_ref,
                "provenance_json": {
                    "sourceId": SOURCE_ID,
                    "featureSpaceId": FEATURE_SPACE_ID,
                    "snapshotPath": source_ref,
                    "summary": asdict(record) | {"path": source_ref},
                },
            },
        )
        register_specimen_study(connection, study_id=study_id, specimen_id=specimen_id)
        upsert_observation(
            connection,
            observation_id=observation_id,
            specimen_id=specimen_id,
            study_id=study_id,
            source_id=SOURCE_ID,
            context_id=context_id,
            observation_kind=OBSERVATION_KIND,
            step=record.getot,
            source_ref=source_ref,
            payload_json={
                "featureSpaceId": FEATURE_SPACE_ID,
                "snapshotPath": source_ref,
                "family": record.family,
                "runName": record.run_name,
                "summary": asdict(record) | {"path": source_ref},
            },
        )
        replace_sparse_feature_values(
            connection,
            observation_id=observation_id,
            feature_space_id=FEATURE_SPACE_ID,
            value_rows=[
                {
                    "axis_id": axis_id,
                    "raw_value": record.values[axis_id],
                    "normalized_value": zscore(
                        record.values[axis_id],
                        center=stats[axis_id]["center"],
                        scale=stats[axis_id]["scale"],
                    ),
                    "metadata_json": {"normalization": "robust_zscore"},
                }
                for axis_id in AXIS_IDS
            ],
        )

    return {
        "studyId": study_id,
        "sourceId": SOURCE_ID,
        "featureSpaceId": FEATURE_SPACE_ID,
        "snapshotRoots": [str(path.resolve()) for path in snapshot_roots],
        "snapshotCount": len(records),
        "skippedSnapshotCount": len(skipped),
        "observationCount": len(records),
        "axisCount": len(AXIS_IDS),
        "featureValueCount": len(records) * len(AXIS_IDS),
        "familyCounts": dict(sorted(family_counts.items())),
        "skippedSnapshots": skipped[:20],
    }
