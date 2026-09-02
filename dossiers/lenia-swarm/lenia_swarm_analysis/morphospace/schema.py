from __future__ import annotations

from duckdb import DuckDBPyConnection

SCHEMA_VERSION = 8


def _table_columns(connection: DuckDBPyConnection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(
    connection: DuckDBPyConnection,
    *,
    table_name: str,
    column_name: str,
    ddl: str,
) -> None:
    if column_name in _table_columns(connection, table_name):
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def create_schema(connection: DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            schema_version INTEGER NOT NULL
        )
        """
    )
    schema_count_row = connection.execute("SELECT COUNT(*) FROM schema_meta").fetchone()
    if schema_count_row is None:
        raise AssertionError("schema_meta count query returned no rows")
    if int(schema_count_row[0]) == 0:
        connection.execute("INSERT INTO schema_meta VALUES (?)", [SCHEMA_VERSION])
    else:
        connection.execute("UPDATE schema_meta SET schema_version = ?", [SCHEMA_VERSION])

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS studies (
            study_id TEXT PRIMARY KEY,
            study_kind TEXT NOT NULL,
            run_id TEXT,
            campaign_id TEXT,
            parent_study_id TEXT,
            label TEXT,
            config_hash TEXT,
            created_at TIMESTAMP,
            metadata_json JSON
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes BIGINT NOT NULL,
            created_at TIMESTAMP,
            metadata_json JSON
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_runs (
            ingest_id TEXT PRIMARY KEY,
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            status TEXT NOT NULL,
            tool_version TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_json_objects (
            artifact_id TEXT NOT NULL,
            object_kind TEXT NOT NULL,
            object_key TEXT NOT NULL,
            payload_json JSON NOT NULL,
            PRIMARY KEY (artifact_id, object_kind, object_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_jsonl_rows (
            artifact_id TEXT NOT NULL,
            row_index BIGINT NOT NULL,
            row_hash TEXT NOT NULL,
            payload_json JSON NOT NULL,
            PRIMARY KEY (artifact_id, row_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_sqlite_rows (
            artifact_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            primary_key TEXT NOT NULL,
            row_hash TEXT NOT NULL,
            payload_json JSON NOT NULL,
            PRIMARY KEY (artifact_id, table_name, primary_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS specimens (
            specimen_id TEXT PRIMARY KEY,
            source_creature_id TEXT,
            study_id TEXT NOT NULL,
            run_id TEXT,
            campaign_id TEXT,
            source_kind TEXT NOT NULL,
            source_mode TEXT,
            source_algorithm TEXT,
            config_hash TEXT,
            initial_condition_family TEXT,
            regime_family TEXT,
            geometry_family TEXT,
            canonical_family TEXT,
            family_kind TEXT,
            score DOUBLE,
            filters_passed BOOLEAN,
            search_is_stable_candidate BOOLEAN,
            recorded_at TIMESTAMP,
            results_path TEXT,
            export_dir TEXT,
            activity_path TEXT,
            fingerprint_path TEXT,
            provenance_json JSON,
            runtime_family TEXT,
            runtime_capabilities_json JSON,
            specimen_manifest_json JSON
        )
        """
    )
    _ensure_column(
        connection,
        table_name="specimens",
        column_name="runtime_family",
        ddl="runtime_family TEXT",
    )
    _ensure_column(
        connection,
        table_name="specimens",
        column_name="runtime_capabilities_json",
        ddl="runtime_capabilities_json JSON",
    )
    _ensure_column(
        connection,
        table_name="specimens",
        column_name="specimen_manifest_json",
        ddl="specimen_manifest_json JSON",
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS study_specimens (
            study_id TEXT NOT NULL,
            specimen_id TEXT NOT NULL,
            PRIMARY KEY (study_id, specimen_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS development_samples (
            specimen_id TEXT NOT NULL,
            step INTEGER NOT NULL,
            sample_index INTEGER NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            center_x DOUBLE NOT NULL,
            center_y DOUBLE NOT NULL,
            frame_path TEXT,
            terminal_descriptor_json JSON NOT NULL,
            PRIMARY KEY (specimen_id, step)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS perturbation_trials (
            trial_id TEXT PRIMARY KEY,
            specimen_id TEXT NOT NULL,
            study_id TEXT NOT NULL,
            run_id TEXT,
            campaign_id TEXT,
            phase_name TEXT,
            environment TEXT NOT NULL,
            perturbation TEXT NOT NULL,
            repeat_index INTEGER NOT NULL,
            results_path TEXT,
            summary_path TEXT,
            raw_response_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS contexts (
            context_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            context_kind TEXT NOT NULL,
            label TEXT NOT NULL,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS control_programs (
            control_program_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            label TEXT NOT NULL,
            sequence_index INTEGER NOT NULL,
            family TEXT,
            payload_json JSON NOT NULL,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS anatomical_states (
            state_id TEXT PRIMARY KEY,
            specimen_id TEXT,
            study_id TEXT NOT NULL,
            context_id TEXT,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            recorded_at TIMESTAMP,
            state_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS anatomical_state_axes (
            state_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            transformed_value DOUBLE,
            PRIMARY KEY (state_id, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS creature_signal_axes (
            state_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            transformed_value DOUBLE,
            PRIMARY KEY (state_id, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS creature_state_labels (
            state_id TEXT PRIMARY KEY,
            coherence_class TEXT,
            organization_class TEXT,
            mobility_class TEXT,
            creature_bucket TEXT,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_export_resolutions (
            specimen_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            original_export_dir TEXT,
            resolved_export_dir TEXT,
            replayable BOOLEAN NOT NULL,
            resolution_source TEXT NOT NULL,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS context_trials (
            context_trial_id TEXT PRIMARY KEY,
            specimen_id TEXT NOT NULL,
            study_id TEXT NOT NULL,
            context_id TEXT NOT NULL,
            control_program_id TEXT,
            environment TEXT,
            perturbation TEXT,
            repeat_index INTEGER NOT NULL,
            results_path TEXT,
            summary_path TEXT,
            provenance_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS context_sample_axes (
            context_trial_id TEXT NOT NULL,
            step INTEGER NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            PRIMARY KEY (context_trial_id, step, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS context_outcomes (
            context_trial_id TEXT NOT NULL,
            outcome_kind TEXT NOT NULL,
            outcome_value DOUBLE,
            metadata_json JSON NOT NULL,
            PRIMARY KEY (context_trial_id, outcome_kind)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trajectory_segments (
            segment_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            specimen_id TEXT,
            context_trial_id TEXT,
            context_id TEXT,
            segment_kind TEXT NOT NULL,
            start_step INTEGER,
            end_step INTEGER,
            segment_index INTEGER NOT NULL,
            summary_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fiber_groups (
            fiber_group_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            grouping_kind TEXT NOT NULL,
            state_class_key TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            volume_proxy DOUBLE,
            diversity_proxy DOUBLE,
            connectivity_proxy DOUBLE,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fiber_group_members (
            fiber_group_id TEXT NOT NULL,
            state_id TEXT NOT NULL,
            specimen_id TEXT,
            PRIMARY KEY (fiber_group_id, state_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS universality_runs (
            universality_run_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            comparison_scope TEXT NOT NULL,
            coarse_kind TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            summary_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS topology_runs (
            topology_run_id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL,
            space_kind TEXT NOT NULL,
            group_key TEXT,
            group_value TEXT,
            input_query_json JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            summary_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS topology_features (
            topology_run_id TEXT NOT NULL,
            feature_index INTEGER NOT NULL,
            dimension INTEGER NOT NULL,
            birth DOUBLE NOT NULL,
            death DOUBLE,
            persistence DOUBLE,
            PRIMARY KEY (topology_run_id, feature_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS specimen_axes (
            specimen_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            axis_family TEXT NOT NULL,
            raw_value DOUBLE,
            transformed_value DOUBLE,
            PRIMARY KEY (specimen_id, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS development_sample_axes (
            specimen_id TEXT NOT NULL,
            step INTEGER NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            PRIMARY KEY (specimen_id, step, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS perturbation_axes (
            trial_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            transformed_value DOUBLE,
            PRIMARY KEY (trial_id, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS specimen_status (
            specimen_id TEXT PRIMARY KEY,
            has_export BOOLEAN NOT NULL,
            has_replay BOOLEAN NOT NULL,
            valid_terminal_fingerprint BOOLEAN NOT NULL,
            valid_development_trace BOOLEAN NOT NULL,
            atlas_eligible BOOLEAN NOT NULL,
            focal_eligible BOOLEAN NOT NULL,
            status_reason TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS morphospace_sources (
            source_id TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            label TEXT NOT NULL,
            version_label TEXT,
            doi TEXT,
            url TEXT,
            license TEXT,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            observation_id TEXT PRIMARY KEY,
            specimen_id TEXT,
            study_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            context_id TEXT,
            observation_kind TEXT NOT NULL,
            observed_at TIMESTAMP,
            step INTEGER,
            source_ref TEXT,
            payload_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_spaces (
            feature_space_id TEXT PRIMARY KEY,
            feature_space_kind TEXT NOT NULL,
            label TEXT NOT NULL,
            version_label TEXT NOT NULL,
            coordinate_policy TEXT NOT NULL,
            metric_json JSON NOT NULL,
            metadata_json JSON NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_axes (
            feature_space_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            axis_index INTEGER NOT NULL,
            axis_family TEXT NOT NULL,
            label TEXT,
            units TEXT,
            metadata_json JSON NOT NULL,
            PRIMARY KEY (feature_space_id, axis_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_values (
            observation_id TEXT NOT NULL,
            feature_space_id TEXT NOT NULL,
            axis_id TEXT NOT NULL,
            raw_value DOUBLE,
            normalized_value DOUBLE,
            metadata_json JSON NOT NULL,
            PRIMARY KEY (observation_id, feature_space_id, axis_id)
        )
        """
    )
    create_views(connection)


def create_views(connection: DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE VIEW atlas_specimens_vw AS
        SELECT ss.study_id, s.*, st.has_replay, st.atlas_eligible, st.focal_eligible
        FROM study_specimens AS ss
        JOIN specimens AS s USING (specimen_id)
        LEFT JOIN specimen_status AS st USING (specimen_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW atlas_group_summary_vw AS
        WITH base AS (
            SELECT study_id, specimen_id, 'family_kind' AS group_key, family_kind AS group_value
            FROM atlas_specimens_vw WHERE family_kind IS NOT NULL
            UNION ALL
            SELECT study_id, specimen_id, 'regime_family', regime_family
            FROM atlas_specimens_vw WHERE regime_family IS NOT NULL
            UNION ALL
            SELECT study_id, specimen_id, 'geometry_family', geometry_family
            FROM atlas_specimens_vw WHERE geometry_family IS NOT NULL
            UNION ALL
            SELECT study_id, specimen_id, 'canonical_family', canonical_family
            FROM atlas_specimens_vw WHERE canonical_family IS NOT NULL
        )
        SELECT
            base.study_id,
            base.group_key,
            base.group_value,
            specimen_axes.axis_id,
            specimen_axes.axis_family,
            COUNT(*) AS specimen_count,
            median(specimen_axes.raw_value) AS raw_median,
            avg(specimen_axes.raw_value) AS raw_mean,
            median(specimen_axes.transformed_value) AS transformed_median,
            avg(specimen_axes.transformed_value) AS transformed_mean
        FROM base
        JOIN specimen_status ON specimen_status.specimen_id = base.specimen_id
        JOIN specimen_axes ON specimen_axes.specimen_id = base.specimen_id
        WHERE specimen_status.atlas_eligible
        GROUP BY 1, 2, 3, 4, 5
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW atlas_pairwise_contrasts_vw AS
        SELECT
            a.study_id,
            a.group_key,
            a.axis_id,
            a.group_value AS group_a,
            b.group_value AS group_b,
            b.transformed_median - a.transformed_median AS median_delta_transformed,
            abs(b.transformed_median - a.transformed_median) AS absolute_median_delta_transformed
        FROM atlas_group_summary_vw AS a
        JOIN atlas_group_summary_vw AS b
          ON a.study_id = b.study_id
         AND a.group_key = b.group_key
         AND a.axis_id = b.axis_id
         AND a.group_value < b.group_value
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW focal_response_summary_vw AS
        SELECT
            perturbation_trials.study_id,
            perturbation_trials.specimen_id,
            specimens.family_kind,
            specimens.regime_family,
            specimens.geometry_family,
            specimens.canonical_family,
            perturbation_trials.environment,
            perturbation_trials.perturbation,
            avg(
                CASE
                    WHEN perturbation_axes.axis_id = 'meanFragilityScore'
                    THEN perturbation_axes.raw_value
                END
            ) AS mean_fragility_score,
            avg(
                CASE
                    WHEN perturbation_axes.axis_id = 'meanRobustnessScore'
                    THEN perturbation_axes.raw_value
                END
            ) AS mean_robustness_score
        FROM perturbation_trials
        JOIN specimens USING (specimen_id)
        LEFT JOIN perturbation_axes USING (trial_id)
        WHERE perturbation_trials.perturbation <> 'baseline'
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW family_comparison_vw AS
        SELECT
            a.study_id,
            a.canonical_family AS family_a,
            b.canonical_family AS family_b,
            a.environment,
            a.perturbation,
            a.mean_fragility_score AS family_a_mean_fragility_score,
            b.mean_fragility_score AS family_b_mean_fragility_score,
            b.mean_fragility_score - a.mean_fragility_score AS delta,
            abs(b.mean_fragility_score - a.mean_fragility_score) AS abs_delta
        FROM focal_response_summary_vw AS a
        JOIN focal_response_summary_vw AS b
          ON a.study_id = b.study_id
         AND a.environment = b.environment
         AND a.perturbation = b.perturbation
         AND a.canonical_family < b.canonical_family
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW topology_summary_vw AS
        WITH h1 AS (
            SELECT
                topology_run_id,
                COUNT(*) AS h1_feature_count,
                max(persistence) AS h1_top_persistence
            FROM topology_features
            WHERE dimension = 1
            GROUP BY topology_run_id
        )
        SELECT
            topology_runs.topology_run_id,
            topology_runs.study_id,
            topology_runs.space_kind,
            topology_runs.group_key,
            topology_runs.group_value,
            coalesce(h1.h1_feature_count, 0) AS h1_feature_count,
            coalesce(h1.h1_top_persistence, 0.0) AS h1_top_persistence
        FROM topology_runs
        LEFT JOIN h1 USING (topology_run_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW biological_states_vw AS
        SELECT
            anatomical_states.state_id,
            anatomical_states.specimen_id,
            anatomical_states.study_id,
            anatomical_states.context_id,
            contexts.context_kind,
            contexts.label AS context_label,
            anatomical_states.source_kind,
            anatomical_states.source_ref,
            anatomical_states.recorded_at,
            specimens.family_kind,
            specimens.regime_family,
            specimens.geometry_family,
            specimens.canonical_family,
            anatomical_states.state_json
        FROM anatomical_states
        LEFT JOIN contexts USING (context_id)
        LEFT JOIN specimens USING (specimen_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW creature_states_vw AS
        SELECT
            biological_states_vw.state_id,
            biological_states_vw.specimen_id,
            biological_states_vw.study_id,
            biological_states_vw.context_id,
            biological_states_vw.context_kind,
            biological_states_vw.context_label,
            biological_states_vw.source_kind,
            biological_states_vw.source_ref,
            biological_states_vw.recorded_at,
            biological_states_vw.family_kind,
            biological_states_vw.regime_family,
            biological_states_vw.geometry_family,
            biological_states_vw.canonical_family,
            biological_states_vw.state_json,
            creature_state_labels.coherence_class,
            creature_state_labels.organization_class,
            creature_state_labels.mobility_class,
            creature_state_labels.creature_bucket,
            max(CASE WHEN creature_signal_axes.axis_id = 'largest_component_share_final'
                THEN creature_signal_axes.raw_value END
            ) AS largest_component_share_final,
            max(CASE WHEN creature_signal_axes.axis_id = 'coherence_mean'
                THEN creature_signal_axes.raw_value END
            ) AS coherence_mean,
            max(CASE WHEN creature_signal_axes.axis_id = 'coherence_min'
                THEN creature_signal_axes.raw_value END
            ) AS coherence_min,
            max(CASE WHEN creature_signal_axes.axis_id = 'fragmentation_peak'
                THEN creature_signal_axes.raw_value END
            ) AS fragmentation_peak,
            max(CASE WHEN creature_signal_axes.axis_id = 'fragmentation_variability'
                THEN creature_signal_axes.raw_value END
            ) AS fragmentation_variability,
            max(CASE WHEN creature_signal_axes.axis_id = 'part_persistence_score'
                THEN creature_signal_axes.raw_value END
            ) AS part_persistence_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'shape_persistence_score'
                THEN creature_signal_axes.raw_value END
            ) AS shape_persistence_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'symmetry_stability_score'
                THEN creature_signal_axes.raw_value END
            ) AS symmetry_stability_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'polarity_stability_score'
                THEN creature_signal_axes.raw_value END
            ) AS polarity_stability_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'enclosure_persistence_score'
                THEN creature_signal_axes.raw_value END
            ) AS enclosure_persistence_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'whole_body_motion_score'
                THEN creature_signal_axes.raw_value END
            ) AS whole_body_motion_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'deformation_without_dissolution_score'
                THEN creature_signal_axes.raw_value END
            ) AS deformation_without_dissolution_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'localization_score'
                THEN creature_signal_axes.raw_value END
            ) AS localization_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'extent_stability_score'
                THEN creature_signal_axes.raw_value END
            ) AS extent_stability_score,
            max(CASE WHEN creature_signal_axes.axis_id = 'temporal_individuality_score'
                THEN creature_signal_axes.raw_value END
            ) AS temporal_individuality_score
        FROM biological_states_vw
        LEFT JOIN creature_state_labels USING (state_id)
        LEFT JOIN creature_signal_axes USING (state_id)
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW context_trial_summary_vw AS
        SELECT
            context_trials.study_id,
            context_trials.context_trial_id,
            context_trials.specimen_id,
            contexts.context_kind,
            contexts.label AS context_label,
            context_trials.environment,
            context_trials.perturbation,
            context_trials.repeat_index,
            specimens.family_kind,
            specimens.regime_family,
            specimens.geometry_family,
            specimens.canonical_family,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'mean_fragility_score'
                    THEN context_outcomes.outcome_value END
            ) AS mean_fragility_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'mean_robustness_score'
                    THEN context_outcomes.outcome_value END
            ) AS mean_robustness_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'class_shift_score'
                    THEN context_outcomes.outcome_value END
            ) AS class_shift_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'goal_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS goal_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'peak_goal_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS peak_goal_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'cumulative_goal_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS cumulative_goal_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_baseline_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_baseline_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'control_cost_proxy'
                    THEN context_outcomes.outcome_value END
            ) AS control_cost_proxy,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'path_length_ratio_to_reference'
                    THEN context_outcomes.outcome_value END
            ) AS path_length_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'displacement_ratio_to_reference'
                    THEN context_outcomes.outcome_value END
            ) AS displacement_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'center_velocity_ratio_to_reference'
                    THEN context_outcomes.outcome_value END
            ) AS center_velocity_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_class_change_count'
                    THEN context_outcomes.outcome_value END
            ) AS trace_class_change_count,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_path_length'
                    THEN context_outcomes.outcome_value END
            ) AS trace_path_length,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_displacement'
                    THEN context_outcomes.outcome_value END
            ) AS trace_displacement,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_peak_center_velocity'
                    THEN context_outcomes.outcome_value END
            ) AS trace_peak_center_velocity,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_mean_center_velocity'
                    THEN context_outcomes.outcome_value END
            ) AS trace_mean_center_velocity,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_sample_count'
                    THEN context_outcomes.outcome_value END
            ) AS trace_sample_count,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_path_length_ratio_to_reference'
                    THEN context_outcomes.outcome_value END
            ) AS trace_path_length_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'trace_displacement_ratio_to_reference'
                    THEN context_outcomes.outcome_value END
            ) AS trace_displacement_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = (
                    'trace_peak_center_velocity_ratio_to_reference'
                )
                    THEN context_outcomes.outcome_value END
            ) AS trace_peak_center_velocity_ratio_to_reference,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'recovery_lag_steps'
                    THEN context_outcomes.outcome_value END
            ) AS recovery_lag_steps
        FROM context_trials
        JOIN contexts USING (context_id)
        LEFT JOIN specimens USING (specimen_id)
        LEFT JOIN context_outcomes USING (context_trial_id)
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW comparison_observations_vw AS
        SELECT
            observations.observation_id,
            observations.specimen_id,
            observations.study_id,
            studies.study_kind,
            studies.label AS study_label,
            observations.source_id,
            morphospace_sources.source_kind,
            morphospace_sources.label AS source_label,
            observations.context_id,
            contexts.context_kind,
            contexts.label AS context_label,
            observations.observation_kind,
            observations.observed_at,
            observations.step,
            observations.source_ref,
            specimens.run_id,
            specimens.campaign_id,
            specimens.source_mode,
            specimens.source_algorithm,
            specimens.config_hash,
            specimens.family_kind,
            specimens.regime_family,
            specimens.geometry_family,
            specimens.canonical_family,
            specimens.runtime_family,
            observations.payload_json
        FROM observations
        LEFT JOIN studies USING (study_id)
        LEFT JOIN morphospace_sources USING (source_id)
        LEFT JOIN contexts USING (context_id)
        LEFT JOIN specimens USING (specimen_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW comparison_feature_values_vw AS
        SELECT
            comparison_observations_vw.observation_id,
            comparison_observations_vw.specimen_id,
            comparison_observations_vw.study_id,
            comparison_observations_vw.study_kind,
            comparison_observations_vw.study_label,
            comparison_observations_vw.source_id,
            comparison_observations_vw.source_kind,
            comparison_observations_vw.source_label,
            comparison_observations_vw.context_id,
            comparison_observations_vw.context_kind,
            comparison_observations_vw.context_label,
            comparison_observations_vw.observation_kind,
            comparison_observations_vw.run_id,
            comparison_observations_vw.campaign_id,
            comparison_observations_vw.source_mode,
            comparison_observations_vw.source_algorithm,
            comparison_observations_vw.config_hash,
            feature_values.feature_space_id,
            feature_spaces.feature_space_kind,
            feature_spaces.label AS feature_space_label,
            feature_spaces.version_label AS feature_space_version_label,
            feature_axes.axis_id,
            feature_axes.axis_index,
            feature_axes.axis_family,
            feature_axes.label AS axis_label,
            feature_axes.units,
            feature_values.raw_value,
            feature_values.normalized_value,
            feature_values.metadata_json
        FROM feature_values
        JOIN comparison_observations_vw USING (observation_id)
        JOIN feature_spaces USING (feature_space_id)
        JOIN feature_axes
          ON feature_axes.feature_space_id = feature_values.feature_space_id
         AND feature_axes.axis_id = feature_values.axis_id
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW lenia_rule_family_summary_vw AS
        WITH lenia_specimens AS (
            SELECT
                specimens.*,
                coalesce(
                    specimens.runtime_family,
                    json_extract_string(specimens.specimen_manifest_json, '$.runtimeFamily'),
                    '<unknown>'
                ) AS resolved_runtime_family,
                try_cast(
                    json_extract(
                        specimens.specimen_manifest_json,
                        '$.snapshots.descriptorBundle.genotype.kernelCount'
                    ) AS INTEGER
                ) AS resolved_kernel_count,
                try_cast(
                    json_extract(
                        specimens.specimen_manifest_json,
                        '$.snapshots.descriptorBundle.terminal.massChannel'
                    ) AS INTEGER
                ) AS resolved_mass_channel
            FROM specimens
            WHERE coalesce(
                    specimens.runtime_family,
                    json_extract_string(specimens.specimen_manifest_json, '$.runtimeFamily')
                ) IS NOT NULL
        ), common_morphology_specimens AS (
            SELECT DISTINCT comparison_observations_vw.specimen_id
            FROM comparison_observations_vw
            JOIN feature_values USING (observation_id)
            WHERE feature_values.feature_space_id = 'common_morphology_v1'
              AND comparison_observations_vw.source_id = 'lenia_swarm'
        )
        SELECT
            concat(
                lenia_specimens.resolved_runtime_family,
                ':',
                coalesce(lenia_specimens.config_hash, '<no-config>'),
                ':',
                coalesce(lenia_specimens.source_mode, '<none>'),
                ':',
                coalesce(lenia_specimens.source_algorithm, '<none>')
            ) AS rule_family_key,
            lenia_specimens.resolved_runtime_family AS runtime_family,
            lenia_specimens.config_hash,
            coalesce(lenia_specimens.source_mode, '<none>') AS source_mode,
            coalesce(lenia_specimens.source_algorithm, '<none>') AS source_algorithm,
            lenia_specimens.resolved_kernel_count AS kernel_count,
            lenia_specimens.resolved_mass_channel AS mass_channel,
            count(*) AS specimen_count,
            count(DISTINCT lenia_specimens.run_id) AS run_count,
            count(DISTINCT lenia_specimens.initial_condition_family)
                AS initial_condition_family_count,
            sum(
                CASE
                    WHEN common_morphology_specimens.specimen_id IS NULL THEN 0
                    ELSE 1
                END
            ) AS common_morphology_specimen_count,
            min(lenia_specimens.recorded_at) AS first_recorded_at,
            max(lenia_specimens.recorded_at) AS last_recorded_at
        FROM lenia_specimens
        LEFT JOIN common_morphology_specimens USING (specimen_id)
        GROUP BY
            lenia_specimens.resolved_runtime_family,
            lenia_specimens.config_hash,
            coalesce(lenia_specimens.source_mode, '<none>'),
            coalesce(lenia_specimens.source_algorithm, '<none>'),
            lenia_specimens.resolved_kernel_count,
            lenia_specimens.resolved_mass_channel
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW creature_context_summary_vw AS
        SELECT
            context_trial_summary_vw.*,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'body_plan_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS body_plan_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_body_plan_error_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_body_plan_error_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'body_plan_class_shift_score'
                    THEN context_outcomes.outcome_value END
            ) AS body_plan_class_shift_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_body_plan_class_shift_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_body_plan_class_shift_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'coherence_drop_score'
                    THEN context_outcomes.outcome_value END
            ) AS coherence_drop_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_coherence_drop_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_coherence_drop_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'organization_drop_score'
                    THEN context_outcomes.outcome_value END
            ) AS organization_drop_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_organization_drop_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_organization_drop_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'whole_body_motion_change_score'
                    THEN context_outcomes.outcome_value END
            ) AS whole_body_motion_change_score,
            avg(
                CASE WHEN context_outcomes.outcome_kind = 'matched_whole_body_motion_change_score'
                    THEN context_outcomes.outcome_value END
            ) AS matched_whole_body_motion_change_score
        FROM context_trial_summary_vw
        LEFT JOIN context_outcomes USING (context_trial_id)
        GROUP BY
            context_trial_summary_vw.study_id,
            context_trial_summary_vw.context_trial_id,
            context_trial_summary_vw.specimen_id,
            context_trial_summary_vw.context_kind,
            context_trial_summary_vw.context_label,
            context_trial_summary_vw.environment,
            context_trial_summary_vw.perturbation,
            context_trial_summary_vw.repeat_index,
            context_trial_summary_vw.family_kind,
            context_trial_summary_vw.regime_family,
            context_trial_summary_vw.geometry_family,
            context_trial_summary_vw.canonical_family,
            context_trial_summary_vw.mean_fragility_score,
            context_trial_summary_vw.mean_robustness_score,
            context_trial_summary_vw.class_shift_score,
            context_trial_summary_vw.goal_error_score,
            context_trial_summary_vw.peak_goal_error_score,
            context_trial_summary_vw.cumulative_goal_error_score,
            context_trial_summary_vw.matched_baseline_error_score,
            context_trial_summary_vw.control_cost_proxy,
            context_trial_summary_vw.path_length_ratio_to_reference,
            context_trial_summary_vw.displacement_ratio_to_reference,
            context_trial_summary_vw.center_velocity_ratio_to_reference,
            context_trial_summary_vw.trace_class_change_count,
            context_trial_summary_vw.trace_path_length,
            context_trial_summary_vw.trace_displacement,
            context_trial_summary_vw.trace_peak_center_velocity,
            context_trial_summary_vw.trace_mean_center_velocity,
            context_trial_summary_vw.trace_sample_count,
            context_trial_summary_vw.trace_path_length_ratio_to_reference,
            context_trial_summary_vw.trace_displacement_ratio_to_reference,
            context_trial_summary_vw.trace_peak_center_velocity_ratio_to_reference,
            context_trial_summary_vw.recovery_lag_steps
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW creature_discovery_candidates_vw AS
        WITH context_preservation AS (
            SELECT
                specimen_id,
                avg(body_plan_error_score) AS mean_body_plan_error_score,
                avg(body_plan_class_shift_score) AS mean_body_plan_class_shift_score,
                avg(coherence_drop_score) AS mean_coherence_drop_score,
                avg(organization_drop_score) AS mean_organization_drop_score,
                avg(whole_body_motion_change_score) AS mean_whole_body_motion_change_score
            FROM creature_context_summary_vw
            WHERE context_kind <> 'baseline'
            GROUP BY specimen_id
        )
        SELECT
            creature_states_vw.state_id,
            creature_states_vw.specimen_id,
            creature_states_vw.study_id,
            studies.study_kind,
            creature_states_vw.context_id,
            creature_states_vw.context_kind,
            creature_states_vw.context_label,
            creature_states_vw.source_kind,
            creature_states_vw.source_ref,
            specimens.score,
            specimens.results_path,
            specimens.export_dir,
            specimens.activity_path,
            specimens.fingerprint_path,
            specimens.provenance_json,
            creature_states_vw.family_kind,
            creature_states_vw.regime_family,
            creature_states_vw.geometry_family,
            creature_states_vw.canonical_family,
            creature_states_vw.coherence_class,
            creature_states_vw.organization_class,
            creature_states_vw.mobility_class,
            creature_states_vw.creature_bucket,
            creature_states_vw.largest_component_share_final,
            creature_states_vw.coherence_mean,
            creature_states_vw.coherence_min,
            creature_states_vw.fragmentation_peak,
            creature_states_vw.fragmentation_variability,
            creature_states_vw.part_persistence_score,
            creature_states_vw.shape_persistence_score,
            creature_states_vw.symmetry_stability_score,
            creature_states_vw.polarity_stability_score,
            creature_states_vw.enclosure_persistence_score,
            creature_states_vw.whole_body_motion_score,
            creature_states_vw.deformation_without_dissolution_score,
            creature_states_vw.localization_score,
            creature_states_vw.extent_stability_score,
            creature_states_vw.temporal_individuality_score,
            discovery_export_resolutions.original_export_dir,
            discovery_export_resolutions.resolved_export_dir,
            discovery_export_resolutions.replayable,
            discovery_export_resolutions.resolution_source,
            discovery_export_resolutions.metadata_json AS resolution_metadata_json,
            context_preservation.mean_body_plan_error_score,
            context_preservation.mean_body_plan_class_shift_score,
            context_preservation.mean_coherence_drop_score,
            context_preservation.mean_organization_drop_score,
            context_preservation.mean_whole_body_motion_change_score
        FROM creature_states_vw
        JOIN studies ON studies.study_id = creature_states_vw.study_id
        LEFT JOIN specimens USING (specimen_id)
        LEFT JOIN discovery_export_resolutions USING (specimen_id)
        LEFT JOIN context_preservation USING (specimen_id)
        WHERE creature_states_vw.context_kind = 'baseline'
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW fiber_groups_vw AS
        SELECT
            fiber_groups.*,
            count(fiber_group_members.state_id) AS joined_member_count
        FROM fiber_groups
        LEFT JOIN fiber_group_members USING (fiber_group_id)
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE VIEW universality_summary_vw AS
        SELECT
            universality_run_id,
            study_id,
            comparison_scope,
            coarse_kind,
            created_at,
            summary_json
        FROM universality_runs
        """
    )
