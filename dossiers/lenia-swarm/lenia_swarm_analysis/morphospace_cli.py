from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.morphospace.atlas_evidence import (
    build_atlas_evidence_packet_from_files,
)
from lenia_swarm_analysis.morphospace.catalog_qc import apply_shape_behavior_qc
from lenia_swarm_analysis.morphospace.common_morphology import derive_common_morphology
from lenia_swarm_analysis.morphospace.derive_anatomy import derive_anatomy
from lenia_swarm_analysis.morphospace.derive_axes import derive_axes
from lenia_swarm_analysis.morphospace.derive_lenia_features import (
    derive_lenia_terminal_features,
)
from lenia_swarm_analysis.morphospace.derive_status import derive_status
from lenia_swarm_analysis.morphospace.export_biological import export_biological_study
from lenia_swarm_analysis.morphospace.export_creature_discovery import (
    export_creature_discovery,
)
from lenia_swarm_analysis.morphospace.feature_matrix import (
    compare_feature_cohorts,
    export_feature_matrix,
    run_feature_tda,
)
from lenia_swarm_analysis.morphospace.feature_tda_profile import (
    profile_names,
    run_feature_tda_profile,
)
from lenia_swarm_analysis.morphospace.finite_size_validation import (
    build_finite_size_validation_packet,
)
from lenia_swarm_analysis.morphospace.high_fiber_null_validation import (
    build_high_fiber_null_validation_packet,
)
from lenia_swarm_analysis.morphospace.ingest_dryad_fish import (
    ingest_dryad_fish_body_shape,
)
from lenia_swarm_analysis.morphospace.ingest_embryomaker import (
    ingest_embryomaker_snapshots,
)
from lenia_swarm_analysis.morphospace.ingest_reference_bundle import import_reference_bundle
from lenia_swarm_analysis.morphospace.promote_results import promote_results_jsonl
from lenia_swarm_analysis.morphospace.run_topology import run_topology
from lenia_swarm_analysis.morphospace.track1_raw_summary import (
    write_track1_candidate_manifest,
    write_track1_raw_summary_packet,
)
from lenia_swarm_analysis.morphospace.warehouse import (
    connect_database,
    connect_read_only_database,
    warehouse_transaction,
)

ConnectionCallback = Callable[[Any], dict[str, Any]]


