from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from .common_morphology import (
    AXIS_IDS as COMMON_AXIS_IDS,
)
from .common_morphology import (
    FEATURE_SPACE_ID as COMMON_FEATURE_SPACE_ID,
)
from .common_morphology import (
    OBSERVATION_KIND as COMMON_OBSERVATION_KIND,
)
from .common_morphology import valid_lenia_common_specimen_count
from .derive_anatomy import ANATOMICAL_AXIS_IDS
from .derive_lenia_features import (
    AXIS_IDS as TERMINAL_AXIS_IDS,
)
from .derive_lenia_features import (
    FEATURE_SPACE_ID as TERMINAL_FEATURE_SPACE_ID,
)
from .ingest_dryad_fish import SOURCE_ID as DRYAD_FISH_SOURCE_ID
from .ingest_embryomaker import SOURCE_ID as EMBRYOMAKER_SOURCE_ID
from .warehouse import (
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
    json_text,
    mark_derived_artifact_state,
)

TERMINAL_OBSERVATION_KIND = "synthetic_ca_terminal_embedding"
GENERATED_FEATURE_SPACE_IDS = (TERMINAL_FEATURE_SPACE_ID, COMMON_FEATURE_SPACE_ID)
GENERATED_OBSERVATION_KINDS = (TERMINAL_OBSERVATION_KIND, COMMON_OBSERVATION_KIND)
GENERATED_ANATOMICAL_STATE_KINDS = ("specimen_baseline", "context_trial_endpoint")
BASELINE_ANATOMICAL_AXIS_IDS = tuple(
    axis_id for axis_id in ANATOMICAL_AXIS_IDS if axis_id in TERMINAL_AXIS_IDS
)
FULL_CUTOVER_LAYER_KINDS = (
    "context_response_coordinates",
    "creature_signals_and_labels",
    "fibers",
    "topology",
    "trajectories",
    "universality",
)


class RegenerationIntegrityError(RuntimeError):
    pass


def _scalar_int(
    connection: DuckDBPyConnection,
    query: str,
    params: list[Any] | None = None,
) -> int:
    row = connection.execute(query, params or []).fetchone()
    if row is None:
        raise AssertionError(f"count query returned no row: {query}")
    return int(row[0])


def eligible_specimen_count(connection: DuckDBPyConnection) -> int:
    return _scalar_int(
        connection,
        """
        SELECT COUNT(*)
        FROM specimens
        JOIN specimen_descriptors USING (specimen_id)
        JOIN studies ON studies.study_id = specimens.study_id
        WHERE EXISTS (
              SELECT 1
              FROM study_specimens
              WHERE study_specimens.study_id = specimens.study_id
                AND study_specimens.specimen_id = specimens.specimen_id
          )
          AND specimens.descriptor_version = ?
          AND specimens.terminal_version = ?
          AND specimens.normalization_policy = ?
          AND specimens.fingerprint_resolution = 32
          AND specimen_descriptors.descriptor_version = ?
          AND specimen_descriptors.terminal_version = ?
          AND specimen_descriptors.normalization_policy = ?
          AND specimen_descriptors.fingerprint_resolution = 32
          AND json_extract_string(
              specimen_descriptors.terminal_descriptor_json,
              '$.borderMode'
          ) = 'torus'
          AND try_cast(json_extract_string(
              specimen_descriptors.terminal_descriptor_json,
              '$.fingerprintResolution'
          ) AS INTEGER) = 32
        """,
        [
            DESCRIPTOR_VERSION,
            TERMINAL_VERSION,
            NORMALIZATION_POLICY,
            DESCRIPTOR_VERSION,
            TERMINAL_VERSION,
            NORMALIZATION_POLICY,
        ],
    )


def clear_full_regeneration_outputs(connection: DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE regenerated_anatomical_state_ids AS
        SELECT state_id
        FROM anatomical_states
        WHERE source_kind IN (SELECT unnest(?::VARCHAR[]))
        """,
        [list(GENERATED_ANATOMICAL_STATE_KINDS)],
    )
    for table_name in (
        "anatomical_state_axes",
        "creature_signal_axes",
        "creature_state_labels",
    ):
        connection.execute(
            f"DELETE FROM {table_name} "
            "WHERE state_id IN (SELECT state_id FROM regenerated_anatomical_state_ids)"
        )
    connection.execute(
        """
        DELETE FROM fiber_group_members
        WHERE state_id IN (SELECT state_id FROM regenerated_anatomical_state_ids)
        """
    )
    connection.execute(
        """
        DELETE FROM anatomical_states
        WHERE state_id IN (SELECT state_id FROM regenerated_anatomical_state_ids)
        """
    )

    connection.execute("DELETE FROM development_sample_axes")
    connection.execute("DELETE FROM specimen_axes")
    connection.execute("DELETE FROM specimen_status")

    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE regenerated_observation_ids AS
        SELECT observation_id
        FROM observations
        WHERE observation_kind IN (SELECT unnest(?::VARCHAR[]))
        """,
        [list(GENERATED_OBSERVATION_KINDS)],
    )
    connection.execute(
        """
        DELETE FROM specimen_feature_vectors
        WHERE feature_space_id IN (SELECT unnest(?::VARCHAR[]))
           OR observation_id IN (SELECT observation_id FROM regenerated_observation_ids)
        """,
        [list(GENERATED_FEATURE_SPACE_IDS)],
    )
    connection.execute(
        """
        DELETE FROM sparse_feature_values
        WHERE feature_space_id IN (SELECT unnest(?::VARCHAR[]))
           OR observation_id IN (SELECT observation_id FROM regenerated_observation_ids)
        """,
        [list(GENERATED_FEATURE_SPACE_IDS)],
    )
    connection.execute(
        """
        DELETE FROM observations
        WHERE observation_id IN (SELECT observation_id FROM regenerated_observation_ids)
        """
    )
    connection.execute(
        """
        DELETE FROM feature_calibrations
        WHERE feature_space_id IN (SELECT unnest(?::VARCHAR[]))
        """,
        [list(GENERATED_FEATURE_SPACE_IDS)],
    )
    connection.execute(
        """
        DELETE FROM derived_artifact_state
        WHERE feature_space_id IN (SELECT unnest(?::VARCHAR[]))
        """,
        [list(GENERATED_FEATURE_SPACE_IDS)],
    )


