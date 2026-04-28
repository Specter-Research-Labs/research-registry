from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return payload


def classify_control_label(
    *,
    dist_to_a: float,
    dist_to_b: float,
    ambiguity_ratio: float = 0.95,
) -> str:
    if dist_to_a < 0 or dist_to_b < 0:
        raise SystemExit("Phenotype distances must be non-negative")
    if dist_to_a == 0 and dist_to_b == 0:
        return "ambiguous"
    larger = max(dist_to_a, dist_to_b)
    smaller = min(dist_to_a, dist_to_b)
    if larger > 0 and (smaller / larger) >= ambiguity_ratio:
        return "ambiguous"
    return "A" if dist_to_a < dist_to_b else "B"


def collapse_path(values: list[str], *, skip: set[str] | None = None) -> list[str]:
    skipped = skip or set()
    collapsed: list[str] = []
    for value in values:
        if value in skipped:
            continue
        if not collapsed or collapsed[-1] != value:
            collapsed.append(value)
    return collapsed


def has_reentry(path: list[str]) -> bool:
    if len(path) < 3:
        return False
    first_seen: dict[str, int] = {}
    for index, label in enumerate(path):
        previous = first_seen.get(label)
        if previous is not None and index - previous >= 2:
            return True
        first_seen.setdefault(label, index)
    return False


def summarize_continuation_rows(
    rows: list[dict[str, Any]],
    *,
    target_control_label: str = "B",
) -> dict[str, Any]:
    successful = [row for row in rows if int(row.get("returncode", 1)) == 0]
    failures = [row for row in rows if int(row.get("returncode", 1)) != 0]
    control_path = collapse_path(
        [str(row.get("controlLabel", "ambiguous")) for row in successful],
        skip={"ambiguous"},
    )
    representative_path = collapse_path(
        [
            str(row["nearestRepresentativeSpecimenId"])
            for row in successful
            if isinstance(row.get("nearestRepresentativeSpecimenId"), str)
        ]
    )
    endpoint_distance = 0.0
    if successful:
        terminal = successful[-1]
        if target_control_label == "A":
            endpoint_distance = float(terminal["distToB"])
        elif target_control_label == "B":
            endpoint_distance = float(terminal["distToA"])
        else:
            raise SystemExit(f"Unsupported target control label: {target_control_label}")
    max_escape_ratio = 0.0
    if endpoint_distance > 0:
        max_escape_ratio = max(
            max(float(row["distToA"]), float(row["distToB"])) / endpoint_distance
            for row in successful
        )
    endpoint_ids = set()
    if representative_path:
        endpoint_ids = {representative_path[0], representative_path[-1]}
    return {
        "successCount": len(successful),
        "failureCount": len(failures),
        "ambiguousCount": sum(row.get("controlLabel") == "ambiguous" for row in successful),
        "branchSwitchCount": max(len(control_path) - 1, 0),
        "collapsedControlPath": control_path,
        "hasReentry": has_reentry(control_path),
        "collapsedRepresentativePath": representative_path,
        "representativeVisitCount": len(representative_path),
        "visitsNonEndpointRepresentative": any(
            specimen_id not in endpoint_ids for specimen_id in representative_path
        )
        if endpoint_ids
        else False,
        "endpointPhenotypeDistance": endpoint_distance,
        "maxNearestAnchorDistance": max(
            (min(float(row["distToA"]), float(row["distToB"])) for row in successful),
            default=0.0,
        ),
        "maxEscapeRatio": max_escape_ratio,
        "maxDistanceToCycleSupport": max(
            (float(row.get("distToCycleSupport", 0.0)) for row in successful),
            default=0.0,
        ),
        "maxStepPhenotypeDelta": max(
            (
                float(row["stepPhenotypeDelta"])
                for row in successful
                if row.get("stepPhenotypeDelta") is not None
            ),
            default=0.0,
        ),
        "maxPhenotypeDistanceToA": max(
            (float(row["distToA"]) for row in successful),
            default=0.0,
        ),
        "maxPhenotypeDistanceToB": max(
            (float(row["distToB"]) for row in successful),
            default=0.0,
        ),
    }
