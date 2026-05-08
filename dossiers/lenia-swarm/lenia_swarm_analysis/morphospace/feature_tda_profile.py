from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
from duckdb import DuckDBPyConnection
from ripser import ripser

from lenia_swarm_analysis.topology.analysis import (
    _diagram_summary,
    _pairwise_distance_matrix,
    _upper_triangle,
)

from .feature_matrix import export_feature_matrix

PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "smoke": {
        "exact_max_observations": 512,
        "threshold_max_observations": 512,
        "threshold_sample_points": 1024,
        "landmark_counts": (128, 256),
        "subsample_sizes": (128, 256),
        "subsample_replicates": 1,
        "threshold_quantiles": (0.02,),
        "pairwise_sample_points": 512,
        "min_stratum_size": 128,
        "max_strata": 4,
    },
    "current": {
        "exact_max_observations": 8192,
        "threshold_max_observations": 8192,
        "threshold_sample_points": 4096,
        "landmark_counts": (512, 1024, 2048, 4096),
        "subsample_sizes": (512, 1024, 2048, 4096),
        "subsample_replicates": 3,
        "threshold_quantiles": (0.01, 0.02),
        "pairwise_sample_points": 4096,
        "min_stratum_size": 256,
        "max_strata": 20,
    },
    "full": {
        "exact_max_observations": 8192,
        "threshold_max_observations": 8192,
        "threshold_sample_points": 8192,
        "landmark_counts": (1024, 2048, 4096, 8192),
        "subsample_sizes": (1024, 2048, 4096),
        "subsample_replicates": 5,
        "threshold_quantiles": (0.005, 0.01, 0.02),
        "pairwise_sample_points": 8192,
        "min_stratum_size": 256,
        "max_strata": 32,
    },
}


def profile_names() -> tuple[str, ...]:
    return tuple(sorted(PROFILE_PRESETS))


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _distribution(values: np.ndarray) -> dict[str, Any]:
    if values.size == 0:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "median": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": int(values.size),
        "min": _finite_or_none(float(np.min(values))),
        "mean": _finite_or_none(float(np.mean(values))),
        "median": _finite_or_none(float(np.median(values))),
        "p90": _finite_or_none(float(np.quantile(values, 0.90))),
        "p95": _finite_or_none(float(np.quantile(values, 0.95))),
        "p99": _finite_or_none(float(np.quantile(values, 0.99))),
        "max": _finite_or_none(float(np.max(values))),
    }