def _external_source_availability(
    connection: DuckDBPyConnection,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    fish_rows = connection.execute(
        """
        SELECT study_id, json_extract_string(metadata_json, '$.datasetRoot')
        FROM studies
        WHERE study_kind = 'biological_morphospace'
          AND json_extract_string(metadata_json, '$.sourceId') = ?
        ORDER BY study_id
        """,
        [DRYAD_FISH_SOURCE_ID],
    ).fetchall()
    for study_id, root_value in fish_rows:
        root = Path(str(root_value)).expanduser() if root_value else None
        required_path = (
            root / "extracted/gpa/Slicer_GPA_output/OutputData.csv" if root is not None else None
        )
        sources.append(
            {
                "sourceId": DRYAD_FISH_SOURCE_ID,
                "studyId": str(study_id),
                "sourceKind": "dryad-fish-landmarks",
                "path": str(required_path) if required_path is not None else None,
                "available": required_path is not None and required_path.is_file(),
                "requiredForRegeneration": True,
            }
        )

    embryo_rows = connection.execute(
        """
        SELECT study_id, source_ref
        FROM observations
        WHERE source_id = ?
          AND observation_kind = 'embryomaker_legacy_snapshot_summary'
        ORDER BY study_id, observation_id
        """,
        [EMBRYOMAKER_SOURCE_ID],
    ).fetchall()
    if embryo_rows:
        paths = [Path(str(source_ref)).expanduser() for _, source_ref in embryo_rows if source_ref]
        missing = [str(path) for path in paths if not path.is_file()]
        sources.append(
            {
                "sourceId": EMBRYOMAKER_SOURCE_ID,
                "sourceKind": "embryomaker-node-files",
                "requiredFileCount": len(embryo_rows),
                "availableFileCount": len(paths) - len(missing),
                "missingFileCount": len(embryo_rows) - len(paths) + len(missing),
                "missingPaths": missing[:20],
                "available": len(paths) == len(embryo_rows) and not missing,
                "requiredForRegeneration": True,
            }
        )
    embryo_studies = connection.execute(
        """
        SELECT study_id, metadata_json
        FROM studies
        WHERE study_kind = 'embryomaker_morphospace'
          AND json_extract_string(metadata_json, '$.sourceId') = ?
        ORDER BY study_id
        """,
        [EMBRYOMAKER_SOURCE_ID],
    ).fetchall()
    for study_id, metadata_json in embryo_studies:
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
        root_values = metadata.get("snapshotRoots") if isinstance(metadata, dict) else None
        roots = (
            [Path(str(value)).expanduser() for value in root_values]
            if isinstance(root_values, list)
            else []
        )
        missing_roots = [str(root) for root in roots if not root.exists()]
        sources.append(
            {
                "sourceId": EMBRYOMAKER_SOURCE_ID,
                "studyId": str(study_id),
                "sourceKind": "embryomaker-snapshot-roots",
                "paths": [str(root) for root in roots],
                "missingPaths": missing_roots,
                "available": bool(roots) and not missing_roots,
                "requiredForRegeneration": False,
                "provenanceOnly": True,
            }
        )
    return sources


def assert_required_external_sources_available(
    connection: DuckDBPyConnection,
) -> list[dict[str, Any]]:
    sources = _external_source_availability(connection)
    missing = [
        source
        for source in sources
        if source["requiredForRegeneration"] and not source["available"]
    ]
    if missing:
        raise RegenerationIntegrityError(
            f"required external regeneration sources are unavailable: {json_text(missing)}"
        )
    return sources


def _orphan_counts(connection: DuckDBPyConnection) -> dict[str, int]:
    checks = {
        "studyParents": """
            SELECT COUNT(*) FROM studies AS child
            LEFT JOIN studies AS parent ON parent.study_id = child.parent_study_id
            WHERE child.parent_study_id IS NOT NULL AND parent.study_id IS NULL
        """,
        "artifacts": """
            SELECT COUNT(*) FROM artifacts
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "rawJsonObjects": """
            SELECT COUNT(*) FROM raw_json_objects
            LEFT JOIN artifacts USING (artifact_id)
            WHERE artifacts.artifact_id IS NULL
        """,
        "rawJsonlRows": """
            SELECT COUNT(*) FROM raw_jsonl_rows
            LEFT JOIN artifacts USING (artifact_id)
            WHERE artifacts.artifact_id IS NULL
        """,
        "sourceReceipts": """
            SELECT COUNT(*) FROM source_receipts
            LEFT JOIN studies USING (study_id)
            LEFT JOIN artifacts USING (artifact_id)
            WHERE studies.study_id IS NULL OR artifacts.artifact_id IS NULL
        """,
        "studyMembership": """
            SELECT COUNT(*) FROM study_specimens
            LEFT JOIN studies USING (study_id)
            LEFT JOIN specimens USING (specimen_id)
            WHERE studies.study_id IS NULL OR specimens.specimen_id IS NULL
        """,
        "specimenCanonicalStudy": """
            SELECT COUNT(*) FROM specimens
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "specimenDescriptors": """
            SELECT COUNT(*) FROM specimen_descriptors
            LEFT JOIN specimens USING (specimen_id)
            WHERE specimens.specimen_id IS NULL
        """,
        "developmentSamples": """
            SELECT COUNT(*) FROM development_samples
            LEFT JOIN specimens USING (specimen_id)
            WHERE specimens.specimen_id IS NULL
        """,
        "perturbationTrials": """
            SELECT COUNT(*) FROM perturbation_trials AS trials
            LEFT JOIN specimens ON specimens.specimen_id = trials.specimen_id
            LEFT JOIN studies ON studies.study_id = trials.study_id
            WHERE specimens.specimen_id IS NULL OR studies.study_id IS NULL
        """,
        "specimenAxes": """
            SELECT COUNT(*) FROM specimen_axes
            LEFT JOIN specimens USING (specimen_id)
            WHERE specimens.specimen_id IS NULL
        """,
        "developmentSampleAxes": """
            SELECT COUNT(*) FROM development_sample_axes AS axes
            LEFT JOIN development_samples AS samples
              ON samples.specimen_id = axes.specimen_id AND samples.step = axes.step
            WHERE samples.specimen_id IS NULL
        """,
        "specimenStatus": """
            SELECT COUNT(*) FROM specimen_status
            LEFT JOIN specimens USING (specimen_id)
            WHERE specimens.specimen_id IS NULL
        """,
        "contexts": """
            SELECT COUNT(*) FROM contexts
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "controlPrograms": """
            SELECT COUNT(*) FROM control_programs
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "anatomicalStates": """
            SELECT COUNT(*) FROM anatomical_states AS states
            LEFT JOIN studies ON studies.study_id = states.study_id
            LEFT JOIN specimens ON specimens.specimen_id = states.specimen_id
            LEFT JOIN contexts ON contexts.context_id = states.context_id
            WHERE studies.study_id IS NULL
               OR (states.specimen_id IS NOT NULL AND specimens.specimen_id IS NULL)
               OR (states.context_id IS NOT NULL AND contexts.context_id IS NULL)
        """,
        "anatomicalStateAxes": """
            SELECT COUNT(*) FROM anatomical_state_axes
            LEFT JOIN anatomical_states USING (state_id)
            WHERE anatomical_states.state_id IS NULL
        """,
        "creatureSignalAxes": """
            SELECT COUNT(*) FROM creature_signal_axes
            LEFT JOIN anatomical_states USING (state_id)
            WHERE anatomical_states.state_id IS NULL
        """,
        "creatureStateLabels": """
            SELECT COUNT(*) FROM creature_state_labels
            LEFT JOIN anatomical_states USING (state_id)
            WHERE anatomical_states.state_id IS NULL
        """,
        "discoveryExportResolutions": """
            SELECT COUNT(*) FROM discovery_export_resolutions AS resolutions
            LEFT JOIN specimens ON specimens.specimen_id = resolutions.specimen_id
            LEFT JOIN studies ON studies.study_id = resolutions.study_id
            WHERE specimens.specimen_id IS NULL OR studies.study_id IS NULL
        """,
        "contextTrials": """
            SELECT COUNT(*) FROM context_trials AS trials
            LEFT JOIN specimens ON specimens.specimen_id = trials.specimen_id
            LEFT JOIN studies ON studies.study_id = trials.study_id
            LEFT JOIN contexts ON contexts.context_id = trials.context_id
            LEFT JOIN control_programs AS programs
              ON programs.control_program_id = trials.control_program_id
            WHERE specimens.specimen_id IS NULL OR studies.study_id IS NULL
               OR contexts.context_id IS NULL
               OR (trials.control_program_id IS NOT NULL
                   AND programs.control_program_id IS NULL)
        """,
        "contextSampleAxes": """
            SELECT COUNT(*) FROM context_sample_axes
            LEFT JOIN context_trials USING (context_trial_id)
            WHERE context_trials.context_trial_id IS NULL
        """,
        "contextOutcomes": """
            SELECT COUNT(*) FROM context_outcomes
            LEFT JOIN context_trials USING (context_trial_id)
            WHERE context_trials.context_trial_id IS NULL
        """,
        "trajectorySegments": """
            SELECT COUNT(*) FROM trajectory_segments AS segments
            LEFT JOIN studies ON studies.study_id = segments.study_id
            LEFT JOIN specimens ON specimens.specimen_id = segments.specimen_id
            LEFT JOIN context_trials AS trials
              ON trials.context_trial_id = segments.context_trial_id
            LEFT JOIN contexts ON contexts.context_id = segments.context_id
            WHERE studies.study_id IS NULL
               OR (segments.specimen_id IS NOT NULL AND specimens.specimen_id IS NULL)
               OR (segments.context_trial_id IS NOT NULL
                   AND trials.context_trial_id IS NULL)
               OR (segments.context_id IS NOT NULL AND contexts.context_id IS NULL)
        """,
        "fiberGroups": """
            SELECT COUNT(*) FROM fiber_groups
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "fiberGroupMembers": """
            SELECT COUNT(*) FROM fiber_group_members AS members
            LEFT JOIN fiber_groups USING (fiber_group_id)
            LEFT JOIN anatomical_states USING (state_id)
            LEFT JOIN specimens ON specimens.specimen_id = members.specimen_id
            WHERE fiber_groups.fiber_group_id IS NULL
               OR anatomical_states.state_id IS NULL
               OR (members.specimen_id IS NOT NULL AND specimens.specimen_id IS NULL)
        """,
        "universalityRuns": """
            SELECT COUNT(*) FROM universality_runs
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "topologyRuns": """
            SELECT COUNT(*) FROM topology_runs
            LEFT JOIN studies USING (study_id)
            WHERE studies.study_id IS NULL
        """,
        "topologyFeatures": """
            SELECT COUNT(*) FROM topology_features
            LEFT JOIN topology_runs USING (topology_run_id)
            WHERE topology_runs.topology_run_id IS NULL
        """,
        "perturbationAxes": """
            SELECT COUNT(*) FROM perturbation_axes
            LEFT JOIN perturbation_trials USING (trial_id)
            WHERE perturbation_trials.trial_id IS NULL
        """,
        "observations": """
            SELECT COUNT(*) FROM observations
            LEFT JOIN studies ON studies.study_id = observations.study_id
            LEFT JOIN specimens ON specimens.specimen_id = observations.specimen_id
            LEFT JOIN contexts ON contexts.context_id = observations.context_id
            LEFT JOIN morphospace_sources
              ON morphospace_sources.source_id = observations.source_id
            WHERE studies.study_id IS NULL OR morphospace_sources.source_id IS NULL
               OR (observations.specimen_id IS NOT NULL AND specimens.specimen_id IS NULL)
               OR (observations.context_id IS NOT NULL AND contexts.context_id IS NULL)
        """,
        "featureAxes": """
            SELECT COUNT(*) FROM feature_axes
            LEFT JOIN feature_spaces USING (feature_space_id)
            WHERE feature_spaces.feature_space_id IS NULL
        """,
        "featureValues": """
            SELECT COUNT(*) FROM sparse_feature_values AS values
            LEFT JOIN observations USING (observation_id)
            LEFT JOIN feature_spaces USING (feature_space_id)
            LEFT JOIN feature_axes AS axes
              ON axes.feature_space_id = values.feature_space_id
             AND axes.axis_id = values.axis_id
            WHERE observations.observation_id IS NULL
               OR feature_spaces.feature_space_id IS NULL
               OR axes.axis_id IS NULL
        """,
        "featureCalibrations": """
            SELECT COUNT(*) FROM feature_calibrations
            LEFT JOIN feature_spaces USING (feature_space_id)
            WHERE feature_spaces.feature_space_id IS NULL
        """,
        "featureVectors": """
            SELECT COUNT(*) FROM specimen_feature_vectors AS vectors
            LEFT JOIN observations
              ON observations.observation_id = vectors.observation_id
            LEFT JOIN specimens
              ON specimens.specimen_id = vectors.specimen_id
            LEFT JOIN studies
              ON studies.study_id = vectors.study_id
            LEFT JOIN feature_spaces
              ON feature_spaces.feature_space_id = vectors.feature_space_id
            LEFT JOIN feature_calibrations AS calibrations
              ON calibrations.calibration_id = vectors.calibration_id
             AND calibrations.feature_space_id = vectors.feature_space_id
            WHERE observations.observation_id IS NULL OR specimens.specimen_id IS NULL
               OR studies.study_id IS NULL OR feature_spaces.feature_space_id IS NULL
               OR calibrations.calibration_id IS NULL
               OR observations.specimen_id != vectors.specimen_id
               OR observations.study_id != vectors.study_id
        """,
    }
    return {label: _scalar_int(connection, query) for label, query in checks.items()}


def _duplicate_generated_observations(connection: DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT observations.specimen_id,
               CASE observations.observation_kind
                   WHEN 'synthetic_ca_terminal_embedding' THEN ?
                   WHEN 'common_point_cloud_morphology' THEN ?
               END AS feature_space_id,
               COUNT(DISTINCT observations.observation_id) AS observation_count
        FROM observations
        WHERE observations.observation_kind IN (SELECT unnest(?::VARCHAR[]))
          AND observations.specimen_id IS NOT NULL
        GROUP BY observations.specimen_id, feature_space_id
        HAVING COUNT(DISTINCT observations.observation_id) > 1
        ORDER BY observations.specimen_id, feature_space_id
        """,
        [
            TERMINAL_FEATURE_SPACE_ID,
            COMMON_FEATURE_SPACE_ID,
            list(GENERATED_OBSERVATION_KINDS),
        ],
    ).fetchall()
    return [
        {
            "specimenId": str(specimen_id),
            "featureSpaceId": str(feature_space_id),
            "observationCount": int(count),
        }
        for specimen_id, feature_space_id, count in rows
    ]


def _baseline_state_violations(connection: DuckDBPyConnection) -> dict[str, int]:
    return {
        "duplicatePerSpecimen": _scalar_int(
            connection,
            """
            SELECT COUNT(*) FROM (
                SELECT specimen_id
                FROM anatomical_states
                WHERE source_kind = 'specimen_baseline'
                GROUP BY specimen_id
                HAVING COUNT(*) > 1
            )
            """,
        ),
        "noncanonicalStudy": _scalar_int(
            connection,
            """
            SELECT COUNT(*)
            FROM anatomical_states
            JOIN specimens USING (specimen_id)
            WHERE anatomical_states.source_kind = 'specimen_baseline'
              AND anatomical_states.study_id != specimens.study_id
            """,
        ),
        "missingAxes": _scalar_int(
            connection,
            """
            SELECT COUNT(*)
            FROM anatomical_states
            LEFT JOIN (
                SELECT state_id, COUNT(*) AS axis_count
                FROM anatomical_state_axes
                GROUP BY state_id
            ) AS axes USING (state_id)
            WHERE anatomical_states.source_kind IN (SELECT unnest(?::VARCHAR[]))
              AND coalesce(axes.axis_count, 0) = 0
            """,
            [list(GENERATED_ANATOMICAL_STATE_KINDS)],
        ),
        "baselineAxisCountMismatch": _scalar_int(
            connection,
            """
            WITH expected AS (
                SELECT anatomical_states.state_id, COUNT(specimen_axes.axis_id) AS axis_count
                FROM anatomical_states
                LEFT JOIN specimen_axes
                  ON specimen_axes.specimen_id = anatomical_states.specimen_id
                 AND specimen_axes.axis_id IN (
                     'fragmentation', 'cavity_count', 'boundary_complexity',
                     'bilateral_symmetry', 'radial_symmetry', 'rotational_symmetry',
                     'left_right_asymmetry', 'axial_polarity', 'center_offset',
                     'coverage', 'compactness', 'elongation', 'expansion_gain',
                     'condensation_gain', 'elongation_gain', 'folding_gain',
                     'fragmentation_gain', 'locomotion_onset_step', 'meander_final'
                 )
                WHERE anatomical_states.source_kind = 'specimen_baseline'
                GROUP BY anatomical_states.state_id
            ), actual AS (
                SELECT state_id, COUNT(*) AS axis_count
                FROM anatomical_state_axes
                GROUP BY state_id
            )
            SELECT COUNT(*)
            FROM expected
            LEFT JOIN actual USING (state_id)
            WHERE expected.axis_count != coalesce(actual.axis_count, 0)
            """,
        ),
    }


def _generated_layer_counts(connection: DuckDBPyConnection) -> dict[str, int]:
    counts = {
        "specimenAxes": _scalar_int(connection, "SELECT COUNT(*) FROM specimen_axes"),
        "terminalSpecimenAxes": _scalar_int(
            connection,
            "SELECT COUNT(*) FROM specimen_axes WHERE axis_family = 'terminal'",
        ),
        "developmentSampleAxes": _scalar_int(
            connection, "SELECT COUNT(*) FROM development_sample_axes"
        ),
        "specimenStatus": _scalar_int(connection, "SELECT COUNT(*) FROM specimen_status"),
        "anatomicalStates": _scalar_int(
            connection,
            "SELECT COUNT(*) FROM anatomical_states "
            "WHERE source_kind IN (SELECT unnest(?::VARCHAR[]))",
            [list(GENERATED_ANATOMICAL_STATE_KINDS)],
        ),
        "anatomicalStateAxes": _scalar_int(
            connection,
            """
            SELECT COUNT(*) FROM anatomical_state_axes
            JOIN anatomical_states USING (state_id)
            WHERE anatomical_states.source_kind IN (SELECT unnest(?::VARCHAR[]))
            """,
            [list(GENERATED_ANATOMICAL_STATE_KINDS)],
        ),
        "baselineAnatomicalStates": _scalar_int(
            connection,
            "SELECT COUNT(*) FROM anatomical_states WHERE source_kind = 'specimen_baseline'",
        ),
        "baselineAnatomicalStateAxes": _scalar_int(
            connection,
            """
            SELECT COUNT(*) FROM anatomical_state_axes
            JOIN anatomical_states USING (state_id)
            WHERE anatomical_states.source_kind = 'specimen_baseline'
            """,
        ),
    }
    for prefix, feature_space_id, observation_kind in (
        ("terminal", TERMINAL_FEATURE_SPACE_ID, TERMINAL_OBSERVATION_KIND),
        ("commonMorphology", COMMON_FEATURE_SPACE_ID, COMMON_OBSERVATION_KIND),
    ):
        counts[f"{prefix}Observations"] = _scalar_int(
            connection,
            "SELECT COUNT(*) FROM observations WHERE observation_kind = ?",
            [observation_kind],
        )
        counts[f"{prefix}FeatureValues"] = _scalar_int(
            connection,
            "SELECT COUNT(*) FROM feature_values WHERE feature_space_id = ?",
            [feature_space_id],
        )
        counts[f"{prefix}PhysicalFeatureValues"] = _scalar_int(
            connection,
            "SELECT COUNT(*) FROM sparse_feature_values WHERE feature_space_id = ?",
            [feature_space_id],
        )
        counts[f"{prefix}Vectors"] = _scalar_int(
            connection,
            "SELECT COUNT(*) FROM specimen_feature_vectors WHERE feature_space_id = ?",
            [feature_space_id],
        )
        counts[f"{prefix}Calibrations"] = _scalar_int(
            connection,
            "SELECT COUNT(*) FROM feature_calibrations WHERE feature_space_id = ?",
            [feature_space_id],
        )
    return counts


def _common_source_counts(connection: DuckDBPyConnection) -> dict[str, int]:
    return {
        str(source_id): int(count)
        for source_id, count in connection.execute(
            """
            SELECT source_id, COUNT(*)
            FROM observations
            WHERE observation_kind = ?
            GROUP BY source_id
            ORDER BY source_id
            """,
            [COMMON_OBSERVATION_KIND],
        ).fetchall()
    }


def _expected_common_source_counts(
    connection: DuckDBPyConnection,
    *,
    eligible_count: int,
) -> dict[str, int]:
    valid_lenia_count = valid_lenia_common_specimen_count(connection)
    if valid_lenia_count <= 0 or valid_lenia_count > eligible_count:
        raise RegenerationIntegrityError(
            "valid Lenia common-morphology cohort is outside terminal eligibility: "
            f"valid={valid_lenia_count}, eligible={eligible_count}"
        )
    counts = {"lenia_swarm": valid_lenia_count}
    for source_id, observation_kind in (
        (DRYAD_FISH_SOURCE_ID, "geometric_morphometric_embedding"),
        (EMBRYOMAKER_SOURCE_ID, "embryomaker_legacy_snapshot_summary"),
    ):
        count = _scalar_int(
            connection,
            """
            SELECT COUNT(*)
            FROM observations
            WHERE source_id = ? AND observation_kind = ?
            """,
            [source_id, observation_kind],
        )
        if count:
            counts[source_id] = count
    return counts


def _vector_shape_violation_count(connection: DuckDBPyConnection) -> int:
    return _scalar_int(
        connection,
        """
        SELECT COUNT(*)
        FROM specimen_feature_vectors AS vectors
        LEFT JOIN (
            SELECT feature_space_id, count(*) AS expected_axis_count
            FROM feature_axes
            GROUP BY feature_space_id
        ) AS axes USING (feature_space_id)
        WHERE vectors.axis_count != coalesce(axes.expected_axis_count, -1)
           OR array_length(raw_vector) != vectors.axis_count
           OR array_length(normalized_vector) != vectors.axis_count
        """,
    )


def _active_feature_nonfinite_count(connection: DuckDBPyConnection) -> int:
    return _scalar_int(
        connection,
        """
        SELECT
            (SELECT count(*)
             FROM sparse_feature_values AS values
             JOIN feature_spaces AS spaces USING (feature_space_id)
             WHERE spaces.storage_mode = 'sparse_values'
               AND (
                   (values.raw_value IS NOT NULL AND NOT isfinite(values.raw_value))
                   OR (values.normalized_value IS NOT NULL
                       AND NOT isfinite(values.normalized_value))
               ))
            +
            (SELECT count(*)
             FROM specimen_feature_vectors AS vectors
             JOIN feature_spaces AS spaces USING (feature_space_id)
             WHERE spaces.storage_mode = 'dense_vectors'
               AND vectors.calibration_id = json_extract_string(
                   spaces.metadata_json, '$.activeCalibrationId'
               )
               AND (
                   len(list_filter(
                       vectors.raw_vector,
                       value -> value IS NULL OR NOT isfinite(value)
                   )) != 0
                   OR len(list_filter(
                       vectors.normalized_vector,
                       value -> value IS NULL OR NOT isfinite(value)
                   )) != 0
               ))
        """,
    )


def _feature_storage_violation_count(connection: DuckDBPyConnection) -> int:
    return _scalar_int(
        connection,
        """
        SELECT
            (SELECT count(*)
             FROM sparse_feature_values AS values
             JOIN feature_spaces AS spaces USING (feature_space_id)
             WHERE spaces.storage_mode != 'sparse_values')
            +
            (SELECT count(*)
             FROM specimen_feature_vectors AS vectors
             JOIN feature_spaces AS spaces USING (feature_space_id)
             WHERE spaces.storage_mode != 'dense_vectors')
        """,
    )


def _nonfinite_axis_counts(connection: DuckDBPyConnection) -> dict[str, int]:
    checks = {
        "specimenAxes": """
            SELECT COUNT(*) FROM specimen_axes
            WHERE (raw_value IS NOT NULL AND NOT isfinite(raw_value))
               OR (transformed_value IS NOT NULL AND NOT isfinite(transformed_value))
        """,
        "developmentSampleAxes": """
            SELECT COUNT(*) FROM development_sample_axes
            WHERE raw_value IS NOT NULL AND NOT isfinite(raw_value)
        """,
        "perturbationAxes": """
            SELECT COUNT(*) FROM perturbation_axes
            WHERE (raw_value IS NOT NULL AND NOT isfinite(raw_value))
               OR (transformed_value IS NOT NULL AND NOT isfinite(transformed_value))
        """,
        "anatomicalStateAxes": """
            SELECT COUNT(*) FROM anatomical_state_axes
            WHERE (raw_value IS NOT NULL AND NOT isfinite(raw_value))
               OR (transformed_value IS NOT NULL AND NOT isfinite(transformed_value))
        """,
        "creatureSignalAxes": """
            SELECT COUNT(*) FROM creature_signal_axes
            WHERE (raw_value IS NOT NULL AND NOT isfinite(raw_value))
               OR (transformed_value IS NOT NULL AND NOT isfinite(transformed_value))
        """,
        "contextSampleAxes": """
            SELECT COUNT(*) FROM context_sample_axes
            WHERE raw_value IS NOT NULL AND NOT isfinite(raw_value)
        """,
        "contextOutcomes": """
            SELECT COUNT(*) FROM context_outcomes
            WHERE outcome_value IS NOT NULL AND NOT isfinite(outcome_value)
        """,
        "fiberGroups": """
            SELECT COUNT(*) FROM fiber_groups
            WHERE (volume_proxy IS NOT NULL AND NOT isfinite(volume_proxy))
               OR (diversity_proxy IS NOT NULL AND NOT isfinite(diversity_proxy))
               OR (connectivity_proxy IS NOT NULL AND NOT isfinite(connectivity_proxy))
        """,
        "topologyFeatures": """
            SELECT COUNT(*) FROM topology_features
            WHERE NOT isfinite(birth)
               OR (death IS NOT NULL AND NOT isfinite(death))
               OR (persistence IS NOT NULL AND NOT isfinite(persistence))
        """,
    }
    return {name: _scalar_int(connection, query) for name, query in checks.items()}


def _validate_balanced_common_calibration(connection: DuckDBPyConnection) -> None:
    row = connection.execute(
        """
        SELECT feature_calibrations.reference_query_json
        FROM feature_spaces
        JOIN feature_calibrations
          ON feature_calibrations.calibration_id = json_extract_string(
              feature_spaces.metadata_json, '$.activeCalibrationId'
          )
        WHERE feature_spaces.feature_space_id = ?
          AND feature_calibrations.feature_space_id = ?
          AND feature_calibrations.frozen
        """,
        [COMMON_FEATURE_SPACE_ID, COMMON_FEATURE_SPACE_ID],
    ).fetchone()
    if row is None:
        raise RegenerationIntegrityError("common morphology has no active frozen calibration")
    reference_query = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    raw_counts = reference_query.get("counts") if isinstance(reference_query, dict) else None
    if not isinstance(raw_counts, dict) or not raw_counts:
        raise RegenerationIntegrityError("common calibration has no balanced reference counts")
    counts = [int(value) for value in raw_counts.values()]
    if min(counts) <= 0 or len(set(counts)) != 1:
        raise RegenerationIntegrityError(
            f"common calibration reference counts are not balanced: {raw_counts}"
        )


def _resolve_regenerated_invalidations(
    connection: DuckDBPyConnection,
    *,
    layer_counts: dict[str, int],
) -> None:
    connection.execute(
        """
        DELETE FROM derived_artifact_state
        WHERE status = 'invalid'
          AND artifact_kind IN (
              'descriptor_axes',
              'specimen_status',
              'anatomical_states',
              'observations'
          )
        """
    )
    metadata = {"layerCounts": layer_counts, "regenerator": "regenerate-derived"}
    for artifact_kind in ("descriptor_axes", "specimen_status", "anatomical_states"):
        mark_derived_artifact_state(
            connection,
            artifact_kind=artifact_kind,
            descriptor_version=DESCRIPTOR_VERSION,
            normalization_policy=NORMALIZATION_POLICY,
            status="valid",
            reason=None,
            metadata_json=metadata,
        )


def build_readiness_report(
    connection: DuckDBPyConnection,
    *,
    eligible_count: int,
) -> dict[str, Any]:
    if eligible_count <= 0:
        raise RegenerationIntegrityError("regenerate-derived found zero exact torus-v2 specimens")

    layer_counts = _generated_layer_counts(connection)
    duplicate_observations = _duplicate_generated_observations(connection)
    orphan_counts = _orphan_counts(connection)
    baseline_state_violations = _baseline_state_violations(connection)
    integrity_violations: list[str] = []
    if duplicate_observations:
        integrity_violations.append("duplicate generated observations")
    nonzero_orphans = {name: count for name, count in orphan_counts.items() if count}
    if nonzero_orphans:
        integrity_violations.append(f"orphaned rows: {nonzero_orphans}")
    nonzero_state_violations = {
        name: count for name, count in baseline_state_violations.items() if count
    }
    if nonzero_state_violations:
        integrity_violations.append(
            f"invalid regenerated anatomical states: {nonzero_state_violations}"
        )

    expected_terminal_values = eligible_count * len(TERMINAL_AXIS_IDS)
    common_source_counts = _common_source_counts(connection)
    expected_common_source_counts = _expected_common_source_counts(
        connection,
        eligible_count=eligible_count,
    )
    expected_common_observations = sum(expected_common_source_counts.values())
    expected_common_values = expected_common_observations * len(COMMON_AXIS_IDS)
    specimen_count = _scalar_int(connection, "SELECT COUNT(*) FROM specimens")
    declared_counts = {
        "terminalSpecimenAxes": (
            layer_counts["terminalSpecimenAxes"],
            expected_terminal_values,
        ),
        "specimenStatus": (layer_counts["specimenStatus"], specimen_count),
        "baselineAnatomicalStates": (
            layer_counts["baselineAnatomicalStates"],
            eligible_count,
        ),
        "baselineAnatomicalStateAxes": (
            layer_counts["baselineAnatomicalStateAxes"],
            eligible_count * len(BASELINE_ANATOMICAL_AXIS_IDS),
        ),
        "terminalObservations": (layer_counts["terminalObservations"], eligible_count),
        "terminalFeatureValues": (
            layer_counts["terminalFeatureValues"],
            expected_terminal_values,
        ),
        "terminalVectors": (layer_counts["terminalVectors"], eligible_count),
        "terminalPhysicalFeatureValues": (
            layer_counts["terminalPhysicalFeatureValues"],
            0,
        ),
        "terminalCalibrations": (layer_counts["terminalCalibrations"], 1),
        "commonMorphologyCalibrations": (
            layer_counts["commonMorphologyCalibrations"],
            1,
        ),
        "commonMorphologyObservations": (
            layer_counts["commonMorphologyObservations"],
            expected_common_observations,
        ),
        "commonMorphologyFeatureValues": (
            layer_counts["commonMorphologyFeatureValues"],
            expected_common_values,
        ),
        "commonMorphologyVectors": (
            layer_counts["commonMorphologyVectors"],
            expected_common_observations,
        ),
        "commonMorphologyPhysicalFeatureValues": (
            layer_counts["commonMorphologyPhysicalFeatureValues"],
            0,
        ),
    }
    mismatched_counts = {
        name: {"actual": actual, "expected": expected}
        for name, (actual, expected) in declared_counts.items()
        if actual != expected
    }
    if mismatched_counts:
        integrity_violations.append(f"declared layer counts changed: {mismatched_counts}")
    if common_source_counts != expected_common_source_counts:
        integrity_violations.append(
            "common morphology source counts changed: "
            f"actual={common_source_counts}, expected={expected_common_source_counts}"
        )
    vector_shape_violations = _vector_shape_violation_count(connection)
    if vector_shape_violations:
        integrity_violations.append(
            f"dense feature vectors have invalid lengths: {vector_shape_violations}"
        )
    storage_violations = _feature_storage_violation_count(connection)
    if storage_violations:
        integrity_violations.append(
            f"feature-space storage modes are violated: {storage_violations}"
        )

    stale_lenia_rows = _scalar_int(
        connection,
        """
        SELECT COUNT(*)
        FROM observations
        JOIN specimens USING (specimen_id)
        WHERE observations.observation_kind IN (?, ?)
          AND observations.source_id = 'lenia_swarm'
          AND (
              observations.study_id != specimens.study_id
              OR specimens.descriptor_version != ?
              OR specimens.terminal_version != ?
              OR specimens.normalization_policy != ?
              OR specimens.fingerprint_resolution != 32
          )
        """,
        [
            TERMINAL_OBSERVATION_KIND,
            COMMON_OBSERVATION_KIND,
            DESCRIPTOR_VERSION,
            TERMINAL_VERSION,
            NORMALIZATION_POLICY,
        ],
    )
    if stale_lenia_rows:
        integrity_violations.append(f"stale or noncanonical Lenia observations: {stale_lenia_rows}")
    active_nonfinite_values = _active_feature_nonfinite_count(connection)
    if active_nonfinite_values:
        integrity_violations.append(
            f"active feature spaces contain nonfinite values: {active_nonfinite_values}"
        )
    nonfinite_axis_counts = _nonfinite_axis_counts(connection)
    nonzero_nonfinite_axes = {name: count for name, count in nonfinite_axis_counts.items() if count}
    if nonzero_nonfinite_axes:
        integrity_violations.append(
            f"derived axes contain nonfinite values: {nonzero_nonfinite_axes}"
        )

    _validate_balanced_common_calibration(connection)
    if integrity_violations:
        raise RegenerationIntegrityError("; ".join(integrity_violations))

    _resolve_regenerated_invalidations(connection, layer_counts=layer_counts)
    invalidation_rows = connection.execute(
        """
        SELECT artifact_kind, feature_space_id, reason
        FROM derived_artifact_state
        WHERE status = 'invalid'
        ORDER BY artifact_kind, feature_space_id
        """
    ).fetchall()
    unresolved_invalidations = [
        {
            "artifactKind": str(artifact_kind),
            "featureSpaceId": str(feature_space_id) if feature_space_id is not None else None,
            "reason": str(reason) if reason is not None else None,
        }
        for artifact_kind, feature_space_id, reason in invalidation_rows
    ]
    unresolved_kinds = sorted({row["artifactKind"] for row in unresolved_invalidations})
    validated_cutover_layers = sorted(
        str(row[0])
        for row in connection.execute(
            """
            SELECT DISTINCT artifact_kind
            FROM derived_artifact_state
            WHERE status = 'valid'
              AND artifact_kind IN (SELECT unnest(?::VARCHAR[]))
              AND descriptor_version = ?
              AND normalization_policy = ?
            """,
            [
                list(FULL_CUTOVER_LAYER_KINDS),
                DESCRIPTOR_VERSION,
                NORMALIZATION_POLICY,
            ],
        ).fetchall()
    )
    missing_cutover_layer_validations = sorted(
        set(FULL_CUTOVER_LAYER_KINDS) - set(validated_cutover_layers)
    )
    external_sources = _external_source_availability(connection)
    external_sources_available = all(
        source["available"] for source in external_sources if source["requiredForRegeneration"]
    )
    external_provenance_complete = all(source["available"] for source in external_sources)
    provenance_pending = [
        f"external-provenance:{source['sourceKind']}:{source.get('studyId', 'global')}"
        for source in external_sources
        if source.get("provenanceOnly") and not source["available"]
    ]
    pending_layers = sorted(set(unresolved_kinds) | set(missing_cutover_layer_validations))
    pending_rebuilds = sorted(set(pending_layers) | set(provenance_pending))
    ready_for_warehouse_cutover = external_sources_available
    ready_for_native_v2_analysis = eligible_count > 0
    ready_for_full_cutover = (
        ready_for_warehouse_cutover
        and ready_for_native_v2_analysis
        and not pending_rebuilds
        and not unresolved_invalidations
        and external_provenance_complete
    )
    return {
        "eligibleSpecimenCount": eligible_count,
        "validLeniaCommonSpecimenCount": expected_common_source_counts["lenia_swarm"],
        "layerCounts": layer_counts,
        "duplicateGeneratedObservations": duplicate_observations,
        "orphanCounts": orphan_counts,
        "anatomicalStateViolations": baseline_state_violations,
        "activeFeatureNonfiniteValueCount": active_nonfinite_values,
        "nonfiniteAxisCounts": nonfinite_axis_counts,
        "commonMorphologySourceCounts": common_source_counts,
        "expectedCommonMorphologySourceCounts": expected_common_source_counts,
        "vectorShapeViolationCount": vector_shape_violations,
        "featureStorageViolationCount": storage_violations,
        "unresolvedInvalidationKinds": unresolved_kinds,
        "unresolvedInvalidations": unresolved_invalidations,
        "validatedCutoverLayers": validated_cutover_layers,
        "missingCutoverLayerValidations": missing_cutover_layer_validations,
        "externalSources": external_sources,
        "externalSourcesAvailable": external_sources_available,
        "externalProvenanceComplete": external_provenance_complete,
        "pendingDerivedLayers": pending_layers,
        "pendingRebuilds": pending_rebuilds,
        "regeneratedLayersValid": True,
        "readyForWarehouseCutover": ready_for_warehouse_cutover,
        "readyForNativeV2Analysis": ready_for_native_v2_analysis,
        "readyForFullCutover": ready_for_full_cutover,
    }
