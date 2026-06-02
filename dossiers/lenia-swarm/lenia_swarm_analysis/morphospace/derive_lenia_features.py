from __future__ import annotations

from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import TERMINAL_AXIS_SPECS

from .warehouse import (
    register_context,
    replace_feature_axes,
    upsert_feature_space,
    upsert_morphospace_source,
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


def _feature_axis_rows_for_study(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> list[tuple[Any, ...]]:
    return connection.execute(
        """
        SELECT
            specimen_axes.specimen_id,
            specimen_axes.axis_id,
            specimen_axes.raw_value,
            specimen_axes.transformed_value
        FROM study_specimens
        JOIN specimen_axes USING (specimen_id)
        WHERE study_specimens.study_id = ?
          AND specimen_axes.axis_family = 'terminal'
          AND specimen_axes.axis_id IN (
              SELECT unnest(?)
          )
        ORDER BY specimen_axes.specimen_id, specimen_axes.axis_id
        """,
        [study_id, list(AXIS_IDS)],
    ).fetchall()


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
        observation_count_row = connection.execute(
            """
            SELECT COUNT(DISTINCT specimens.specimen_id)
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            JOIN specimen_axes USING (specimen_id)
            WHERE study_specimens.study_id = ?
              AND specimen_axes.axis_family = 'terminal'
            """,
            [resolved_study_id],
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
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            JOIN specimen_axes USING (specimen_id)
            WHERE study_specimens.study_id = ?
              AND specimen_axes.axis_family = 'terminal'
            """,
            [SOURCE_ID, resolved_study_id, FEATURE_SPACE_ID, resolved_study_id],
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
            DELETE FROM feature_values
            WHERE feature_space_id = ?
              AND observation_id IN (
                  SELECT observation_id FROM tmp_lenia_terminal_observations
              )
            """,
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            """
            INSERT INTO feature_values (
                observation_id, feature_space_id, axis_id, raw_value,
                normalized_value, metadata_json
            )
            SELECT
                tmp_lenia_terminal_observations.observation_id,
                ?,
                specimen_axes.axis_id,
                specimen_axes.raw_value,
                specimen_axes.transformed_value,
                json_object('sourceTable', 'specimen_axes')
            FROM tmp_lenia_terminal_observations
            JOIN specimen_axes USING (specimen_id)
            WHERE specimen_axes.axis_family = 'terminal'
              AND specimen_axes.axis_id IN (SELECT unnest(?))
            """,
            [FEATURE_SPACE_ID, list(AXIS_IDS)],
        )
        feature_value_count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM feature_values
            WHERE feature_space_id = ?
              AND observation_id IN (
                  SELECT observation_id FROM tmp_lenia_terminal_observations
              )
            """,
            [FEATURE_SPACE_ID],
        ).fetchone()
        resolved_feature_value_count = (
            int(feature_value_count_row[0]) if feature_value_count_row else 0
        )
        observation_count += resolved_observation_count
        feature_value_count += resolved_feature_value_count
        study_counts[resolved_study_id] = (
            study_counts.get(resolved_study_id, 0) + resolved_observation_count
        )

    return {
        "sourceId": SOURCE_ID,
        "featureSpaceId": FEATURE_SPACE_ID,
        "axisCount": len(TERMINAL_AXIS_SPECS),
        "observationCount": observation_count,
        "featureValueCount": feature_value_count,
        "studyCounts": dict(sorted(study_counts.items())),
    }