def _pairwise_sample(
    matrix: np.ndarray,
    *,
    max_points: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    if matrix.shape[0] < 2:
        raise ValueError("pairwise sampling requires at least two observations")
    sample_size = min(max_points, matrix.shape[0])
    if sample_size == matrix.shape[0]:
        indices = np.arange(matrix.shape[0], dtype=np.int64)
    else:
        indices = np.sort(rng.choice(matrix.shape[0], size=sample_size, replace=False))
    distances = _pairwise_distance_matrix(matrix[indices])
    pairwise = _upper_triangle(distances)
    quantiles = {
        f"{quantile:.3f}": float(np.quantile(pairwise, quantile))
        for quantile in (0.005, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50)
        if pairwise.size
    }
    return {
        "samplePointCount": int(sample_size),
        "distribution": _distribution(pairwise),
        "quantiles": quantiles,
    }


def _persistence_threshold_counts(diagrams: list[list[dict[str, Any]]]) -> dict[str, int]:
    if len(diagrams) <= 1:
        return {}
    persistences = [
        float(entry["persistence"])
        for entry in diagrams[1]
        if entry.get("persistence") is not None
    ]
    return {
        f">={threshold:.3f}": int(sum(value >= threshold for value in persistences))
        for threshold in (0.01, 0.02, 0.05, 0.10, 0.25, 0.50)
    }


def _peak_betti_one(betti_curves: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(betti_curves) <= 1:
        return None
    betti = betti_curves[1].get("betti")
    scale = betti_curves[1].get("scale")
    if not isinstance(betti, list) or not betti:
        return None
    if not isinstance(scale, list) or len(scale) != len(betti):
        return None
    peak_index = max(range(len(betti)), key=betti.__getitem__)
    return {"count": int(betti[peak_index]), "scale": float(scale[peak_index])}


def _topology_metrics(
    diagrams: list[np.ndarray],
    *,
    pairwise_max: float,
) -> dict[str, Any]:
    topology = _diagram_summary(diagrams, pairwise_max)
    h1 = topology["summaries"][1] if len(topology["summaries"]) > 1 else None
    return {
        **topology,
        "h1ThresholdCounts": _persistence_threshold_counts(topology["diagrams"]),
        "peakBetti1": _peak_betti_one(topology["bettiCurves"]),
        "h1TopPersistence": h1["topPersistence"][0] if h1 and h1["topPersistence"] else None,
    }


def _run_tda_case(
    matrix: np.ndarray,
    *,
    label: str,
    max_homology_dim: int,
    pairwise_sample_points: int,
    rng: np.random.Generator,
    threshold: float | None = None,
    threshold_quantile: float | None = None,
    landmark_count: int | None = None,
) -> dict[str, Any]:
    if matrix.shape[0] < 2:
        raise ValueError(f"{label}: TDA requires at least two observations")
    pairwise = _pairwise_sample(matrix, max_points=pairwise_sample_points, rng=rng)
    ripser_kwargs: dict[str, Any] = {
        "maxdim": max_homology_dim,
        "metric": "euclidean",
    }
    if threshold is not None:
        ripser_kwargs["thresh"] = threshold
    if landmark_count is not None and landmark_count < matrix.shape[0]:
        ripser_kwargs["n_perm"] = landmark_count
    result = ripser(matrix, **ripser_kwargs)
    extra: dict[str, Any] = {}
    if "r_cover" in result:
        extra["coveringRadius"] = _finite_or_none(float(result["r_cover"]))
    if "num_edges" in result:
        extra["edgeCount"] = int(result["num_edges"])
    return {
        "label": label,
        "pointCount": int(matrix.shape[0]),
        "dimension": int(matrix.shape[1]),
        "maxHomologyDim": max_homology_dim,
        "backend": "ripser-euclidean",
        "threshold": threshold,
        "thresholdQuantile": threshold_quantile,
        "landmarkCount": landmark_count,
        "pairwiseDistanceSample": pairwise,
        **extra,
        "topology": _topology_metrics(
            list(result["dgms"]),
            pairwise_max=float(pairwise["distribution"]["max"] or 0.0),
        ),
    }


def _rule_family_key(observation: dict[str, Any]) -> str:
    source_id = str(observation.get("sourceId") or "<none>")
    runtime_family = str(observation.get("runtimeFamily") or source_id)
    config_hash = str(observation.get("configHash") or "<none>")
    source_mode = str(observation.get("sourceMode") or "<none>")
    source_algorithm = str(observation.get("sourceAlgorithm") or "<none>")
    if source_id != "lenia_swarm":
        return source_id
    return f"{runtime_family}:{config_hash}:{source_mode}:{source_algorithm}"


def _stratum_key(observation: dict[str, Any], stratify_by: str) -> str:
    if stratify_by == "rule_family_key":
        return _rule_family_key(observation)
    value = observation.get(stratify_by)
    return str(value) if value not in (None, "") else "<none>"


def _effective_counts(counts: tuple[int, ...], point_count: int) -> tuple[int, ...]:
    values = sorted({count for count in counts if 1 < count < point_count})
    return tuple(values)


def _subsample_indices(
    *,
    point_count: int,
    sample_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if sample_size > point_count:
        raise ValueError("sample_size cannot exceed point_count")
    return np.sort(rng.choice(point_count, size=sample_size, replace=False))


def _bounded_tda_matrix(
    matrix: np.ndarray,
    *,
    max_observations: int,
    sample_points: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, Any] | None]:
    if matrix.shape[0] <= max_observations:
        return matrix, None
    sample_size = min(sample_points, matrix.shape[0])
    indices = _subsample_indices(
        point_count=matrix.shape[0],
        sample_size=sample_size,
        rng=rng,
    )
    return matrix[indices], {
        "status": "sampled",
        "sourcePointCount": int(matrix.shape[0]),
        "samplePointCount": int(sample_size),
        "maxObservations": int(max_observations),
    }


def run_feature_tda_profile(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    profile: str = "current",
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    study_kind: str | None = None,
    run_id: str | None = None,
    run_id_contains: str | None = None,
    source_mode: str | None = None,
    observation_kind: str | None = None,
    source_algorithm: str | None = None,
    canonical_family: str | None = None,
    max_homology_dim: int = 1,
    stratify_by: str = "rule_family_key",
    seed: int = 0,
) -> dict[str, Any]:
    if profile not in PROFILE_PRESETS:
        raise ValueError(f"unknown TDA profile: {profile}")
    preset = PROFILE_PRESETS[profile]
    matrix_packet = export_feature_matrix(
        connection,
        feature_space_id=feature_space_id,
        value_column=value_column,
        source_id=source_id,
        study_id=study_id,
        study_kind=study_kind,
        run_id=run_id,
        run_id_contains=run_id_contains,
        source_mode=source_mode,
        observation_kind=observation_kind,
        source_algorithm=source_algorithm,
        canonical_family=canonical_family,
    )
    matrix = np.asarray(matrix_packet["matrix"], dtype=np.float64)
    observations = matrix_packet["observations"]
    if matrix.shape[0] < 2:
        raise ValueError("TDA profile requires at least two complete observations")

    rng = np.random.default_rng(seed)
    pairwise_sample_points = int(preset["pairwise_sample_points"])
    pairwise = _pairwise_sample(matrix, max_points=pairwise_sample_points, rng=rng)
    quantiles = pairwise["quantiles"]

    exact: dict[str, Any]
    exact_max = int(preset["exact_max_observations"])
    if matrix.shape[0] <= exact_max:
        exact = _run_tda_case(
            matrix,
            label="exact",
            max_homology_dim=max_homology_dim,
            pairwise_sample_points=pairwise_sample_points,
            rng=rng,
        )
    else:
        exact = {
            "label": "exact",
            "status": "skipped",
            "reason": (
                f"observationCount {matrix.shape[0]} exceeds "
                f"exactMaxObservations {exact_max}"
            ),
        }

    thresholded: list[dict[str, Any]] = []
    threshold_max = int(preset["threshold_max_observations"])
    threshold_sample_points = int(preset["threshold_sample_points"])
    for quantile in preset["threshold_quantiles"]:
        key = f"{float(quantile):.3f}"
        threshold = quantiles.get(key)
        if threshold is None:
            continue
        threshold_matrix, sample_info = _bounded_tda_matrix(
            matrix,
            max_observations=threshold_max,
            sample_points=threshold_sample_points,
            rng=rng,
        )
        label = f"threshold-q{key}"
        if sample_info is not None:
            label = f"{label}-sample-{sample_info['samplePointCount']}"
            sample_info["reason"] = (
                f"observationCount {matrix.shape[0]} exceeds "
                f"thresholdMaxObservations {threshold_max}"
            )
        case = _run_tda_case(
            threshold_matrix,
            label=label,
            max_homology_dim=max_homology_dim,
            pairwise_sample_points=pairwise_sample_points,
            rng=rng,
            threshold=threshold,
            threshold_quantile=float(quantile),
        )
        if sample_info is not None:
            case["sample"] = sample_info
        thresholded.append(
            case
        )

    landmarks: list[dict[str, Any]] = []
    for landmark_count in _effective_counts(tuple(preset["landmark_counts"]), matrix.shape[0]):
        landmarks.append(
            _run_tda_case(
                matrix,
                label=f"landmark-{landmark_count}",
                max_homology_dim=max_homology_dim,
                pairwise_sample_points=pairwise_sample_points,
                rng=rng,
                landmark_count=landmark_count,
            )
        )

    subsamples: list[dict[str, Any]] = []
    for sample_size in tuple(preset["subsample_sizes"]):
        if sample_size > matrix.shape[0]:
            continue
        for replicate in range(int(preset["subsample_replicates"])):
            indices = _subsample_indices(
                point_count=matrix.shape[0],
                sample_size=int(sample_size),
                rng=rng,
            )
            subsamples.append(
                {
                    "sampleSize": int(sample_size),
                    "replicate": replicate,
                    "tda": _run_tda_case(
                        matrix[indices],
                        label=f"subsample-{sample_size}-{replicate}",
                        max_homology_dim=max_homology_dim,
                        pairwise_sample_points=pairwise_sample_points,
                        rng=rng,
                    ),
                }
            )

    strata: dict[str, list[int]] = defaultdict(list)
    for index, observation in enumerate(observations):
        strata[_stratum_key(observation, stratify_by)].append(index)
    stratum_rows: list[dict[str, Any]] = []
    min_stratum_size = int(preset["min_stratum_size"])
    max_strata = int(preset["max_strata"])
    for key, indices in sorted(strata.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(indices) < min_stratum_size:
            continue
        if len(stratum_rows) >= max_strata:
            break
        stratum_matrix = matrix[np.asarray(indices, dtype=np.int64)]
        stratum_landmarks: list[dict[str, Any]] = []
        for landmark_count in _effective_counts(tuple(preset["landmark_counts"]), len(indices))[:2]:
            stratum_landmarks.append(
                _run_tda_case(
                    stratum_matrix,
                    label=f"{key}-landmark-{landmark_count}",
                    max_homology_dim=max_homology_dim,
                    pairwise_sample_points=pairwise_sample_points,
                    rng=rng,
                    landmark_count=landmark_count,
                )
            )
        stratum_exact: dict[str, Any]
        if len(indices) <= exact_max:
            stratum_exact = _run_tda_case(
                stratum_matrix,
                label=f"{key}-exact",
                max_homology_dim=max_homology_dim,
                pairwise_sample_points=pairwise_sample_points,
                rng=rng,
            )
        else:
            stratum_exact = {
                "label": f"{key}-exact",
                "status": "skipped",
                "reason": f"stratum size {len(indices)} exceeds exactMaxObservations {exact_max}",
            }
        stratum_rows.append(
            {
                "stratumKey": key,
                "pointCount": len(indices),
                "exact": stratum_exact,
                "landmarks": stratum_landmarks,
            }
        )

    return {
        "packetKind": "comparative_feature_tda_profile_v1",
        "summary": {
            **matrix_packet["summary"],
            "profile": profile,
            "maxHomologyDim": max_homology_dim,
            "seed": seed,
            "stratifyBy": stratify_by,
            "exactMaxObservations": exact_max,
            "thresholdMaxObservations": threshold_max,
            "thresholdSamplePoints": threshold_sample_points,
        },
        "featureSpace": matrix_packet["featureSpace"],
        "axes": matrix_packet["axes"],
        "pairwiseDistanceSample": pairwise,
        "exact": exact,
        "thresholded": thresholded,
        "landmarks": landmarks,
        "subsamples": subsamples,
        "strata": stratum_rows,
    }
