from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from .warehouse import (
    ingest_json_object_artifact,
    register_artifact,
    register_context,
    register_specimen_study,
    register_study,
    replace_feature_axes,
    replace_feature_values,
    stable_id,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_observation,
    upsert_specimen,
)

SOURCE_ID = "dryad_fish_body_shape_20240112"
FEATURE_SPACE_ID = "fish_gpa_pc_v1"
FEATURE_SPACE_LABEL = "Fish SlicerMorph GPA principal components"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _axis_id(label: str) -> str:
    match = re.fullmatch(r"PC\s+(\d+)", label.strip())
    if not match:
        raise ValueError(f"unsupported PC axis label: {label!r}")
    return f"pc_{int(match.group(1)):02d}"


def _read_eigenvalues(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            if len(row) != 2:
                raise ValueError(f"{path}: expected two columns per eigenvalue row")
            values[_axis_id(row[0])] = float(row[1])
    return values


def _read_pc_scores(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames or fieldnames[0] != "Sample_name":
            raise ValueError(f"{path}: first column must be Sample_name")
        axis_labels = fieldnames[1:]
        axis_ids = [_axis_id(label) for label in axis_labels]
        rows: list[dict[str, Any]] = []
        for index, row in enumerate(reader):
            sample_name = row.get("Sample_name")
            if not sample_name:
                raise ValueError(f"{path}: row {index + 2} is missing Sample_name")
            values = {
                axis_id: float(row[axis_label])
                for axis_id, axis_label in zip(axis_ids, axis_labels, strict=True)
            }
            rows.append(
                {
                    "sample_name": sample_name,
                    "values": values,
                    "source_row_index": index,
                }
            )
    return axis_ids, rows


def _population_stats(
    rows: list[dict[str, Any]],
    axis_ids: list[str],
) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for axis_id in axis_ids:
        values = [float(row["values"][axis_id]) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        stats[axis_id] = (mean, math.sqrt(variance))
    return stats


def _species_label(sample_name: str) -> str | None:
    tokens = re.findall(r"[A-Za-z]+", sample_name)
    if len(tokens) < 2:
        return None
    genus, species = tokens[0], tokens[1]
    if genus[0].isupper() and species.islower():
        return f"{genus} {species}"
    return None


def _register_dataset_artifacts(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    dataset_root: Path,
    source_manifest: dict[str, Any],
) -> None:
    candidate_paths = [
        ("dryad_dataset_archive", dataset_root / "raw/doi_10_5061_dryad_n2z34tn2t__v20240112.zip"),
        ("dryad_source_manifest", dataset_root / "provenance/source.json"),
        ("dryad_files_api", dataset_root / "provenance/dryad-files-api.json"),
        (
            "dryad_fish_pc_scores",
            dataset_root / "extracted/gpa/Slicer_GPA_output/pcScores.csv",
        ),
        (
            "dryad_fish_eigenvalues",
            dataset_root / "extracted/gpa/Slicer_GPA_output/eigenvalues.csv",
        ),
        (
            "dryad_fish_output_data",
            dataset_root / "extracted/gpa/Slicer_GPA_output/OutputData.csv",
        ),
        ("dryad_fish_family_tree", dataset_root / "extracted/family_skeletal.tre"),
    ]
    for artifact_kind, path in candidate_paths:
        if not path.exists():
            continue
        artifact_id = register_artifact(
            connection,
            study_id=study_id,
            artifact_kind=artifact_kind,
            path=path,
            metadata_json={"datasetId": source_manifest.get("dataset_id")},
        )
        if artifact_kind == "dryad_source_manifest":
            ingest_json_object_artifact(
                connection,
                artifact_id=artifact_id,
                object_kind="dryad_source_manifest",
                payload=source_manifest,
            )


def ingest_dryad_fish_body_shape(
    connection: DuckDBPyConnection,
    *,
    dataset_root: Path,
    label: str | None = None,
) -> dict[str, Any]:
    root = dataset_root.resolve()
    source_manifest = _read_json(root / "provenance/source.json")
    pc_scores_path = root / "extracted/gpa/Slicer_GPA_output/pcScores.csv"
    eigenvalues_path = root / "extracted/gpa/Slicer_GPA_output/eigenvalues.csv"
    if not pc_scores_path.exists():
        raise FileNotFoundError(pc_scores_path)
    if not eigenvalues_path.exists():
        raise FileNotFoundError(eigenvalues_path)

    axis_ids, rows = _read_pc_scores(pc_scores_path)
    if not rows:
        raise ValueError(f"{pc_scores_path}: no specimen rows found")
    eigenvalues = _read_eigenvalues(eigenvalues_path)
    missing_eigenvalues = sorted(set(axis_ids).difference(eigenvalues))
    if missing_eigenvalues:
        raise ValueError(f"{eigenvalues_path}: missing eigenvalues for {missing_eigenvalues}")

    study_label = label or "Dryad fish body-shape GPA morphospace"
    study_id = register_study(
        connection,
        study_kind="biological_morphospace",
        label=study_label,
        metadata_json={
            "sourceId": SOURCE_ID,
            "datasetRoot": str(root),
            "doi": source_manifest.get("doi", "10.5061/dryad.n2z34tn2t"),
            "featureSpaceId": FEATURE_SPACE_ID,
        },
    )
    upsert_morphospace_source(
        connection,
        source_id=SOURCE_ID,
        source_kind="biological_landmark_dataset",
        label=str(
            source_manifest.get(
                "title",
                "Phylogenetic structure of body shape in a diverse inland ichthyofauna",
            )
        ),
        version_label=str(source_manifest.get("publication_date", "2024-01-12")),
        doi=str(source_manifest.get("doi", "10.5061/dryad.n2z34tn2t")),
        url=str(
            source_manifest.get(
                "url",
                "https://datadryad.org/dataset/doi:10.5061/dryad.n2z34tn2t",
            )
        ),
        license=str(source_manifest.get("license", "CC0-1.0")),
        metadata_json={
            "authors": source_manifest.get("authors", []),
            "apiVersionId": source_manifest.get("api_version_id"),
            "datasetId": source_manifest.get("dataset_id"),
        },
    )
    _register_dataset_artifacts(
        connection,
        study_id=study_id,
        dataset_root=root,
        source_manifest=source_manifest,
    )

    eigenvalue_total = sum(max(0.0, value) for value in eigenvalues.values())
    stats = _population_stats(rows, axis_ids)
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="geometric_morphometrics",
        label=FEATURE_SPACE_LABEL,
        version_label="v1",
        coordinate_policy="SlicerMorph GPA PC scores; normalized_value is corpus z-score",
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "sourceId": SOURCE_ID,
            "axisCount": len(axis_ids),
            "normalization": "per-axis population z-score within imported Dryad corpus",
        },
    )
    replace_feature_axes(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        axis_rows=[
            {
                "axis_id": axis_id,
                "axis_index": index,
                "axis_family": "gpa_pc",
                "label": f"PC {index + 1}",
                "units": "unitless",
                "metadata_json": {
                    "eigenvalue": eigenvalues[axis_id],
                    "explainedVariance": (
                        max(0.0, eigenvalues[axis_id]) / eigenvalue_total
                        if eigenvalue_total
                        else None
                    ),
                    "mean": stats[axis_id][0],
                    "standardDeviation": stats[axis_id][1],
                },
            }
            for index, axis_id in enumerate(axis_ids)
        ],
    )
    context_id = register_context(
        connection,
        study_id=study_id,
        context_kind="baseline",
        label="gpa_baseline",
        metadata_json={"sourceId": SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
    )

    for row in rows:
        sample_name = str(row["sample_name"])
        specimen_id = stable_id(SOURCE_ID, "specimen", sample_name)
        observation_id = stable_id(
            SOURCE_ID,
            "observation",
            study_id,
            sample_name,
            FEATURE_SPACE_ID,
        )
        upsert_specimen(
            connection,
            {
                "specimen_id": specimen_id,
                "source_creature_id": sample_name,
                "study_id": study_id,
                "source_kind": "biological",
                "source_mode": "dryad_fish_body_shape",
                "source_algorithm": "slicermorph_gpa",
                "family_kind": "actinopterygian_fish",
                "regime_family": "adult_body_shape",
                "geometry_family": "3d_landmark_gpa",
                "canonical_family": _species_label(sample_name),
                "recorded_at": source_manifest.get("publication_date", "2024-01-12"),
                "results_path": str(pc_scores_path),
                "provenance_json": {
                    "sourceId": SOURCE_ID,
                    "sampleName": sample_name,
                    "doi": source_manifest.get("doi", "10.5061/dryad.n2z34tn2t"),
                    "featureSpaceId": FEATURE_SPACE_ID,
                    "sourceRowIndex": row["source_row_index"],
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
            observation_kind="geometric_morphometric_embedding",
            observed_at=source_manifest.get("publication_date", "2024-01-12"),
            source_ref=f"{pc_scores_path}#{row['source_row_index'] + 2}",
            payload_json={
                "sampleName": sample_name,
                "featureSpaceId": FEATURE_SPACE_ID,
                "sourceRowIndex": row["source_row_index"],
            },
        )
        replace_feature_values(
            connection,
            observation_id=observation_id,
            feature_space_id=FEATURE_SPACE_ID,
            value_rows=[
                {
                    "axis_id": axis_id,
                    "raw_value": float(row["values"][axis_id]),
                    "normalized_value": (
                        0.0
                        if stats[axis_id][1] == 0.0
                        else (float(row["values"][axis_id]) - stats[axis_id][0])
                        / stats[axis_id][1]
                    ),
                    "metadata_json": {"sourceAxis": f"PC {index + 1}"},
                }
                for index, axis_id in enumerate(axis_ids)
            ],
        )

    return {
        "studyId": study_id,
        "sourceId": SOURCE_ID,
        "featureSpaceId": FEATURE_SPACE_ID,
        "datasetRoot": str(root),
        "specimenCount": len(rows),
        "observationCount": len(rows),
        "axisCount": len(axis_ids),
        "featureValueCount": len(rows) * len(axis_ids),
    }
