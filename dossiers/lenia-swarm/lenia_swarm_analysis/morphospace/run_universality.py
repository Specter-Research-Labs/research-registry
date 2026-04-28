from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from typing import Any

from duckdb import DuckDBPyConnection

from .warehouse import replace_universality_runs, stable_id, utc_now

_COARSE_LADDER = (0.05, 0.1, 0.2, 0.4)
_COARSE_AXIS_IDS = (
    "center_offset",
    "coverage",
    "compactness",
    "elongation",
    "fragmentation",
    "cavity_count",
    "bilateral_symmetry",
    "radial_symmetry",
    "rotational_symmetry",
)


def _baseline_state_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT anatomical_states.state_id, anatomical_states.state_json,
               specimens.regime_family, specimens.canonical_family
        FROM anatomical_states
        LEFT JOIN specimens USING (specimen_id)
        WHERE anatomical_states.study_id = ?
          AND anatomical_states.source_kind = 'specimen_baseline'
        ORDER BY anatomical_states.state_id
        """,
        [study_id],
    ).fetchall()
    resolved: list[dict[str, Any]] = []
    for state_id, state_json, regime_family, canonical_family in rows:
        resolved.append(
            {
                "state_id": str(state_id),
                "state_json": json.loads(state_json) if state_json else {},
                "regime_family": str(regime_family) if regime_family is not None else None,
                "canonical_family": str(canonical_family) if canonical_family is not None else None,
            }
        )
    return resolved


def _axis_map(connection: DuckDBPyConnection, *, state_id: str) -> dict[str, float]:
    return {
        str(axis_id): float(value)
        for axis_id, value in connection.execute(
            """
            SELECT axis_id, raw_value
            FROM anatomical_state_axes
            WHERE state_id = ? AND raw_value IS NOT NULL
            ORDER BY axis_id
            """,
            [state_id],
        ).fetchall()
    }


def _coarse_token(state_json: dict[str, Any], raw_axes: dict[str, float], *, epsilon: float) -> str:
    bins = []
    for axis_id in _COARSE_AXIS_IDS:
        value = raw_axes.get(axis_id)
        if value is None:
            continue
        bins.append(f"{axis_id}={round(value / epsilon):d}")
    bins.extend(
        [
            f"sym={state_json.get('symmetry_class', 'unknown')}",
            f"arr={state_json.get('arrangement_class', 'unknown')}",
            f"enc={state_json.get('enclosure_class', 'unknown')}",
            f"asm={state_json.get('assembly_class', 'unknown')}",
        ]
    )
    return "|".join(bins)


def _weighted_jaccard(lhs: Counter[str], rhs: Counter[str]) -> float:
    keys = set(lhs) | set(rhs)
    if not keys:
        return 1.0
    intersection = sum(min(lhs.get(key, 0), rhs.get(key, 0)) for key in keys)
    union = sum(max(lhs.get(key, 0), rhs.get(key, 0)) for key in keys)
    if union == 0:
        return 1.0
    return float(intersection) / float(union)


def run_universality(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    comparison_scope: str = "regime_family",
) -> str:
    rows = _baseline_state_rows(connection, study_id=study_id)
    if comparison_scope != "regime_family":
        raise SystemExit(f"Unsupported universality comparison scope: {comparison_scope}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        regime_family = row["regime_family"]
        if regime_family is None:
            continue
        grouped.setdefault(regime_family, []).append(row)
    comparisons: list[dict[str, Any]] = []
    for lhs_key, rhs_key in combinations(sorted(grouped), 2):
        lhs_rows = grouped[lhs_key]
        rhs_rows = grouped[rhs_key]
        ladder_rows: list[dict[str, Any]] = []
        previous_similarity: float | None = None
        strengthens_monotonically = True
        for epsilon in _COARSE_LADDER:
            lhs_counts = Counter(
                _coarse_token(
                    row["state_json"],
                    _axis_map(connection, state_id=row["state_id"]),
                    epsilon=epsilon,
                )
                for row in lhs_rows
            )
            rhs_counts = Counter(
                _coarse_token(
                    row["state_json"],
                    _axis_map(connection, state_id=row["state_id"]),
                    epsilon=epsilon,
                )
                for row in rhs_rows
            )
            similarity = _weighted_jaccard(lhs_counts, rhs_counts)
            if previous_similarity is not None and similarity + 1e-9 < previous_similarity:
                strengthens_monotonically = False
            ladder_rows.append(
                {
                    "epsilon": epsilon,
                    "weightedJaccard": similarity,
                    "lhsClassCount": len(lhs_counts),
                    "rhsClassCount": len(rhs_counts),
                    "sharedClassCount": len(set(lhs_counts) & set(rhs_counts)),
                }
            )
            previous_similarity = similarity
        comparisons.append(
            {
                "lhs": lhs_key,
                "rhs": rhs_key,
                "strengthensMonotonically": strengthens_monotonically,
                "ladder": ladder_rows,
            }
        )
    universality_run_id = stable_id("universality", study_id, comparison_scope, "coarse_anatomy_v1")
    replace_universality_runs(
        connection,
        study_id=study_id,
        runs=[
            {
                "universality_run_id": universality_run_id,
                "comparison_scope": comparison_scope,
                "coarse_kind": "coarse_anatomy_v1",
                "created_at": utc_now(),
                "summary_json": {
                    "studyId": study_id,
                    "comparisonScope": comparison_scope,
                    "coarseKind": "coarse_anatomy_v1",
                    "epsilonLadder": list(_COARSE_LADDER),
                    "comparisonCount": len(comparisons),
                    "comparisons": comparisons,
                },
            }
        ],
    )
    return universality_run_id
