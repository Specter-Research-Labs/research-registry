from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{path}: expected a JSON array of objects")
    return value


def _top_row(candidate: dict[str, Any]) -> dict[str, Any]:
    source_run_dir = Path(str(candidate["sourceRunDir"])).expanduser().resolve()
    source_index = int(candidate["sourceIndex"])
    rows = _read_json_array(source_run_dir / "top.json")
    if source_index < 0 or source_index >= len(rows):
        raise SystemExit(f"{source_run_dir}/top.json: source index {source_index} is out of range")
    return rows[source_index]


def _hashes(row: dict[str, Any]) -> tuple[str, str]:
    descriptor_bundle = row.get("descriptor_bundle")
    if not isinstance(descriptor_bundle, dict):
        raise SystemExit("top row is missing descriptor_bundle")
    terminal = descriptor_bundle.get("terminal")
    genotype = descriptor_bundle.get("genotype")
    if not isinstance(terminal, dict) or not isinstance(genotype, dict):
        raise SystemExit("descriptor_bundle is missing terminal/genotype sections")
    fingerprint_hash = terminal.get("fingerprintHash12")
    genotype_hash = genotype.get("hash12")
    if not isinstance(fingerprint_hash, str) or not isinstance(genotype_hash, str):
        raise SystemExit("descriptor hashes are missing from descriptor_bundle")
    return fingerprint_hash, genotype_hash


