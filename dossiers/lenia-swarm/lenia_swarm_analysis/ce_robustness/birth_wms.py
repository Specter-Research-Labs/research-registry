"""Robustness sweep and nulls for the organism-birth whole-minus-sum (WMS) rise.

The baseline reproduces organism-birth-signal-v1/prospective.py: square-root mass
composition of four 64x64 arena quadrants, one Gaussian fitted to standardized
lag-1 transitions of steps 1-400 of the 64 development specimens, the bipartition
with minimum entropy-normalized WMS, pointwise (local) scores, and the rise
mean(event-16..event-1) - mean(event-32..event-17) over the 63 prospective
specimens with an observed event. Each variant changes one choice.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.special import digamma

RIDGE = 1e-6
FIT_STOP = 400
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20260821
NULL_REPEATS = 40


@dataclass(frozen=True)
class Variant:
    name: str
    parts: str = "g2"
    representation: str = "sqrt"
    partition: str = "mib"
    fit: str = "global"
    lag: int = 1
    near: int = 16
    prior: int = 16


BASELINE = Variant("baseline")


def load(path: Path) -> dict:
    archive = np.load(path)
    columns = [str(c) for c in archive["columns"]]
    return {
        "data": archive["data"],
        "index": {name: i for i, name in enumerate(columns)},
        "phase": archive["phase"].astype(str),
        "run_id": archive["run_id"].astype(str),
        "family": archive["family"].astype(str),
        "event": archive["event_step"].astype(int),
    }


def part_masses(store: dict, run: int, parts: str) -> np.ndarray:
    prefix = {"g2": "g2_", "g3": "g3_", "g4": "g4_", "body": "body_q"}[parts]
    count = {"g2": 4, "g3": 9, "g4": 16, "body": 4}[parts]
    columns = [store["index"][f"{prefix}{i}"] for i in range(count)]
    return store["data"][run][:, columns]


def represent(masses: np.ndarray, representation: str) -> np.ndarray:
    composition = masses / masses.sum(axis=1, keepdims=True)
    if representation == "sqrt":
        return np.sqrt(composition)
    if representation == "linear":
        return composition
    if representation == "clr":
        if np.any(composition <= 0):
            raise ValueError("centred log-ratio requires strictly positive parts")
        logs = np.log(composition)
        return logs - logs.mean(axis=1, keepdims=True)
    raise ValueError(representation)


def gaussian_entropy(covariance: np.ndarray) -> float:
    sign, logdet = np.linalg.slogdet(covariance)
    if sign <= 0:
        raise ValueError("covariance not positive definite")
    return 0.5 * (covariance.shape[0] * np.log(2 * np.pi * np.e) + logdet)


@dataclass(frozen=True)
class Model:
    center: np.ndarray
    scale: np.ndarray
    mean: np.ndarray
    covariance: np.ndarray
    groups: tuple[tuple[int, ...], ...]


def standardize_pairs(states: list[np.ndarray], lag: int, stop: int | None):
    stacked = np.concatenate([s[:stop] for s in states])
    center = stacked.mean(axis=0)
    scale = stacked.std(axis=0)
    if np.any(scale <= 1e-8):
        raise ValueError("coordinate lacks variation")
    pairs = np.concatenate(
        [np.column_stack(((s[:stop][:-lag] - center) / scale, (s[:stop][lag:] - center) / scale))
         for s in states])
    return center, scale, pairs


def ridge_covariance(values: np.ndarray) -> np.ndarray:
    covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=0))
    scale = max(float(np.trace(covariance) / covariance.shape[0]), np.finfo(float).eps)
    return covariance + np.eye(covariance.shape[0]) * RIDGE * scale


def gaussian_mi(covariance: np.ndarray, first: tuple[int, ...], second: tuple[int, ...]) -> float:
    joint = first + second
    blocks = [np.linalg.slogdet(covariance[np.ix_(g, g)]) for g in (first, second, joint)]
    if any(sign <= 0 or not np.isfinite(logdet) for sign, logdet in blocks):
        raise ValueError("covariance block not positive definite")
    return 0.5 * (blocks[0][1] + blocks[1][1] - blocks[2][1])


def bipartitions(k: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    result = []
    for size in range(1, k // 2 + 1):
        for left in itertools.combinations(range(k), size):
            right = tuple(i for i in range(k) if i not in left)
            if size == k - size and left > right:
                continue
            result.append((left, right))
    return sorted(result)


def wms_of(covariance: np.ndarray, k: int, groups) -> float:
    whole = gaussian_mi(covariance, tuple(range(k)), tuple(range(k, 2 * k)))
    return whole - sum(gaussian_mi(covariance, g, tuple(k + i for i in g)) for g in groups)


def choose_groups(pairs: np.ndarray, covariance: np.ndarray, k: int, partition: str):
    if partition == "atomic":
        return tuple((i,) for i in range(k))
    if partition.startswith("fixed:"):
        left = tuple(int(c) for c in partition.split(":")[1])
        return (left, tuple(i for i in range(k) if i not in left))
    if partition != "mib":
        raise ValueError(partition)
    if k != 4:
        raise ValueError("exhaustive minimum-information bipartition is declared for four parts only")
    past = pairs[:, :k]
    candidates = []
    for groups in bipartitions(k):
        normalizer = min(gaussian_entropy(ridge_covariance(past[:, g])) for g in groups)
        candidates.append((wms_of(covariance, k, groups) / normalizer, groups))
    return min(candidates)[1]


def fit(states: list[np.ndarray], variant: Variant, stop: int | None = FIT_STOP) -> Model:
    center, scale, pairs = standardize_pairs(states, variant.lag, stop)
    covariance = ridge_covariance(pairs)
    k = states[0].shape[1]
    groups = choose_groups(pairs, covariance, k, variant.partition)
    return Model(center, scale, pairs.mean(axis=0), covariance, groups)


def log_density(values: np.ndarray, mean: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    centred = values - mean
    inverse = np.linalg.inv(covariance)
    sign, logdet = np.linalg.slogdet(covariance)
    if sign <= 0 or not np.isfinite(logdet):
        raise ValueError("covariance not positive definite")
    return -0.5 * (np.einsum("ij,jk,ik->i", centred, inverse, centred) + logdet
                   + values.shape[1] * np.log(2 * np.pi))


def local_mi(z: np.ndarray, model: Model, first, second) -> np.ndarray:
    joint = list(first) + list(second)
    m, c = model.mean, model.covariance
    return (log_density(z[:, joint], m[joint], c[np.ix_(joint, joint)])
            - log_density(z[:, list(first)], m[list(first)], c[np.ix_(first, first)])
            - log_density(z[:, list(second)], m[list(second)], c[np.ix_(second, second)]))


def local_scores(model: Model, states: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Scores indexed by transition-end step: entry s-1-lag is the transition (s-lag) -> s."""
    standardized = (states - model.center) / model.scale
    z = np.column_stack((standardized[:-lag], standardized[lag:]))
    k = states.shape[1]
    whole = local_mi(z, model, tuple(range(k)), tuple(range(k, 2 * k)))
    parts = sum(local_mi(z, model, g, tuple(k + i for i in g)) for g in model.groups)
    return whole - parts, whole


