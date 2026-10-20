"""Behavior spread among Flow Lenia rules that grow the same shape.

A behavior-spread run (LeniaCLI `discover evaluate`, one corpus per arm) measures, around
each base rule, three arms over the same post-lesion window: shape-mates (rules whose
shape matches the base within the tolerance tau), neighbours (random rules at each mate's
genotype distance, not screened on shape) and replicates (the base rule over many init
seeds). Every arm is run twice per (genotype, init seed), once unmodified (sham) and once
with a zero_state_patch lesion, so sham and lesion rows differ only by the lesion.

The spread statistic R_f is the SD over genotypes of the K-seed mean of feature f in units
of the chaos floor, the standard error of one K-seed mean of the base rule. R = 1 means
the rules differ no more than reruns of the base from new init seeds.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import rankdata

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis._io import write_json as _write_json

SHAPE_KEYS = ("occupancy_mean", "gyration", "moment_anisotropy", "largest_component_fraction",
              "component_count", "largest_component_anisotropy", "largest_component_filamentarity",
              "largest_component_solidity", "largest_component_mean_thickness",
              "largest_component_max_thickness", "largest_component_internal_stripe",
              "largest_component_oriented_ridge")
SHAPE_LOG_KEYS = frozenset({"gyration", "component_count", "largest_component_mean_thickness",
                            "largest_component_max_thickness"})
BEHAVIOR_KEYS = ("log_displacement", "log_speed", "log_tortuosity", "log_energy", "log_variance",
                 "log_lesion_drift")
DRIFT_KEYS = ("occupancy_mean", "gyration", "largest_component_fraction")
CV_MOTION_KEYS = ("displacement", "speed_mean")
# Energy is the sum of squared mass, so it reads interior mass concentration, which the
# thresholded silhouette features in SHAPE_KEYS cannot see; R_base without it separates
# hidden behavior from hidden interior shape.
DENSITY_DOMAIN = "energy"
FINGERPRINT_SIDE = 32
RADIAL_EDGES = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 16.0 * np.sqrt(2.0))
MOMENT_KEYS = ("hu1", "hu2", "hu3", "hu4", "hu5", "hu6", "hu7", "flusser1", "flusser2", "flusser3",
               "flusser4")
RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
ARMS = ("mates", "neighbours", "replicates")


def metric_matrix(metrics: list[dict[str, Any]], keys: tuple[str, ...]) -> np.ndarray:
    return np.asarray([[float(m[k]) for k in keys] for m in metrics], dtype=np.float64)


def shape_matrix(metrics: list[dict[str, Any]]) -> np.ndarray:
    """Terminal-frame morphology plus window-mean occupancy, with the heavy-tailed count,
    size and thickness features on a log scale."""
    raw = metric_matrix(metrics, SHAPE_KEYS)
    for j, key in enumerate(SHAPE_KEYS):
        if key in SHAPE_LOG_KEYS:
            raw[:, j] = np.log(raw[:, j])
    return raw


def interior_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    """Rotation-invariant description of where the mass sits inside the terminal body, from
    the centre-of-mass-centred 32x32 L1 fingerprint (one pixel is four cells): the mass
    fraction in rings of one pixel out to eight and beyond, the log inverse participation
    of the fingerprint, the angular harmonic amplitudes, the Hu and Flusser moments and the
    moment density. Heading differs between init seeds, so nothing orientation-bound enters."""
    centre = (FINGERPRINT_SIDE - 1) / 2.0
    yy, xx = np.mgrid[:FINGERPRINT_SIDE, :FINGERPRINT_SIDE]
    ring = np.digitize(np.hypot(yy - centre, xx - centre).ravel(), RADIAL_EDGES[1:-1])
    out = []
    for row in rows:
        terminal = row["descriptor_bundle"]["terminal"]
        if terminal["fingerprintResolution"] != FINGERPRINT_SIDE:
            raise ValueError(f"fingerprint resolution {terminal['fingerprintResolution']}")
        fp = np.frombuffer(base64.b64decode(terminal["fingerprintU8"]), dtype=np.uint8).astype(np.float64)
        if fp.size != FINGERPRINT_SIDE ** 2 or fp.sum() == 0.0:
            raise ValueError("fingerprint is not a non-empty 32x32 u8 grid")
        fp /= fp.sum()
        radial = np.bincount(ring, weights=fp, minlength=len(RADIAL_EDGES) - 1)
        out.append(np.concatenate([radial, [np.log((fp ** 2).sum())],
                                   terminal["angularSymmetry"]["harmonics"],
                                   [float(row["metrics"][k]) for k in MOMENT_KEYS],
                                   [terminal["momentDensity"]]]))
    return np.asarray(out, dtype=np.float64)


def behavior_matrix(sham: list[dict[str, Any]], lesion: list[dict[str, Any]]) -> np.ndarray:
    """Per-rollout behavior over the recorded window. Tortuosity is path length over net
    displacement; lesion drift is the mean relative sham-lesion difference of DRIFT_KEYS
    for the same genotype and init seed (the functional_map assay)."""
    if len(sham) != len(lesion):
        raise ValueError(f"{len(sham)} sham rows against {len(lesion)} lesion rows")
    disp = metric_matrix(sham, ("displacement",))[:, 0]
    path = metric_matrix(sham, ("path_length",))[:, 0]
    s, les = metric_matrix(sham, DRIFT_KEYS), metric_matrix(lesion, DRIFT_KEYS)
    if np.any(s == 0.0):
        raise ValueError("sham rollout with zero occupancy, gyration or component fraction")
    drift = np.mean(np.abs(s - les) / np.abs(s), axis=1)
    cols = [np.log(disp), np.log(metric_matrix(sham, ("speed_mean",))[:, 0]), np.log(path / disp),
            np.log(metric_matrix(sham, ("energy_mean",))[:, 0]),
            np.log(metric_matrix(sham, ("variance_mean",))[:, 0]), np.log(drift)]
    out = np.stack(cols, axis=1)
    if not np.all(np.isfinite(out)):
        raise ValueError("non-finite behavior feature (zero displacement or zero drift)")
    return out


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def write_json(path: Path, payload: Any) -> None:
    _write_json(path, to_jsonable(payload))


@dataclass(frozen=True)
class Arm:
    """One measured arm, genotype-major over the arm's seeds: behavior, shape and interior
    features per (genotype, seed) and the raw sham shape and motion metrics."""

    behavior: np.ndarray
    shape: np.ndarray
    interior: np.ndarray
    raw: np.ndarray
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class Base:
    base: int
    tau: float
    units: np.ndarray
    u0: np.ndarray
    mates: Arm
    neighbours: Arm
    replicates: Arm


def _results_rows(rollouts: Path, tag: str) -> list[dict[str, Any]]:
    found = sorted((rollouts / tag / "eval").glob("*/results.jsonl"))
    if len(found) != 1:
        raise SystemExit(f"{rollouts / tag}: expected one eval/*/results.jsonl, found {len(found)}")
    return read_jsonl(found[0])


def load_arm(rollouts: Path, base: int, arm: str, genotypes: int, seeds: tuple[int, ...]) -> Arm:
    sham = _results_rows(rollouts, f"b{base}-measure-{arm}-sham")
    lesion = _results_rows(rollouts, f"b{base}-measure-{arm}-lesion")
    expected = list(seeds) * genotypes
    for tag, rows in (("sham", sham), ("lesion", lesion)):
        if [int(r["init_seed"]) for r in rows] != expected:
            raise SystemExit(f"b{base} {arm} {tag}: rows are not genotype-major over seeds {seeds}")
    for s, les in zip(sham, lesion, strict=True):
        if s["descriptor_bundle"]["genotype"]["hash12"] != les["descriptor_bundle"]["genotype"]["hash12"]:
            raise SystemExit(f"b{base} {arm}: sham and lesion rows disagree on genotype")
    k = len(seeds)
    sham_m = [r["metrics"] for r in sham]
    return Arm(
        behavior=behavior_matrix(sham_m, [r["metrics"] for r in lesion]).reshape(genotypes, k, -1),
        shape=shape_matrix(sham_m).reshape(genotypes, k, -1),
        interior=interior_matrix(sham).reshape(genotypes, k, -1),
        raw=metric_matrix(sham_m, SHAPE_KEYS + CV_MOTION_KEYS).reshape(genotypes, k, -1),
        seeds=seeds,
    )


def load_base(run_dir: Path, plan: dict[str, Any], base: int) -> Base:
    rec = read_json(run_dir / "results" / f"base-{base}.json")
    if rec["status"] != "measured":
        raise SystemExit(f"base {base} has status {rec['status']!r}; only measured bases load")
    design = plan["design"]
    measure = tuple(int(s) for s in design["measure_seeds"])
    replicate = tuple(int(s) for s in design["replicate_seeds"])
    n = len(rec["mates"])
    if len(rec["neighbours"]) != n:
        raise SystemExit(f"base {base}: {n} mates but {len(rec['neighbours'])} neighbours")
    rollouts = run_dir / "rollouts"
    return Base(
        base=base, tau=float(rec["tau"]), units=np.asarray(rec["mates"], dtype=np.float64),
        u0=np.asarray(rec["u0"], dtype=np.float64),
        mates=load_arm(rollouts, base, "mates", n, measure),
        neighbours=load_arm(rollouts, base, "neighbours", n, measure),
        replicates=load_arm(rollouts, base, "replicates", 1, replicate),
    )


def chaos_floor(replicates: np.ndarray, k: int) -> np.ndarray:
    """Standard error of one k-seed mean of the base rule, from its replicate seeds."""
    return replicates.std(axis=0, ddof=1) / np.sqrt(k)


def pooled_floor(values: np.ndarray) -> np.ndarray:
    """Standard error of one k-seed mean from the genotypes' own seed scatter, pooled
    over genotypes (values: genotypes x seeds x features)."""
    return np.sqrt(values.var(axis=1, ddof=1).mean(axis=0) / values.shape[1])


def paired_floor(values: np.ndarray) -> np.ndarray:
    """Standard error of one k-seed mean when every genotype runs on the same seeds: the
    genotype x seed interaction mean square of the two-way layout, because a seed's
    common effect cancels between genotypes that share it. spread / paired_floor is the
    square root of the genotype F statistic."""
    g, k = values.shape[:2]
    resid = (values - values.mean(axis=1, keepdims=True) - values.mean(axis=0, keepdims=True)
             + values.mean(axis=(0, 1), keepdims=True))
    return np.sqrt((resid ** 2).sum(axis=(0, 1)) / ((g - 1) * (k - 1)) / k)


def spread(values: np.ndarray) -> np.ndarray:
    return values.mean(axis=1).std(axis=0, ddof=1)


def _domain_columns(domains: dict[str, list[str]]) -> dict[str, list[int]]:
    return {d: [BEHAVIOR_KEYS.index(f) for f in fs] for d, fs in domains.items()}


def domain_ratios(log_ratio: np.ndarray, domains: dict[str, list[str]]) -> dict[str, float]:
    return {d: float(np.exp(np.mean(log_ratio[cols]))) for d, cols in _domain_columns(domains).items()}


def domain_index(log_ratio: np.ndarray, domains: dict[str, list[str]]) -> float:
    """R_base: exp of the mean over domains of the mean log ratio within each domain."""
    return float(np.exp(np.mean(np.log(list(domain_ratios(log_ratio, domains).values())))))


def _resample(rng: np.random.Generator, n: int) -> np.ndarray:
    """Bootstrap indices with at least two distinct values, so that every draw has a
    defined SD."""
    while True:
        idx = rng.integers(0, n, n)
        if np.unique(idx).size >= 2:
            return idx


def paired_bootstrap(mates: np.ndarray, neighbours: np.ndarray, replicates: np.ndarray,
                     domains: dict[str, list[str]], draws: int, ci: float,
                     rng: np.random.Generator) -> dict[str, Any]:
    """CI that keeps the shared-seed pairing: resample genotypes, draw one seed resample
    shared by every genotype of both arms, and resample the base's replicate seeds."""
    g, k = mates.shape[:2]
    names = list(domains)
    no_density = {d: fs for d, fs in domains.items() if d != DENSITY_DOMAIN}
    stats: dict[str, list[Any]] = {"R_base": [], "R_base_paired": [], "R_base_no_density": [],
                                   "domains": [], "R_ac": []}
    for _ in range(draws):
        gi, si = _resample(rng, g), _resample(rng, k)
        a, c = mates[gi][:, si], neighbours[gi][:, si]
        rep = replicates[rng.integers(0, replicates.shape[0], replicates.shape[0])]
        sa = spread(a)
        log_r = np.log(sa / chaos_floor(rep, k))
        stats["R_base"].append(np.log(domain_index(log_r, domains)))
        stats["R_base_paired"].append(np.log(domain_index(np.log(sa / paired_floor(a)), domains)))
        stats["R_base_no_density"].append(np.log(domain_index(log_r, no_density)))
        stats["domains"].append(np.log([domain_ratios(log_r, domains)[d] for d in names]))
        stats["R_ac"].append(np.log(sa / spread(c)))
    q = [100 * (1 - ci) / 2, 100 * (1 + ci) / 2]
    out: dict[str, Any] = {key: np.exp(np.percentile(np.asarray(v), q, axis=0)) for key, v in stats.items()}
    out["domains"] = dict(zip(names, out["domains"].T, strict=True))
    out["R_ac"] = dict(zip(BEHAVIOR_KEYS, out["R_ac"].T, strict=True))
    return out


