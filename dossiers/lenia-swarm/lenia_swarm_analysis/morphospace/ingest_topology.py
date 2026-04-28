from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from duckdb import DuckDBPyConnection

from .warehouse import json_text, register_artifact, register_study, stable_id


def _topology_entries(space: dict[str, Any]) -> list[tuple[str | None, str | None, dict[str, Any]]]:
    rows: list[tuple[str | None, str | None, dict[str, Any]]] = []
    global_topology = space.get("global")
    if isinstance(global_topology, dict):
        rows.append((None, None, global_topology))
    groups = space.get("groups")
    if not isinstance(groups, dict):
        return rows
    for group_key, entries in groups.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            group_value = entry.get(group_key)
            topology = entry.get("topology")
            if isinstance(group_value, str) and isinstance(topology, dict):
                rows.append((str(group_key), group_value, topology))
    return rows


def _insert_features(
    connection: DuckDBPyConnection,
    *,
    topology_run_id: str,
    topology_summary: dict[str, Any],
) -> None:
    connection.execute(
        "DELETE FROM topology_features WHERE topology_run_id = ?",
        [topology_run_id],
    )
    diagrams = topology_summary.get("diagrams")
    if not isinstance(diagrams, list):
        return
    feature_index = 0
    for dimension, entries in enumerate(diagrams):
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            typed_entry = cast(dict[str, Any], entry)
            birth = typed_entry.get("birth")
            death = typed_entry.get("death")
            persistence = typed_entry.get("persistence")
            if not isinstance(birth, (int, float)):
                continue
            connection.execute(
                """
                INSERT INTO topology_features (
                    topology_run_id, feature_index, dimension, birth, death, persistence
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    topology_run_id,
                    feature_index,
                    dimension,
                    float(birth),
                    None if death is None else float(death),
                    None if persistence is None else float(persistence),
                ],
            )
            feature_index += 1


def ingest_topology_packet(
    connection: DuckDBPyConnection,
    *,
    topology_packet_path: Path,
    study_id: str | None = None,
    parent_study_id: str | None = None,
    label: str | None = None,
) -> str:
    packet = json.loads(topology_packet_path.read_text(encoding="utf-8"))
    if packet.get("packetKind") != "transformation_topology_packet_v1":
        raise SystemExit(f"{topology_packet_path}: expected transformation_topology_packet_v1")
    resolved_study_id = register_study(
        connection,
        study_kind="topology_run",
        label=label or topology_packet_path.stem,
        study_id=study_id,
        parent_study_id=parent_study_id,
        metadata_json={"sourceArtifact": str(topology_packet_path)},
    )
    artifact_id = register_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_kind="topology_packet",
        path=topology_packet_path,
    )
    from .warehouse import ingest_json_object_artifact

    ingest_json_object_artifact(
        connection,
        artifact_id=artifact_id,
        object_kind="topology_packet",
        payload=packet,
    )

    spaces = packet.get("spaces")
    if not isinstance(spaces, dict):
        raise SystemExit(f"{topology_packet_path}: missing spaces")
    for space_kind, space in spaces.items():
        if not isinstance(space, dict):
            continue
        for group_key, group_value, topology_summary in _topology_entries(space):
            topology_run_id = stable_id(
                "topology",
                resolved_study_id,
                space_kind,
                group_key or "global",
                group_value or "",
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO topology_runs (
                    topology_run_id, study_id, space_kind, group_key, group_value,
                    input_query_json, created_at, summary_json
                )
                VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), current_timestamp, CAST(? AS JSON))
                """,
                [
                    topology_run_id,
                    resolved_study_id,
                    str(space_kind),
                    group_key,
                    group_value,
                    json_text(packet.get("summary", {})),
                    json_text(topology_summary),
                ],
            )
            _insert_features(
                connection,
                topology_run_id=topology_run_id,
                topology_summary=topology_summary,
            )

    return resolved_study_id