def rise(series: np.ndarray, event: int, lag: int, near: int, prior: int) -> float | None:
    first_step = 1 + lag
    near_steps = range(event - near, event)
    prior_steps = range(event - near - prior, event - near)
    if prior_steps.start < first_step:
        return None
    to_index = lambda steps: [s - first_step for s in steps]  # noqa: E731
    return float(series[to_index(near_steps)].mean() - series[to_index(prior_steps)].mean())


def bootstrap(values: np.ndarray, offset: int) -> list[float]:
    rng = np.random.default_rng(BOOTSTRAP_SEED + offset)
    means = rng.choice(values, size=(BOOTSTRAP_DRAWS, values.size), replace=True).mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def summarize(values: list[float], families: list[str], offset: int) -> dict:
    array = np.asarray(values)
    family_means = {f: float(np.mean([v for v, g in zip(values, families, strict=True) if g == f]))
                    for f in sorted(set(families))}
    return {
        "n": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "positive": int((array > 0).sum()),
        "bootstrap95": bootstrap(array, offset),
        "familiesPositive": sum(v > 0 for v in family_means.values()),
        "families": len(family_means),
    }


def cohort(store: dict, variant: Variant, transform=None):
    def states_for(run: int) -> np.ndarray:
        masses = part_masses(store, run, variant.parts)
        if transform is not None:
            masses = transform(run, masses)
        return represent(masses, variant.representation)
    development = [i for i, p in enumerate(store["phase"]) if p in ("calibration", "test")]
    prospective = [i for i, p in enumerate(store["phase"])
                   if p == "prospective" and store["event"][i] > 0]
    return states_for, development, prospective


