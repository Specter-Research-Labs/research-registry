from __future__ import annotations

from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import TERMINAL_AXIS_SPECS

from .warehouse import (
    register_context,
    replace_feature_axes,
    replace_feature_values,
    stable_id,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_observation,
)

SOURCE_ID = "lenia_swarm"
FEATURE_SPACE_ID = "lenia_terminal_v1"
FEATURE_SPACE_LABEL = "Lenia terminal descriptor axes"
AXIS_IDS = tuple(spec["id"] for spec in TERMINAL_AXIS_SPECS)
AXIS_ORDER = {axis_id: index for index, axis_id in enumerate(AXIS_IDS)}


def _study_ids(connection: DuckDBPyConnection, study_id: str | None) -> list[str]:
    if study_id is not None:
        row = connection.execute(
            "SELECT COUNT(*) FROM studies WHERE study_id = ?",
            [study_id],
        ).fetchone()
        if row is None or int(row[0]) == 0:
            raise ValueError(f"unknown study_id: {study_id}")
        return [study_id]
    rows = connection.execute(
        """
        SELECT DISTINCT study_specimens.study_id
        FROM study_specimens
        JOIN specimen_axes USING (specimen_id)
        WHERE specimen_axes.axis_family = 'terminal'
        ORDER BY study_specimens.study_id
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _register_lenia_source_and_space(connection: DuckDBPyConnection) -> None:
    upsert_morphospace_source(
        connection,
        source_id=SOURCE_ID,
        source_kind="synthetic_cellular_automaton",
        label="Lenia synthetic morphospace",
        version_label="v1",
        metadata_json={
            "system": "lenia-swarm",
            "featureSpaceId": FEATURE_SPACE_ID,
        },
    )
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="synthetic_ca_descriptor",
        label=FEATURE_SPACE_LABEL,
        version_label="v1",
        coordinate_policy=(
            "raw_value is the Lenia descriptor value; normalized_value is the "
            "transformed_value from transformation_metrics"
        ),
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "sourceId": SOURCE_ID,
            "axisCount": len(TERMINAL_AXIS_SPECS),
            "normalization": "axis-local descriptor transforms, not corpus z-scores",
        },
    )
    replace_feature_axes(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        axis_rows=[
            {
                "axis_id": spec["id"],
                "axis_index": index,
                "axis_family": "terminal",
                "label": spec["label"],
                "units": "unitless",
                "metadata_json": {
                    "source": spec["source"],
                    "transform": spec["transform"],
                    "positiveMeaning": spec["positiveMeaning"],
                },
            }
            for index, spec in enumerate(TERMINAL_AXIS_SPECS)
        ],
    )


def _specimen_rows(connection: DuckDBPyConnection, *, study_id: str) -> list[tuple[Any, ...]]:
    return connection.execute(
        """
        SELECT DISTINCT
            specimens.specimen_id,
            specimens.recorded_at,
            specimens.results_path,
            specimens.export_dir,
            specimens.activity_path,
            specimens.fingerprint_path,
            specimens.source_kind,
            specimens.source_mode,
            specimens.source_algorithm
        FROM study_specimens
        JOIN specimens USING (specimen_id)
        WHERE study_specimens.study_id = ?
          AND EXISTS (
              SELECT 1
              FROM specimen_axes
              WHERE specimen_axes.specimen_id = specimens.specimen_id
                AND specimen_axes.axis_family = 'terminal'
          )
        ORDER BY specimens.specimen_id
        """,
        [study_id],
    ).fetchall()


def _feature_value_rows(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT axis_id, raw_value, transformed_value
        FROM specimen_axes
        WHERE specimen_id = ?
          AND axis_family = 'terminal'
        """,
        [specimen_id],
    ).fetchall()
    value_rows = [
        {
            "axis_id": str(axis_id),
            "raw_value": raw_value,
            "normalized_value": transformed_value,
            "metadata_json": {"sourceTable": "specimen_axes"},
        }
        for axis_id, raw_value, transformed_value in rows
        if str(axis_id) in AXIS_ORDER
    ]
    return sorted(value_rows, key=lambda row: AXIS_ORDER[str(row["axis_id"])])


def derive_lenia_terminal_features(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None = None,
) -> dict[str, Any]:
    _register_lenia_source_and_space(connection)
    observation_count = 0
    feature_value_count = 0
    study_counts: dict[str, int] = {}

    for resolved_study_id in _study_ids(connection, study_id):
        context_id = register_context(
            connection,
            study_id=resolved_study_id,
            context_kind="baseline",
            label="terminal_descriptor",
            metadata_json={"sourceId": SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
        )
        for row in _specimen_rows(connection, study_id=resolved_study_id):
            (
                specimen_id,
                recorded_at,
                results_path,
                export_dir,
                activity_path,
                fingerprint_path,
                source_kind,
                source_mode,
                source_algorithm,
            ) = row
            observation_id = stable_id(
                SOURCE_ID,
                "observation",
                resolved_study_id,
                specimen_id,
                FEATURE_SPACE_ID,
            )
            source_ref = results_path or export_dir or activity_path or fingerprint_path
            upsert_observation(
                connection,
                observation_id=observation_id,
                specimen_id=str(specimen_id),
                study_id=resolved_study_id,
                source_id=SOURCE_ID,
                context_id=context_id,
                observation_kind="synthetic_ca_terminal_embedding",
                observed_at=recorded_at,
                source_ref=str(source_ref) if source_ref is not None else None,
                payload_json={
                    "featureSpaceId": FEATURE_SPACE_ID,
                    "sourceKind": source_kind,
                    "sourceMode": source_mode,
                    "sourceAlgorithm": source_algorithm,
                },
            )
            value_rows = _feature_value_rows(connection, specimen_id=str(specimen_id))
            replace_feature_values(
                connection,
                observation_id=observation_id,
                feature_space_id=FEATURE_SPACE_ID,
                value_rows=value_rows,
            )
            observation_count += 1
            feature_value_count += len(value_rows)
            study_counts[resolved_study_id] = study_counts.get(resolved_study_id, 0) + 1

    if study_id is not None and observation_count == 0:
        raise ValueError(f"{study_id}: no Lenia terminal axes found")

    return {
        "sourceId": SOURCE_ID,
        "featureSpaceId": FEATURE_SPACE_ID,
        "axisCount": len(TERMINAL_AXIS_SPECS),
        "observationCount": observation_count,
        "featureValueCount": feature_value_count,
        "studyCounts": dict(sorted(study_counts.items())),
    }
