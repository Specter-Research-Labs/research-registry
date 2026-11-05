"""Rewrite lenia-swarm JSON artifacts into the current storage format.

`lenia-swarm-analysis compact ROOT` converts retired `f32le` field patches to
`f32le-shuffle-zlib`, drops specimen-manifest snapshots that duplicate the creature,
and rewrites the retired record shapes LeniaCLI no longer decodes. The formats and the
rules are documented in docs/contracts/LocalCLI.md ("Storage compaction").
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.trace_codec import FIELD_ENCODING, decode_field, encode_field

RECEIPT_DIR = "compaction-receipts"
RETIRED_FIELD_ENCODING = "f32le"
DUPLICATED_SNAPSHOT_KEYS = ("genotype", "initialCondition", "metrics", "descriptorBundle")
SNAPSHOT_KEYS = frozenset((*DUPLICATED_SNAPSHOT_KEYS, "morphometrics"))
MANIFEST_KEYS = ("specimen_manifest", "specimenManifest")
SAVED_CREATURE_KEYS = (
    "id",
    "name",
    "timestamp",
    "ownerId",
    "genotype",
    "initialCondition",
    "metrics",
)
LIBRARY_ENTRY_KEYS = frozenset(
    {
        "creature",
        "campaign_id",
        "run_id",
        "recorded_at",
        "config_hash",
        "source_mode",
        "source_algorithm",
        "research_metadata",
        "runtime_family",
        "runtime_capabilities",
        "specimen_manifest",
    }
)
EXPORT_METADATA_KEYS = frozenset(
    {
        "creature",
        "runId",
        "campaignId",
        "bundleKind",
        "exportedAt",
        "reason",
        "score",
        "filtersPassed",
        "runtimeFamily",
        "runtimeCapabilities",
        "specimenManifest",
    }
)
EXPORT_RECORD_KEYS = frozenset(
    {
        "creatureId",
        "name",
        "ownerId",
        "runId",
        "campaignId",
        "bundleKind",
        "exportDir",
        "baseConfigPath",
        "searchConfigPath",
        "payloadPath",
        "exportedAt",
        "reason",
        "score",
        "filtersPassed",
        "runtimeFamily",
        "runtimeCapabilities",
        "specimenManifest",
    }
)
CAPABILITIES = frozenset(
    {"archive", "warehouse_ingest", "replay", "topology", "intervention", "media"}
)
RETIRED_CAPABILITIES = frozenset({"native-intervention", "native-replay", "phenotype-queryable"})
RETIRED_RUNTIME_FAMILIES = {"qd-2024": "qd24_paper"}
BUNDLE_RUNTIME_FAMILY = {
    "strict_replay_bundle_v1": "flow_lenia",
    "flowlenia_ecology2025_arena_replay_bundle_v1": "flow_lenia",
    "qd24_paper_replay_bundle_v1": "qd24_paper",
    "sensorimotor24_paper_replay_bundle_v1": "sensorimotor24_paper",
}
SOURCE_MODE_RUNTIME_FAMILY = {"qd-2024": "qd24_paper", "sensorimotor-2024": "sensorimotor24_paper"}

_PENDING_ENCODING = re.compile(rb'"encoding"\s*:\s*"(?!f32le-shuffle-zlib")')
_NULL_MANIFEST = re.compile(rb'"specimen_?[mM]anifest"\s*:\s*null')
_ANY_MANIFEST = re.compile(rb'"specimen_?[mM]anifest"')
_SNAPSHOTS = re.compile(rb'"snapshots"\s*:')
_CLEAN_SNAPSHOTS = re.compile(
    rb'"snapshots"\s*:\s*\{\s*(?:"morphometrics"\s*:\s*(?:null|\{[^{}]*\})\s*)?\}'
)
_RETIRED_RUNTIME_FAMILY = re.compile(rb'"runtime_?[fF]amily"\s*:\s*"qd-2024"')


class CompactionError(ValueError):
    """A record the compactor cannot rewrite without information the file does not hold."""


@dataclass
class Stats:
    patches_converted: int = 0
    raw_sha256: list[str] = field(default_factory=list)
    snapshots_dropped: int = 0
    manifests_written: int = 0
    shapes_rewritten: Counter[str] = field(default_factory=Counter)

    def mutations(self) -> int:
        return (
            self.patches_converted
            + self.snapshots_dropped
            + self.manifests_written
            + sum(self.shapes_rewritten.values())
        )


@dataclass(frozen=True)
class Style:
    indent: int | None
    key_separator: str
    escape_slash: bool
    ensure_ascii: bool


def needs_parse(raw: bytes) -> bool:
    """Byte-level superset test: False guarantees the document needs no rewrite."""
    if b'"phenotype"' in raw or _PENDING_ENCODING.search(raw) or _NULL_MANIFEST.search(raw):
        return True
    if _RETIRED_RUNTIME_FAMILY.search(raw):
        return True
    if len(_SNAPSHOTS.findall(raw)) != len(_CLEAN_SNAPSHOTS.findall(raw)):
        return True
    if (b'"creature"' in raw or b'"creatureId"' in raw) and not _ANY_MANIFEST.search(raw):
        return True
    if b'"creature"' in raw and b'"run_id"' in raw:
        return b'"runtime_family"' not in raw or b'"runtime_capabilities"' not in raw
    if b'"creature"' in raw and b'"exportedAt"' in raw and b'"bundleKind"' not in raw:
        return True
    if b'"creature"' in raw or b'"creatureId"' in raw:
        return b'"runtimeFamily"' not in raw or b'"runtimeCapabilities"' not in raw
    return False


def _patch_count(patch: dict[str, Any], label: str) -> int:
    count = 1
    for key in ("width", "height", "channels"):
        value = patch.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CompactionError(f"{label}: encoded payload without a positive {key}")
        count *= value
    return count


def patch_raw(patch: dict[str, Any], label: str) -> bytes:
    """Little-endian float32 bytes of a field patch in either the retired or the current encoding."""
    count = _patch_count(patch, label)
    encoding = patch["encoding"]
    if encoding == FIELD_ENCODING:
        return decode_field(patch["data"], count=count, label=label).tobytes()
    if encoding != RETIRED_FIELD_ENCODING:
        raise CompactionError(f"{label}: unknown field encoding {encoding!r}")
    raw = base64.b64decode(patch["data"], validate=True)
    if len(raw) != 4 * count:
        raise CompactionError(
            f"{label}: f32le payload holds {len(raw)} bytes, expected {4 * count}"
        )
    return raw


def convert_patches(node: Any, stats: Stats, label: str, raw_sha256: list[str]) -> None:
    """Convert every f32le patch in place; append each patch's raw sha256 in walk order."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            convert_patches(item, stats, f"{label}[{index}]", raw_sha256)
        return
    if not isinstance(node, dict):
        return
    if "encoding" in node and "data" in node:
        raw = patch_raw(node, label)
        digest = hashlib.sha256(raw).hexdigest()
        if node["encoding"] == RETIRED_FIELD_ENCODING:
            encoded = encode_field(np.frombuffer(raw, dtype="<f4"))
            roundtrip = decode_field(encoded, count=len(raw) // 4, label=label).tobytes()
            if hashlib.sha256(roundtrip).hexdigest() != digest:
                raise CompactionError(
                    f"{label}: re-encoded patch does not reproduce the raw float32 bytes"
                )
            node["encoding"] = FIELD_ENCODING
            node["data"] = encoded
            stats.patches_converted += 1
            stats.raw_sha256.append(digest)
        raw_sha256.append(digest)
        return
    for key, value in node.items():
        convert_patches(value, stats, f"{label}.{key}", raw_sha256)


def _canonical(value: Any, label: str) -> Any:
    """A value with every field patch replaced by its shape and raw sha256, so encodings compare equal."""
    if isinstance(value, list):
        return [_canonical(item, label) for item in value]
    if not isinstance(value, dict):
        return value
    if "encoding" in value and "data" in value:
        rest = {key: item for key, item in value.items() if key not in ("encoding", "data")}
        return {**rest, "raw_sha256": hashlib.sha256(patch_raw(value, label)).hexdigest()}
    return {key: _canonical(item, f"{label}.{key}") for key, item in value.items()}


def _export_bundle_creature(record: dict[str, Any], label: str) -> Any:
    """The creature of the bundle an export record points at; export records carry none themselves."""
    meta_path = Path(record["exportDir"]) / "meta.json"
    if not meta_path.is_file():
        raise CompactionError(
            f"{label}: snapshots can only be checked against {meta_path}, which does not exist"
        )
    return json.loads(meta_path.read_bytes())["creature"]


def drop_duplicated_snapshots(node: Any, stats: Stats, label: str) -> None:
    """Remove manifest snapshots that repeat the specimen's creature; fail on anything else.

    The creature is the record's own `creature`, or for an export record (which has none) the
    `creature` of `<exportDir>/meta.json`.
    """
    if isinstance(node, list):
        for index, item in enumerate(node):
            drop_duplicated_snapshots(item, stats, f"{label}[{index}]")
        return
    if not isinstance(node, dict):
        return
    for manifest_key in MANIFEST_KEYS:
        manifest = node.get(manifest_key)
        if not isinstance(manifest, dict) or "snapshots" not in manifest:
            continue
        snapshots = manifest["snapshots"]
        where = f"{label}.{manifest_key}.snapshots"
        if not isinstance(snapshots, dict):
            raise CompactionError(f"{where}: expected an object")
        unknown = sorted(set(snapshots) - SNAPSHOT_KEYS)
        if unknown:
            raise CompactionError(f"{where}: unknown snapshot keys {unknown}")
        held = [key for key in DUPLICATED_SNAPSHOT_KEYS if snapshots.get(key) is not None]
        if held:
            if "creature" in node:
                creature = node["creature"]
            elif "exportDir" in node:
                creature = _export_bundle_creature(node, where)
            else:
                raise CompactionError(f"{where}: no creature beside the manifest to compare with")
            for key in held:
                if not isinstance(creature, dict) or key not in creature:
                    raise CompactionError(f"{where}.{key}: the creature holds no {key}")
                if _canonical(creature[key], where) != _canonical(snapshots[key], where):
                    raise CompactionError(
                        f"{where}.{key}: differs from the creature's {key}; it is not a duplicate"
                    )
        for key in DUPLICATED_SNAPSHOT_KEYS:
            if key in snapshots:
                del snapshots[key]
                stats.snapshots_dropped += 1
    for key, value in node.items():
        drop_duplicated_snapshots(value, stats, f"{label}.{key}")


def _keys_sorted(node: dict[str, Any]) -> bool:
    keys = list(node)
    return keys == sorted(keys)


def _set_key(node: dict[str, Any], key: str, value: Any) -> None:
    """Set a key, keeping the object's key order sorted when LeniaCLI wrote it sorted."""
    was_sorted = _keys_sorted(node)
    node[key] = value
    if was_sorted and key not in list(node)[:-1]:
        items = sorted(node.items())
        node.clear()
        node.update(items)


def _rename_key(node: dict[str, Any], old: str, new: str) -> None:
    was_sorted = _keys_sorted(node)
    items = [(new if key == old else key, value) for key, value in node.items()]
    node.clear()
    node.update(sorted(items) if was_sorted else items)


def swift_float(value: Any, label: str) -> str:
    """Swift JSONEncoder's text for a Float: shortest round-trip digits, positional between 1e-4 and 2^24."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompactionError(f"{label}: expected a number, got {value!r}")
    single = np.float32(value)
    if not np.isfinite(single):
        raise CompactionError(f"{label}: non-finite Float {value!r}")
    if single == 0:
        return "-0" if np.signbit(single) else "0"
    scientific = np.format_float_scientific(single, unique=True, trim="-", exp_digits=2)
    exponent = int(scientific.split("e")[1])
    if exponent >= -4 and abs(float(single)) <= 2**24:
        return np.format_float_positional(single, unique=True, trim="-")
    return scientific


def _int(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompactionError(f"{label}: expected an integer, got {value!r}")
    return str(value)


def _center(center: Any, label: str) -> str:
    if not isinstance(center, list):
        raise CompactionError(f"{label}: expected a center array")
    return "[" + ",".join(_int(value, label) for value in center) + "]"


def _normalized_state_patch(patch: dict[str, Any], label: str) -> str:
    hash12 = hashlib.sha256(patch_raw(patch, label)).hexdigest()[:12]
    return (
        f'{{"center":{_center(patch["center"], label)},"channels":{_int(patch["channels"], label)},'
        f'"hash12":"{hash12}","height":{_int(patch["height"], label)},"width":{_int(patch["width"], label)}}}'
    )


def initial_condition_family(init: dict[str, Any], label: str) -> str:
    """Python port of LeniaCore `morphospaceInitialConditionFamily` (MorphospaceDescriptors.swift)."""
    patches = sorted((patch["center"], patch["size"]) for patch in init["patches"])
    for center, size in patches:
        _center(center, label)
        _int(size, label)
    state = init.get("state_patch")
    param = init.get("p_state_patch")
    a_uniform = init["a_uniform"]
    p_uniform = init.get("p_uniform")
    fields = [
        f'"aUniformHigh":{swift_float(a_uniform["high"], label)}',
        f'"aUniformLow":{swift_float(a_uniform["low"], label)}',
    ]
    if p_uniform is not None:
        fields.append(f'"pUniformHigh":{swift_float(p_uniform["high"], label)}')
        fields.append(f'"pUniformLow":{swift_float(p_uniform["low"], label)}')
    if param is not None:
        fields.append(f'"paramStatePatch":{_normalized_state_patch(param, label)}')
    patch_items = ",".join(
        f'{{"center":{_center(center, label)},"size":{size}}}' for center, size in patches
    )
    fields.append(f'"patches":[{patch_items}]')
    if state is not None:
        fields.append(f'"statePatch":{_normalized_state_patch(state, label)}')
    payload = "{" + ",".join(fields) + "}"
    if state is not None:
        patch_label = f"state_patch{state['width']}x{state['height']}x{state['channels']}"
    elif param is not None:
        patch_label = f"param_patch{param['width']}x{param['height']}x{param['channels']}"
    else:
        patch_label = "single_patch" if len(patches) == 1 else f"patches{len(patches)}"
    return f"initfam:v2:{patch_label}:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def _metadata_value(research_metadata: Any, key: str) -> Any:
    if not isinstance(research_metadata, dict):
        return None
    if key in research_metadata:
        return research_metadata[key]
    nested = research_metadata.get("source_research_metadata")
    return nested.get(key) if isinstance(nested, dict) else None


def _canonical_export_bundle_kind(research_metadata: Any) -> str | None:
    if not isinstance(research_metadata, dict):
        return None
    for source in (research_metadata, research_metadata.get("source_research_metadata")):
        if isinstance(source, dict) and isinstance(source.get("canonical_export_kind"), str):
            kind = source["canonical_export_kind"]
            return kind if kind in BUNDLE_RUNTIME_FAMILY else None
    return None


def _normalized_source_mode(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower()
    return "replay" if normalized == "replay-specimens" else normalized


def runtime_family(source_mode: str | None, bundle_kind: str | None, research_metadata: Any) -> str:
    """Python port of LeniaCore `specimenRuntimeFamily` without a backend hint."""
    if bundle_kind is not None:
        return BUNDLE_RUNTIME_FAMILY[bundle_kind]
    canonical = _canonical_export_bundle_kind(research_metadata)
    if canonical is not None:
        return BUNDLE_RUNTIME_FAMILY[canonical]
    mode = _normalized_source_mode(source_mode)
    if mode in SOURCE_MODE_RUNTIME_FAMILY:
        return SOURCE_MODE_RUNTIME_FAMILY[mode]
    if mode == "replay" and isinstance(research_metadata, dict):
        inner = research_metadata.get("source_mode")
        if isinstance(inner, str):
            return runtime_family(inner, None, None)
    return "flow_lenia"


def runtime_capabilities(
    descriptor_bundle: Any, bundle_kind: str | None, research_metadata: Any
) -> list[str]:
    """Python port of LeniaCore `specimenRuntimeCapabilities`."""
    capabilities = {"archive", "warehouse_ingest"}
    if (
        bundle_kind is not None
        or _metadata_value(research_metadata, "canonical_export_available") is True
    ):
        capabilities |= {"replay", "intervention", "media"}
    if (
        descriptor_bundle is not None
        or _metadata_value(research_metadata, "morphospace_ready") is True
    ):
        capabilities.add("topology")
    return sorted(capabilities)


def _manifest(
    *,
    creature_id: str,
    run_id: Any,
    campaign_id: Any,
    source_kind: str,
    source_mode: str | None,
    source_algorithm: Any,
    family: str,
    capabilities: list[str],
    config_hash: Any,
    recorded_at: Any,
    initial_condition_family_value: str | None,
    replay: dict[str, Any],
    research_metadata: Any,
) -> dict[str, Any]:
    """A SpecimenManifest as LeniaCLI's sorted-keys JSONEncoder writes it (nil optionals omitted)."""
    values = {
        "version": 1,
        "specimenID": creature_id,
        "creatureID": creature_id,
        "runID": run_id,
        "campaignID": campaign_id,
        "sourceKind": source_kind,
        "sourceMode": source_mode,
        "sourceAlgorithm": source_algorithm,
        "runtimeFamily": family,
        "runtimeCapabilities": capabilities,
        "configHash": config_hash,
        "recordedAt": recorded_at,
        "initialConditionFamily": initial_condition_family_value,
        "replay": {key: value for key, value in sorted(replay.items()) if value is not None},
        "snapshots": {},
        "researchMetadata": research_metadata,
    }
    return {key: value for key, value in sorted(values.items()) if value is not None}


def _require(record: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise CompactionError(
            f"{label}: missing required {missing}; the file does not say what to write"
        )


def _creature(record: dict[str, Any], stats: Stats, label: str) -> dict[str, Any]:
    """The record's SavedCreature, with the retired key `phenotype` renamed to `initialCondition`."""
    creature = record["creature"]
    if not isinstance(creature, dict):
        raise CompactionError(f"{label}.creature: expected an object")
    if "phenotype" in creature:
        if "initialCondition" in creature:
            raise CompactionError(f"{label}.creature: holds both phenotype and initialCondition")
        _rename_key(creature, "phenotype", "initialCondition")
        stats.shapes_rewritten["creature.phenotype->initialCondition"] += 1
    _require(creature, SAVED_CREATURE_KEYS, f"{label}.creature")
    return creature


def _creature_family(creature: dict[str, Any], label: str) -> str:
    family = creature.get("initialConditionFamily")
    if family is not None:
        return family
    return initial_condition_family(
        creature["initialCondition"], f"{label}.creature.initialCondition"
    )


def _fill_runtime(
    record: dict[str, Any], manifest_key: str, keys: tuple[str, str], stats: Stats
) -> None:
    """Copy runtime family and capabilities from the record's manifest when the record lacks them."""
    family_key, capabilities_key = keys
    manifest = record[manifest_key]
    if record.get(family_key) is None:
        _set_key(record, family_key, manifest["runtimeFamily"])
        stats.shapes_rewritten[f"{family_key} from manifest"] += 1
    if record.get(capabilities_key) is None:
        _set_key(record, capabilities_key, manifest["runtimeCapabilities"])
        stats.shapes_rewritten[f"{capabilities_key} from manifest"] += 1


def rewrite_library_entry(record: dict[str, Any], stats: Stats, label: str) -> None:
    """ResearchLibraryEntry rows (`library/index.jsonl`, `library-entry.json`)."""
    creature = _creature(record, stats, label)
    if record.get("specimen_manifest") is None:
        _write_library_manifest(record, creature, stats, label)
    _fill_runtime(record, "specimen_manifest", ("runtime_family", "runtime_capabilities"), stats)


def _write_library_manifest(
    record: dict[str, Any], creature: dict[str, Any], stats: Stats, label: str
) -> None:
    research_metadata = record.get("research_metadata")
    bundle_kind = _canonical_export_bundle_kind(research_metadata)
    source_mode = _normalized_source_mode(record.get("source_mode"))
    config_hash = record.get("config_hash")
    manifest = _manifest(
        creature_id=creature["id"].upper(),
        run_id=record["run_id"],
        campaign_id=record.get("campaign_id"),
        source_kind="library",
        source_mode=source_mode,
        source_algorithm=record.get("source_algorithm"),
        family=runtime_family(source_mode, bundle_kind, research_metadata),
        capabilities=runtime_capabilities(
            creature.get("descriptorBundle"), bundle_kind, research_metadata
        ),
        config_hash=config_hash if config_hash is not None else creature.get("configHash"),
        recorded_at=record["recorded_at"],
        initial_condition_family_value=_creature_family(creature, label),
        replay={"bundleKind": bundle_kind},
        research_metadata=research_metadata,
    )
    _set_key(record, "specimen_manifest", manifest)
    stats.manifests_written += 1


def _bundle_kind_from_export_index(creature_id: str, export_dir: Path, label: str) -> str:
    index = export_dir.parent / "index.jsonl"
    if not index.is_file():
        raise CompactionError(f"{label}: no bundleKind and no export index at {index}")
    kinds = set()
    with index.open("rb") as handle:
        for line in handle:
            if creature_id.encode() not in line.upper():
                continue
            row = json.loads(line)
            if (
                str(row.get("creatureId", "")).upper() == creature_id
                and Path(row.get("exportDir", "")).name == export_dir.name
            ):
                kinds.add(row["bundleKind"])
    if len(kinds) != 1:
        raise CompactionError(
            f"{label}: export index {index} names bundle kinds {sorted(kinds)} for {creature_id}"
        )
    return kinds.pop()


def rewrite_export_metadata(record: dict[str, Any], stats: Stats, label: str, path: Path) -> None:
    """CreatureExportMetadata (`exports/<bundle>/meta.json`)."""
    creature = _creature(record, stats, label)
    _require(record, ("runId", "exportedAt", "reason"), label)
    creature_id = creature["id"].upper()
    if "bundleKind" not in record:
        _set_key(
            record, "bundleKind", _bundle_kind_from_export_index(creature_id, path.parent, label)
        )
        stats.shapes_rewritten["bundleKind from export index"] += 1
    bundle_kind = record["bundleKind"]
    if bundle_kind not in BUNDLE_RUNTIME_FAMILY:
        raise CompactionError(f"{label}: unknown bundleKind {bundle_kind!r}")
    family = record.get("runtimeFamily")
    if family in RETIRED_RUNTIME_FAMILIES:
        _set_key(record, "runtimeFamily", RETIRED_RUNTIME_FAMILIES[family])
        stats.shapes_rewritten["runtimeFamily vocabulary"] += 1
    capabilities = record.get("runtimeCapabilities")
    if capabilities is not None:
        names = set(capabilities)
        if names & RETIRED_CAPABILITIES:
            if names - RETIRED_CAPABILITIES:
                raise CompactionError(
                    f"{label}: runtimeCapabilities mix retired and current names {sorted(names)}"
                )
            _set_key(
                record,
                "runtimeCapabilities",
                runtime_capabilities(creature.get("descriptorBundle"), bundle_kind, None),
            )
            stats.shapes_rewritten["runtimeCapabilities vocabulary"] += 1
        elif not names <= CAPABILITIES:
            raise CompactionError(
                f"{label}: unknown runtimeCapabilities {sorted(names - CAPABILITIES)}"
            )
    if record.get("specimenManifest") is None:
        manifest = _manifest(
            creature_id=creature_id,
            run_id=record["runId"],
            campaign_id=record.get("campaignId"),
            source_kind="export_metadata",
            source_mode=None,
            source_algorithm=None,
            family=runtime_family(None, bundle_kind, None),
            capabilities=runtime_capabilities(creature.get("descriptorBundle"), bundle_kind, None),
            config_hash=creature.get("configHash"),
            recorded_at=record["exportedAt"],
            initial_condition_family_value=_creature_family(creature, label),
            replay={"bundleKind": bundle_kind},
            research_metadata=None,
        )
        _set_key(record, "specimenManifest", manifest)
        stats.manifests_written += 1
    _fill_runtime(record, "specimenManifest", ("runtimeFamily", "runtimeCapabilities"), stats)


def rewrite_export_record(record: dict[str, Any], stats: Stats, label: str) -> None:
    """CreatureExportRecord rows (`exports/index.jsonl`)."""
    _require(
        record,
        (
            "creatureId",
            "name",
            "ownerId",
            "runId",
            "bundleKind",
            "exportDir",
            "exportedAt",
            "reason",
        ),
        label,
    )
    if record["bundleKind"] not in BUNDLE_RUNTIME_FAMILY:
        raise CompactionError(f"{label}: unknown bundleKind {record['bundleKind']!r}")
    if record.get("specimenManifest") is None:
        _write_export_record_manifest(record, stats)
    _fill_runtime(record, "specimenManifest", ("runtimeFamily", "runtimeCapabilities"), stats)


def _write_export_record_manifest(record: dict[str, Any], stats: Stats) -> None:
    bundle_kind = record["bundleKind"]
    manifest = _manifest(
        creature_id=str(record["creatureId"]).upper(),
        run_id=record["runId"],
        campaign_id=record.get("campaignId"),
        source_kind="export",
        source_mode=None,
        source_algorithm=None,
        family=runtime_family(None, bundle_kind, None),
        capabilities=runtime_capabilities(None, bundle_kind, None),
        config_hash=None,
        recorded_at=record["exportedAt"],
        initial_condition_family_value=None,
        replay={
            "bundleKind": bundle_kind,
            "exportDir": record["exportDir"],
            "baseConfigPath": record.get("baseConfigPath"),
            "searchConfigPath": record.get("searchConfigPath"),
            "payloadPath": record.get("payloadPath"),
        },
        research_metadata=None,
    )
    _set_key(record, "specimenManifest", manifest)
    stats.manifests_written += 1


def compact_document(doc: Any, stats: Stats, label: str, path: Path) -> list[str]:
    """Rewrite one JSON document in place; returns the raw sha256 of every patch it still holds."""
    if isinstance(doc, dict):
        keys = doc.keys()
        if {"creature", "run_id"} <= keys and keys <= LIBRARY_ENTRY_KEYS:
            rewrite_library_entry(doc, stats, label)
        elif {"creature", "runId", "exportedAt"} <= keys and keys <= EXPORT_METADATA_KEYS:
            rewrite_export_metadata(doc, stats, label, path)
        elif {"creatureId", "exportDir"} <= keys and keys <= EXPORT_RECORD_KEYS:
            rewrite_export_record(doc, stats, label)
    drop_duplicated_snapshots(doc, stats, label)
    raw_sha256: list[str] = []
    convert_patches(doc, stats, label, raw_sha256)
    return raw_sha256


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def detect_style(text: str, label: str) -> Style:
    """Formatting of an existing document: indent width, key separator, slash and non-ASCII escaping."""
    index = _skip_whitespace(text, 0)
    depth = 0
    while index < len(text) and text[index] == "[":
        depth += 1
        index = _skip_whitespace(text, index + 1)
    if index >= len(text) or text[index] != "{":
        raise CompactionError(
            f"{label}: cannot read the formatting of a document that does not open with an object"
        )
    depth += 1
    opening = index
    index = _skip_whitespace(text, index + 1)
    if text[index] != '"':
        raise CompactionError(f"{label}: cannot read the formatting of an empty object")
    _, key_end = json.decoder.scanstring(text, index + 1)  # type: ignore[attr-defined]
    separator = re.match(r"[ \t]*:[ \t]*", text[key_end:])
    if separator is None:
        raise CompactionError(f"{label}: no key separator after the first key")
    gap = text[opening + 1 : index]
    if "\n" in gap:
        width = len(gap.rsplit("\n", 1)[1])
        if width % depth:
            raise CompactionError(
                f"{label}: indentation {width} is not a multiple of nesting depth {depth}"
            )
        indent = width // depth
    else:
        indent = None
    return Style(
        indent=indent,
        key_separator=separator.group(0),
        escape_slash="\\/" in text,
        ensure_ascii=text.isascii(),
    )


def dump(doc: Any, style: Style) -> str:
    if style.indent is not None:
        item_separator = ","
    elif style.key_separator == ":":
        item_separator = ","
    elif style.key_separator == ": ":
        item_separator = ", "
    else:
        raise CompactionError(f"single-line document with key separator {style.key_separator!r}")
    text = json.dumps(
        doc,
        indent=style.indent,
        separators=(item_separator, style.key_separator),
        ensure_ascii=style.ensure_ascii,
    )
    # json.dumps never emits "/" outside strings, so this reproduces Foundation's escaped slashes.
    return text.replace("/", "\\/") if style.escape_slash else text


def verify(output: str, label: str, expected_sha256: list[str]) -> None:
    """Re-read a rewritten document: no f32le patch remains and every patch decodes to its original raw bytes."""
    found: list[str] = []
    retired = Stats()
    convert_patches(json.loads(output), retired, label, found)
    if retired.patches_converted:
        raise CompactionError(f"{label}: rewritten output still holds f32le patches")
    if found != expected_sha256:
        raise CompactionError(f"{label}: patch raw sha256 sequence changed in the rewritten output")


def _compact_text(text: str, stats: Stats, label: str, path: Path) -> str | None:
    start = _skip_whitespace(text, 0)
    doc, end = json.JSONDecoder().raw_decode(text, start)
    if text[end:].strip():
        raise CompactionError(f"{label}: trailing content after the JSON document")
    before = stats.mutations()
    shas = compact_document(doc, stats, label, path)
    if stats.mutations() == before:
        return None
    output = dump(doc, detect_style(text, label))
    verify(output, label, shas)
    return text[:start] + output + text[end:]


def compact_bytes(raw: bytes, *, jsonl: bool, path: Path, label: str, stats: Stats) -> bytes | None:
    """The rewritten file contents, or None when the file is already in the current format."""
    if not jsonl:
        if not needs_parse(raw):
            return None
        output = _compact_text(raw.decode("utf-8"), stats, label, path)
        return None if output is None else output.encode("utf-8")
    lines = raw.split(b"\n")
    changed = False
    for number, line in enumerate(lines):
        if not line.strip() or not needs_parse(line):
            continue
        output = _compact_text(line.decode("utf-8"), stats, f"{label}:{number + 1}", path)
        if output is not None:
            lines[number] = output.encode("utf-8")
            changed = True
    return b"\n".join(lines) if changed else None


def atomic_write(path: Path, data: bytes) -> None:
    """Temp file in the same directory, fsync, rename over the original, fsync the directory."""
    mode = path.stat().st_mode & 0o7777
    handle, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".compact"
    )
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def compact_file(task: tuple[str, str, bool]) -> dict[str, Any]:
    root, relative, dry_run = task
    path = Path(root) / relative
    raw = path.read_bytes()
    stats = Stats()
    jsonl = path.suffix == ".jsonl"
    try:
        output = compact_bytes(raw, jsonl=jsonl, path=path, label=relative, stats=stats)
    except (CompactionError, ValueError, KeyError, TypeError, UnicodeDecodeError) as error:
        return {"path": relative, "error": f"{type(error).__name__}: {error}"}
    if output is None:
        return {"path": relative, "changed": False}
    if not dry_run:
        atomic_write(path, output)
    return {
        "path": relative,
        "changed": True,
        "bytes_before": len(raw),
        "bytes_after": len(output),
        "sha256_before": hashlib.sha256(raw).hexdigest(),
        "sha256_after": hashlib.sha256(output).hexdigest(),
        "patches_converted": stats.patches_converted,
        "raw_sha256": stats.raw_sha256,
        "snapshots_dropped": stats.snapshots_dropped,
        "manifests_written": stats.manifests_written,
        "shapes_rewritten": dict(sorted(stats.shapes_rewritten.items())),
    }


def discover(root: Path) -> tuple[list[str], list[str]]:
    """JSON and JSONL files under root, largest first, and the symlinks that were skipped."""
    files: list[tuple[int, str]] = []
    symlinks: list[str] = []
    for directory, subdirectories, names in os.walk(root):
        if Path(directory) == root and RECEIPT_DIR in subdirectories:
            subdirectories.remove(RECEIPT_DIR)
        for name in names:
            if not name.endswith((".json", ".jsonl")):
                continue
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            if path.is_symlink():
                symlinks.append(relative)
                continue
            files.append((path.stat().st_size, relative))
    files.sort(reverse=True)
    return [relative for _, relative in files], sorted(symlinks)


def _top_level(relative: str) -> str:
    parts = Path(relative).parts
    return parts[0] if len(parts) > 1 else "."


def _table(results: list[dict[str, Any]]) -> list[str]:
    groups: dict[str, Counter[str]] = {}
    for result in results:
        if not result.get("changed"):
            continue
        group = groups.setdefault(_top_level(result["path"]), Counter())
        group["files"] += 1
        for key in (
            "bytes_before",
            "bytes_after",
            "patches_converted",
            "snapshots_dropped",
            "manifests_written",
        ):
            group[key] += result[key]
    total: Counter[str] = Counter()
    for group in groups.values():
        total.update(group)
    header = f"{'directory':<36} {'files':>7} {'bytes before':>16} {'bytes after':>16} {'saved':>16} {'patches':>8} {'snapshots':>9} {'manifests':>9}"
    rows = [header]
    for name, group in [*sorted(groups.items()), ("total", total)]:
        rows.append(
            f"{name:<36} {group['files']:>7} {group['bytes_before']:>16,} {group['bytes_after']:>16,} "
            f"{group['bytes_before'] - group['bytes_after']:>16,} {group['patches_converted']:>8} "
            f"{group['snapshots_dropped']:>9} {group['manifests_written']:>9}"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-analysis compact",
        description=(
            "Rewrite every .json/.jsonl file under ROOT into the current storage format: f32le patches "
            "become f32le-shuffle-zlib, duplicated manifest snapshots are dropped, retired record shapes "
            "are rewritten. Files are replaced atomically after their patches verify; a receipt is "
            f"appended to ROOT/{RECEIPT_DIR}/."
        ),
    )
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute every rewrite and report savings; write nothing",
    )
    parser.add_argument(
        "--jobs", type=int, default=os.cpu_count(), help="worker processes (default: all cores)"
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"{root}: not a directory")
    relatives, symlinks = discover(root)
    started = datetime.now(UTC)
    receipt_path = root / RECEIPT_DIR / f"{started.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    receipt = None
    if not args.dry_run:
        receipt_path.parent.mkdir(exist_ok=True)
        receipt = receipt_path.open("x", encoding="utf-8")
        receipt.write(
            json.dumps(
                {
                    "kind": "run",
                    "root": str(root),
                    "started_at": started.isoformat(),
                    "encoding": FIELD_ENCODING,
                }
            )
            + "\n"
        )

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with Pool(args.jobs) as pool:
        for result in pool.imap_unordered(
            compact_file, [(str(root), rel, args.dry_run) for rel in relatives]
        ):
            if "error" in result:
                errors.append(result)
                continue
            results.append(result)
            if receipt is not None and result["changed"]:
                receipt.write(json.dumps({"kind": "file", **result}) + "\n")
                receipt.flush()
    if receipt is not None:
        receipt.close()

    mode = "dry run" if args.dry_run else "compacted"
    print(f"{mode}: {root}")
    print(f"scanned {len(relatives)} files, skipped {len(symlinks)} symlinks, {len(errors)} errors")
    for row in _table(results):
        print(row)
    if receipt is not None:
        print(f"receipt: {receipt_path}")
    for error in sorted(errors, key=lambda item: item["path"]):
        print(f"error: {error['path']}: {error['error']}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