def run_variant(store: dict, variant: Variant, transform=None, events=None) -> dict:
    states_for, development, prospective = cohort(store, variant, transform)
    events = store["event"] if events is None else events
    if variant.fit == "global":
        model = fit([states_for(i) for i in development], variant)
        models = {i: model for i in prospective}
    elif variant.fit == "specimen":
        models = {i: fit([states_for(i)], variant) for i in prospective}
    else:
        raise ValueError(variant.fit)
    series = {i: local_scores(models[i], states_for(i), variant.lag) for i in prospective}
    window = lambda values, event: rise(values, event, variant.lag, variant.near, variant.prior)  # noqa: E731
    rises, tdmi_rises, matched, families = [], [], [], []
    for i in prospective:
        r = window(series[i][0], events[i])
        if r is None:
            continue
        rises.append(r)
        tdmi_rises.append(window(series[i][1], events[i]))
        matched.append(float(np.mean([window(series[j][0], events[i])
                                      for j in prospective if j != i])))
        families.append(store["family"][i])
    result = {
        "variant": variant.__dict__,
        "wmsRise": summarize(rises, families, 101),
        "tdmiRise": summarize(tdmi_rises, families, 103),
        "wmsMinusTdmiRise": summarize([a - b for a, b in zip(rises, tdmi_rises, strict=True)], families, 104),
        "ageMatchedRise": summarize(matched, families, 105),
        "excessOverAgeMatched": summarize([a - b for a, b in zip(rises, matched, strict=True)], families, 106),
    }
    if variant.fit == "global":
        result["selectedGroups"] = [list(g) for g in model.groups]
        k = len(model.center)
        result["meanWholeTDMI"] = float(gaussian_mi(model.covariance, tuple(range(k)),
                                                    tuple(range(k, 2 * k))))
        result["meanWMS"] = float(wms_of(model.covariance, k, model.groups))
    return result


def ksg_mi(x: np.ndarray, y: np.ndarray, k: int = 4) -> float:
    """Kraskov-Stoegbauer-Grassberger estimator 1 with max-norm, in nats."""
    joint = np.column_stack((x, y))
    n = joint.shape[0]
    radius = cKDTree(joint).query(joint, k=k + 1, p=np.inf)[0][:, -1]
    nx = cKDTree(x).query_ball_point(x, radius - 1e-12, p=np.inf, return_length=True) - 1
    ny = cKDTree(y).query_ball_point(y, radius - 1e-12, p=np.inf, return_length=True) - 1
    return float(digamma(k) + digamma(n) - np.mean(digamma(nx + 1) + digamma(ny + 1)))


def transition_rows(z: np.ndarray, end_steps: range, lag: int) -> np.ndarray:
    return np.column_stack((z[[s - 1 - lag for s in end_steps]], z[[s - 1 for s in end_steps]]))