def _using_warehouse(
    warehouse_path: Path,
    callback: ConnectionCallback,
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    connector = connect_read_only_database if read_only else connect_database
    connection = connector(warehouse_path)
    try:
        if read_only:
            return callback(connection)
        with warehouse_transaction(connection):
            return callback(connection)
    finally:
        connection.close()


def _resolve_optional_path(path: Path | None) -> Path | None:
    return path.resolve() if path is not None else None


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _add_feature_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-id")
    parser.add_argument("--study-id")
    parser.add_argument("--study-kind")
    parser.add_argument("--run-id")
    parser.add_argument("--run-id-contains")
    parser.add_argument("--source-mode")
    parser.add_argument("--observation-kind")
    parser.add_argument("--source-algorithm")
    parser.add_argument("--canonical-family")


def _feature_filter_kwargs(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "source_id": args.source_id,
        "study_id": args.study_id,
        "study_kind": args.study_kind,
        "run_id": args.run_id,
        "run_id_contains": args.run_id_contains,
        "source_mode": args.source_mode,
        "observation_kind": args.observation_kind,
        "source_algorithm": args.source_algorithm,
        "canonical_family": args.canonical_family,
    }


def _add_cohort_filter_args(parser: argparse.ArgumentParser, prefix: str) -> None:
    for name in (
        "source-id",
        "study-id",
        "study-kind",
        "run-id",
        "run-id-contains",
        "source-mode",
        "observation-kind",
        "source-algorithm",
        "canonical-family",
    ):
        parser.add_argument(f"--{prefix}-{name}")


def _cohort_filter_kwargs(args: argparse.Namespace, prefix: str) -> dict[str, str | None]:
    return {
        f"{prefix}_source_id": getattr(args, f"{prefix}_source_id"),
        f"{prefix}_study_id": getattr(args, f"{prefix}_study_id"),
        f"{prefix}_study_kind": getattr(args, f"{prefix}_study_kind"),
        f"{prefix}_run_id": getattr(args, f"{prefix}_run_id"),
        f"{prefix}_run_id_contains": getattr(args, f"{prefix}_run_id_contains"),
        f"{prefix}_source_mode": getattr(args, f"{prefix}_source_mode"),
        f"{prefix}_observation_kind": getattr(args, f"{prefix}_observation_kind"),
        f"{prefix}_source_algorithm": getattr(args, f"{prefix}_source_algorithm"),
        f"{prefix}_canonical_family": getattr(args, f"{prefix}_canonical_family"),
    }


def refresh_compendium_warehouse(
    *,
    warehouse_path: Path,
    compendium_path: Path,
    label: str | None = None,
    run_id: str | None = None,
    topology: bool = False,
    source_packet_kind: str = "focal",
    min_group_size: int = 2,
    max_homology_dim: int = 1,
) -> dict[str, Any]:
    from lenia_swarm_analysis.morphospace.ingest_compendium import (
        _ingest_compendium,
        _open_compendium_snapshot,
        _source_identity,
    )

    connection = connect_database(warehouse_path)
    resolved_compendium_path = compendium_path.expanduser().resolve(strict=True)
    source = _open_compendium_snapshot(resolved_compendium_path, run_id=run_id)
    try:
        with warehouse_transaction(connection):
            study_id = _ingest_compendium(
                connection,
                compendium_path=resolved_compendium_path,
                source=source,
                label=label,
                run_id=run_id,
            )
            axes_updated = (
                0
                if run_id is not None
                else derive_axes(connection, study_id=study_id)
            )
            status_updated = derive_status(connection, study_id=study_id)
            anatomy_updated = derive_anatomy(connection, study_id=study_id)
            terminal_features = derive_lenia_terminal_features(connection, study_id=study_id)
            common_features = derive_common_morphology(connection, study_id=study_id)
            topology_study_id: str | None = None
            if topology:
                topology_study_id = run_topology(
                    connection,
                    study_id=study_id,
                    source_packet_kind=source_packet_kind,
                    min_group_size=min_group_size,
                    max_homology_dim=max_homology_dim,
                )
            if _source_identity(resolved_compendium_path) != source.source_identity:
                raise ValueError(
                    f"{resolved_compendium_path}: compendium changed during warehouse refresh"
                )
        return {
            "warehousePath": str(warehouse_path),
            "compendiumPath": str(resolved_compendium_path),
            "studyId": study_id,
            "runId": run_id,
            "axesUpdated": axes_updated,
            "statusUpdated": status_updated,
            "anatomyUpdated": anatomy_updated,
            "comparisonFeatureSpaceId": terminal_features["featureSpaceId"],
            "comparisonObservationsUpdated": terminal_features["observationCount"],
            "comparisonFeatureValuesUpdated": terminal_features["featureValueCount"],
            "terminalFeatureSpaceId": terminal_features["featureSpaceId"],
            "terminalObservationsUpdated": terminal_features["observationCount"],
            "terminalFeatureValuesUpdated": terminal_features["featureValueCount"],
            "commonFeatureSpaceId": common_features["featureSpaceId"],
            "commonObservationsUpdated": common_features["observationCount"],
            "commonFeatureValuesUpdated": common_features["featureValueCount"],
            "topologyStudyId": topology_study_id,
        }
    finally:
        source.connection.close()
        connection.close()


def migrate_warehouse(
    *,
    source_path: Path,
    destination_path: Path,
) -> dict[str, Any]:
    from lenia_swarm_analysis.morphospace.migrate_v9 import (
        build_warehouse_side_by_side,
    )

    result = build_warehouse_side_by_side(source_path, destination_path)
    return {
        "sourcePath": str(result.source_path),
        "destinationPath": str(result.destination_path),
        "sourceSha256": result.source_sha256,
        "receiptId": result.receipt_id,
        "copiedRowCounts": result.copied_row_counts,
        "descriptorCount": result.descriptor_count,
        "invalidationCount": result.invalidation_count,
        "membershipNormalization": result.membership_normalization,
        "nonfiniteFeatureQuarantine": result.nonfinite_feature_quarantine,
        "orphanContextOmission": result.orphan_context_omission,
    }


def regenerate_derived(
    *,
    warehouse_path: Path,
    study_id: str | None = None,
) -> dict[str, Any]:
    from lenia_swarm_analysis.morphospace.regenerate_v9 import (
        assert_required_external_sources_available,
        build_readiness_report,
        clear_full_regeneration_outputs,
        eligible_specimen_count,
    )
    from lenia_swarm_analysis.morphospace.warehouse import warehouse_transaction

    connection = connect_database(warehouse_path)
    try:
        with warehouse_transaction(connection):
            eligible_count: int | None = None
            if study_id is None:
                eligible_count = eligible_specimen_count(connection)
                if eligible_count <= 0:
                    raise ValueError("regenerate-derived found zero exact torus-v2 specimens")
                assert_required_external_sources_available(connection)
                clear_full_regeneration_outputs(connection)
            axes_updated = derive_axes(connection, study_id=study_id)
            status_updated = derive_status(connection, study_id=study_id)
            anatomy_updated = derive_anatomy(connection, study_id=study_id)
            terminal = derive_lenia_terminal_features(connection, study_id=study_id)
            common = derive_common_morphology(connection, study_id=study_id)
            readiness = (
                build_readiness_report(connection, eligible_count=eligible_count)
                if eligible_count is not None
                else None
            )
        return {
            "warehousePath": str(warehouse_path),
            "studyId": study_id,
            "axesUpdated": axes_updated,
            "statusUpdated": status_updated,
            "anatomyUpdated": anatomy_updated,
            "terminalFeatures": terminal,
            "commonMorphology": common,
            "readiness": readiness,
            "readyForWarehouseCutover": (
                readiness["readyForWarehouseCutover"] if readiness is not None else None
            ),
            "readyForNativeV2Analysis": (
                readiness["readyForNativeV2Analysis"] if readiness is not None else None
            ),
            "readyForFullCutover": (
                readiness["readyForFullCutover"] if readiness is not None else None
            ),
        }
    finally:
        connection.close()


def promote_results_packet(
    *,
    compendium_path: Path,
    run_dir: Path,
    run_id: str,
    source_mode: str,
    source_algorithm: str,
    batch_size: int,
) -> dict[str, Any]:
    return promote_results_jsonl(
        compendium_path=compendium_path,
        run_dir=run_dir,
        run_id=run_id,
        source_mode=source_mode,
        source_algorithm=source_algorithm,
        batch_size=batch_size,
    )


def apply_catalog_qc_packet(
    *,
    compendium_path: Path,
    audit_db: Path | None = None,
) -> dict[str, Any]:
    return apply_shape_behavior_qc(
        compendium_path=compendium_path,
        audit_db=audit_db,
    )


def run_topology_for_study(
    *,
    warehouse_path: Path,
    study_id: str,
    source_packet_kind: str,
    min_group_size: int,
    max_homology_dim: int,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        topology_study_id = run_topology(
            connection,
            study_id=study_id,
            source_packet_kind=source_packet_kind,
            min_group_size=min_group_size,
            max_homology_dim=max_homology_dim,
        )
        return {
            "warehousePath": str(warehouse_path),
            "studyId": study_id,
            "topologyStudyId": topology_study_id,
        }

    return _using_warehouse(warehouse_path, run)


def export_biological_packet(
    *,
    warehouse_path: Path,
    study_id: str,
    context_study_id: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return export_biological_study(
            connection,
            study_id=study_id,
            context_study_id=context_study_id,
        )

    return _using_warehouse(warehouse_path, run)


def export_creature_discovery_packet(
    *,
    warehouse_path: Path,
    study_id: str | None = None,
    lens: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return export_creature_discovery(
            connection,
            study_id=study_id,
            lens=lens,
        )

    return _using_warehouse(warehouse_path, run)


def import_dryad_fish_dataset(
    *,
    warehouse_path: Path,
    dataset_root: Path,
    label: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        payload = ingest_dryad_fish_body_shape(
            connection,
            dataset_root=dataset_root,
            label=label,
        )
        return {
            "warehousePath": str(warehouse_path),
            **payload,
        }

    return _using_warehouse(warehouse_path, run)


def import_embryomaker_snapshots_dataset(
    *,
    warehouse_path: Path,
    snapshot_roots: list[Path],
    label: str | None = None,
    limit: int | None = None,
    skip_invalid: bool = False,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        payload = ingest_embryomaker_snapshots(
            connection,
            snapshot_roots=snapshot_roots,
            label=label,
            limit=limit,
            skip_invalid=skip_invalid,
        )
        return {
            "warehousePath": str(warehouse_path),
            **payload,
        }

    return _using_warehouse(warehouse_path, run)


def import_reference_bundle_dataset(
    *,
    warehouse_path: Path,
    bundle_root: Path,
    label: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return {
            "warehousePath": str(warehouse_path),
            **import_reference_bundle(
                connection,
                bundle_root=bundle_root,
                label=label,
            ),
        }

    return _using_warehouse(warehouse_path, run)


def derive_lenia_features_packet(
    *,
    warehouse_path: Path,
    study_id: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return {
            "warehousePath": str(warehouse_path),
            **derive_lenia_terminal_features(connection, study_id=study_id),
        }

    return _using_warehouse(warehouse_path, run)


def derive_common_morphology_packet(
    *,
    warehouse_path: Path,
    dryad_fish_root: Path | None = None,
    study_id: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return {
            "warehousePath": str(warehouse_path),
            **derive_common_morphology(
                connection,
                dryad_fish_root=dryad_fish_root,
                study_id=study_id,
            ),
        }

    return _using_warehouse(warehouse_path, run)


def export_feature_matrix_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    study_kind: str | None = None,
    run_id: str | None = None,
    run_id_contains: str | None = None,
    source_mode: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    canonical_family: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return export_feature_matrix(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            run_id_contains=run_id_contains,
            source_mode=source_mode,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
            canonical_family=canonical_family,
        )

    return _using_warehouse(warehouse_path, run, read_only=True)


def run_feature_tda_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    study_kind: str | None = None,
    run_id: str | None = None,
    run_id_contains: str | None = None,
    source_mode: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    canonical_family: str | None = None,
    max_homology_dim: int = 1,
    summary_only: bool = False,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        payload = run_feature_tda(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            run_id_contains=run_id_contains,
            source_mode=source_mode,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
            canonical_family=canonical_family,
            max_homology_dim=max_homology_dim,
        )
        return _feature_tda_summary_payload(payload) if summary_only else payload

    return _using_warehouse(warehouse_path, run, read_only=True)


def run_feature_tda_profile_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    profile: str = "current",
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    study_kind: str | None = None,
    run_id: str | None = None,
    run_id_contains: str | None = None,
    source_mode: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    canonical_family: str | None = None,
    max_homology_dim: int = 1,
    stratify_by: str = "rule_family_key",
    seed: int = 0,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return run_feature_tda_profile(
            connection,
            feature_space_id=feature_space_id,
            profile=profile,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            run_id_contains=run_id_contains,
            source_mode=source_mode,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
            canonical_family=canonical_family,
            max_homology_dim=max_homology_dim,
            stratify_by=stratify_by,
            seed=seed,
        )

    return _using_warehouse(warehouse_path, run, read_only=True)


def compare_feature_cohorts_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    left_label: str = "left",
    right_label: str = "right",
    left_source_id: str | None = None,
    left_study_id: str | None = None,
    left_study_kind: str | None = None,
    left_run_id: str | None = None,
    left_run_id_contains: str | None = None,
    left_source_mode: str | None = None,
    left_observation_kind: str | None = None,
    left_source_algorithm: str | None = None,
    left_canonical_family: str | None = None,
    right_source_id: str | None = None,
    right_study_id: str | None = None,
    right_study_kind: str | None = None,
    right_run_id: str | None = None,
    right_run_id_contains: str | None = None,
    right_source_mode: str | None = None,
    right_observation_kind: str | None = None,
    right_source_algorithm: str | None = None,
    right_canonical_family: str | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return compare_feature_cohorts(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            left_label=left_label,
            right_label=right_label,
            left_source_id=left_source_id,
            left_study_id=left_study_id,
            left_study_kind=left_study_kind,
            left_run_id=left_run_id,
            left_run_id_contains=left_run_id_contains,
            left_source_mode=left_source_mode,
            left_observation_kind=left_observation_kind,
            left_source_algorithm=left_source_algorithm,
            left_canonical_family=left_canonical_family,
            right_source_id=right_source_id,
            right_study_id=right_study_id,
            right_study_kind=right_study_kind,
            right_run_id=right_run_id,
            right_run_id_contains=right_run_id_contains,
            right_source_mode=right_source_mode,
            right_observation_kind=right_observation_kind,
            right_source_algorithm=right_source_algorithm,
            right_canonical_family=right_canonical_family,
        )

    return _using_warehouse(warehouse_path, run, read_only=True)


def build_atlas_evidence_packet(
    *,
    atlas_findings_path: Path,
    common_tda_path: Path,
    h1_regions_path: Path | None = None,
    validation256_path: Path | None = None,
    terminal_tda_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    payload = build_atlas_evidence_packet_from_files(
        atlas_findings_path=atlas_findings_path,
        common_tda_path=common_tda_path,
        h1_regions_path=h1_regions_path,
        validation256_path=validation256_path,
        terminal_tda_path=terminal_tda_path,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_finite_size_packet(
    *,
    run_specs: list[str],
    output_path: Path | None = None,
) -> dict[str, Any]:
    runs: dict[str, Path] = {}
    for spec in run_specs:
        label, separator, path = spec.partition("=")
        if separator != "=" or not label or not path:
            raise ValueError(f"Invalid --run value '{spec}', expected label=path")
        if label in runs:
            raise ValueError(f"Duplicate finite-size run label '{label}'")
        runs[label] = Path(path).resolve()
    payload = build_finite_size_validation_packet(runs)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_high_fiber_null_validation(
    *,
    warehouse_path: Path,
    source_packet_path: Path,
    target_region_limit: int = 3,
    null_replicates: int = 256,
    seed: int = 20260527,
    min_region_count: int = 128,
    output_path: Path | None = None,
) -> dict[str, Any]:
    def run(connection: Any) -> dict[str, Any]:
        return build_high_fiber_null_validation_packet(
            connection,
            source_packet_path=source_packet_path,
            target_region_limit=target_region_limit,
            null_replicates=null_replicates,
            seed=seed,
            min_region_count=min_region_count,
        )

    payload = _using_warehouse(warehouse_path, run, read_only=True)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def summarize_track1_raw_packet(
    *,
    run_root: Path,
    output_path: Path,
    candidate_manifest_path: Path | None = None,
) -> dict[str, Any]:
    payload = write_track1_raw_summary_packet(
        run_root=run_root,
        output_path=output_path,
    )
    result = {
        "packetKind": payload["packetKind"],
        "outputPath": str(output_path),
        "completedRunCount": payload["completedRunCount"],
        "completedResultCount": payload["completedResultCount"],
        "runningRuns": payload["runningRuns"],
        "lineCountAnomalyCount": len(payload["lineCountAnomalies"]),
        "families": {
            key: {
                "runCount": family["runCount"],
                "resultCount": family["resultCount"],
                "moving": family["counts"].get("moving", 0),
                "compactMoving": family["counts"].get("compactMoving", 0),
                "coherentMover": family["counts"].get("coherentMover", 0),
                "compactConnected": family["counts"].get("compactConnected", 0),
            }
            for key, family in payload["families"].items()
        },
    }
    if candidate_manifest_path is not None:
        manifest = write_track1_candidate_manifest(
            summary_path=output_path,
            output_path=candidate_manifest_path,
        )
        result["candidateManifestPath"] = str(candidate_manifest_path)
        result["candidateCount"] = manifest["candidateCount"]
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-morphospace",
        description="Canonical warehouse lifecycle for lenia-swarm morphospace analysis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser(
        "migrate-warehouse",
        help="Build and publish a compact v10 warehouse beside a read-only v8 source",
    )
    migrate_parser.add_argument("--source", required=True, type=Path)
    migrate_parser.add_argument("--destination", required=True, type=Path)
    _add_json(migrate_parser)
    migrate_parser.set_defaults(
        handler=lambda args: migrate_warehouse(
            source_path=args.source.resolve(),
            destination_path=args.destination.resolve(),
        )
    )

    regenerate_parser = subparsers.add_parser(
        "regenerate-derived",
        help="Regenerate derived layers for torus-aware v2 specimens",
    )
    regenerate_parser.add_argument("--warehouse", required=True, type=Path)
    regenerate_parser.add_argument("--study-id")
    _add_json(regenerate_parser)
    regenerate_parser.set_defaults(
        handler=lambda args: regenerate_derived(
            warehouse_path=args.warehouse.resolve(),
            study_id=args.study_id,
        )
    )

    refresh = subparsers.add_parser(
        "refresh-compendium",
        help="Ingest a canonical compendium SQLite database into the DuckDB warehouse",
    )
    refresh.add_argument("--warehouse", required=True, type=Path)
    refresh.add_argument("--compendium", required=True, type=Path)
    refresh.add_argument("--label")
    refresh.add_argument("--run-id")
    refresh.add_argument("--topology", action="store_true")
    refresh.add_argument("--source-packet-kind", default="focal")
    refresh.add_argument("--min-group-size", type=int, default=2)
    refresh.add_argument("--max-homology-dim", type=int, default=1)
    _add_json(refresh)
    refresh.set_defaults(
        handler=lambda args: refresh_compendium_warehouse(
            warehouse_path=args.warehouse.resolve(),
            compendium_path=args.compendium.resolve(),
            label=args.label,
            run_id=args.run_id,
            topology=bool(args.topology),
            source_packet_kind=str(args.source_packet_kind),
            min_group_size=int(args.min_group_size),
            max_homology_dim=int(args.max_homology_dim),
        )
    )

    promote = subparsers.add_parser(
        "promote-results",
        help="Promote a completed results.jsonl run into the canonical compendium",
    )
    promote.add_argument("--compendium", required=True, type=Path)
    promote.add_argument("--run-dir", required=True, type=Path)
    promote.add_argument("--run-id", required=True)
    promote.add_argument("--source-mode", default="atlas-random")
    promote.add_argument("--source-algorithm", default="fl-2c20-motion-scorev2")
    promote.add_argument("--batch-size", type=int, default=2048)
    _add_json(promote)
    promote.set_defaults(
        handler=lambda args: promote_results_packet(
            compendium_path=args.compendium.resolve(),
            run_dir=args.run_dir.resolve(),
            run_id=str(args.run_id),
            source_mode=str(args.source_mode),
            source_algorithm=str(args.source_algorithm),
            batch_size=int(args.batch_size),
        )
    )

    catalog_qc = subparsers.add_parser(
        "apply-catalog-qc",
        help="Apply catalog QC status and quality flags to a compendium",
    )
    catalog_qc.add_argument("--compendium", required=True, type=Path)
    catalog_qc.add_argument("--audit-db", type=Path)
    _add_json(catalog_qc)
    catalog_qc.set_defaults(
        handler=lambda args: apply_catalog_qc_packet(
            compendium_path=args.compendium.resolve(),
            audit_db=_resolve_optional_path(args.audit_db),
        )
    )

    topology = subparsers.add_parser(
        "run-topology",
        help="Compute topology for an existing warehouse study",
    )
    topology.add_argument("--warehouse", required=True, type=Path)
    topology.add_argument("--study-id", required=True)
    topology.add_argument("--source-packet-kind", default="focal")
    topology.add_argument("--min-group-size", type=int, default=2)
    topology.add_argument("--max-homology-dim", type=int, default=1)
    _add_json(topology)
    topology.set_defaults(
        handler=lambda args: run_topology_for_study(
            warehouse_path=args.warehouse.resolve(),
            study_id=str(args.study_id),
            source_packet_kind=str(args.source_packet_kind),
            min_group_size=int(args.min_group_size),
            max_homology_dim=int(args.max_homology_dim),
        )
    )

    biological = subparsers.add_parser(
        "export-biological",
        help="Export a biological packet from an existing warehouse study",
    )
    biological.add_argument("--warehouse", required=True, type=Path)
    biological.add_argument("--study-id", required=True)
    biological.add_argument("--context-study-id")
    _add_json(biological)
    biological.set_defaults(
        handler=lambda args: export_biological_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=str(args.study_id),
            context_study_id=args.context_study_id,
        )
    )

    discovery = subparsers.add_parser(
        "export-creature-discovery",
        help="Export discovery candidates from the warehouse",
    )
    discovery.add_argument("--warehouse", required=True, type=Path)
    discovery.add_argument("--study-id")
    discovery.add_argument("--lens")
    _add_json(discovery)
    discovery.set_defaults(
        handler=lambda args: export_creature_discovery_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=args.study_id,
            lens=args.lens,
        )
    )

    dryad_fish = subparsers.add_parser(
        "import-dryad-fish",
        help="Import the Dryad fish body-shape GPA morphospace into the comparison layer",
    )
    dryad_fish.add_argument("--warehouse", required=True, type=Path)
    dryad_fish.add_argument("--dataset-root", required=True, type=Path)
    dryad_fish.add_argument("--label")
    _add_json(dryad_fish)
    dryad_fish.set_defaults(
        handler=lambda args: import_dryad_fish_dataset(
            warehouse_path=args.warehouse.resolve(),
            dataset_root=args.dataset_root.resolve(),
            label=args.label,
        )
    )

    embryomaker = subparsers.add_parser(
        "import-embryomaker-snapshots",
        help="Import external EmbryoMaker legacy snapshots into the comparison layer",
    )
    embryomaker.add_argument("--warehouse", required=True, type=Path)
    embryomaker.add_argument(
        "--snapshot-root",
        required=True,
        action="append",
        type=Path,
        help="Snapshot file or directory; may be passed more than once",
    )
    embryomaker.add_argument("--label")
    embryomaker.add_argument("--limit", type=int)
    embryomaker.add_argument("--skip-invalid", action="store_true")
    _add_json(embryomaker)
    embryomaker.set_defaults(
        handler=lambda args: import_embryomaker_snapshots_dataset(
            warehouse_path=args.warehouse.resolve(),
            snapshot_roots=[path.resolve() for path in args.snapshot_root],
            label=args.label,
            limit=args.limit,
            skip_invalid=bool(args.skip_invalid),
        )
    )

    reference_bundle = subparsers.add_parser(
        "import-reference-bundle",
        help="Register an external morphospace reference bundle in the warehouse",
    )
    reference_bundle.add_argument("--warehouse", required=True, type=Path)
    reference_bundle.add_argument("--bundle-root", required=True, type=Path)
    reference_bundle.add_argument("--label")
    _add_json(reference_bundle)
    reference_bundle.set_defaults(
        handler=lambda args: import_reference_bundle_dataset(
            warehouse_path=args.warehouse.resolve(),
            bundle_root=args.bundle_root.resolve(),
            label=args.label,
        )
    )

    lenia_features = subparsers.add_parser(
        "derive-lenia-features",
        help="Populate the comparison layer from existing Lenia terminal axes",
    )
    lenia_features.add_argument("--warehouse", required=True, type=Path)
    lenia_features.add_argument("--study-id")
    _add_json(lenia_features)
    lenia_features.set_defaults(
        handler=lambda args: derive_lenia_features_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=args.study_id,
        )
    )

    common_morphology = subparsers.add_parser(
        "derive-common-morphology",
        help="Populate a shared point-cloud morphology feature space",
    )
    common_morphology.add_argument("--warehouse", required=True, type=Path)
    common_morphology.add_argument("--dryad-fish-root", type=Path)
    common_morphology.add_argument("--study-id")
    _add_json(common_morphology)
    common_morphology.set_defaults(
        handler=lambda args: derive_common_morphology_packet(
            warehouse_path=args.warehouse.resolve(),
            dryad_fish_root=_resolve_optional_path(args.dryad_fish_root),
            study_id=args.study_id,
        )
    )

    matrix = subparsers.add_parser(
        "export-feature-matrix",
        help="Export a complete observation-by-feature matrix from the comparison layer",
    )
    matrix.add_argument("--warehouse", required=True, type=Path)
    matrix.add_argument("--feature-space-id", required=True)
    matrix.add_argument("--value-column", default="normalized_value")
    _add_feature_filter_args(matrix)
    _add_json(matrix)
    matrix.set_defaults(
        handler=lambda args: export_feature_matrix_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            **_feature_filter_kwargs(args),
        )
    )

    feature_tda = subparsers.add_parser(
        "run-feature-tda",
        help="Run persistent homology on a comparison-layer feature matrix",
    )
    feature_tda.add_argument("--warehouse", required=True, type=Path)
    feature_tda.add_argument("--feature-space-id", required=True)
    feature_tda.add_argument("--value-column", default="normalized_value")
    _add_feature_filter_args(feature_tda)
    feature_tda.add_argument("--max-homology-dim", type=int, default=1)
    feature_tda.add_argument("--summary-only", action="store_true")
    _add_json(feature_tda)
    feature_tda.set_defaults(
        handler=lambda args: run_feature_tda_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            **_feature_filter_kwargs(args),
            max_homology_dim=int(args.max_homology_dim),
            summary_only=bool(args.summary_only),
        )
    )

    feature_tda_profile = subparsers.add_parser(
        "run-feature-tda-profile",
        help="Run exact, thresholded, landmark, bootstrap, and stratum TDA diagnostics",
    )
    feature_tda_profile.add_argument("--warehouse", required=True, type=Path)
    feature_tda_profile.add_argument("--feature-space-id", required=True)
    feature_tda_profile.add_argument("--profile", choices=profile_names(), default="current")
    feature_tda_profile.add_argument("--value-column", default="normalized_value")
    _add_feature_filter_args(feature_tda_profile)
    feature_tda_profile.add_argument("--max-homology-dim", type=int, default=1)
    feature_tda_profile.add_argument("--stratify-by", default="rule_family_key")
    feature_tda_profile.add_argument("--seed", type=int, default=0)
    _add_json(feature_tda_profile)
    feature_tda_profile.set_defaults(
        handler=lambda args: run_feature_tda_profile_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            profile=str(args.profile),
            value_column=str(args.value_column),
            **_feature_filter_kwargs(args),
            max_homology_dim=int(args.max_homology_dim),
            stratify_by=str(args.stratify_by),
            seed=int(args.seed),
        )
    )

    compare = subparsers.add_parser(
        "compare-feature-cohorts",
        help="Compare two cohorts inside one comparison-layer feature space",
    )
    compare.add_argument("--warehouse", required=True, type=Path)
    compare.add_argument("--feature-space-id", required=True)
    compare.add_argument("--value-column", default="normalized_value")
    compare.add_argument("--left-label", default="left")
    compare.add_argument("--right-label", default="right")
    _add_cohort_filter_args(compare, "left")
    _add_cohort_filter_args(compare, "right")
    _add_json(compare)
    compare.set_defaults(
        handler=lambda args: compare_feature_cohorts_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            left_label=str(args.left_label),
            right_label=str(args.right_label),
            **_cohort_filter_kwargs(args, "left"),
            **_cohort_filter_kwargs(args, "right"),
        )
    )

    evidence = subparsers.add_parser(
        "build-atlas-evidence",
        help="Assemble FL-2C20 atlas findings, TDA, H1 localization, and validation evidence",
    )
    evidence.add_argument("--atlas-findings", required=True, type=Path)
    evidence.add_argument("--common-tda", required=True, type=Path)
    evidence.add_argument("--h1-regions", type=Path)
    evidence.add_argument("--validation256", type=Path)
    evidence.add_argument("--terminal-tda", type=Path)
    evidence.add_argument("--output", type=Path)
    _add_json(evidence)
    evidence.set_defaults(
        handler=lambda args: build_atlas_evidence_packet(
            atlas_findings_path=args.atlas_findings.resolve(),
            common_tda_path=args.common_tda.resolve(),
            h1_regions_path=_resolve_optional_path(args.h1_regions),
            validation256_path=_resolve_optional_path(args.validation256),
            terminal_tda_path=_resolve_optional_path(args.terminal_tda),
            output_path=_resolve_optional_path(args.output),
        )
    )

    finite_size = subparsers.add_parser(
        "build-finite-size-validation",
        help="Compare selected Lenia seeds across grid-size validation runs",
    )
    finite_size.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run label and run directory or results.jsonl path, formatted label=path",
    )
    finite_size.add_argument("--output", type=Path)
    _add_json(finite_size)
    finite_size.set_defaults(
        handler=lambda args: build_finite_size_packet(
            run_specs=list(args.run),
            output_path=_resolve_optional_path(args.output),
        )
    )

    high_fiber_null = subparsers.add_parser(
        "build-high-fiber-null-validation",
        help="Validate high-fiber regions against terminal-label shuffle nulls",
    )
    high_fiber_null.add_argument("--warehouse", required=True, type=Path)
    high_fiber_null.add_argument("--source-packet", required=True, type=Path)
    high_fiber_null.add_argument("--target-region-limit", type=int, default=3)
    high_fiber_null.add_argument("--null-replicates", type=int, default=256)
    high_fiber_null.add_argument("--seed", type=int, default=20260527)
    high_fiber_null.add_argument("--min-region-count", type=int, default=128)
    high_fiber_null.add_argument("--output", type=Path)
    _add_json(high_fiber_null)
    high_fiber_null.set_defaults(
        handler=lambda args: build_high_fiber_null_validation(
            warehouse_path=args.warehouse.resolve(),
            source_packet_path=args.source_packet.resolve(),
            target_region_limit=int(args.target_region_limit),
            null_replicates=int(args.null_replicates),
            seed=int(args.seed),
            min_region_count=int(args.min_region_count),
            output_path=_resolve_optional_path(args.output),
        )
    )

    track1_raw = subparsers.add_parser(
        "summarize-track1-raw",
        help="Summarize completed raw Track 1 result chunks without touching databases",
    )
    track1_raw.add_argument("--run-root", required=True, type=Path)
    track1_raw.add_argument("--output", required=True, type=Path)
    track1_raw.add_argument("--candidate-manifest", type=Path)
    _add_json(track1_raw)
    track1_raw.set_defaults(
        handler=lambda args: summarize_track1_raw_packet(
            run_root=args.run_root.resolve(),
            output_path=args.output.resolve(),
            candidate_manifest_path=_resolve_optional_path(args.candidate_manifest),
        )
    )

    return parser


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def _feature_tda_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    topology = payload["topology"]
    return {
        "packetKind": payload["packetKind"],
        "summary": payload["summary"],
        "featureSpace": payload["featureSpace"],
        "topology": {
            "scaleMax": topology["scaleMax"],
            "summaries": topology["summaries"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = args.handler(args)
    _print_payload(payload, as_json=bool(args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
