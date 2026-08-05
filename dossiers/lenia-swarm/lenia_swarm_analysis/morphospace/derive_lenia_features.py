from __future__ import annotations

from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import TERMINAL_AXIS_SPECS

from .warehouse import (
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
    mark_derived_artifact_state,
    register_context,
    register_feature_calibration,
    replace_feature_axes,
    upsert_feature_space,
    upsert_morphospace_source,
    validate_dense_feature_space,
)

SOURCE_ID = "lenia_swarm"
FEATURE_SPACE_ID = "lenia_terminal_v2_torus_peak_u8"
FEATURE_SPACE_LABEL = "Lenia terminal descriptor axes"
AXIS_IDS = tuple(spec["id"] for spec in TERMINAL_AXIS_SPECS)


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
        SELECT DISTINCT specimens.study_id
        FROM specimens
        JOIN studies ON studies.study_id = specimens.study_id
        JOIN specimen_axes USING (specimen_id)
        WHERE specimen_axes.axis_family = 'terminal'
          AND specimens.descriptor_version = ?
          AND specimens.terminal_version = ?
          AND specimens.normalization_policy = ?
          AND EXISTS (
              SELECT 1 FROM study_specimens
              WHERE study_specimens.study_id = specimens.study_id
                AND study_specimens.specimen_id = specimens.specimen_id
          )
        ORDER BY specimens.study_id
        """,
        [DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY],
    ).fetchall()
    return [str(row[0]) for row in rows]


def _upsert_lenia_feature_space(
    connection: DuckDBPyConnection,
    *,
    calibration_id: str | None,
) -> None:
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="synthetic_ca_descriptor",
        storage_mode="dense_vectors",
        label=FEATURE_SPACE_LABEL,
        version_label="v2",
        coordinate_policy=(
            "raw_value is the Lenia descriptor value; normalized_value is the "
            "transformed_value from transformation_metrics"
        ),
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "sourceId": SOURCE_ID,
            "axisCount": len(TERMINAL_AXIS_SPECS),
            "normalization": "axis-local descriptor transforms, not corpus z-scores",
            "descriptorVersion": DESCRIPTOR_VERSION,
            "terminalVersion": TERMINAL_VERSION,
            "normalizationPolicy": NORMALIZATION_POLICY,
            "activeCalibrationId": calibration_id,
        },
    )


def _register_lenia_source_and_space(connection: DuckDBPyConnection) -> None:
    upsert_morphospace_source(
        connection,
        source_id=SOURCE_ID,
        source_kind="synthetic_cellular_automaton",
        label="Lenia synthetic morphospace",
        version_label="v2",
        metadata_json={
            "system": "lenia-swarm",
            "featureSpaceId": FEATURE_SPACE_ID,
        },
    )
    _upsert_lenia_feature_space(connection, calibration_id=None)
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


def derive_lenia_terminal_features(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None = None,
) -> dict[str, Any]:
    _register_lenia_source_and_space(connection)
    calibration_id = register_feature_calibration(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        calibration_version="axis-local-v2",
        axis_order=AXIS_IDS,
        reference_query={
            "kind": "descriptor-contract",
            "descriptorVersion": DESCRIPTOR_VERSION,
            "terminalVersion": TERMINAL_VERSION,
            "normalizationPolicy": NORMALIZATION_POLICY,
        },
        axis_transforms={
            str(spec["id"]): str(spec["transform"]) for spec in TERMINAL_AXIS_SPECS
        },
        metadata_json={"frozen": True, "axisOrder": list(AXIS_IDS)},
    )
    _upsert_lenia_feature_space(connection, calibration_id=calibration_id)
    mark_derived_artifact_state(
        connection,
        artifact_kind="feature-space",
        feature_space_id=FEATURE_SPACE_ID,
        descriptor_version=DESCRIPTOR_VERSION,
        normalization_policy=NORMALIZATION_POLICY,
        status="invalid",
        reason="native v2 terminal feature vectors are being rebuilt",
        metadata_json={"calibrationId": calibration_id, "lifecycle": "building"},
    )
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
        observation_count_row = connection.execute(
            """
            SELECT COUNT(DISTINCT specimens.specimen_id)
            FROM specimens
            JOIN specimen_axes USING (specimen_id)
            WHERE specimens.study_id = ?
              AND EXISTS (
                  SELECT 1 FROM study_specimens
                  WHERE study_specimens.study_id = specimens.study_id
                    AND study_specimens.specimen_id = specimens.specimen_id
              )
              AND specimen_axes.axis_family = 'terminal'
              AND specimens.descriptor_version = ?
              AND specimens.terminal_version = ?
              AND specimens.normalization_policy = ?
            """,
            [resolved_study_id, DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY],
        ).fetchone()
        resolved_observation_count = int(observation_count_row[0]) if observation_count_row else 0

        observation_id_sql = """
            substr(sha256(concat(
                ?, chr(0), 'observation', chr(0), ?, chr(0),
                specimens.specimen_id, chr(0), ?, chr(0)
            )), 1, 24)
        """
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE tmp_lenia_terminal_observations AS
            SELECT DISTINCT
                {observation_id_sql} AS observation_id,
                specimens.specimen_id,
                specimens.recorded_at,
                coalesce(
                    specimens.results_path,
                    specimens.export_dir,
                    specimens.activity_path,
                    specimens.fingerprint_path
                ) AS source_ref,
                specimens.source_kind,
                specimens.source_mode,
                specimens.source_algorithm
            FROM specimens
            JOIN specimen_axes USING (specimen_id)
            WHERE specimens.study_id = ?
              AND EXISTS (
                  SELECT 1 FROM study_specimens
                  WHERE study_specimens.study_id = specimens.study_id
                    AND study_specimens.specimen_id = specimens.specimen_id
              )
              AND specimen_axes.axis_family = 'terminal'
              AND specimens.descriptor_version = ?
              AND specimens.terminal_version = ?
              AND specimens.normalization_policy = ?
            """,
            [
                SOURCE_ID,
                resolved_study_id,
                FEATURE_SPACE_ID,
                resolved_study_id,
                DESCRIPTOR_VERSION,
                TERMINAL_VERSION,
                NORMALIZATION_POLICY,
            ],
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO observations (
                observation_id, specimen_id, study_id, source_id, context_id,
                observation_kind, observed_at, step, source_ref, payload_json
            )
            SELECT
                observation_id,
                specimen_id,
                ?,
                ?,
                ?,
                'synthetic_ca_terminal_embedding',
                recorded_at,
                NULL,
                source_ref,
                json_object(
                    'featureSpaceId', ?,
                    'sourceKind', source_kind,
                    'sourceMode', source_mode,
                    'sourceAlgorithm', source_algorithm
                )
            FROM tmp_lenia_terminal_observations
            """,
            [resolved_study_id, SOURCE_ID, context_id, FEATURE_SPACE_ID],
        )
        connection.execute(
            """
            DELETE FROM specimen_feature_vectors
            WHERE feature_space_id = ?
              AND observation_id IN (
                  SELECT observation_id FROM tmp_lenia_terminal_observations
              )
            """,
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            """
            DELETE FROM sparse_feature_values
            WHERE feature_space_id = ?
              AND observation_id IN (
                  SELECT observation_id FROM tmp_lenia_terminal_observations
              )
            """,
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO specimen_feature_vectors (
                observation_id, specimen_id, study_id, feature_space_id,
                calibration_id, vector_version, axis_count, raw_vector,
                normalized_vector, content_sha256, created_at
            )
            WITH vectors AS (
                SELECT observations.observation_id, observations.specimen_id,
                       ? AS study_id,
                       list(specimen_axes.raw_value ORDER BY feature_axes.axis_index)
                           AS raw_vector,
                       list(
                           specimen_axes.transformed_value ORDER BY feature_axes.axis_index
                       ) AS normalized_vector
                FROM tmp_lenia_terminal_observations AS observations
                JOIN specimen_axes USING (specimen_id)
                JOIN feature_axes
                  ON feature_axes.feature_space_id = ?
                 AND feature_axes.axis_id = specimen_axes.axis_id
                WHERE specimen_axes.axis_family = 'terminal'
                GROUP BY observations.observation_id, observations.specimen_id
                HAVING count(*) = ?
            )
            SELECT observation_id, specimen_id, study_id, ?, ?, 'v2', ?,
                   raw_vector, normalized_vector,
                   sha256(to_json(struct_pack(
                       observationId := observation_id,
                       specimenId := specimen_id,
                       featureSpaceId := ?,
                       calibrationId := ?,
                       vectorVersion := 'v2',
                       rawVector := raw_vector,
                       normalizedVector := normalized_vector
                   ))),
                   current_timestamp
            FROM vectors
            """,
            [
                resolved_study_id,
                FEATURE_SPACE_ID,
                len(AXIS_IDS),
                FEATURE_SPACE_ID,
                calibration_id,
                len(AXIS_IDS),
                FEATURE_SPACE_ID,
                calibration_id,
            ],
        )
        feature_value_count_row = connection.execute(
            """
            SELECT COUNT(*) * ?
            FROM specimen_feature_vectors
            WHERE feature_space_id = ?
              AND calibration_id = ?
              AND observation_id IN (
                  SELECT observation_id FROM tmp_lenia_terminal_observations
              )
            """,
            [len(AXIS_IDS), FEATURE_SPACE_ID, calibration_id],
        ).fetchone()
        resolved_feature_value_count = (
            int(feature_value_count_row[0]) if feature_value_count_row else 0
        )
        observation_count += resolved_observation_count
        feature_value_count += resolved_feature_value_count
        study_counts[resolved_study_id] = (
            study_counts.get(resolved_study_id, 0) + resolved_observation_count
        )

    vector_count_row = connection.execute(
        """
        SELECT count(*)
        FROM specimen_feature_vectors
        WHERE feature_space_id = ? AND calibration_id = ?
          AND (? IS NULL OR study_id = ?)
        """,
        [FEATURE_SPACE_ID, calibration_id, study_id, study_id],
    ).fetchone()
    vector_count = int(vector_count_row[0]) if vector_count_row is not None else 0
    validate_dense_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        calibration_id=calibration_id,
        observation_kind="synthetic_ca_terminal_embedding",
        axis_count=len(AXIS_IDS),
    )
    mark_derived_artifact_state(
        connection,
        artifact_kind="feature-space",
        feature_space_id=FEATURE_SPACE_ID,
        descriptor_version=DESCRIPTOR_VERSION,
        normalization_policy=NORMALIZATION_POLICY,
        status="valid",
        reason=None,
        metadata_json={"calibrationId": calibration_id, "lifecycle": "complete"},
    )
    return {
        "sourceId": SOURCE_ID,
        "featureSpaceId": FEATURE_SPACE_ID,
        "axisCount": len(TERMINAL_AXIS_SPECS),
        "observationCount": observation_count,
        "featureValueCount": feature_value_count,
        "calibrationId": calibration_id,
        "vectorCount": vector_count,
        "studyCounts": dict(sorted(study_counts.items())),
    }
