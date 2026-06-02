from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _dist(value: dict[str, Any], key: str) -> dict[str, Any] | None:
    item = value.get(key)
    return item if isinstance(item, dict) else None


def _top_h1_landmarks(tda: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    landmarks = tda.get("landmarks")
    if not isinstance(landmarks, list):
        return rows
    for row in landmarks:
        if not isinstance(row, dict):
            continue
        topology = row.get("topology")
        if not isinstance(topology, dict):
            continue
        rows.append(
            {
                "label": row.get("label"),
                "landmarkCount": row.get("landmarkCount"),
                "pointCount": row.get("pointCount"),
                "h1TopPersistence": topology.get("h1TopPersistence"),
                "h1ThresholdCounts": topology.get("h1ThresholdCounts"),
                "peakBetti1": topology.get("peakBetti1"),
            }
        )
    return rows


def _subsample_h1(tda: dict[str, Any]) -> dict[str, Any]:
    rows: dict[str, list[float]] = {}
    subsamples = tda.get("subsamples")
    if not isinstance(subsamples, list):
        return {}
    for row in subsamples:
        if not isinstance(row, dict):
            continue
        sample_size = row.get("sampleSize")
        tda_case = row.get("tda")
        if not isinstance(tda_case, dict):
            continue
        topology = tda_case.get("topology")
        if not isinstance(topology, dict):
            continue
        value = topology.get("h1TopPersistence")
        if isinstance(sample_size, int) and isinstance(value, int | float):
            rows.setdefault(str(sample_size), []).append(float(value))
    return {
        size: {
            "count": len(values),
            "min": min(values),
            "mean": sum(values) / len(values),
            "max": max(values),
        }
        for size, values in sorted(rows.items())
        if values
    }


def _region_seed_rows(h1_regions: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for region in h1_regions.get("topRegions", []):
        if not isinstance(region, dict):
            continue
        seeds = []
        for endpoint in region.get("endpointRepresentatives", []):
            if isinstance(endpoint, dict) and isinstance(endpoint.get("seed"), int):
                seeds.append(int(endpoint["seed"]))
        rows.append(
            {
                "rank": region.get("rank"),
                "persistence": region.get("persistence"),
                "birth": region.get("birth"),
                "death": region.get("death"),
                "endpointCount": region.get("endpointCount"),
                "endpointSeeds": seeds,
                "axisMeanNormalized": region.get("axisMeanNormalized"),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _candidate_seeds(candidates: dict[str, Any], key: str, *, limit: int) -> list[int]:
    rows = candidates.get(key)
    if not isinstance(rows, list):
        return []
    seeds: list[int] = []
    for row in rows[:limit]:
        if isinstance(row, dict) and isinstance(row.get("seed"), int):
            seeds.append(int(row["seed"]))
    return seeds


def _distortion_seeds(distortion: dict[str, Any], key: str, *, limit: int) -> list[int]:
    rows = distortion.get(key)
    if not isinstance(rows, list):
        return []
    seeds: list[int] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        for seed_key in ("seed", "neighborSeed"):
            if isinstance(row.get(seed_key), int):
                seeds.append(int(row[seed_key]))
    return seeds


def _dedupe(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_atlas_evidence_packet(
    *,
    atlas_findings: dict[str, Any],
    common_tda: dict[str, Any],
    h1_regions: dict[str, Any] | None = None,
    validation256: dict[str, Any] | None = None,
    terminal_tda: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    motion = atlas_findings.get("motionSummary")
    biological = atlas_findings.get("biologicalNearSummary")
    distortion = atlas_findings.get("genotypePhenotypeDistortion")
    candidates = atlas_findings.get("candidates")
    if not isinstance(motion, dict):
        raise ValueError("atlas findings missing motionSummary")
    if not isinstance(biological, dict):
        raise ValueError("atlas findings missing biologicalNearSummary")
    if not isinstance(distortion, dict):
        raise ValueError("atlas findings missing genotypePhenotypeDistortion")
    if not isinstance(candidates, dict):
        raise ValueError("atlas findings missing candidates")

    h1_rows = _region_seed_rows(h1_regions or {})
    h1_seeds: list[int] = []
    for row in h1_rows:
        h1_seeds.extend(row["endpointSeeds"])

    selected_seed_sets = {
        "compactConnectedMovers": _candidate_seeds(candidates, "compactConnectedMovers", limit=12),
        "fishNearest": _candidate_seeds(candidates, "fishNearest", limit=12),
        "embryomakerNearest": _candidate_seeds(candidates, "embryomakerNearest", limit=12),
        "topDisplacement": _candidate_seeds(candidates, "topDisplacement", limit=8),
        "h1EndpointRepresentatives": _dedupe(h1_seeds),
        "highSensitivityPairs": _distortion_seeds(distortion, "highSensitivityExamples", limit=8),
        "highDegeneracyPairs": _distortion_seeds(distortion, "highDegeneracyExamples", limit=8),
    }
    validation_seeds = _dedupe(
        [
            seed
            for seeds in selected_seed_sets.values()
            for seed in seeds
        ]
    )

    validation_summary = (validation256 or {}).get("summary")
    validation_rows = (validation256 or {}).get("rows")
    if not isinstance(validation_summary, dict):
        validation_summary = {}
    if not isinstance(validation_rows, list):
        validation_rows = []

    common_summary = (
        common_tda.get("summary")
        if isinstance(common_tda.get("summary"), dict)
        else {}
    )
    terminal_summary = (
        terminal_tda.get("summary")
        if terminal_tda is not None and isinstance(terminal_tda.get("summary"), dict)
        else {}
    )

    return {
        "packetKind": "fl2c20_motion_atlas_evidence_v1",
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "run": {
            "runId": atlas_findings.get("runId"),
            "resultCount": atlas_findings.get("resultCount"),
            "featureSpaceId": atlas_findings.get("featureSpaceId"),
            "commonTdaObservationCount": common_summary.get("observationCount"),
            "terminalTdaObservationCount": terminal_summary.get("observationCount"),
        },
        "motion": {
            "counts": motion.get("counts"),
            "displacement": _dist(motion, "displacement"),
            "pathLength": _dist(motion, "pathLength"),
            "movementEfficiency": _dist(motion, "movementEfficiency"),
            "largestComponentFraction": _dist(motion, "largestComponentFraction"),
            "componentCount": _dist(motion, "componentCount"),
        },
        "biologicalNear": {
            "fishDistance": _dist(biological, "fishDistance"),
            "fishDistanceLt1": biological.get("fishDistanceLt1"),
            "fishDistanceLt2": biological.get("fishDistanceLt2"),
            "embryomakerDistance": _dist(biological, "embryomakerDistance"),
            "embryomakerDistanceLt1": biological.get("embryomakerDistanceLt1"),
            "embryomakerDistanceLt2": biological.get("embryomakerDistanceLt2"),
        },
        "topology": {
            "commonLandmarks": _top_h1_landmarks(common_tda),
            "commonSubsampleH1TopPersistence": _subsample_h1(common_tda),
            "terminalLandmarks": _top_h1_landmarks(terminal_tda or {}),
            "h1Regions": h1_rows,
        },
        "genotypePhenotype": {
            "sampleCount": distortion.get("sampleCount"),
            "sensitivityRatio": _dist(distortion, "sensitivityRatio"),
            "degeneracyRatio": _dist(distortion, "degeneracyRatio"),
            "phenotypeJumpForGenotypeNearest": _dist(
                distortion,
                "phenotypeJumpForGenotypeNearest",
            ),
            "genotypeJumpForPhenotypeNearest": _dist(
                distortion,
                "genotypeJumpForPhenotypeNearest",
            ),
        },
        "finiteSizeValidation": {
            "summary": validation_summary,
            "movingSurvivalFraction": _ratio(
                validation_summary.get("moving256"),
                validation_summary.get("moving128"),
            ),
            "compactMovingSurvivalFraction": _ratio(
                validation_summary.get("compactMoving256"),
                validation_summary.get("compactMoving128"),
            ),
            "rows": validation_rows[:24],
        },
        "selection": {
            "seedSets": selected_seed_sets,
            "validationSeeds": validation_seeds,
            "validationSeedCount": len(validation_seeds),
        },
        "interpretation": [
            "Transport exists but is rare in the broad atlas.",
            (
                "Strict compact-moving morphology is not stable under the current "
                "256 validation slice."
            ),
            (
                "Common morphology has persistent H1 across landmark scales; "
                "terminal dynamics show weaker H1."
            ),
            "Nearest biological neighborhoods exist but remain small pockets, not a global match.",
            "Genotype-to-phenotype distortion is large enough to justify local fiber-style tests.",
        ],
    }


def _ratio(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, int | float) or not isinstance(denominator, int | float):
        return None
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def build_atlas_evidence_packet_from_files(
    *,
    atlas_findings_path: Path,
    common_tda_path: Path,
    h1_regions_path: Path | None = None,
    validation256_path: Path | None = None,
    terminal_tda_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return build_atlas_evidence_packet(
        atlas_findings=read_json_object(atlas_findings_path),
        common_tda=read_json_object(common_tda_path),
        h1_regions=read_json_object(h1_regions_path) if h1_regions_path else None,
        validation256=read_json_object(validation256_path) if validation256_path else None,
        terminal_tda=read_json_object(terminal_tda_path) if terminal_tda_path else None,
        generated_at=generated_at,
    )
