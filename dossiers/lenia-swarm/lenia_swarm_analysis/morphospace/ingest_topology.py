from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from duckdb import DuckDBPyConnection

from .warehouse import json_text, register_study, stable_id, utc_now


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


def _register_topology_packet_artifact(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    artifact_ref: str,
    packet: dict[str, Any],
) -> str:
    encoded = json_text(packet).encode("utf-8")
    content_sha256 = hashlib.sha256(encoded).hexdigest()
    artifact_id = stable_id(
        "artifact",
        study_id,
        "topology_packet",
        artifact_ref,
        content_sha256,
    )
    connection.execute(
        """
        DELETE FROM raw_json_objects
        WHERE artifact_id IN (
            SELECT artifact_id FROM artifacts
            WHERE study_id = ? AND artifact_kind = 'topology_packet'
              AND artifact_id != ?
        )
        """,
        [study_id, artifact_id],
    )
    connection.execute(
        """
        DELETE FROM artifacts
        WHERE study_id = ? AND artifact_kind = 'topology_packet'
          AND artifact_id != ?
        """,
        [study_id, artifact_id],
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO artifacts (
            artifact_id, study_id, artifact_kind, path, sha256, size_bytes,
            created_at, metadata_json
        )
        VALUES (?, ?, 'topology_packet', ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            artifact_id,
            study_id,
            artifact_ref,
            content_sha256,
            len(encoded),
            utc_now(),
            json_text(
                {
                    "contentHashPolicy": "canonical-json-sha256-v1",
                    "sourceArtifact": packet.get("sourceArtifact"),
                }
            ),
        ],
    )
    return artifact_id


def ingest_topology_packet_payload(
    connection: DuckDBPyConnection,
    *,
    packet: dict[str, Any],
    artifact_ref: str | None = None,
    study_id: str | None = None,
    parent_study_id: str | None = None,
    label: str | None = None,
) -> str:
    if packet.get("packetKind") != "transformation_topology_packet_v1":
        raise SystemExit("topology payload: expected transformation_topology_packet_v1")
    resolved_study_id = register_study(
        connection,
        study_kind="topology_run",
        label=label or "topology-packet",
        study_id=study_id,
        parent_study_id=parent_study_id,
        metadata_json={"sourceArtifact": packet.get("sourceArtifact")},
    )
    resolved_artifact_ref = artifact_ref or (
        f"duckdb://study/{resolved_study_id}/topology-packet"
    )
    artifact_id = _register_topology_packet_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_ref=resolved_artifact_ref,
        packet=packet,
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
        raise SystemExit("topology payload: missing spaces")
    incoming_topology_run_ids: list[str] = []
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
            incoming_topology_run_ids.append(topology_run_id)
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

    connection.execute(
        "CREATE OR REPLACE TEMP TABLE incoming_topology_runs (topology_run_id TEXT PRIMARY KEY)"
    )
    if incoming_topology_run_ids:
        connection.execute(
            "INSERT INTO incoming_topology_runs SELECT unnest(?::VARCHAR[])",
            [incoming_topology_run_ids],
        )
    connection.execute(
        """
        DELETE FROM topology_features
        WHERE topology_run_id IN (
            SELECT topology_runs.topology_run_id
            FROM topology_runs
            WHERE topology_runs.study_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM incoming_topology_runs AS incoming
                  WHERE incoming.topology_run_id = topology_runs.topology_run_id
              )
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM topology_runs
        WHERE study_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM incoming_topology_runs AS incoming
              WHERE incoming.topology_run_id = topology_runs.topology_run_id
          )
        """,
        [resolved_study_id],
    )

    return resolved_study_id


def ingest_topology_packet(
    connection: DuckDBPyConnection,
    *,
    topology_packet_path: Path,
    study_id: str | None = None,
    parent_study_id: str | None = None,
    label: str | None = None,
) -> str:
    resolved_path = topology_packet_path.expanduser().resolve(strict=True)
    packet = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise SystemExit(f"{resolved_path}: expected a JSON object")
    return ingest_topology_packet_payload(
        connection,
        packet=packet,
        artifact_ref=str(resolved_path),
        study_id=study_id,
        parent_study_id=parent_study_id,
        label=label or resolved_path.stem,
    )
