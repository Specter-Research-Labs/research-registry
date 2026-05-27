from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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
from lenia_swarm_analysis.morphospace.ingest_compendium import ingest_compendium
from lenia_swarm_analysis.morphospace.ingest_dryad_fish import (
    ingest_dryad_fish_body_shape,
)
from lenia_swarm_analysis.morphospace.run_topology import run_topology
from lenia_swarm_analysis.morphospace.warehouse import connect_database


def refresh_compendium_warehouse(
    *,
    warehouse_path: Path,
    compendium_path: Path,
    label: str | None = None,
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
        )
        axes_updated = derive_axes(connection, study_id=study_id)
        status_updated = derive_status(connection, study_id=study_id)
        anatomy_updated = derive_anatomy(connection, study_id=study_id)
        comparison_features = derive_lenia_terminal_features(connection, study_id=study_id)
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
            "axesUpdated": axes_updated,
            "statusUpdated": status_updated,
            "anatomyUpdated": anatomy_updated,
            "comparisonFeatureSpaceId": comparison_features["featureSpaceId"],
            "comparisonObservationsUpdated": comparison_features["observationCount"],
            "comparisonFeatureValuesUpdated": comparison_features["featureValueCount"],
            "topologyStudyId": topology_study_id,
        }
    finally:
        connection.close()


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
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return export_feature_matrix(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            observation_kind=observation_kind,
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
    max_homology_dim: int = 1,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
    try:
        return run_feature_tda(
            connection,
            feature_space_id=feature_space_id,
            value_column=value_column,
            source_id=source_id,
            study_id=study_id,
            run_id=run_id,
            observation_kind=observation_kind,
            max_homology_dim=max_homology_dim,
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
    right_source_id: str | None = None,
    right_study_id: str | None = None,
    right_run_id: str | None = None,
    right_observation_kind: str | None = None,
) -> dict[str, Any]:
    connection = connect_database(warehouse_path)
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
            right_source_id=right_source_id,
            right_study_id=right_study_id,
            right_run_id=right_run_id,
            right_observation_kind=right_observation_kind,
        )
    finally:
        connection.close()


def apply_catalog_qc_packet(
    *,
    compendium_path: Path,
    audit_db: Path | None = None,
) -> dict[str, Any]:
    return apply_shape_behavior_qc(
        compendium_path=compendium_path,
        audit_db=audit_db,
    )


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
    refresh.add_argument("--topology", action="store_true")
    refresh.add_argument("--source-packet-kind", default="focal")
    refresh.add_argument("--min-group-size", type=int, default=2)
    refresh.add_argument("--max-homology-dim", type=int, default=1)
    refresh.add_argument("--json", action="store_true")

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
    feature_tda.add_argument("--max-homology-dim", type=int, default=1)
    feature_tda.add_argument("--json", action="store_true")

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
    compare.add_argument("--right-source-id")
    compare.add_argument("--right-study-id")
    compare.add_argument("--right-run-id")
    compare.add_argument("--right-observation-kind")
    compare.add_argument("--json", action="store_true")

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
            topology=bool(args.topology),
            source_packet_kind=str(args.source_packet_kind),
            min_group_size=int(args.min_group_size),
            max_homology_dim=int(args.max_homology_dim),
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
            max_homology_dim=int(args.max_homology_dim),
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
            right_source_id=args.right_source_id,
            right_study_id=args.right_study_id,
            right_run_id=args.right_run_id,
            right_observation_kind=args.right_observation_kind,
        )
        _print_payload(payload, as_json=bool(args.json))
        return 0

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
