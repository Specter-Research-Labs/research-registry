from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class FiberGenerator:
    generator_id: str
    persistence: float | None
    representative_specimen_ids: tuple[str, ...]
    member_specimen_ids: tuple[str, ...]
    cycle_edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FiberGeneratorPacket:
    version: int
    packet_kind: str
    source_manifest: str | None
    representation: str | None
    generators: tuple[FiberGenerator, ...]


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(f"fiber packet field {field_name} must be a list of strings")
    return tuple(value)


def _edge_list(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SystemExit("fiber packet field cycleEdges must be a list")
    edges: list[tuple[str, str]] = []
    for entry in value:
        if isinstance(entry, dict):
            source_specimen_id = entry.get("fromSpecimenId")
            target_specimen_id = entry.get("toSpecimenId")
            if isinstance(source_specimen_id, str) and isinstance(target_specimen_id, str):
                edges.append((source_specimen_id, target_specimen_id))
                continue
        if isinstance(entry, list) and len(entry) == 2:
            source_specimen_id, target_specimen_id = entry
            if isinstance(source_specimen_id, str) and isinstance(target_specimen_id, str):
                edges.append((source_specimen_id, target_specimen_id))
                continue
        raise SystemExit(
            "fiber packet cycleEdges entries must be either "
            "{fromSpecimenId,toSpecimenId} or [sourceSpecimenId, targetSpecimenId]"
        )
    return tuple(edges)


def load_generator_packet(path: Path) -> FiberGeneratorPacket:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    version = raw.get("version")
    if version != 1:
        raise SystemExit(f"{path}: unsupported fiber packet version {version!r}")
    packet_kind = raw.get("packetKind")
    if not isinstance(packet_kind, str) or not packet_kind:
        raise SystemExit(f"{path}: missing packetKind")
    generators_raw = raw.get("generators")
    if not isinstance(generators_raw, list) or not generators_raw:
        raise SystemExit(f"{path}: missing generators")
    generators: list[FiberGenerator] = []
    for index, entry in enumerate(generators_raw):
        if not isinstance(entry, dict):
            raise SystemExit(f"{path}: generator[{index}] must be an object")
        entry_dict = cast(dict[str, Any], entry)
        generator_id = entry_dict.get("generatorId")
        if not isinstance(generator_id, str) or not generator_id:
            raise SystemExit(f"{path}: generator[{index}] is missing generatorId")
        persistence = entry_dict.get("persistence")
        if persistence is not None and not isinstance(persistence, (int, float)):
            raise SystemExit(f"{path}: generator[{index}] persistence must be numeric")
        representatives = _string_list(
            entry_dict.get("representativeSpecimenIds") or entry_dict.get("anchorSpecimenIds"),
            f"generators[{index}].representativeSpecimenIds",
        )
        members = _string_list(
            entry_dict.get("memberSpecimenIds"),
            f"generators[{index}].memberSpecimenIds",
        )
        generators.append(
            FiberGenerator(
                generator_id=generator_id,
                persistence=float(persistence) if persistence is not None else None,
                representative_specimen_ids=representatives,
                member_specimen_ids=members,
                cycle_edges=_edge_list(entry_dict.get("cycleEdges")),
            )
        )
    return FiberGeneratorPacket(
        version=1,
        packet_kind=packet_kind,
        source_manifest=(
            raw.get("sourceManifest")
            if isinstance(raw.get("sourceManifest"), str)
            else None
        ),
        representation=(
            raw.get("representation")
            if isinstance(raw.get("representation"), str)
            else None
        ),
        generators=tuple(generators),
    )


def generator_by_id(packet: FiberGeneratorPacket, generator_id: str) -> FiberGenerator:
    for generator in packet.generators:
        if generator.generator_id == generator_id:
            return generator
    raise SystemExit(f"fiber packet is missing generatorId={generator_id}")


def generator_edge_pair(generator: FiberGenerator, edge_index: int = 0) -> tuple[str, str]:
    if generator.cycle_edges:
        if edge_index < 0 or edge_index >= len(generator.cycle_edges):
            raise SystemExit(
                f"generator {generator.generator_id} is missing cycle edge index {edge_index}"
            )
        return generator.cycle_edges[edge_index]
    if len(generator.representative_specimen_ids) >= 2:
        return (
            generator.representative_specimen_ids[0],
            generator.representative_specimen_ids[1],
        )
    raise SystemExit(
        f"generator {generator.generator_id} does not expose a usable control pair"
    )
