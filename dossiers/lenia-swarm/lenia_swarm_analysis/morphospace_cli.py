from __future__ import annotations

import argparse
import json
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
from lenia_swarm_analysis.morphospace.ingest_compendium import ingest_compendium
from lenia_swarm_analysis.morphospace.ingest_dryad_fish import (
    ingest_dryad_fish_body_shape,
)
from lenia_swarm_analysis.morphospace.promote_results import promote_results_jsonl
from lenia_swarm_analysis.morphospace.run_topology import run_topology
from lenia_swarm_analysis.morphospace.track1_raw_summary import (
    write_track1_candidate_manifest,
    write_track1_raw_summary_packet,
)
from lenia_swarm_analysis.morphospace.warehouse import (
    connect_database,
    connect_read_only_database,
)


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
    connection = connect_database(warehouse_path)
    try:
        study_id = ingest_compendium(
            connection,
            compendium_path=compendium_path,
            label=label,
            run_id=run_id,
            ingest_raw_rows=run_id is None,
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
        return {
            "warehousePath": str(warehouse_path),
            "compendiumPath": str(compendium_path),
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
    connection = connect_database(warehouse_path)
    try:
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
    finally:
        connection.close()


def export_biological_packet(
    *,
    warehouse_path: Path,
    study_id: str,
    context_study_id: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return export_biological_study(
            connection,
            study_id=study_id,
            context_study_id=context_study_id,
        )
    finally:
        connection.close()


def export_creature_discovery_packet(
    *,
    warehouse_path: Path,
    study_id: str | None = None,
    lens: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return export_creature_discovery(
            connection,
            study_id=study_id,
            lens=lens,
        )
    finally:
        connection.close()


def import_dryad_fish_dataset(
    *,
    warehouse_path: Path,
    dataset_root: Path,
    label: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        payload = ingest_dryad_fish_body_shape(
            connection,
            dataset_root=dataset_root,
            label=label,
        )
        return {
            "warehousePath": str(warehouse_path),
            **payload,
        }
    finally:
        connection.close()


def derive_lenia_features_packet(
    *,
    warehouse_path: Path,
    study_id: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return {
            "warehousePath": str(warehouse_path),
            **derive_lenia_terminal_features(connection, study_id=study_id),
        }
    finally:
        connection.close()


def derive_common_morphology_packet(
    *,
    warehouse_path: Path,
    dryad_fish_root: Path | None = None,
    study_id: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return {
            "warehousePath": str(warehouse_path),
            **derive_common_morphology(
                connection,
                dryad_fish_root=dryad_fish_root,
                study_id=study_id,
            ),
        }
    finally:
        connection.close()


def export_feature_matrix_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    run_id: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
) -> dict[str, Any]:
    connection = connect_read_only_database(warehouse_path)
    try:
        return export_feature_matrix(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
        )
    finally:
        connection.close()


def run_feature_tda_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    run_id: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    max_homology_dim: int = 1,
) -> dict[str, Any]:
    connection = connect_read_only_database(warehouse_path)
    try:
        return run_feature_tda(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
            max_homology_dim=max_homology_dim,
        )
    finally:
        connection.close()


def run_feature_tda_profile_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    profile: str = "current",
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    run_id: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    max_homology_dim: int = 1,
    stratify_by: str = "rule_family_key",
    seed: int = 0,
) -> dict[str, Any]:
    connection = connect_read_only_database(warehouse_path)
    try:
        return run_feature_tda_profile(
            connection,
            feature_space_id=feature_space_id,
            profile=profile,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            observation_kind=observation_kind,
            source_algorithm=source_algorithm,
            max_homology_dim=max_homology_dim,
            stratify_by=stratify_by,
            seed=seed,
        )
    finally:
        connection.close()


def compare_feature_cohorts_packet(
    *,
    warehouse_path: Path,
    feature_space_id: str,
    value_column: str = "normalized_value",
    left_label: str = "left",
    right_label: str = "right",
    left_source_id: str | None = None,
    left_study_id: str | None = None,
    left_run_id: str | None = None,
    left_observation_kind: str | None = None,
    left_source_algorithm: str | None = None,
    right_source_id: str | None = None,
    right_study_id: str | None = None,
    right_run_id: str | None = None,
    right_observation_kind: str | None = None,
    right_source_algorithm: str | None = None,
) -> dict[str, Any]:
    connection = connect_read_only_database(warehouse_path)
    try:
        return compare_feature_cohorts(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            left_label=left_label,
            right_label=right_label,
            left_source_id=left_source_id,
            left_study_id=left_study_id,
            left_run_id=left_run_id,
            left_observation_kind=left_observation_kind,
            left_source_algorithm=left_source_algorithm,
            right_source_id=right_source_id,
            right_study_id=right_study_id,
            right_run_id=right_run_id,
            right_observation_kind=right_observation_kind,
            right_source_algorithm=right_source_algorithm,
        )
    finally:
        connection.close()


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
    refresh.add_argument("--json", action="store_true")

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
    promote.add_argument("--json", action="store_true")

    catalog_qc = subparsers.add_parser(
        "apply-catalog-qc",
        help="Apply catalog QC status and quality flags to a compendium",
    )
    catalog_qc.add_argument("--compendium", required=True, type=Path)
    catalog_qc.add_argument("--audit-db", type=Path)
    catalog_qc.add_argument("--json", action="store_true")

    topology = subparsers.add_parser(
        "run-topology",
        help="Compute topology for an existing warehouse study",
    )
    topology.add_argument("--warehouse", required=True, type=Path)
    topology.add_argument("--study-id", required=True)
    topology.add_argument("--source-packet-kind", default="focal")
    topology.add_argument("--min-group-size", type=int, default=2)
    topology.add_argument("--max-homology-dim", type=int, default=1)
    topology.add_argument("--json", action="store_true")

    biological = subparsers.add_parser(
        "export-biological",
        help="Export a biological packet from an existing warehouse study",
    )
    biological.add_argument("--warehouse", required=True, type=Path)
    biological.add_argument("--study-id", required=True)
    biological.add_argument("--context-study-id")
    biological.add_argument("--json", action="store_true")

    discovery = subparsers.add_parser(
        "export-creature-discovery",
        help="Export discovery candidates from the warehouse",
    )
    discovery.add_argument("--warehouse", required=True, type=Path)
    discovery.add_argument("--study-id")
    discovery.add_argument("--lens")
    discovery.add_argument("--json", action="store_true")

    dryad_fish = subparsers.add_parser(
        "import-dryad-fish",
        help="Import the Dryad fish body-shape GPA morphospace into the comparison layer",
    )
    dryad_fish.add_argument("--warehouse", required=True, type=Path)
    dryad_fish.add_argument("--dataset-root", required=True, type=Path)
    dryad_fish.add_argument("--label")
    dryad_fish.add_argument("--json", action="store_true")

    lenia_features = subparsers.add_parser(
        "derive-lenia-features",
        help="Populate the comparison layer from existing Lenia terminal axes",
    )
    lenia_features.add_argument("--warehouse", required=True, type=Path)
    lenia_features.add_argument("--study-id")
    lenia_features.add_argument("--json", action="store_true")

    common_morphology = subparsers.add_parser(
        "derive-common-morphology",
        help="Populate a shared point-cloud morphology feature space",
    )
    common_morphology.add_argument("--warehouse", required=True, type=Path)
    common_morphology.add_argument("--dryad-fish-root", type=Path)
    common_morphology.add_argument("--study-id")
    common_morphology.add_argument("--json", action="store_true")

    matrix = subparsers.add_parser(
        "export-feature-matrix",
        help="Export a complete observation-by-feature matrix from the comparison layer",
    )
    matrix.add_argument("--warehouse", required=True, type=Path)
    matrix.add_argument("--feature-space-id", required=True)
    matrix.add_argument("--value-column", default="normalized_value")
    matrix.add_argument("--source-id")
    matrix.add_argument("--study-id")
    matrix.add_argument("--run-id")
    matrix.add_argument("--observation-kind")
    matrix.add_argument("--source-algorithm")
    matrix.add_argument("--json", action="store_true")

    feature_tda = subparsers.add_parser(
        "run-feature-tda",
        help="Run persistent homology on a comparison-layer feature matrix",
    )
    feature_tda.add_argument("--warehouse", required=True, type=Path)
    feature_tda.add_argument("--feature-space-id", required=True)
    feature_tda.add_argument("--value-column", default="normalized_value")
    feature_tda.add_argument("--source-id")
    feature_tda.add_argument("--study-id")
    feature_tda.add_argument("--run-id")
    feature_tda.add_argument("--observation-kind")
    feature_tda.add_argument("--source-algorithm")
    feature_tda.add_argument("--max-homology-dim", type=int, default=1)
    feature_tda.add_argument("--json", action="store_true")

    feature_tda_profile = subparsers.add_parser(
        "run-feature-tda-profile",
        help="Run exact, thresholded, landmark, bootstrap, and stratum TDA diagnostics",
    )
    feature_tda_profile.add_argument("--warehouse", required=True, type=Path)
    feature_tda_profile.add_argument("--feature-space-id", required=True)
    feature_tda_profile.add_argument("--profile", choices=profile_names(), default="current")
    feature_tda_profile.add_argument("--value-column", default="normalized_value")
    feature_tda_profile.add_argument("--source-id")
    feature_tda_profile.add_argument("--study-id")
    feature_tda_profile.add_argument("--run-id")
    feature_tda_profile.add_argument("--observation-kind")
    feature_tda_profile.add_argument("--source-algorithm")
    feature_tda_profile.add_argument("--max-homology-dim", type=int, default=1)
    feature_tda_profile.add_argument("--stratify-by", default="rule_family_key")
    feature_tda_profile.add_argument("--seed", type=int, default=0)
    feature_tda_profile.add_argument("--json", action="store_true")

    compare = subparsers.add_parser(
        "compare-feature-cohorts",
        help="Compare two cohorts inside one comparison-layer feature space",
    )
    compare.add_argument("--warehouse", required=True, type=Path)
    compare.add_argument("--feature-space-id", required=True)
    compare.add_argument("--value-column", default="normalized_value")
    compare.add_argument("--left-label", default="left")
    compare.add_argument("--right-label", default="right")
    compare.add_argument("--left-source-id")
    compare.add_argument("--left-study-id")
    compare.add_argument("--left-run-id")
    compare.add_argument("--left-observation-kind")
    compare.add_argument("--left-source-algorithm")
    compare.add_argument("--right-source-id")
    compare.add_argument("--right-study-id")
    compare.add_argument("--right-run-id")
    compare.add_argument("--right-observation-kind")
    compare.add_argument("--right-source-algorithm")
    compare.add_argument("--json", action="store_true")

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
    evidence.add_argument("--json", action="store_true")

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
    finite_size.add_argument("--json", action="store_true")

    track1_raw = subparsers.add_parser(
        "summarize-track1-raw",
        help="Summarize completed raw Track 1 result chunks without touching databases",
    )
    track1_raw.add_argument("--run-root", required=True, type=Path)
    track1_raw.add_argument("--output", required=True, type=Path)
    track1_raw.add_argument("--candidate-manifest", type=Path)
    track1_raw.add_argument("--json", action="store_true")

    return parser


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "refresh-compendium":
        payload = refresh_compendium_warehouse(
            warehouse_path=args.warehouse.resolve(),
            compendium_path=args.compendium.resolve(),
            label=args.label,
            run_id=args.run_id,
            topology=bool(args.topology),
            source_packet_kind=str(args.source_packet_kind),
            min_group_size=int(args.min_group_size),
            max_homology_dim=int(args.max_homology_dim),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "promote-results":
        payload = promote_results_packet(
            compendium_path=args.compendium.resolve(),
            run_dir=args.run_dir.resolve(),
            run_id=str(args.run_id),
            source_mode=str(args.source_mode),
            source_algorithm=str(args.source_algorithm),
            batch_size=int(args.batch_size),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "apply-catalog-qc":
        payload = apply_catalog_qc_packet(
            compendium_path=args.compendium.resolve(),
            audit_db=args.audit_db.resolve() if args.audit_db is not None else None,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "run-topology":
        payload = run_topology_for_study(
            warehouse_path=args.warehouse.resolve(),
            study_id=str(args.study_id),
            source_packet_kind=str(args.source_packet_kind),
            min_group_size=int(args.min_group_size),
            max_homology_dim=int(args.max_homology_dim),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "export-biological":
        payload = export_biological_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=str(args.study_id),
            context_study_id=args.context_study_id,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "export-creature-discovery":
        payload = export_creature_discovery_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=args.study_id,
            lens=args.lens,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "import-dryad-fish":
        payload = import_dryad_fish_dataset(
            warehouse_path=args.warehouse.resolve(),
            dataset_root=args.dataset_root.resolve(),
            label=args.label,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "derive-lenia-features":
        payload = derive_lenia_features_packet(
            warehouse_path=args.warehouse.resolve(),
            study_id=args.study_id,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "derive-common-morphology":
        payload = derive_common_morphology_packet(
            warehouse_path=args.warehouse.resolve(),
            dryad_fish_root=(
                args.dryad_fish_root.resolve()
                if args.dryad_fish_root is not None
                else None
            ),
            study_id=args.study_id,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "export-feature-matrix":
        payload = export_feature_matrix_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            source_id=args.source_id,
            study_id=args.study_id,
            run_id=args.run_id,
            observation_kind=args.observation_kind,
            source_algorithm=args.source_algorithm,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "run-feature-tda":
        payload = run_feature_tda_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            source_id=args.source_id,
            study_id=args.study_id,
            run_id=args.run_id,
            observation_kind=args.observation_kind,
            source_algorithm=args.source_algorithm,
            max_homology_dim=int(args.max_homology_dim),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "run-feature-tda-profile":
        payload = run_feature_tda_profile_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            profile=str(args.profile),
            value_column=str(args.value_column),
            source_id=args.source_id,
            study_id=args.study_id,
            run_id=args.run_id,
            observation_kind=args.observation_kind,
            source_algorithm=args.source_algorithm,
            max_homology_dim=int(args.max_homology_dim),
            stratify_by=str(args.stratify_by),
            seed=int(args.seed),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "compare-feature-cohorts":
        payload = compare_feature_cohorts_packet(
            warehouse_path=args.warehouse.resolve(),
            feature_space_id=str(args.feature_space_id),
            value_column=str(args.value_column),
            left_label=str(args.left_label),
            right_label=str(args.right_label),
            left_source_id=args.left_source_id,
            left_study_id=args.left_study_id,
            left_run_id=args.left_run_id,
            left_observation_kind=args.left_observation_kind,
            left_source_algorithm=args.left_source_algorithm,
            right_source_id=args.right_source_id,
            right_study_id=args.right_study_id,
            right_run_id=args.right_run_id,
            right_observation_kind=args.right_observation_kind,
            right_source_algorithm=args.right_source_algorithm,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "build-atlas-evidence":
        payload = build_atlas_evidence_packet(
            atlas_findings_path=args.atlas_findings.resolve(),
            common_tda_path=args.common_tda.resolve(),
            h1_regions_path=args.h1_regions.resolve() if args.h1_regions else None,
            validation256_path=args.validation256.resolve() if args.validation256 else None,
            terminal_tda_path=args.terminal_tda.resolve() if args.terminal_tda else None,
            output_path=args.output.resolve() if args.output else None,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "build-finite-size-validation":
        payload = build_finite_size_packet(
            run_specs=list(args.run),
            output_path=args.output.resolve() if args.output else None,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    if args.command == "summarize-track1-raw":
        payload = summarize_track1_raw_packet(
            run_root=args.run_root.resolve(),
            output_path=args.output.resolve(),
            candidate_manifest_path=(
                args.candidate_manifest.resolve()
                if args.candidate_manifest is not None
                else None
            ),
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
