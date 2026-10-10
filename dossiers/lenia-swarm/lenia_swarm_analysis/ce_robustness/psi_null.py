"""Nulls for the positive Rosas Psi values in formal-ce.json.

Psi is positive for an aggregate of independent, individually persistent parts, because each
part predicts only a small share of the aggregate's future. Two checks address that and the
pooling of many runs. The part-shuffle surrogate gives every one of the 16 parts the trajectory
of a different run drawn from the same age and arm, which keeps each part's own dynamics and
its marginal distribution and removes all coupling between parts; macro variables are then
recomputed from the recombined parts. Because the parts are mass shares, recombined parts no
longer sum to one; the renormalized surrogate divides each recombined record by its sum, which
restores the constraint at the cost of slightly altering each part's marginal. The within-run variant subtracts each run's own mean
from every variable before estimation, so that static differences between runs, which make any
persistent variable predict its own future, do not contribute. It also reports how much of the
micro transition matrix used for Hoel's effective information stays in the same state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from lenia_swarm_analysis.ce_robustness import formal_ce

CASES = (("all", "quadrantShares", 1), ("all", "secondMoments", 1), ("late", "quadrantShares", 1),
         ("late", "secondMoments", 1), ("late", "secondMoments", 4), ("all", "quadrantShares", 4))
SHUFFLES = 20
SEED = 20261011


def terms(parts: np.ndarray, macro: np.ndarray, lag: int, within_run: bool) -> dict:
    blocks = [parts[:, :-lag], parts[:, lag:], macro[:, :-lag], macro[:, lag:]]
    if within_run:
        blocks = [b - b.mean(axis=1, keepdims=True) for b in blocks]
    values = np.column_stack([b.reshape(-1, b.shape[-1]) for b in blocks])
    values = (values - values.mean(axis=0)) / values.std(axis=0)
    covariance = formal_ce.ridge_covariance(values)
    k, d = parts.shape[-1], macro.shape[-1]
    vn, vf = list(range(2 * k, 2 * k + d)), list(range(2 * k + d, 2 * k + 2 * d))
    self_info = formal_ce.gaussian_mi(covariance, vn, vf)
    part_to_macro = sum(formal_ce.gaussian_mi(covariance, [j], vf) for j in range(k))
    return {"psi": self_info - part_to_macro, "macroSelfInformation": self_info,
            "sumPartToMacro": float(part_to_macro)}


def part_shuffle(share4: np.ndarray, strata: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    shuffled = np.empty_like(share4)
    for stratum in np.unique(strata):
        rows = np.flatnonzero(strata == stratum)
        for j in range(share4.shape[-1]):
            shuffled[rows, :, j] = share4[rng.permutation(rows), :, j]
    return shuffled


def renormalize(share4: np.ndarray) -> np.ndarray:
    return share4 / share4.sum(axis=-1, keepdims=True)


def persistence(store: dict) -> list[dict]:
    flat = store["share8"].reshape(-1, 64)
    projected = PCA(formal_ce.PCA_COMPONENTS, random_state=formal_ce.SEED).fit_transform(flat)
    output = []
    for n in (32, 64, 128):
        labels = KMeans(n, n_init=4, random_state=formal_ce.SEED).fit(projected).labels_
        labels = labels.reshape(store["share8"].shape[:2])
        for lag in (1, 4, 8, 15, 30):
            same = float(np.mean(labels[:, :-lag] == labels[:, lag:]))
            output.append({"microStates": n, "lagRecords": lag, "sameStateFraction": same})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    store = formal_ce.load(args.measurements)
    rng = np.random.default_rng(SEED)
    share4 = store["share4"]
    pc1_axis = PCA(1, random_state=formal_ce.SEED).fit(share4.reshape(-1, 16)).components_[0]
    masks = formal_ce.subsets(store)
    strata = np.char.add(store["age"].astype(str), store["arm"])
    cases = []
    for subset, name, lag in CASES:
        runs = np.flatnonzero(masks[subset])
        parts = share4[runs]
        macro = formal_ce.macro_variables(parts, pc1_axis)[name]
        surrogate, renormalized = [], []
        for _ in range(SHUFFLES):
            shuffled = part_shuffle(parts, strata[runs], rng)
            surrogate.append(terms(shuffled, formal_ce.macro_variables(shuffled, pc1_axis)[name], lag,
                                   False)["psi"])
            constrained = renormalize(shuffled)
            renormalized.append(terms(constrained, formal_ce.macro_variables(constrained, pc1_axis)[name],
                                      lag, False)["psi"])
        cases.append({"subset": subset, "macro": name, "lagRecords": lag,
                      "pooled": terms(parts, macro, lag, False),
                      "withinRun": terms(parts, macro, lag, True),
                      "partShufflePsi": formal_ce.quantiles(surrogate) | {"values": surrogate},
                      "partShuffleRenormalizedPsi": formal_ce.quantiles(renormalized) | {"values": renormalized}})
        print(json.dumps({k: v for k, v in cases[-1].items() if not k.startswith("partShuffle")}),
              formal_ce.quantiles(surrogate), formal_ce.quantiles(renormalized), flush=True)
    result = {"settings": {"shuffles": SHUFFLES, "seed": SEED, "strata": "age x arm"},
              "psiCases": cases, "microPersistence": persistence(store)}
    args.output.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
