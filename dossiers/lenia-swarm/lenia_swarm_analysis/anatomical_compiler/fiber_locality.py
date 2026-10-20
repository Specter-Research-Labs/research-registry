"""How much of a Flow Lenia rule does the grown body pin down?

For a cohort of rules sampled at random, each with the body it grew, the inverse-locality
ratio at k is the mean rule distance between a rule and the k rules whose bodies are
nearest to its own, divided by the mean rule distance between random pairs. A ratio of 1
means bodies say nothing about rules; a ratio well below 1 means nearby bodies come from
nearby rules. The rule floor, the same ratio for the k nearest rules themselves, is the
lowest value a body could reach at the cohort's sampling density. The same neighbour sets give the rule spread as a function of body radius,
the share of each rule invariant that the body predicts, and the local participation ratio
of the rule scatter. TwoNN and MLE estimate the intrinsic dimensions of the two clouds.

Rules are compared in three coordinate systems, all in units of each parameter's sampling
range: raw (kernels in the order the engine wires them), canonical (the engine's
kernel_permutation_sort_v1 descriptor, which sorts all kernels together regardless of which
channels they connect) and quotient (the exact minimum over kernel permutations within each
source-target block and over channel relabelings that preserve the connectivity, the true
symmetry of the rule).

The track-1 loader pairs each harvest's current results with the archived results it
replaced, seed by seed, and reads the body from the common_morphology_v1 observations in
the frozen May frame.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import tarfile
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from scipy.spatial import KDTree

from lenia_swarm_analysis._io import read_json, write_json
from lenia_swarm_analysis.morphospace.common_morphology import AXIS_IDS
from lenia_swarm_analysis.morphospace.track1_common_morphology import (
    COMPACT_BODY_COMPONENTS,
    COMPACT_BODY_FRACTION,
    load_frame,
)
from lenia_swarm_analysis.morphospace.track1_spec import track1_family_metadata

CORRECTED_ENGINE_SHA256 = "060e90a71ec10199ccbf8af466306b0cd35679f118c6a332c717dca96c15de3c"
CORRECTED_METALLIB_SHA256 = "cad60789bcc44ace33cfd3f78f63579f384baad5fd7db34acd4f0b26f46e0f45"
KERNEL_FIELDS = ("r", "m", "s", "h", "b", "w", "a")
KERNEL_WIDTH = 13
LOCALITY_KS = (1, 2, 5, 8, 10, 20, 50, 100)
DENSITY_K = 20
PINNING_K = 10
FIBER_K = 15
METRICS = ("raw", "canonical", "quotient")
ERAS = ("archived", "current")
INVARIANTS = ("R", "mean_r", "mean_m", "mean_s", "mean_h", "std_m", "std_s", "mean_a", "mean_b",
              "mean_w")


@dataclass(frozen=True)
class Symmetry:
    """Kernel blocks per (source, target) channel pair, in engine order, and the channel
    relabelings that map the connectivity onto itself."""

    blocks: dict[tuple[int, int], np.ndarray]
    relabelings: tuple[tuple[int, ...], ...]

    @classmethod
    def from_connectivity(cls, connectivity: list[list[int]]) -> Symmetry:
        channels = len(connectivity)
        blocks: dict[tuple[int, int], np.ndarray] = {}
        index = 0
        for source in range(channels):
            for target in range(channels):
                count = connectivity[source][target]
                if count:
                    blocks[(source, target)] = np.arange(index, index + count)
                index += count
        relabelings = tuple(
            p for p in itertools.permutations(range(channels))
            if all(connectivity[p[s]][p[t]] == connectivity[s][t]
                   for s in range(channels) for t in range(channels)))
        return cls(blocks, relabelings)


@dataclass
class Cohort:
    keys: np.ndarray
    raw: np.ndarray
    canonical: np.ndarray
    shape: np.ndarray
    motion: np.ndarray
    compact: np.ndarray

    def take(self, index: np.ndarray) -> Cohort:
        return Cohort(self.keys[index], self.raw[index], self.canonical[index], self.shape[index],
                      self.motion[index], self.compact[index])

    def __len__(self) -> int:
        return int(self.keys.shape[0])


def quotient_distance(a: np.ndarray, b: np.ndarray, symmetry: Symmetry) -> np.ndarray:
    """Exact rule distance up to the rule's symmetry for row-paired raw unit vectors.

    Invariant: the last column is R, shared by all kernels; kernel k occupies columns
    k*KERNEL_WIDTH to (k+1)*KERNEL_WIDTH. Blocks are small (at most 5 kernels), so every
    within-block permutation is enumerated instead of solving an assignment problem."""
    pairs = a.shape[0]
    ka = a[:, :-1].reshape(pairs, -1, KERNEL_WIDTH)
    kb = b[:, :-1].reshape(pairs, -1, KERNEL_WIDTH)
    best = np.full(pairs, np.inf)
    perms = {n: np.asarray(list(itertools.permutations(range(n))))
             for n in {len(v) for v in symmetry.blocks.values()}}
    for relabel in symmetry.relabelings:
        total = np.zeros(pairs)
        for (source, target), index in symmetry.blocks.items():
            other = symmetry.blocks[(relabel[source], relabel[target])]
            cost = ((ka[:, index, None, :] - kb[:, None, other, :]) ** 2).sum(-1)
            p = perms[len(index)]
            total += cost[:, np.arange(len(index))[None, :], p].sum(-1).min(axis=1)
        best = np.minimum(best, total)
    return np.sqrt(best + (a[:, -1] - b[:, -1]) ** 2)


def rule_distance(cohort: Cohort, i: np.ndarray, j: np.ndarray, metric: str,
                  symmetry: Symmetry, chunk: int = 20000) -> np.ndarray:
    rules = cohort.canonical if metric == "canonical" else cohort.raw
    out = np.empty(i.shape[0])
    for start in range(0, i.shape[0], chunk):
        a = rules[i[start:start + chunk]].astype(np.float64)
        b = rules[j[start:start + chunk]].astype(np.float64)
        out[start:start + chunk] = (quotient_distance(a, b, symmetry) if metric == "quotient"
                                    else np.linalg.norm(a - b, axis=1))
    return out


def phenotype_neighbours(phenotype: np.ndarray, anchors: np.ndarray, k: int) -> tuple[np.ndarray,
                                                                                       np.ndarray]:
    """k nearest other bodies of each anchor. The query asks for k+1 and drops the anchor
    itself, or the farthest hit when ties with identical bodies pushed the anchor out."""
    distance, index = KDTree(phenotype).query(phenotype[anchors], k=k + 1, workers=-1)
    keep = index != anchors[:, None]
    keep[keep.all(axis=1), -1] = False
    return index[keep].reshape(-1, k), distance[keep].reshape(-1, k)


def _bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, draws: int = 400
                       ) -> list[float]:
    means = values[rng.integers(0, values.shape[0], (draws, values.shape[0]))].mean(axis=1)
    return [float(q) for q in np.quantile(means, [0.025, 0.975])]


def locality(cohort: Cohort, phenotype: np.ndarray, anchors: np.ndarray, metrics: tuple[str, ...],
             symmetry: Symmetry, rng: np.random.Generator, random_pairs: int = 100000
             ) -> dict[str, Any]:
    """Inverse-locality ratio at each k in LOCALITY_KS, its rule-distance denominator from
    random pairs, the median body radius at each k and the per-anchor values used for
    paired comparisons."""
    kmax = max(LOCALITY_KS)
    index, radius = phenotype_neighbours(phenotype, anchors, kmax)
    i = rng.integers(0, len(cohort), random_pairs)
    j = rng.integers(0, len(cohort), random_pairs)
    j = np.where(i == j, (j + 1) % len(cohort), j)
    out: dict[str, Any] = {"anchors": int(anchors.shape[0]),
                           "radius_median": {str(k): float(np.median(radius[:, k - 1]))
                                             for k in LOCALITY_KS}}
    for metric in metrics:
        denominator = float(rule_distance(cohort, i, j, metric, symmetry).mean())
        d = rule_distance(cohort, np.repeat(anchors, kmax), index.ravel(), metric,
                          symmetry).reshape(-1, kmax) / denominator
        cumulative = np.cumsum(d, axis=1) / np.arange(1, kmax + 1)
        out[metric] = {
            "random_pair_distance": denominator,
            "ratio": {str(k): float(cumulative[:, k - 1].mean()) for k in LOCALITY_KS},
            "ci": {str(k): _bootstrap_mean_ci(cumulative[:, k - 1], rng) for k in LOCALITY_KS},
            "per_anchor": cumulative,
        }
    out["radius_per_anchor"] = radius
    return out


def rule_floor(cohort: Cohort, anchors: np.ndarray, metric: str, chunk: int = 128) -> np.ndarray:
    """Cumulative mean rule distance from each anchor to its k nearest other rules, k up to
    max(LOCALITY_KS). Divided by the random-pair distance it is the smallest inverse-locality
    ratio any body could reach in this cohort, because no k rules lie closer to the anchor.
    The quotient metric has no floor here because its nearest rules need all-pairs quotient
    distances."""
    kmax = max(LOCALITY_KS)
    rules = (cohort.canonical if metric == "canonical" else cohort.raw).astype(np.float64)
    squared = (rules ** 2).sum(axis=1)
    nearest = np.empty((anchors.shape[0], kmax))
    for start in range(0, anchors.shape[0], chunk):
        a = anchors[start:start + chunk]
        d2 = squared[a, None] + squared[None, :] - 2.0 * rules[a] @ rules.T
        d2[np.arange(a.shape[0]), a] = np.inf
        part = np.sort(np.partition(d2, kmax - 1, axis=1)[:, :kmax], axis=1)
        nearest[start:start + a.shape[0]] = np.sqrt(np.maximum(part, 0.0))
    return np.cumsum(nearest, axis=1) / np.arange(1, kmax + 1)


def _floor_ratios(cohort: Cohort, anchors: np.ndarray, result: dict[str, Any]) -> dict[str, Any]:
    """Rule floor per k on the anchors of a locality result, over that result's random-pair
    distance so that the floor and the ratio share one denominator."""
    out: dict[str, Any] = {}
    for metric in ("raw", "canonical"):
        if metric in result:
            floor = rule_floor(cohort, anchors, metric).mean(axis=0)
            out[metric] = {str(k): float(floor[k - 1] / result[metric]["random_pair_distance"])
                           for k in LOCALITY_KS}
    return out


def density_deciles(per_anchor: np.ndarray, radius: np.ndarray, k: int) -> list[dict[str, float]]:
    """Ratio at k within each decile of local body density (radius to the DENSITY_K-th
    neighbour), so dense and sparse regions of the body space are compared separately."""
    r = radius[:, DENSITY_K - 1]
    edges = np.quantile(r, np.linspace(0.0, 1.0, 11))
    decile = np.clip(np.searchsorted(edges, r, side="right") - 1, 0, 9)
    return [{"decile": d, "radius_k20_median": float(np.median(r[decile == d])),
             "ratio": float(per_anchor[decile == d, k - 1].mean())} for d in range(10)]


def invariants(raw: np.ndarray) -> np.ndarray:
    """Rule summaries unchanged by every kernel permutation and channel relabeling."""
    kernels = raw[:, :-1].reshape(raw.shape[0], -1, KERNEL_WIDTH).astype(np.float64)
    return np.stack([raw[:, -1], kernels[:, :, 0].mean(1), kernels[:, :, 1].mean(1),
                     kernels[:, :, 2].mean(1), kernels[:, :, 3].mean(1), kernels[:, :, 1].std(1),
                     kernels[:, :, 2].std(1), kernels[:, :, 10:13].mean((1, 2)),
                     kernels[:, :, 4:7].mean((1, 2)), kernels[:, :, 7:10].mean((1, 2))], axis=1)


def coordinate_names(kernels: int) -> list[str]:
    fields = [f for f in KERNEL_FIELDS for _ in range(3 if f in ("a", "b", "w") else 1)]
    index = [i for f in KERNEL_FIELDS for i in (range(3) if f in ("a", "b", "w") else [0])]
    return [f"k{k}.{f}{i if f in ('a', 'b', 'w') else ''}" for k in range(kernels)
            for f, i in zip(fields, index, strict=True)] + ["R"]


def pinning(cohort: Cohort, phenotype: np.ndarray, anchors: np.ndarray, top: int = 12
            ) -> dict[str, Any]:
    """Share of the variance of each rule invariant, and of each raw coordinate, predicted by
    the mean over the PINNING_K nearest bodies. With no information the expected value is
    -1/PINNING_K; bits are the Gaussian-equivalent information -log2(1 - R2)/2."""
    index, _ = phenotype_neighbours(phenotype, anchors, PINNING_K)

    def r2(x: np.ndarray) -> np.ndarray:
        return 1.0 - ((x[anchors] - x[index].mean(axis=1)) ** 2).mean(axis=0) / x.var(axis=0)

    inv = r2(invariants(cohort.raw))
    coords = r2(cohort.raw.astype(np.float64))
    names = coordinate_names((cohort.raw.shape[1] - 1) // KERNEL_WIDTH)
    order = np.argsort(coords)[::-1][:top]
    return {
        "null": -1.0 / PINNING_K,
        "invariants": {n: float(v) for n, v in zip(INVARIANTS, inv, strict=True)},
        "invariant_bits": {n: float(-0.5 * np.log2(1.0 - max(v, 0.0)))
                           for n, v in zip(INVARIANTS, inv, strict=True)},
        "coordinates_top": {names[i]: float(coords[i]) for i in order},
        "coordinates_above_0.05": int((coords > 0.05).sum()),
        "coordinates": int(coords.shape[0]),
    }


def _participation_ratio(matrix: np.ndarray) -> float:
    eigenvalues = np.linalg.svd(matrix - matrix.mean(axis=0), compute_uv=False) ** 2
    return float(eigenvalues.sum() ** 2 / (eigenvalues ** 2).sum())


def local_fiber_dimension(cohort: Cohort, phenotype: np.ndarray, anchors: np.ndarray,
                          rng: np.random.Generator) -> dict[str, float]:
    """Participation ratio of the raw rule scatter among each anchor's FIBER_K body
    neighbours, against the same statistic for FIBER_K random rules."""
    index, _ = phenotype_neighbours(phenotype, anchors, FIBER_K)
    rules = cohort.raw.astype(np.float64)
    near = np.mean([_participation_ratio(rules[row]) for row in index])
    random = np.mean([_participation_ratio(rules[rng.choice(len(cohort), FIBER_K, replace=False)])
                      for _ in range(anchors.shape[0])])
    return {"neighbours": float(near), "random": float(random)}


def _distinct(matrix: np.ndarray) -> np.ndarray:
    return np.unique(matrix, axis=0)


def _sorted_distances(matrix: np.ndarray, k: int) -> np.ndarray:
    distance, _ = KDTree(matrix).query(matrix, k=k + 1, workers=-1)
    if np.any(distance[:, 1] <= 0.0):
        raise ValueError("duplicate points; pass distinct rows")
    return distance[:, 1:]


def twonn(matrix: np.ndarray, discard: float = 0.1) -> float:
    """TwoNN (Facco et al. 2017): log(r2/r1) is exponential with rate equal to the intrinsic
    dimension; fit -log(1-F) against log(mu) through the origin without the top tail."""
    distance = _sorted_distances(matrix, 2)
    mu = np.sort(distance[:, 1] / distance[:, 0])
    n = mu.shape[0]
    keep = int(round(n * (1.0 - discard)))
    x = np.log(mu[:keep])
    y = -np.log1p(-np.arange(1, n + 1)[:keep] / n)
    return float((x * y).sum() / (x * x).sum())


def mle_dimension(matrix: np.ndarray, k1: int = 10, k2: int = 20) -> float:
    """Levina-Bickel MLE with MacKay-Ghahramani averaging over points and over k1..k2."""
    distance = _sorted_distances(matrix, k2)
    inverse = [np.log(distance[:, k - 1:k] / distance[:, :k - 1]).sum(axis=1) / (k - 1)
               for k in range(k1, k2 + 1)]
    return float(1.0 / np.mean(inverse))


def dimensions(cohort: Cohort, phenotypes: dict[str, np.ndarray], sample: np.ndarray
               ) -> dict[str, Any]:
    clouds = {"rule": cohort.raw[sample].astype(np.float64),
              **{name: p[sample] for name, p in phenotypes.items()}}
    out: dict[str, Any] = {}
    for name, cloud in clouds.items():
        distinct = _distinct(cloud)
        out[name] = {"points": int(distinct.shape[0]), "duplicates": int(cloud.shape[0]
                                                                          - distinct.shape[0]),
                     "twonn": twonn(distinct), "mle": mle_dimension(distinct)}
    return out


def _strip(result: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in result.items() if k != "radius_per_anchor"}
    for metric in METRICS:
        if metric in out:
            out[metric] = {k: v for k, v in out[metric].items() if k != "per_anchor"}
    return out


def analyze_cohort(cohort: Cohort, symmetry: Symmetry, scale: np.ndarray, *, quotient_anchors: int,
                   dimension_sample: int, rng: np.random.Generator) -> dict[str, Any]:
    phenotypes = {"shape": cohort.shape,
                  "shape_motion": np.concatenate([cohort.shape, cohort.motion / scale], axis=1)}
    everyone = np.arange(len(cohort))
    sub = np.sort(rng.choice(len(cohort), min(quotient_anchors, len(cohort)), replace=False))
    dims = np.sort(rng.choice(len(cohort), min(dimension_sample, len(cohort)), replace=False))
    out: dict[str, Any] = {"rows": len(cohort), "compact_rows": int(cohort.compact.sum())}
    for name, phenotype in phenotypes.items():
        full = locality(cohort, phenotype, everyone, ("raw", "canonical"), symmetry, rng)
        subsample = locality(cohort, phenotype, sub, METRICS, symmetry, rng)
        if name == "shape":
            out["rule_floor"] = _floor_ratios(cohort, sub, subsample)
        out[name] = {
            "all_anchors": _strip(full),
            "anchor_subsample": _strip(subsample),
            "density_deciles_k5_raw": density_deciles(full["raw"]["per_anchor"],
                                                      full["radius_per_anchor"], 5),
            "pinning": pinning(cohort, phenotype, everyone),
            "local_fiber_dimension": local_fiber_dimension(cohort, phenotype, sub[:2000], rng),
        }
    out["dimensions"] = dimensions(cohort, phenotypes, dims)
    return out


def paired_eras(cohorts: dict[str, Cohort], symmetry: Symmetry, scale: np.ndarray,
                rng: np.random.Generator) -> dict[str, Any]:
    """Locality on the genotypes present in both eras' cohorts, anchor by anchor, so the
    engine correction is the only difference."""
    common = np.intersect1d(cohorts["archived"].keys, cohorts["current"].keys)
    paired = {era: c.take(np.searchsorted(c.keys, common)) for era, c in cohorts.items()}
    out: dict[str, Any] = {"genotypes": int(common.shape[0])}
    for name in ("shape", "shape_motion"):
        per: dict[str, Any] = {}
        for era, c in paired.items():
            p = c.shape if name == "shape" else np.concatenate([c.shape, c.motion / scale], axis=1)
            per[era] = locality(c, p, np.arange(len(c)), ("raw",), symmetry, rng)
        diff = per["current"]["raw"]["per_anchor"] - per["archived"]["raw"]["per_anchor"]
        out[name] = {
            **{era: {str(k): v for k, v in per[era]["raw"]["ratio"].items()} for era in per},
            "current_minus_archived": {str(k): float(diff[:, k - 1].mean()) for k in LOCALITY_KS},
            "current_minus_archived_ci": {str(k): _bootstrap_mean_ci(diff[:, k - 1], rng)
                                          for k in LOCALITY_KS},
            "anchor_correlation_k5": float(np.corrcoef(per["current"]["raw"]["per_anchor"][:, 4],
                                                       per["archived"]["raw"]["per_anchor"][:, 4])
                                           [0, 1]),
        }
    return out


def matched_size(cohorts: dict[str, Cohort], symmetry: Symmetry, n: int, compact: bool,
                 rng: np.random.Generator) -> dict[str, Any]:
    """Shape locality per era on equal-size random subsets, because a kNN ratio depends on
    how densely the body space is sampled."""
    out: dict[str, Any] = {"n": n, "compact_only": compact}
    for era, cohort in cohorts.items():
        pool = np.flatnonzero(cohort.compact) if compact else np.arange(len(cohort))
        if pool.shape[0] < n:
            raise ValueError(f"{era}: {pool.shape[0]} rows, fewer than the matched size {n}")
        sub = cohort.take(np.sort(rng.choice(pool, n, replace=False)))
        result = locality(sub, sub.shape, np.arange(n), ("raw", "quotient"), symmetry, rng)
        out[era] = {**_strip(result), "rule_floor": _floor_ratios(sub, np.arange(n), result),
                    "pinning": pinning(sub, sub.shape, np.arange(n))}
    return out


def _kernel_units(params: dict[str, Any], ranges: dict[str, list[float]]) -> np.ndarray:
    kernels = len(params["r"])
    rows = np.empty((kernels, KERNEL_WIDTH))
    for k in range(kernels):
        values: list[float] = []
        for field in KERNEL_FIELDS:
            lo, hi = ranges[field]
            raw = params[field][k]
            items = raw if isinstance(raw, list) else [raw]
            values.extend((float(v) - lo) / (hi - lo) for v in items)
        rows[k] = values
    return rows


def _rule_vectors(row: dict[str, Any], ranges: dict[str, list[float]]) -> tuple[np.ndarray,
                                                                               np.ndarray]:
    """Raw and canonical unit vectors. The canonical order is recovered by matching the
    stored descriptor's kernels to the params kernels, which fails loudly if they differ."""
    params = row["params"]
    raw_kernels = _kernel_units(params, ranges)
    lo, hi = ranges["R"]
    r_unit = (float(params["R"]) - lo) / (hi - lo)
    stored = np.asarray(row["descriptor_bundle"]["genotype"]["vector"], dtype=np.float32)
    stored_kernels = stored[:-1].reshape(-1, KERNEL_WIDTH)
    param_kernels = np.asarray([[v for f in KERNEL_FIELDS for v in (
        params[f][k] if isinstance(params[f][k], list) else [params[f][k]])]
        for k in range(len(params["r"]))], dtype=np.float32)
    order_stored = np.lexsort(stored_kernels.T[::-1])
    order_params = np.lexsort(param_kernels.T[::-1])
    perm = np.empty_like(order_stored)
    perm[order_stored] = order_params
    if not np.array_equal(param_kernels[perm], stored_kernels) or stored[-1] != np.float32(
            params["R"]):
        raise SystemExit(f"seed {row['seed']}: genotype descriptor is not a kernel permutation "
                         "of params")
    raw = np.append(raw_kernels.ravel(), r_unit)
    canonical = np.append(raw_kernels[perm].ravel(), r_unit)
    return raw, canonical