def _export_rows(export_packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = export_packet.get("candidates")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit("export packet is missing candidates[]")
    return {str(row["candidateId"]): row for row in rows}


def _top_hotspots(empirical_packet: dict[str, Any] | None) -> set[str]:
    if empirical_packet is None:
        return set()
    rows = empirical_packet.get("topHotspots")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit("empirical packet is missing topHotspots[]")
    return {
        str(row["id"])
        for row in rows
        if isinstance(row.get("kind"), str) and row["kind"] == "transport_group"
    }


def _compendium_matches(
    connection: sqlite3.Connection,
    *,
    fingerprint_hash: str,
    genotype_hash: str,
) -> list[dict[str, str | None]]:
    rows = connection.execute(
        """
        select id, run_id, campaign_id, result_id, creature_id
        from specimens
        where json_extract(terminal_descriptor_json, '$.fingerprintHash12') = ?
          and json_extract(genotype_descriptor_json, '$.hash12') = ?
        order by run_id, id
        """,
        (fingerprint_hash, genotype_hash),
    ).fetchall()
    return [
        {
            "specimenId": str(specimen_id),
            "runId": str(run_id),
            "campaignId": str(campaign_id) if campaign_id is not None else None,
            "resultId": str(result_id) if result_id is not None else None,
            "creatureId": str(creature_id) if creature_id is not None else None,
        }
        for specimen_id, run_id, campaign_id, result_id, creature_id in rows
    ]


def build_hotspot_neighborhood_packet(
    *,
    report_path: Path,
    export_packet_path: Path,
    compendium_db_path: Path,
    empirical_packet_path: Path | None = None,
) -> dict[str, Any]:
    report = _read_json(report_path)
    export_packet = _read_json(export_packet_path)
    empirical_packet = _read_json(empirical_packet_path) if empirical_packet_path else None
    selected_candidates = report.get("selectedCandidates")
    groups = report.get("groups")
    if not isinstance(selected_candidates, list) or any(
        not isinstance(row, dict) for row in selected_candidates
    ):
        raise SystemExit("report is missing selectedCandidates[]")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("report is missing groups[]")

    export_by_candidate = _export_rows(export_packet)
    top_hotspots = _top_hotspots(empirical_packet)
    connection = sqlite3.connect(compendium_db_path)

    candidates_by_group: dict[str, list[dict[str, Any]]] = {}
    for candidate in selected_candidates:
        candidates_by_group.setdefault(str(candidate["controlGroup"]), []).append(candidate)

    group_rows: list[dict[str, Any]] = []
    total_matches = 0
    matched_candidates = 0
    for group in groups:
        control_group = str(group["controlGroup"])
        group_candidates = candidates_by_group.get(control_group, [])
        candidate_rows: list[dict[str, Any]] = []
        group_specimen_ids: set[str] = set()
        group_run_ids: set[str] = set()
        for candidate in group_candidates:
            source_row = _top_row(candidate)
            fingerprint_hash, genotype_hash = _hashes(source_row)
            matches = _compendium_matches(
                connection,
                fingerprint_hash=fingerprint_hash,
                genotype_hash=genotype_hash,
            )
            if matches:
                matched_candidates += 1
                total_matches += len(matches)
                group_specimen_ids.update(str(row["specimenId"]) for row in matches)
                group_run_ids.update(str(row["runId"]) for row in matches)
            export_row = export_by_candidate.get(str(candidate["candidateId"]))
            export_dir = (
                Path(str(export_row["exportDir"])).expanduser().resolve()
                if export_row is not None
                else None
            )
            candidate_rows.append(
                {
                    "candidateId": str(candidate["candidateId"]),
                    "scale": str(candidate["scale"]),
                    "sourceRunDir": str(candidate["sourceRunDir"]),
                    "sourceIndex": int(candidate["sourceIndex"]),
                    "sourceSeed": int(candidate["sourceSeed"]),
                    "sourceInitSeed": int(candidate["sourceInitSeed"]),
                    "distanceToSeedEmbedding": float(candidate["distanceToSeedEmbedding"]),
                    "featureEmbedding": [float(value) for value in candidate["featureEmbedding"]],
                    "metrics": {
                        str(key): float(value)
                        for key, value in dict(candidate["metrics"]).items()
                    },
                    "fingerprintHash12": fingerprint_hash,
                    "genotypeHash12": genotype_hash,
                    "exportDir": str(export_dir) if export_dir is not None else None,
                    "baseConfigPath": (
                        str((export_dir / "base.json").resolve())
                        if export_dir is not None
                        else None
                    ),
                    "searchConfigPath": (
                        str((export_dir / "search.json").resolve())
                        if export_dir is not None
                        else None
                    ),
                    "compendiumMatches": matches,
                }
            )
        group_rows.append(
            {
                "controlGroup": control_group,
                "specimen": str(group["specimen"]),
                "recommendedReplayScale": str(group["recommendedReplayScale"]),
                "followupScales": [str(value) for value in group["followupScales"]],
                "selectedCandidateCount": len(candidate_rows),
                "matchedCandidateCount": sum(
                    1 for row in candidate_rows if len(row["compendiumMatches"]) > 0
                ),
                "strictSpecimenCount": len(group_specimen_ids),
                "strictRunIds": sorted(group_run_ids),
                "isTopTransportHotspot": control_group in top_hotspots,
                "selectedCandidates": candidate_rows,
            }
        )

    connection.close()
    return {
        "version": 1,
        "packetKind": "hotspot_neighborhood_packet_v1",
        "sourceReport": str(report_path),
        "sourceExportPacket": str(export_packet_path),
        "sourceCompendium": str(compendium_db_path),
        "sourceEmpiricalPacket": str(empirical_packet_path) if empirical_packet_path else None,
        "groupCount": len(group_rows),
        "selectedCandidateCount": len(selected_candidates),
        "matchedCandidateCount": matched_candidates,
        "strictSpecimenMatchCount": total_matches,
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind hotspot report candidates to replay bundle paths and strict compendium specimens."
        )
    )
    parser.add_argument("--report", required=True, help="Path to imgep-hotspot-report.json")
    parser.add_argument(
        "--export-packet",
        required=True,
        help="Path to imgep-hotspot-export-packet.json",
    )
    parser.add_argument("--db", required=True, help="Path to compendium.sqlite")
    parser.add_argument(
        "--empirical-packet",
        help="Optional empirical_fibration_packet_v1 to flag top transport hotspots",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet = build_hotspot_neighborhood_packet(
        report_path=Path(args.report).expanduser().resolve(),
        export_packet_path=Path(args.export_packet).expanduser().resolve(),
        compendium_db_path=Path(args.db).expanduser().resolve(),
        empirical_packet_path=(
            Path(args.empirical_packet).expanduser().resolve()
            if args.empirical_packet
            else None
        ),
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(args.export_packet).expanduser().resolve().parent
        / "hotspot-neighborhood-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Hotspot neighborhood packet:"
        f" groups={packet['groupCount']}"
        f" selected={packet['selectedCandidateCount']}"
        f" strict_matches={packet['strictSpecimenMatchCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
