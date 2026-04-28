from __future__ import annotations

import json
from itertools import combinations
from statistics import mean
from typing import Any

from duckdb import DuckDBPyConnection

from .warehouse import replace_fiber_groups, stable_id


def _state_class_key(payload: dict[str, Any]) -> str:
    return "|".join(
        [
            str(payload.get("assembly_class", "unknown")),
            str(payload.get("enclosure_class", "unknown")),
            str(payload.get("symmetry_class", "unknown")),
            str(payload.get("arrangement_class", "unknown")),
        ]
    )


def _state_axis_map(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
) -> dict[str, float]:
    return {
        str(axis_id): float(value)
        for axis_id, value in connection.execute(
            """
            SELECT axis_id, transformed_value
            FROM anatomical_state_axes
            WHERE state_id = ? AND transformed_value IS NOT NULL
            ORDER BY axis_id
            """,
            [state_id],
        ).fetchall()
    }


def _mean_pairwise_distance(axis_maps: list[dict[str, float]]) -> float:
    distances: list[float] = []
    for lhs, rhs in combinations(axis_maps, 2):
        shared = sorted(set(lhs) & set(rhs))
        if not shared:
            continue
        distances.append(
            sum(abs(lhs[axis_id] - rhs[axis_id]) for axis_id in shared) / len(shared)
        )
    if not distances:
        return 0.0
    return float(mean(distances))


def derive_fibers(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        study_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT study_id FROM anatomical_states ORDER BY study_id"
            ).fetchall()
        ]
    else:
        study_ids = [study_id]

    updated = 0
    for resolved_study_id in study_ids:
        rows = connection.execute(
            """
            SELECT anatomical_states.state_id,
                   anatomical_states.specimen_id,
                   anatomical_states.state_json,
                   specimens.regime_family, specimens.canonical_family
            FROM anatomical_states
            LEFT JOIN specimens USING (specimen_id)
            WHERE anatomical_states.study_id = ?
              AND anatomical_states.source_kind = 'specimen_baseline'
            ORDER BY anatomical_states.state_id
            """,
            [resolved_study_id],
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for state_id, specimen_id, state_json, regime_family, canonical_family in rows:
            payload = json.loads(state_json) if state_json else {}
            class_key = _state_class_key(payload)
            grouped.setdefault(class_key, []).append(
                {
                    "state_id": str(state_id),
                    "specimen_id": str(specimen_id) if specimen_id is not None else None,
                    "payload": payload,
                    "regime_family": str(regime_family) if regime_family is not None else None,
                    "canonical_family": (
                        str(canonical_family) if canonical_family is not None else None
                    ),
                }
            )
        fiber_groups: list[dict[str, Any]] = []
        for class_key, members in sorted(grouped.items()):
            axis_maps = [
                _state_axis_map(connection, state_id=member["state_id"]) for member in members
            ]
            pairwise_distance = _mean_pairwise_distance(axis_maps)
            regimes = sorted(
                {
                    member["regime_family"]
                    for member in members
                    if member["regime_family"] is not None
                }
            )
            canonical_families = sorted(
                {
                    member["canonical_family"]
                    for member in members
                    if member["canonical_family"] is not None
                }
            )
            member_count = len(members)
            fiber_groups.append(
                {
                    "fiber_group_id": stable_id(
                        "fiber-group",
                        resolved_study_id,
                        "coarse_anatomy_v1",
                        class_key,
                    ),
                    "grouping_kind": "coarse_anatomy_v1",
                    "state_class_key": class_key,
                    "member_count": member_count,
                    "volume_proxy": float(member_count),
                    "diversity_proxy": (
                        float(len(canonical_families)) / float(member_count)
                        if member_count > 0
                        else 0.0
                    ),
                    "connectivity_proxy": 1.0 / (1.0 + pairwise_distance),
                    "metadata_json": {
                        "regimeFamilies": regimes,
                        "canonicalFamilies": canonical_families,
                        "meanPairwiseDistance": pairwise_distance,
                    },
                    "members": [
                        {
                            "state_id": member["state_id"],
                            "specimen_id": member["specimen_id"],
                        }
                        for member in members
                    ],
                }
            )
        replace_fiber_groups(connection, study_id=resolved_study_id, groups=fiber_groups)
        updated += len(fiber_groups)
    return updated
