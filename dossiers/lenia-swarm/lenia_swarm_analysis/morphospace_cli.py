from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.morphospace.derive_anatomy import derive_anatomy
from lenia_swarm_analysis.morphospace.derive_axes import derive_axes
from lenia_swarm_analysis.morphospace.derive_status import derive_status
from lenia_swarm_analysis.morphospace.export_biological import export_biological_study
from lenia_swarm_analysis.morphospace.export_creature_discovery import (
    export_creature_discovery,
)
from lenia_swarm_analysis.morphospace.ingest_compendium import ingest_compendium
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

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