def _archived_lines(archive_dir: Path, run_id: str) -> Iterator[bytes]:
    member = f"{run_id}/results.jsonl"
    process = subprocess.Popen(["zstd", "-dc", str(archive_dir / f"{run_id}.tar.zst")],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if process.stdout is None:
        raise SystemExit(f"{run_id}: zstd produced no output stream")
    found = False
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        for info in archive:
            if info.name == member:
                handle = archive.extractfile(info)
                if handle is None:
                    raise SystemExit(f"{archive_dir}: {member} is not a regular file")
                found = True
                yield from handle
                break
    process.stdout.close()
    process.wait()
    if not found:
        raise SystemExit(f"{archive_dir}: {member} not in archive")


def _read_rules(lines: Iterator[bytes], ranges: dict[str, list[float]]) -> dict[str, np.ndarray]:
    seeds, hashes, raws, canonicals, speeds = [], [], [], [], []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        raw, canonical = _rule_vectors(row, ranges)
        seeds.append(int(row["seed"]))
        hashes.append(row["descriptor_bundle"]["genotype"]["hash12"])
        raws.append(raw)
        canonicals.append(canonical)
        speeds.append(float(row["metrics"]["speed_mean"]))
    return {"seed": np.asarray(seeds, dtype=np.int64), "hash12": np.asarray(hashes),
            "raw": np.asarray(raws, dtype=np.float32),
            "canonical": np.asarray(canonicals, dtype=np.float32),
            "speed_mean": np.asarray(speeds)}


def _load_run(args: tuple[Path, Path, str]) -> dict[str, dict[str, np.ndarray]]:
    run_root, archive_dir, run_id = args
    ranges = read_json(run_root / run_id / "config.json")["params"]["ranges"]
    with (run_root / run_id / "results.jsonl").open("rb") as handle:
        current = _read_rules(handle, ranges)
    return {"current": current, "archived": _read_rules(_archived_lines(archive_dir, run_id), ranges)}


def verified_runs(verification_dir: Path) -> tuple[list[str], dict[str, str]]:
    """Runs the regeneration check found complete, regenerated and bitwise reproduced on the
    corrected engine; every other run is excluded with its reason."""
    plan = read_json(verification_dir / "plan.json")["inputs"]["engine"]
    if plan["sha256"] != CORRECTED_ENGINE_SHA256 or not plan["metallib"].endswith(
            CORRECTED_METALLIB_SHA256):
        raise SystemExit(f"{verification_dir}: verification engine is not the corrected build")
    included: list[str] = []
    excluded: dict[str, str] = {}
    for line in (verification_dir / "verification.jsonl").read_text().splitlines():
        row = json.loads(line)
        reasons = [name for name, ok in (
            ("incomplete", row["complete"]), ("not replay-exact", row["replay"]["exact"]),
            ("not regenerated", row["provenance"]["resultsDifferFromArchive"])) if not ok]
        if reasons:
            excluded[row["runId"]] = ", ".join(reasons)
        else:
            included.append(row["runId"])
    return included, excluded


def load_family(run_root: Path, archive_dir: Path, run_ids: list[str], observations: Path,
                frame: dict[str, tuple[float, float]], jobs: int) -> tuple[dict[str, Cohort],
                                                                           dict[str, Any]]:
    """Both eras of one family as cohorts of bodies that passed the harvest filters and have
    an observation. A (run, seed) with more than one row in either era is dropped from both
    eras and counted, because its pairing is ambiguous."""
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        loaded = list(pool.map(_load_run, [(run_root, archive_dir, r) for r in run_ids]))
    con = duckdb.connect()
    axes = ", ".join(AXIS_IDS)
    ids = ", ".join(f"'{r}'" for r in run_ids)
    obs = con.execute(f"""
        SELECT run_id, seed, era, {axes}, displacement, has_observation AND filters_passed,
               harvest_largest_component_fraction >= {COMPACT_BODY_FRACTION}
               AND harvest_component_count <= {COMPACT_BODY_COMPONENTS}
        FROM read_parquet('{observations}') WHERE run_id IN ({ids})""").fetchnumpy()
    centre = np.asarray([frame[a][0] for a in AXIS_IDS])
    width = np.asarray([frame[a][1] for a in AXIS_IDS])
    run_index = {r: i for i, r in enumerate(run_ids)}
    obs_key = np.asarray([run_index[r] for r in obs["run_id"]], dtype=np.int64) * 2**32 + obs["seed"]
    usable_col = list(obs)[-2]
    compact_col = list(obs)[-1]
    eras: dict[str, dict[str, np.ndarray]] = {}
    for era in ERAS:
        parts = [run[era] for run in loaded]
        key = np.concatenate([run_index[r] * 2**32 + p["seed"] for r, p in zip(run_ids, parts,
                                                                              strict=True)])
        eras[era] = {"key": key, **{f: np.concatenate([p[f] for p in parts])
                                    for f in ("hash12", "raw", "canonical", "speed_mean")}}
    duplicated = np.union1d(*[np.unique(e["key"])[np.unique(e["key"], return_counts=True)[1] > 1]
                              for e in eras.values()])
    common, ia, ic = np.intersect1d(eras["archived"]["key"], eras["current"]["key"],
                                    return_indices=True)
    same = eras["archived"]["hash12"][ia] == eras["current"]["hash12"][ic]
    mismatched = np.setdiff1d(common[~same], duplicated)
    report: dict[str, Any] = {"duplicateKeys": int(duplicated.shape[0]),
                              "archivedGenotypeMismatches": int(mismatched.shape[0]),
                              "cohortRows": {}}
    cohorts: dict[str, Cohort] = {}
    for era in ERAS:
        e = eras[era]
        # Archived rows whose genotype differs from the regenerated row of the same seed are
        # repeats of another genotype in the May harvest, not the paired rule, so they leave
        # the archived cohort.
        drop = np.union1d(duplicated, mismatched) if era == "archived" else duplicated
        o_mask = (obs["era"] == era) & ~np.isin(obs_key, drop)
        r_mask = ~np.isin(e["key"], drop)
        o_order = np.flatnonzero(o_mask)[np.argsort(obs_key[o_mask])]
        r_order = np.flatnonzero(r_mask)[np.argsort(e["key"][r_mask])]
        if not np.array_equal(obs_key[o_order], e["key"][r_order]):
            raise SystemExit(f"{era}: observation keys do not match results keys")
        usable = obs[usable_col][o_order].astype(bool)
        o, r = o_order[usable], r_order[usable]
        shape = (np.stack([obs[a][o] for a in AXIS_IDS], axis=1) - centre) / width
        speed = e["speed_mean"][r]
        if np.any(obs["displacement"][o] <= 0.0) or np.any(speed <= 0.0):
            raise SystemExit(f"{era}: non-positive displacement or speed in the cohort")
        motion = np.stack([np.log(obs["displacement"][o]), np.log(speed)], axis=1)
        cohorts[era] = Cohort(e["key"][r], e["raw"][r], e["canonical"][r], shape, motion,
                              obs[compact_col][o].astype(bool))
        report["cohortRows"][era] = len(cohorts[era])
    return cohorts, report


def motion_scale(cohorts: dict[str, Cohort]) -> np.ndarray:
    """Interquartile range of the motion columns over both eras together, so the two eras
    share one body metric."""
    pooled = np.concatenate([c.motion for c in cohorts.values()])
    q25, q75 = np.quantile(pooled, [0.25, 0.75], axis=0)
    return q75 - q25


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True,
                        help="track-1 regeneration verification run directory")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quotient-anchors", type=int, default=20000)
    parser.add_argument("--dimension-sample", type=int, default=5000)
    parser.add_argument("--matched-size", type=int, default=5000)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--family", action="append",
                        help="family key to analyse (repeatable); default all families")
    args = parser.parse_args(argv)

    frame = load_frame(args.frame)
    included, excluded = verified_runs(args.verification)
    families: dict[str, list[str]] = {}
    for run_id in included:
        families.setdefault(track1_family_metadata(run_id)["familyKey"], []).append(run_id)
    selected = args.family or sorted(families)
    report: dict[str, Any] = {"excludedRuns": excluded, "families": {}}
    for family in selected:
        run_ids = sorted(families[family])
        connectivity = read_json(args.run_root / run_ids[0] / "config.json")["connectivity"]
        for run_id in run_ids:
            config = read_json(args.run_root / run_id / "config.json")
            if config["connectivity"] != connectivity:
                raise SystemExit(f"{run_id}: connectivity differs within {family}")
        symmetry = Symmetry.from_connectivity(connectivity)
        cohorts, loading = load_family(args.run_root, args.archive_dir, run_ids,
                                       args.observations, frame, args.jobs)
        scale = motion_scale(cohorts)
        rng = np.random.default_rng([args.seed, selected.index(family)])
        entry: dict[str, Any] = {
            "runs": run_ids, "loading": loading, "connectivity": connectivity,
            "symmetryGroupOrder": int(len(symmetry.relabelings) * np.prod(
                [np.prod(np.arange(1, len(v) + 1)) for v in symmetry.blocks.values()])),
            "motionScale": scale.tolist(),
        }
        for era, cohort in cohorts.items():
            entry[era] = {
                "all": analyze_cohort(cohort, symmetry, scale, quotient_anchors=args.quotient_anchors,
                                      dimension_sample=args.dimension_sample, rng=rng),
                "compact": analyze_cohort(cohort.take(np.flatnonzero(cohort.compact)), symmetry,
                                          scale, quotient_anchors=args.quotient_anchors,
                                          dimension_sample=args.dimension_sample, rng=rng),
            }
        entry["paired"] = paired_eras(cohorts, symmetry, scale, rng)
        entry["matchedSize"] = {
            "all": matched_size(cohorts, symmetry, args.matched_size, False, rng),
            "compact": matched_size(cohorts, symmetry, min(
                args.matched_size, *(int(c.compact.sum()) for c in cohorts.values())), True, rng),
        }
        report["families"][family] = entry
        write_json(args.output, report)
        print(f"{family}: wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
