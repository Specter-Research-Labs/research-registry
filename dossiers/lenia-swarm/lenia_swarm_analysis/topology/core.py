from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, MutableMapping
from typing import Any

import numpy as np

MAX_PAIRWISE_BYTES = 512 * 1024 * 1024
MAX_EXACT_POINTS = int(math.sqrt(MAX_PAIRWISE_BYTES / np.dtype(np.float64).itemsize))
MAX_RIPS_POINTS = 4096
MAX_RIPS_HOMOLOGY_DIM = 2
# Reserve both dense distance buffers and generous queue/index overhead per candidate simplex.
MAX_RIPS_WORKING_BYTES = 2 * 1024 * 1024 * 1024
RIPS_BYTES_PER_SIMPLEX = 64
RIPS_DISTANCE_MATRIX_COPIES = 2
RIPS_VALIDATION_BYTES_PER_ENTRY = 1
RIPS_WRAPPER_BYTES_PER_ENTRY = 21
MAX_RIPS_SIMPLEX_RISK = MAX_RIPS_WORKING_BYTES // RIPS_BYTES_PER_SIMPLEX
PERSISTENCE_RATIOS = (0.01, 0.02, 0.05, 0.10, 0.25, 0.50)

RipserResult = dict[str, Any]
RipserCache = MutableMapping[tuple[Any, ...], RipserResult]


def _format_bytes(byte_count: int) -> str:
    if byte_count >= 1024**3:
        return f"{byte_count / (1024**3):.3f} GiB ({byte_count:,} bytes)"
    return f"{byte_count / (1024**2):.2f} MiB ({byte_count:,} bytes)"


def _pairwise_bytes(point_count: int) -> int:
    return point_count * point_count * np.dtype(np.float64).itemsize


def stable_sample_indices(
    keys: list[str],
    *,
    sample_size: int,
    seed: int,
    replicate: int = 0,
) -> np.ndarray:
    if sample_size < 0 or sample_size > len(keys):
        raise ValueError("sample_size must be between zero and the number of keys")
    ranked = sorted(
        range(len(keys)),
        key=lambda index: (
            hashlib.sha256(
                f"{seed}:{replicate}:{keys[index]}".encode("utf-8")
            ).digest(),
            keys[index],
            index,
        ),
    )
    return np.asarray(ranked[:sample_size], dtype=np.int64)