def ensemble_window(store: dict, variant: Variant, estimator: str, draws: int, seed: int) -> dict:
    """Non-pointwise WMS: pool the transitions in each event-aligned window across specimens."""
    states_for, development, prospective = cohort(store, variant)
    model = fit([states_for(i) for i in development], variant)
    k = len(model.center)
    windows: dict[int, dict[str, np.ndarray]] = {}
    lag = variant.lag
    for i in prospective:
        event = store["event"][i]
        if event - variant.near - variant.prior < 1 + lag:
            continue
        z = (states_for(i) - model.center) / model.scale
        windows[i] = {"near": transition_rows(z, range(event - variant.near, event), lag),
                      "prior": transition_rows(z, range(event - variant.near - variant.prior,
                                                        event - variant.near), lag)}

    def wms(rows: np.ndarray) -> float:
        if estimator == "gaussian":
            return wms_of(ridge_covariance(rows), k, model.groups)
        whole = ksg_mi(rows[:, :k], rows[:, k:])
        return whole - sum(ksg_mi(rows[:, list(g)], rows[:, [k + j for j in g]])
                           for g in model.groups)

    ids = sorted(windows)

    def contrast(sample: list[int]) -> float:
        near = np.concatenate([windows[i]["near"] for i in sample])
        prior = np.concatenate([windows[i]["prior"] for i in sample])
        return wms(near) - wms(prior)

    observed = contrast(ids)
    rng = np.random.default_rng(seed)
    # Half-samples without replacement because duplicated specimens would become each
    # other's nearest neighbours and inflate KSG; the range is wider than a bootstrap CI.
    halves = [contrast(list(rng.choice(ids, size=len(ids) // 2, replace=False)))
              for _ in range(draws)]
    return {"variant": variant.__dict__, "estimator": estimator, "specimens": len(ids),
            "selectedGroups": [list(g) for g in model.groups], "nearMinusPrior": observed,
            "halfSample95": [float(np.quantile(halves, 0.025)), float(np.quantile(halves, 0.975))],
            "halfSamplePositiveFraction": float(np.mean(np.asarray(halves) > 0))}


def null_part_shuffle(store: dict, variant: Variant, repeats: int, seed: int) -> list[float]:
    """Each part's composition share comes from a different specimen, aligned on the event
    step, then the composition is re-closed. Coupling between parts then arises only from
    closure and from shared event-locked trends."""
    rng = np.random.default_rng(seed)
    events = store["event"]
    pool = {phase: [i for i, p in enumerate(store["phase"]) if p in phase and events[i] > 0]
            for phase in (("calibration", "test"), ("prospective",))}
    means = []
    for _ in range(repeats):
        donors: dict[int, list[int]] = {}
        for members in pool.values():
            for i in members:
                others = [j for j in members if j != i]
                donors[i] = [i] + list(rng.choice(others, size=3 if variant.parts != "g3" else 8,
                                                  replace=False))

        def transform(run: int, masses: np.ndarray, donors=donors) -> np.ndarray:
            if run not in donors:
                return masses
            share = masses / masses.sum(axis=1, keepdims=True)
            mixed = share.copy()
            for part in range(1, share.shape[1]):
                donor = donors[run][(part % (len(donors[run]) - 1)) + 1]
                source = part_masses(store, donor, variant.parts)
                source = source / source.sum(axis=1, keepdims=True)
                shift = events[donor] - events[run]
                index = np.clip(np.arange(share.shape[0]) + shift, 0, share.shape[0] - 1)
                mixed[:, part] = source[index, part]
            return mixed
        means.append(run_variant(store, variant, transform)["wmsRise"]["mean"])
    return means


def null_phase_randomized(store: dict, variant: Variant, repeats: int, seed: int) -> list[float]:
    """Multivariate phase randomization (common random phases across parts) of each
    specimen's square-root composition, then projection back to the unit sphere."""
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(repeats):
        phases: dict[int, np.ndarray] = {}

        def transform(run: int, masses: np.ndarray, phases=phases) -> np.ndarray:
            root = np.sqrt(masses / masses.sum(axis=1, keepdims=True))
            spectrum = np.fft.rfft(root - root.mean(axis=0), axis=0)
            if run not in phases:
                angle = rng.uniform(0, 2 * np.pi, spectrum.shape[0])
                angle[0] = 0
                phases[run] = angle
            surrogate = np.fft.irfft(spectrum * np.exp(1j * phases[run])[:, None],
                                     n=root.shape[0], axis=0) + root.mean(axis=0)
            surrogate = np.abs(surrogate)
            return surrogate ** 2
        means.append(run_variant(store, variant, transform)["wmsRise"]["mean"])
    return means


def later_born_rows(store: dict, variant: Variant, fit_phases: tuple[str, ...],
                    eval_phases: tuple[str, ...], gap: int, shifts: tuple[int, ...],
                    minimum_controls: int = 5) -> tuple[Model, dict[int, dict[int, float]]]:
    """Per specimen, own rise minus the same-step rise of specimens whose event is more than
    `gap` steps later, so that controls share developmental age but are not yet approaching
    birth. A positive shift moves the focal windows that many steps before the true event
    (placebo); control eligibility always uses true events."""
    def states_for(run: int) -> np.ndarray:
        return represent(part_masses(store, run, variant.parts), variant.representation)
    events = store["event"]
    fitted = [i for i, p in enumerate(store["phase"]) if p in fit_phases]
    evaluated = [i for i, p in enumerate(store["phase"]) if p in eval_phases and events[i] > 0]
    model = fit([states_for(i) for i in fitted], variant)
    series = {i: local_scores(model, states_for(i), variant.lag)[0] for i in evaluated}
    window = lambda values, event: rise(values, event, variant.lag, variant.near, variant.prior)  # noqa: E731
    rows: dict[int, dict[int, float]] = {shift: {} for shift in shifts}
    for shift in shifts:
        for i in evaluated:
            anchor = events[i] - shift
            own = window(series[i], anchor)
            if own is None:
                continue
            controls = [window(series[j], anchor) for j in evaluated
                        if j != i and events[j] - events[i] > gap]
            if len(controls) < minimum_controls:
                continue
            rows[shift][i] = own - float(np.mean(controls))
    return model, rows


def later_born_excess(store: dict, variant: Variant, fit_phases: tuple[str, ...],
                      eval_phases: tuple[str, ...], gap: int, shift: int = 0) -> dict:
    model, rows = later_born_rows(store, variant, fit_phases, eval_phases, gap, (shift,))
    chosen = rows[shift]
    return {"variant": variant.__dict__, "fitPhases": list(fit_phases),
            "evalPhases": list(eval_phases), "gap": gap, "shift": shift,
            "selectedGroups": [list(g) for g in model.groups],
            "excessOverLaterBorn": summarize(list(chosen.values()),
                                             [store["family"][i] for i in chosen], 301 + gap)}


def placebo_paired(store: dict, variant: Variant, fit_phases: tuple[str, ...],
                   eval_phases: tuple[str, ...], gap: int, shift: int) -> dict:
    """True-anchor and placebo excess on the same specimens, those eligible for the placebo,
    so that the comparison is not confounded by which specimens each anchor admits."""
    _, rows = later_born_rows(store, variant, fit_phases, eval_phases, gap, (0, shift))
    common = sorted(set(rows[0]) & set(rows[shift]))
    families = [store["family"][i] for i in common]
    true = [rows[0][i] for i in common]
    placebo = [rows[shift][i] for i in common]
    return {"variant": variant.__dict__, "fitPhases": list(fit_phases),
            "evalPhases": list(eval_phases), "gap": gap, "shift": shift,
            "trueAnchor": summarize(true, families, 401 + shift),
            "placeboAnchor": summarize(placebo, families, 501 + shift),
            "trueMinusPlacebo": summarize(list(np.subtract(true, placebo)), families, 601 + shift)}


def variants() -> list[Variant]:
    b = BASELINE
    fixed = [replace(b, name=f"partition-{''.join(map(str, left))}|{''.join(map(str, right))}",
                     partition="fixed:" + "".join(map(str, left)))
             for left, right in bipartitions(4)]
    return [
        b,
        *fixed,
        replace(b, name="partition-atomic-4", partition="atomic"),
        replace(b, name="parts-3x3-atomic", parts="g3", partition="atomic"),
        replace(b, name="parts-4x4-atomic", parts="g4", partition="atomic"),
        replace(b, name="parts-body-centred-mib", parts="body"),
        replace(b, name="parts-body-centred-atomic", parts="body", partition="atomic"),
        replace(b, name="representation-linear", representation="linear"),
        replace(b, name="representation-clr", representation="clr"),
        replace(b, name="fit-per-specimen", fit="specimen"),
        replace(b, name="lag-2", lag=2),
        replace(b, name="lag-4", lag=4),
        replace(b, name="lag-8", lag=8),
        replace(b, name="window-8", near=8, prior=8),
        replace(b, name="window-24", near=24, prior=24),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ksg-draws", type=int, default=200)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    store = load(args.measurements)
    sweep = []
    for variant in variants():
        try:
            sweep.append(run_variant(store, variant))
        except ValueError as error:
            sweep.append({"variant": variant.__dict__, "unavailable": str(error)})
        print(variant.name, json.dumps(sweep[-1].get("wmsRise", sweep[-1].get("unavailable"))))
    ensemble = [ensemble_window(store, BASELINE, "gaussian", 2000, 11),
                ensemble_window(store, BASELINE, "ksg", args.ksg_draws, 12),
                ensemble_window(store, replace(BASELINE, name="atomic", partition="atomic"),
                                "ksg", args.ksg_draws, 13)]
    print("ensemble", json.dumps(ensemble))
    nulls = {
        "partShuffle": null_part_shuffle(store, BASELINE, NULL_REPEATS, 21),
        "phaseRandomized": null_phase_randomized(store, BASELINE, NULL_REPEATS, 22),
    }
    development, prospective = ("calibration", "test"), ("prospective",)
    atomic = replace(BASELINE, name="partition-atomic-4", partition="atomic")
    later_born = {
        "exploratoryProspective": [later_born_excess(store, v, development, prospective, gap)
                                   for v in (BASELINE, atomic) for gap in (0, 48, 96)],
        "declaredReplicationDevelopment": [later_born_excess(store, v, prospective, development, gap)
                                           for v in (BASELINE, atomic) for gap in (0, 48, 96)],
        "placeboEarlierAnchor": [later_born_excess(store, v, fit, evaluate, 48, shift)
                                 for fit, evaluate in ((development, prospective),
                                                       (prospective, development))
                                 for v in (BASELINE, atomic) for shift in (32, 64)],
        "placeboPaired": [placebo_paired(store, v, fit, evaluate, 48, 32)
                          for fit, evaluate in ((development, prospective), (prospective, development))
                          for v in (BASELINE, atomic)],
    }
    for key, group in later_born.items():
        if key == "placeboPaired":
            continue
        for entry in group:
            print("later-born", entry["variant"]["name"], entry["evalPhases"], entry["gap"],
                  entry["shift"],
                  json.dumps(entry["excessOverLaterBorn"]))
    print("nulls", json.dumps({k: [min(v), float(np.mean(v)), max(v)]
                               for k, v in nulls.items()}))
    args.output.write_text(json.dumps({"sweep": sweep, "ensembleWindow": ensemble, "nulls": nulls,
                                       "laterBornControl": later_born},
                                      indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