def _zero_shape_intercept(b: np.ndarray, s: np.ndarray, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    x = np.mean((s[i] - s[j]) ** 2, axis=1)
    design = np.stack([np.ones_like(x), x], axis=1)
    coef, *_ = np.linalg.lstsq(design, (b[i] - b[j]) ** 2 / 2.0, rcond=None)
    return coef[0]


def residual_shape(behavior: np.ndarray, shape: np.ndarray, floor: np.ndarray, scale: np.ndarray,
                   domains: dict[str, list[str]], draws: int, ci: float,
                   rng: np.random.Generator) -> dict[str, Any]:
    """Behavior spread among mates extrapolated to zero residual shape difference.

    For mates i, j with k-seed behavior means b (floor units) and scaled shape means s,
    E[(b_i - b_j)^2] / 2 = R_hidden^2 + beta^2 |s_i - s_j|^2 / 2 when behavior is linear in
    residual shape, so the pairwise intercept at zero squared shape distance estimates
    R^2 with the shape-explained part removed. Noise in the held-out shape means biases
    the slope down and the intercept up, so this is an upper estimate. Domains combine
    quadratically (mean R^2 over features, then over domains) because a bootstrap
    intercept can be negative; `R_all` is the same aggregate without the adjustment."""
    b, s = behavior.mean(axis=1) / floor, shape.mean(axis=1) / scale
    cols = _domain_columns(domains)

    def aggregate(r2: np.ndarray) -> float:
        return float(np.mean([np.mean(r2[c]) for c in cols.values()]))

    i, j = np.triu_indices(b.shape[0], 1)
    r2 = _zero_shape_intercept(b, s, i, j)
    r2_all = (b[i] - b[j]) ** 2 / 2.0
    boot = np.empty(draws)
    for d in range(draws):
        gi = _resample(rng, b.shape[0])
        keep = gi[i] != gi[j]
        boot[d] = aggregate(_zero_shape_intercept(b[gi], s[gi], i[keep], j[keep]))
    q = np.percentile(boot, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    r2_base = aggregate(r2)
    return {"R2_at_zero": dict(zip(BEHAVIOR_KEYS, r2, strict=True)),
            "R2_base_at_zero": r2_base,
            "R_base_at_zero": float(np.sqrt(np.clip(r2_base, 0.0, None))),
            "R_base_at_zero_ci": np.sqrt(np.clip(q, 0.0, None)),
            "R_base_all": float(np.sqrt(aggregate(r2_all.mean(axis=0)))),
            "shape_distance_median": float(np.sqrt(np.median(np.mean((s[i] - s[j]) ** 2, axis=1))))}


def rule_distance_correlation(behavior: np.ndarray, floor: np.ndarray, units: np.ndarray,
                              draws: int, rng: np.random.Generator) -> dict[str, float]:
    """Mantel test: Spearman correlation between pairwise behavior distance (RMS over
    features in floor units) and pairwise genotype distance, with a one-sided
    permutation p-value."""
    b = behavior.mean(axis=1) / floor
    i, j = np.triu_indices(b.shape[0], 1)
    db = rankdata(np.sqrt(np.mean((b[i] - b[j]) ** 2, axis=1)))
    dist = np.linalg.norm(units[:, None] - units[None], axis=2)
    observed = float(np.corrcoef(db, rankdata(dist[i, j]))[0, 1])
    null = np.empty(draws)
    for d in range(draws):
        p = rng.permutation(b.shape[0])
        null[d] = np.corrcoef(db, rankdata(dist[p][:, p][i, j]))[0, 1]
    return {"rho": observed, "p": float((1 + np.sum(null >= observed)) / (1 + draws))}


def _ridge_gcv_alpha(x: np.ndarray, y: np.ndarray) -> float:
    def gcv(alpha: float) -> float:
        hat = x @ np.linalg.solve(x.T @ x + alpha * np.eye(x.shape[1]), x.T)
        resid = y - hat @ y
        return float(np.mean(resid ** 2) / (1.0 - np.trace(hat) / len(y)) ** 2)

    return min(RIDGE_ALPHAS, key=gcv)


def rule_predictability(behavior: np.ndarray, units: np.ndarray, u0: np.ndarray) -> dict[str, Any]:
    """How much of each mate's behavior its rule offset predicts: leave-one-out R^2 of a
    ridge regression of the k-seed behavior mean on the offset u - u0, with the ridge
    penalty chosen by GCV inside each fold. The split-half reliability (correlation of
    means over the first and second half of the seeds) bounds what any predictor can
    reach."""
    offsets = units - u0
    offsets = offsets / np.linalg.norm(offsets, axis=1).mean()
    means = behavior.mean(axis=1)
    half = behavior.shape[1] // 2
    first, second = behavior[:, :half].mean(axis=1), behavior[:, half:].mean(axis=1)
    r2, reliability = {}, {}
    for f, key in enumerate(BEHAVIOR_KEYS):
        r2[key] = _r2(means[:, f], _loo_ridge(offsets, means[:, f]))
        reliability[key] = float(np.corrcoef(first[:, f], second[:, f])[0, 1])
    return {"loo_r2": r2, "split_half_r": reliability}


def _loo_ridge(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-out ridge predictions of y from x, the penalty chosen by GCV in each fold."""
    n = y.shape[0]
    pred = np.empty(n)
    for i in range(n):
        train = np.arange(n) != i
        xt, yt = x[train], y[train]
        xm, ym = xt.mean(axis=0), yt.mean()
        alpha = _ridge_gcv_alpha(xt - xm, yt - ym)
        coef = np.linalg.solve((xt - xm).T @ (xt - xm) + alpha * np.eye(x.shape[1]), (xt - xm).T @ (yt - ym))
        pred[i] = ym + (x[i] - xm) @ coef
    return pred


def _r2(y: np.ndarray, pred: np.ndarray) -> float:
    return float(1.0 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))


def form_predictability(behavior: np.ndarray, forms: dict[str, np.ndarray]) -> dict[str, Any]:
    """How much of each mate's behavior its grown form predicts, seed-split so that no
    rollout supplies both sides: form means from one half of the seeds predict behavior
    means from the other half (leave-one-mate-out ridge on standardized form features),
    averaged over the two directions. The split-half correlation of behavior is the
    reference, since a predictor that recovered each mate's true mean would reach about
    that R^2. Form features constant across mates carry nothing and are dropped."""
    half = behavior.shape[1] // 2
    halves = (slice(None, half), slice(half, None))
    out: dict[str, Any] = {}
    for name, form in forms.items():
        r2 = {}
        for f, key in enumerate(BEHAVIOR_KEYS):
            scores = []
            for src, dst in (halves, halves[::-1]):
                x = form[:, src].mean(axis=1)
                sd = x.std(axis=0)
                x = (x[:, sd > 0] - x[:, sd > 0].mean(axis=0)) / sd[sd > 0]
                y = behavior[:, dst, f].mean(axis=1)
                scores.append(_r2(y, _loo_ridge(x, y)))
            r2[key] = float(np.mean(scores))
        out[name] = r2
    return out


def canalization(replicates: Arm) -> dict[str, Any]:
    """Coefficient of variation over the base's replicate seeds of each raw shape metric
    and of displacement and speed."""
    raw = replicates.raw[0]
    cv = raw.std(axis=0, ddof=1) / np.abs(raw.mean(axis=0))
    keys = SHAPE_KEYS + CV_MOTION_KEYS
    return {"cv": dict(zip(keys, cv, strict=True)),
            "shape_cv_median": float(np.median(cv[: len(SHAPE_KEYS)])),
            "displacement_cv": float(cv[keys.index("displacement")]),
            "speed_cv": float(cv[keys.index("speed_mean")])}


def analyze_base(run_dir: Path, plan: dict[str, Any], base: int, scale: np.ndarray) -> dict[str, Any]:
    analysis = plan["analysis"]
    domains, draws, ci = analysis["domains"], analysis["bootstrap"], analysis["ci"]
    b = load_base(run_dir, plan, base)
    k = len(b.mates.seeds)
    a, c, rep = b.mates.behavior, b.neighbours.behavior, b.replicates.behavior[0]
    floors = {"replicates": chaos_floor(rep, k), "pooled_mates": pooled_floor(a), "paired": paired_floor(a)}
    sd_a, sd_c = spread(a), spread(c)
    rng = np.random.default_rng([analysis["rng_seed"], base])
    return {
        "n_mates": a.shape[0], "tau": b.tau,
        "floors": {name: dict(zip(BEHAVIOR_KEYS, f, strict=True)) for name, f in floors.items()},
        "R_base": {name: domain_index(np.log(sd_a / f), domains) for name, f in floors.items()},
        "R_base_no_density": domain_index(np.log(sd_a / floors["replicates"]),
                                          {d: fs for d, fs in domains.items() if d != DENSITY_DOMAIN}),
        "R_domains": {name: domain_ratios(np.log(sd_a / f), domains) for name, f in floors.items()},
        "R_a": dict(zip(BEHAVIOR_KEYS, sd_a / floors["replicates"], strict=True)),
        "R_c": dict(zip(BEHAVIOR_KEYS, sd_c / floors["replicates"], strict=True)),
        "R_ac": dict(zip(BEHAVIOR_KEYS, sd_a / sd_c, strict=True)),
        "paired_ci": paired_bootstrap(a, c, rep, domains, draws, ci, rng),
        "residual_shape": residual_shape(a, b.mates.shape, floors["replicates"], scale, domains,
                                         draws, ci, rng),
        "rule_distance": rule_distance_correlation(a, floors["replicates"], b.units, draws, rng),
        "rule_predictability": rule_predictability(a, b.units, b.u0),
        "form_predictability": form_predictability(a, {
            "shape": b.mates.shape, "interior": b.mates.interior,
            "shape_interior": np.concatenate([b.mates.shape, b.mates.interior], axis=2)}),
        "canalization": canalization(b.replicates),
    }


def verdict(ci: np.ndarray, analysis: dict[str, Any]) -> str:
    lo, hi = ci
    return ("supports" if lo > analysis["support_lower"] else
            "falsifies" if hi < analysis["falsify_upper"] else "inconclusive")


def analyze_run(run_dir: Path) -> dict[str, Any]:
    plan = read_json(run_dir / "plan.json")
    analysis = plan["analysis"]
    scale = np.asarray(read_json(run_dir / "results" / "scale.json")["scale"], dtype=np.float64)
    bases = [int(x) for x in plan["design"]["bases"]]
    status = {x: read_json(run_dir / "results" / f"base-{x}.json")["status"] for x in bases}
    per_base = {x: analyze_base(run_dir, plan, x, scale) for x in bases if status[x] == "measured"}
    return {
        "bases": {str(x): v for x, v in per_base.items()},
        "not_measured": {str(x): s for x, s in status.items() if s != "measured"},
        "paired_verdicts": {
            "replicate_floor": {str(x): verdict(v["paired_ci"]["R_base"], analysis) for x, v in per_base.items()},
            "paired_floor": {str(x): verdict(v["paired_ci"]["R_base_paired"], analysis) for x, v in per_base.items()},
            "no_density": {str(x): verdict(v["paired_ci"]["R_base_no_density"], analysis) for x, v in per_base.items()},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-behavior-spread",
        description="Behavior spread among shape-mates, with paired-seed and residual-shape controls",
    )
    parser.add_argument("run_dir", type=Path, help="behavior-spread run with plan.json, results/ and rollouts/")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    write_json(args.output, analyze_run(args.run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