def sample_plan_hash(keys: list[str]) -> str:
    digest = hashlib.sha256()
    for key in keys:
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def pairwise_distance_matrix(
    matrix: np.ndarray,
    *,
    max_bytes: int = MAX_PAIRWISE_BYTES,
) -> np.ndarray:
    if matrix.ndim != 2:
        raise ValueError("distance matrices require a 2D input matrix")
    point_count = int(matrix.shape[0])
    required_bytes = _pairwise_bytes(point_count)
    if required_bytes > max_bytes:
        raise ValueError(
            "exact pairwise distances require "
            f"{_format_bytes(required_bytes)}, above the "
            f"{_format_bytes(max_bytes)} limit; use a bounded TDA profile"
        )
    if point_count == 0:
        return np.zeros((0, 0), dtype=np.float64)
    features = np.asarray(matrix, dtype=np.float64, order="C")
    if not np.isfinite(features).all():
        raise ValueError("pairwise-distance features must be finite")
    squared_norms = np.sum(features * features, axis=1, dtype=np.float64)
    distances = features @ features.T
    distances *= -2.0
    distances += squared_norms[:, None]
    distances += squared_norms[None, :]
    np.maximum(distances, 0.0, out=distances)
    np.sqrt(distances, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def _dense_simplex_risk(point_count: int, maxdim: int) -> int:
    return sum(
        math.comb(point_count, simplex_vertices) for simplex_vertices in range(1, maxdim + 3)
    )


def _rips_budget(
    *,
    point_count: int,
    effective_point_count: int,
    maxdim: int,
    simplex_risk: int,
    edge_count: int | None,
) -> dict[str, int | float | None]:
    distance_matrix_bytes = _pairwise_bytes(point_count)
    estimated_simplex_bytes = simplex_risk * RIPS_BYTES_PER_SIMPLEX
    validation_workspace_bytes = (
        point_count * point_count * RIPS_VALIDATION_BYTES_PER_ENTRY
    )
    wrapper_workspace_bytes = point_count * point_count * RIPS_WRAPPER_BYTES_PER_ENTRY
    estimated_working_bytes = (
        distance_matrix_bytes * RIPS_DISTANCE_MATRIX_COPIES
        + validation_workspace_bytes
        + wrapper_workspace_bytes
        + estimated_simplex_bytes
    )
    return {
        "pointCount": point_count,
        "effectivePointCount": effective_point_count,
        "requestedHomologyDim": maxdim,
        "edgeCount": edge_count,
        "simplexRiskUpperBound": simplex_risk,
        "distanceMatrixBytes": distance_matrix_bytes,
        "estimatedSimplexBytes": estimated_simplex_bytes,
        "validationWorkspaceBytes": validation_workspace_bytes,
        "wrapperWorkspaceBytes": wrapper_workspace_bytes,
        "estimatedWorkingBytes": estimated_working_bytes,
        "maxPairwiseBytes": MAX_PAIRWISE_BYTES,
        "maxWorkingBytes": MAX_RIPS_WORKING_BYTES,
        "bytesPerSimplex": RIPS_BYTES_PER_SIMPLEX,
        "distanceMatrixCopies": RIPS_DISTANCE_MATRIX_COPIES,
        "validationBytesPerEntry": RIPS_VALIDATION_BYTES_PER_ENTRY,
        "wrapperBytesPerEntry": RIPS_WRAPPER_BYTES_PER_ENTRY,
        "maxPointCount": MAX_RIPS_POINTS,
        "maxHomologyDim": MAX_RIPS_HOMOLOGY_DIM,
        "maxSimplexRisk": MAX_RIPS_SIMPLEX_RISK,
    }


def _validate_rips_parameters(
    *,
    point_count: int,
    maxdim: int,
    landmark_count: int | None,
) -> int:
    if point_count < 2:
        raise ValueError("Ripser requires at least two points")
    if not 0 <= maxdim <= MAX_RIPS_HOMOLOGY_DIM:
        raise ValueError(f"maxdim {maxdim} exceeds supported range 0..{MAX_RIPS_HOMOLOGY_DIM}")
    if landmark_count is not None and not 2 <= landmark_count <= point_count:
        raise ValueError("landmark_count must be between 2 and pointCount")
    return landmark_count or point_count


def _enforce_rips_budget(
    budget: dict[str, int | float | None],
    *,
    threshold: float | None,
) -> None:
    point_count = int(budget["pointCount"] or 0)
    estimated_working_bytes = int(budget["estimatedWorkingBytes"] or 0)
    if point_count > MAX_RIPS_POINTS:
        raise ValueError(
            f"Ripser pointCount {point_count} exceeds hard limit {MAX_RIPS_POINTS}; "
            f"estimated working memory is {_format_bytes(estimated_working_bytes)}. "
            "Use a bounded sample"
        )
    if estimated_working_bytes > MAX_RIPS_WORKING_BYTES:
        qualifier = f" at threshold {threshold:.6g}" if threshold is not None else ""
        simplex_risk = int(budget["simplexRiskUpperBound"] or 0)
        raise ValueError(
            f"Ripser simplex-risk upper bound {simplex_risk:,}{qualifier} has estimated "
            f"working memory {_format_bytes(estimated_working_bytes)}, above the "
            f"{_format_bytes(MAX_RIPS_WORKING_BYTES)} limit; reduce points, maxdim, "
            "or threshold"
        )


def preflight_rips_request(
    point_count: int,
    *,
    maxdim: int,
    landmark_count: int | None = None,
) -> dict[str, int | float | None]:
    """Reject a dense Rips job before allocating its pairwise distance matrix."""
    effective_point_count = _validate_rips_parameters(
        point_count=point_count,
        maxdim=maxdim,
        landmark_count=landmark_count,
    )
    simplex_risk = _dense_simplex_risk(effective_point_count, maxdim)
    budget = _rips_budget(
        point_count=point_count,
        effective_point_count=effective_point_count,
        maxdim=maxdim,
        simplex_risk=simplex_risk,
        edge_count=None,
    )
    _enforce_rips_budget(budget, threshold=None)
    return budget


def max_dense_rips_points(maxdim: int) -> int:
    """Largest dense request admitted by the point and working-memory limits."""
    if not 0 <= maxdim <= MAX_RIPS_HOMOLOGY_DIM:
        raise ValueError(f"maxdim must be between 0 and {MAX_RIPS_HOMOLOGY_DIM}, got {maxdim}")
    low = 0
    high = MAX_RIPS_POINTS
    while low < high:
        midpoint = (low + high + 1) // 2
        budget = _rips_budget(
            point_count=midpoint,
            effective_point_count=midpoint,
            maxdim=maxdim,
            simplex_risk=_dense_simplex_risk(midpoint, maxdim),
            edge_count=None,
        )
        if int(budget["estimatedWorkingBytes"] or 0) <= MAX_RIPS_WORKING_BYTES:
            low = midpoint
        else:
            high = midpoint - 1
    return low


def validate_rips_request(
    distances: np.ndarray,
    *,
    maxdim: int,
    threshold: float | None = None,
    landmark_count: int | None = None,
) -> dict[str, int | float | None]:
    """Reject Rips jobs whose point count or estimated working memory is unsafe."""
    matrix = np.asarray(distances, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("Ripser precomputed distances must be a square matrix")
    point_count = int(matrix.shape[0])
    diagonal = np.diag(matrix)
    if not np.isfinite(diagonal).all() or np.count_nonzero(diagonal):
        raise ValueError("Ripser precomputed distances must have a finite zero diagonal")
    validation_batch_size = 512
    for start in range(0, point_count, validation_batch_size):
        stop = min(start + validation_batch_size, point_count)
        block = matrix[start:stop]
        if not np.isfinite(block).all():
            raise ValueError("Ripser precomputed distances must be finite")
        if np.any(block < 0.0):
            raise ValueError("Ripser precomputed distances must be non-negative")
        if not np.allclose(
            block,
            matrix[:, start:stop].T,
            rtol=1e-12,
            atol=1e-12,
        ):
            raise ValueError("Ripser precomputed distances must be symmetric")
    effective_point_count = _validate_rips_parameters(
        point_count=point_count,
        maxdim=maxdim,
        landmark_count=landmark_count,
    )
    if threshold is not None and (not math.isfinite(threshold) or threshold < 0):
        raise ValueError("threshold must be a finite non-negative distance")

    edge_count: int | None = None
    if threshold is None or landmark_count is not None:
        simplex_risk = _dense_simplex_risk(effective_point_count, maxdim)
    else:
        # ripser.py passes the strict lower triangle to DRFDM. Model exactly
        # that edge set, then account for both endpoints when bounding cofaces.
        adjacency = matrix <= threshold
        for row_index in range(point_count):
            adjacency[row_index, row_index:] = False
        edge_count = int(np.count_nonzero(adjacency))
        degrees = np.count_nonzero(adjacency, axis=0) + np.count_nonzero(
            adjacency,
            axis=1,
        )
        simplex_risk = effective_point_count + edge_count
        if maxdim >= 1:
            triangle_upper_bound = (
                sum(int(degree) * (int(degree) - 1) // 2 for degree in degrees) // 3
            )
            simplex_risk += triangle_upper_bound
        if maxdim >= 2:
            tetrahedron_upper_bound = (
                sum(math.comb(int(degree), 3) for degree in degrees if degree >= 3) // 4
            )
            simplex_risk += tetrahedron_upper_bound

    budget = _rips_budget(
        point_count=point_count,
        effective_point_count=effective_point_count,
        maxdim=maxdim,
        simplex_risk=simplex_risk,
        edge_count=edge_count,
    )
    _enforce_rips_budget(budget, threshold=threshold)
    return budget


def run_ripser_precomputed(
    distances: np.ndarray,
    *,
    maxdim: int,
    threshold: float | None = None,
    landmark_count: int | None = None,
    do_cocycles: bool = False,
    coeff: int = 2,
    cache: RipserCache | None = None,
    cache_key: str | None = None,
    runner: Callable[..., RipserResult] | None = None,
) -> tuple[RipserResult, dict[str, int | float | None]]:
    """Run bounded Ripser once per immutable distance object and parameter tuple."""
    budget = validate_rips_request(
        distances,
        maxdim=maxdim,
        threshold=threshold,
        landmark_count=landmark_count,
    )
    resolved_landmark_count = (
        landmark_count
        if landmark_count is not None and landmark_count < distances.shape[0]
        else None
    )
    resolved_key = (
        cache_key,
        id(distances),
        maxdim,
        threshold,
        resolved_landmark_count,
        do_cocycles,
        coeff,
    )
    if cache is not None and cache_key is not None and resolved_key in cache:
        return cache[resolved_key], budget

    if runner is None:
        from ripser import ripser

        runner = ripser
    kwargs: dict[str, Any] = {
        "maxdim": maxdim,
        "distance_matrix": True,
        "do_cocycles": do_cocycles,
        "coeff": coeff,
    }
    if threshold is not None:
        kwargs["thresh"] = threshold
    if resolved_landmark_count is not None:
        kwargs["n_perm"] = resolved_landmark_count
    # ripser.py treats the strict lower triangle as authoritative. Mirror that
    # triangle so its optional landmark selection and returned matrix see the
    # same metric that DRFDM consumes.
    canonical_distances = np.array(distances, dtype=np.float64, order="C", copy=True)
    for column_index in range(1, canonical_distances.shape[0]):
        canonical_distances[:column_index, column_index] = canonical_distances[
            column_index,
            :column_index,
        ]
    result = runner(canonical_distances, **kwargs)
    if cache is not None and cache_key is not None:
        cache[resolved_key] = result
    return result, budget


def upper_triangle(distances: np.ndarray) -> np.ndarray:
    if distances.ndim != 2 or distances.shape[0] != distances.shape[1]:
        raise ValueError("upper-triangle extraction requires a square matrix")
    if distances.shape[0] < 2:
        return np.zeros((0,), dtype=np.float64)
    return distances[np.triu_indices(distances.shape[0], k=1)]


def distance_scale(
    pairwise: np.ndarray,
    *,
    quantile: float = 0.95,
) -> tuple[float, str]:
    values = np.asarray(pairwise, dtype=np.float64)
    if values.size:
        robust_value = float(np.quantile(values, quantile))
        if math.isfinite(robust_value) and robust_value > 0:
            return robust_value, f"pairwise_q{quantile:.3f}"
        max_value = float(np.max(values))
        if math.isfinite(max_value) and max_value > 0:
            return max_value, "pairwise_max_nonzero_fallback"
    return 1.0, "unit_degenerate_fallback"


def exact_betti_events(
    diagram: np.ndarray,
    *,
    max_scale: float | None = None,
) -> tuple[list[float], list[int]]:
    """Evaluate Betti numbers at every filtration event, where intervals are [birth, death)."""
    array = np.asarray(diagram, dtype=np.float64)
    if array.size == 0:
        return [], []
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError("persistence diagrams must have shape (n, 2)")

    births: dict[float, int] = {}
    deaths: dict[float, int] = {}
    for birth, death in array:
        birth_value = float(birth)
        if max_scale is None or birth_value <= max_scale:
            births[birth_value] = births.get(birth_value, 0) + 1
        if math.isfinite(float(death)):
            death_value = float(death)
            if max_scale is None or death_value <= max_scale:
                deaths[death_value] = deaths.get(death_value, 0) + 1

    events = sorted(set(births) | set(deaths))
    if max_scale is not None and (not events or events[-1] < max_scale):
        events.append(float(max_scale))
    alive = 0
    betti: list[int] = []
    for scale in events:
        # Deaths at scale are excluded while births at scale are included.
        alive += births.get(scale, 0) - deaths.get(scale, 0)
        betti.append(alive)
    return events, betti


def peak_betti(curves: list[dict[str, Any]], dimension: int = 1) -> dict[str, Any] | None:
    if dimension >= len(curves):
        return None
    curve = curves[dimension]
    values = curve.get("betti")
    scales = curve.get("scale")
    if not isinstance(values, list) or not values:
        return None
    if not isinstance(scales, list) or len(scales) != len(values):
        return None
    index = max(range(len(values)), key=values.__getitem__)
    out = {"count": int(values[index]), "scale": float(scales[index])}
    normalized = curve.get("scaleNormalized")
    if isinstance(normalized, list) and len(normalized) == len(values):
        out["scaleNormalized"] = float(normalized[index])
    return out


def diagram_summary(
    diagrams: list[np.ndarray],
    *,
    distance_scale: float,
    scale_kind: str,
    censor_at: float | None = None,
) -> dict[str, Any]:
    """Serialize diagrams and exact Betti event curves against an explicit metric scale."""
    if not math.isfinite(distance_scale) or distance_scale <= 0:
        distance_scale = 1.0
        scale_kind = f"{scale_kind}_degenerate_unit_fallback"
    finite_deaths = [
        float(death)
        for diagram in diagrams
        for death in np.asarray(diagram)[:, 1]
        if math.isfinite(float(death))
    ]
    scale_max = max([distance_scale, *finite_deaths])
    curve_max = min(scale_max, censor_at) if censor_at is not None else scale_max

    summaries: list[dict[str, Any]] = []
    json_diagrams: list[list[dict[str, Any]]] = []
    betti_curves: list[dict[str, Any]] = []
    for dimension, raw_diagram in enumerate(diagrams):
        diagram = np.asarray(raw_diagram, dtype=np.float64)
        entries: list[dict[str, Any]] = []
        persistences: list[float] = []
        essential_count = 0
        censored_count = 0
        for birth_raw, death_raw in diagram.tolist():
            birth = float(birth_raw)
            finite_death = None if math.isinf(death_raw) else float(death_raw)
            right_censored = finite_death is None and censor_at is not None
            persistence = None if finite_death is None else finite_death - birth
            lower_bound = persistence
            if right_censored and censor_at is not None:
                lower_bound = max(0.0, float(censor_at) - birth)
            if persistence is not None:
                persistences.append(persistence)
            elif right_censored:
                censored_count += 1
            else:
                essential_count += 1
            entries.append(
                {
                    "birth": birth,
                    "death": finite_death,
                    "persistence": persistence,
                    "persistenceNormalized": (
                        persistence / distance_scale if persistence is not None else None
                    ),
                    "persistenceLowerBound": lower_bound,
                    "persistenceLowerBoundNormalized": (
                        lower_bound / distance_scale if lower_bound is not None else None
                    ),
                    "rightCensored": right_censored,
                }
            )
        persistences.sort(reverse=True)
        event_scale, event_betti = exact_betti_events(diagram, max_scale=curve_max)
        json_diagrams.append(entries)
        betti_curves.append(
            {
                "dimension": dimension,
                "evaluation": "exact_filtration_events",
                "scale": event_scale,
                "scaleNormalized": [value / distance_scale for value in event_scale],
                "betti": event_betti,
            }
        )
        summaries.append(
            {
                "dimension": dimension,
                "featureCount": len(entries),
                "essentialCount": essential_count,
                "rightCensoredCount": censored_count,
                "topPersistence": persistences[:8],
                "topPersistenceNormalized": [
                    value / distance_scale for value in persistences[:8]
                ],
            }
        )
    return {
        "scaleMax": scale_max,
        "scaleReference": {"kind": scale_kind, "value": distance_scale},
        "censorAt": censor_at,
        "summaries": summaries,
        "diagrams": json_diagrams,
        "bettiCurves": betti_curves,
    }


def persistence_threshold_bounds(
    diagrams: list[list[dict[str, Any]]],
    *,
    dimension: int = 1,
    ratios: tuple[float, ...] = PERSISTENCE_RATIOS,
) -> dict[str, dict[str, int]]:
    if dimension >= len(diagrams):
        return {}
    entries = diagrams[dimension]
    out: dict[str, dict[str, int]] = {}
    for ratio in ratios:
        certain = 0
        possible = 0
        for entry in entries:
            value = entry.get("persistenceNormalized")
            lower_bound = entry.get("persistenceLowerBoundNormalized")
            censored = bool(entry.get("rightCensored"))
            if isinstance(value, (int, float)):
                if float(value) >= ratio:
                    certain += 1
                    possible += 1
            elif censored:
                possible += 1
                if isinstance(lower_bound, (int, float)) and float(lower_bound) >= ratio:
                    certain += 1
        out[f">={ratio:.3f}"] = {"certain": certain, "possible": possible}
    return out


def persistence_threshold_counts(
    diagrams: list[list[dict[str, Any]]],
    *,
    dimension: int = 1,
    ratios: tuple[float, ...] = PERSISTENCE_RATIOS,
) -> dict[str, int]:
    bounds = persistence_threshold_bounds(diagrams, dimension=dimension, ratios=ratios)
    return {key: value["certain"] for key, value in bounds.items()}


def normalized_bottleneck_distance(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    left_scale: float,
    right_scale: float,
) -> float:
    """Bottleneck distance after each diagram is normalized by its declared metric scale."""
    import gudhi

    def finite(entries: list[dict[str, Any]], scale: float) -> np.ndarray:
        rows = [
            [float(entry["birth"]) / scale, float(entry["death"]) / scale]
            for entry in entries
            if entry.get("death") is not None and not entry.get("rightCensored", False)
        ]
        return np.asarray(rows, dtype=np.float64).reshape((-1, 2))

    if left_scale <= 0 or right_scale <= 0:
        raise ValueError("diagram scales must be positive")
    return float(
        gudhi.bottleneck_distance(
            finite(left, left_scale),
            finite(right, right_scale),
        )
    )
