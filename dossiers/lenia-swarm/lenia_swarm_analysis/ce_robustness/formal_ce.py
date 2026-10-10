"""Hoel effective information and Rosas Psi/Delta/Gamma on the impedance futures.

Input is the compact measurement file from measure_futures.py: 8512 futures (64 organisms in
16 groups, 19 ages, untouched plus six perturbed arms per organism and age), 60 records each,
one record every 4 simulation steps, each record an 8x8 block-mass summary of the body-centred
32x32 field.

Hoel. Micro states are k-means clusters of the mass-normalized 8x8 composition (after PCA to
ten components, fitted on all records). The transition probability matrix (TPM) is the
row-normalized count of within-run transitions at the stated lag. The intervention
distribution is uniform over eligible micro states, those with at least MIN_ROW_COUNT outgoing
transitions in the data subset. A macro coarse-graining groups micro states by a feature of
their centroid; its TPM is T_M[A, B] = mean over i in A of sum over j in B of T[i, j], i.e. a
uniform intervention over the members of A. Causal emergence is EI(macro) - EI(micro) in bits.
Each feature partition is compared with random partitions of the same group sizes.

Rosas. Parts X^j are the 16 mass shares of a 4x4 block grid. Macro variables V are functions
of those shares: quadrant shares (three free coordinates), the mass second-moment tensor
(three coordinates) and the first principal component of the shares. With Gaussian mutual
information on standardized pooled transitions,
Psi = I(V_t; V_t+L) - sum_j I(X^j_t; V_t+L),
Delta = max_j [I(V_t; X^j_t+L) - sum_i I(X^i_t; X^j_t+L)],
Gamma = max_j I(X^j_t; V_t+L).
Psi > 0 is the sufficient criterion for causal emergence of V. Intervals resample the 16
organism groups.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

EARLY = (60, 100, 140, 180)
LATE = (660, 700, 740, 780)
MIN_ROW_COUNT = 20
PCA_COMPONENTS = 10
RANDOM_PARTITIONS = 200
GROUP_BOOTSTRAP = 200
RIDGE = 1e-6
SEED = 20261010


def load(path: Path) -> dict:
    archive = np.load(path)
    data = archive["data"].astype(np.float64)
    blocks8 = data[:, :, :64].reshape(data.shape[0], data.shape[1], 8, 8)
    share8 = blocks8 / blocks8.sum(axis=(2, 3), keepdims=True)
    share4 = share8.reshape(data.shape[0], data.shape[1], 4, 2, 4, 2).sum(axis=(3, 5))
    return {
        "share8": share8.reshape(data.shape[0], data.shape[1], 64),
        "share4": share4.reshape(data.shape[0], data.shape[1], 16),
        "group": archive["group"].astype(str),
        "age": archive["age"].astype(int),
        "arm": archive["arm"].astype(str),
    }


def subsets(store: dict) -> dict[str, np.ndarray]:
    age, arm = store["age"], store["arm"]
    every = np.ones(age.size, bool)
    return {
        "all": every,
        "untouched": arm == "untouched",
        "perturbed": arm != "untouched",
        "early": np.isin(age, EARLY),
        "late": np.isin(age, LATE),
    }


def entropy_bits(p: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(p > 0, -p * np.log2(p), 0.0)
    return terms.sum(axis=-1)


def effective_information(tpm: np.ndarray) -> dict:
    mean_row = tpm.mean(axis=0)
    determinism_loss = float(entropy_bits(tpm).mean())
    degeneracy_loss = float(np.log2(tpm.shape[1]) - entropy_bits(mean_row))
    ei = float(entropy_bits(mean_row) - determinism_loss)
    return {"ei": ei, "states": int(tpm.shape[0]), "eiPerLogStates": ei / np.log2(tpm.shape[0]),
            "meanRowEntropy": determinism_loss, "degeneracyGap": degeneracy_loss}


def counts(labels: np.ndarray, runs: np.ndarray, lag: int, states: int) -> np.ndarray:
    source = labels[runs, :-lag].ravel()
    target = labels[runs, lag:].ravel()
    matrix = np.zeros((states, states))
    np.add.at(matrix, (source, target), 1)
    return matrix


def micro_tpm(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rows and columns restricted to eligible states; transitions into ineligible states
    are dropped so that the TPM is square over the intervention support."""
    eligible = np.flatnonzero(matrix.sum(axis=1) >= MIN_ROW_COUNT)
    square = matrix[np.ix_(eligible, eligible)]
    if np.any(square.sum(axis=1) == 0):
        raise ValueError("eligible state with no transitions inside the support")
    return square / square.sum(axis=1, keepdims=True), eligible


def macro_tpm(tpm: np.ndarray, groups: np.ndarray) -> np.ndarray:
    labels = np.unique(groups)
    member = (groups[:, None] == labels[None, :]).astype(float)
    to_groups = tpm @ member
    return (member.T @ to_groups) / member.sum(axis=0)[:, None]


def feature_partitions(centroids8: np.ndarray, pca1: np.ndarray, macro_sizes: tuple[int, ...],
                       rng: np.random.Generator) -> dict[str, dict[int, np.ndarray]]:
    grid = centroids8.reshape(-1, 8, 8)
    quadrants = grid.reshape(-1, 2, 4, 2, 4).sum(axis=(2, 4)).reshape(-1, 4)
    axis = np.arange(8) + 0.5
    cy = (grid.sum(axis=2) * axis).sum(axis=1)
    cx = (grid.sum(axis=1) * axis).sum(axis=1)
    radius = np.sqrt((grid * ((axis[None, :, None] - cy[:, None, None]) ** 2
                              + (axis[None, None, :] - cx[:, None, None]) ** 2)).sum(axis=(1, 2)))
    result: dict[str, dict[int, np.ndarray]] = {"quadrantComposition": {}, "radius": {},
                                                "shapePC1": {}}
    for m in macro_sizes:
        seed = int(rng.integers(2**31))
        result["quadrantComposition"][m] = KMeans(m, n_init=8, random_state=seed).fit_predict(quadrants)
        for name, values in (("radius", radius), ("shapePC1", pca1)):
            ranks = np.argsort(np.argsort(values))
            result[name][m] = (ranks * m) // values.size
    return result


def hoel(store: dict, micro_sizes: tuple[int, ...], macro_sizes: tuple[int, ...],
         lags: tuple[int, ...]) -> list[dict]:
    rng = np.random.default_rng(SEED)
    flat = store["share8"].reshape(-1, 64)
    pca = PCA(PCA_COMPONENTS, random_state=SEED).fit(flat)
    projected = pca.transform(flat)
    groups_all = np.unique(store["group"])
    output = []
    for n in micro_sizes:
        km = KMeans(n, n_init=4, random_state=SEED).fit(projected)
        labels = km.labels_.reshape(store["share8"].shape[:2])
        centroids8 = np.stack([flat[km.labels_ == k].mean(axis=0) for k in range(n)])
        pca1 = km.cluster_centers_[:, 0]
        partitions = feature_partitions(centroids8, pca1, macro_sizes, rng)
        for subset_name, mask in subsets(store).items():
            runs = np.flatnonzero(mask)
            for lag in lags:
                tpm, eligible = micro_tpm(counts(labels, runs, lag, n))
                micro = effective_information(tpm)
                independent = independent_successor_floor(labels, runs, lag, n, eligible, rng)
                entry = {"microStates": n, "subset": subset_name, "lagRecords": lag,
                         "lagSteps": 4 * lag, "transitions": int(runs.size * (60 - lag)),
                         "micro": micro, "independentSuccessorEI": independent, "macro": []}
                for feature, by_size in partitions.items():
                    for m, assignment in by_size.items():
                        restricted = assignment[eligible]
                        if np.unique(restricted).size < 2:
                            raise ValueError(f"{feature} M={m} collapses on the eligible support")
                        macro = effective_information(macro_tpm(tpm, restricted))
                        sizes = np.bincount(np.unique(restricted, return_inverse=True)[1])
                        null = [effective_information(macro_tpm(tpm, random_partition(sizes, rng)))["ei"]
                                for _ in range(RANDOM_PARTITIONS)]
                        record = {"feature": feature, "macroStates": int(sizes.size),
                                  "macro": macro, "ce": macro["ei"] - micro["ei"],
                                  "randomPartitionEI": quantiles(null),
                                  "featureAboveRandomFraction": float(np.mean(np.asarray(null) < macro["ei"]))}
                        if subset_name == "all" and lag == lags[0]:
                            record["groupBootstrapCE"] = group_bootstrap_ce(
                                labels, store["group"], groups_all, mask, lag, n, assignment, rng)
                        entry["macro"].append(record)
                output.append(entry)
                print("hoel", n, subset_name, lag, round(micro["ei"], 3),
                      [(r["feature"], r["macroStates"], round(r["ce"], 3)) for r in entry["macro"]])
    return output


def random_partition(sizes: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return rng.permutation(np.repeat(np.arange(sizes.size), sizes))


def quantiles(values) -> dict:
    array = np.asarray(values)
    return {"q025": float(np.quantile(array, 0.025)), "median": float(np.median(array)),
            "q975": float(np.quantile(array, 0.975)), "max": float(array.max())}


def independent_successor_floor(labels, runs, lag, n, eligible, rng) -> float:
    """EI of a TPM whose successors are drawn from the pooled successor distribution with the
    observed row counts: the finite-sample EI of a system with no causal structure."""
    matrix = counts(labels, runs, lag, n)[np.ix_(eligible, eligible)]
    rows = matrix.sum(axis=1).astype(int)
    pooled = matrix.sum(axis=0) / matrix.sum()
    sampled = np.stack([rng.multinomial(r, pooled) for r in rows]).astype(float)
    return effective_information(sampled / sampled.sum(axis=1, keepdims=True))["ei"]


def group_bootstrap_ce(labels, group, groups_all, mask, lag, n, assignment, rng) -> dict:
    values = []
    for _ in range(GROUP_BOOTSTRAP):
        chosen = rng.choice(groups_all, size=groups_all.size, replace=True)
        runs = np.concatenate([np.flatnonzero(mask & (group == g)) for g in chosen])
        tpm, eligible = micro_tpm(counts(labels, runs, lag, n))
        restricted = assignment[eligible]
        values.append(effective_information(macro_tpm(tpm, restricted))["ei"]
                      - effective_information(tpm)["ei"])
    return quantiles(values) | {"positiveFraction": float(np.mean(np.asarray(values) > 0))}


def ridge_covariance(values: np.ndarray) -> np.ndarray:
    covariance = np.cov(values, rowvar=False, ddof=0)
    return covariance + np.eye(covariance.shape[0]) * RIDGE * np.trace(covariance) / covariance.shape[0]


def gaussian_mi(covariance: np.ndarray, first, second) -> float:
    joint = list(first) + list(second)
    blocks = [np.linalg.slogdet(covariance[np.ix_(g, g)]) for g in (list(first), list(second), joint)]
    if any(sign <= 0 or not np.isfinite(logdet) for sign, logdet in blocks):
        raise ValueError("covariance block not positive definite")
    return 0.5 * (blocks[0][1] + blocks[1][1] - blocks[2][1])


def macro_variables(share4: np.ndarray, pc1_axis: np.ndarray) -> dict[str, np.ndarray]:
    grid = share4.reshape(*share4.shape[:-1], 4, 4)
    quadrants = grid.reshape(*grid.shape[:-2], 2, 2, 2, 2).sum(axis=(-3, -1)).reshape(*grid.shape[:-2], 4)
    axis = np.arange(4) + 0.5
    cy = (grid.sum(axis=-1) * axis).sum(axis=-1)
    cx = (grid.sum(axis=-2) * axis).sum(axis=-1)
    dy = axis[:, None] - cy[..., None, None]
    dx = axis[None, :] - cx[..., None, None]
    moments = np.stack([(grid * dy * dy).sum(axis=(-2, -1)), (grid * dx * dx).sum(axis=(-2, -1)),
                        (grid * dy * dx).sum(axis=(-2, -1))], axis=-1)
    return {"quadrantShares": quadrants[..., :3], "secondMoments": moments,
            "sharePC1": (share4 @ pc1_axis)[..., None]}


def rosas_terms(parts: np.ndarray, macro: np.ndarray, runs: np.ndarray, lag: int) -> dict:
    x_now = parts[runs, :-lag].reshape(-1, parts.shape[-1])
    x_next = parts[runs, lag:].reshape(-1, parts.shape[-1])
    v_now = macro[runs, :-lag].reshape(-1, macro.shape[-1])
    v_next = macro[runs, lag:].reshape(-1, macro.shape[-1])
    values = np.column_stack((x_now, x_next, v_now, v_next))
    values = (values - values.mean(axis=0)) / values.std(axis=0)
    covariance = ridge_covariance(values)
    k, d = parts.shape[-1], macro.shape[-1]
    xn, xf = list(range(k)), list(range(k, 2 * k))
    vn, vf = list(range(2 * k, 2 * k + d)), list(range(2 * k + d, 2 * k + 2 * d))
    self_info = gaussian_mi(covariance, vn, vf)
    part_to_macro = [gaussian_mi(covariance, [xn[j]], vf) for j in range(k)]
    downward = [gaussian_mi(covariance, vn, [xf[j]])
                - sum(gaussian_mi(covariance, [xn[i]], [xf[j]]) for i in range(k)) for j in range(k)]
    return {"psi": self_info - sum(part_to_macro), "macroSelfInformation": self_info,
            "sumPartToMacro": float(sum(part_to_macro)), "delta": float(max(downward)),
            "gamma": float(max(part_to_macro))}


def rosas(store: dict, lags: tuple[int, ...]) -> list[dict]:
    rng = np.random.default_rng(SEED + 1)
    share4 = store["share4"]
    pc1_axis = PCA(1, random_state=SEED).fit(share4.reshape(-1, 16)).components_[0]
    macros = macro_variables(share4, pc1_axis)
    groups_all = np.unique(store["group"])
    output = []
    for subset_name, mask in subsets(store).items():
        runs = np.flatnonzero(mask)
        for name, macro in macros.items():
            for lag in lags:
                observed = rosas_terms(share4, macro, runs, lag)
                boot = []
                for _ in range(GROUP_BOOTSTRAP):
                    chosen = rng.choice(groups_all, size=groups_all.size, replace=True)
                    sample = np.concatenate([np.flatnonzero(mask & (store["group"] == g)) for g in chosen])
                    boot.append(rosas_terms(share4, macro, sample, lag))
                entry = {"subset": subset_name, "macro": name, "lagRecords": lag, "lagSteps": 4 * lag,
                         **observed,
                         "bootstrap": {key: quantiles([b[key] for b in boot])
                                       for key in ("psi", "delta", "gamma")},
                         "psiPositiveFraction": float(np.mean([b["psi"] > 0 for b in boot]))}
                output.append(entry)
                print("rosas", subset_name, name, lag, round(observed["psi"], 3),
                      round(observed["delta"], 3), round(observed["gamma"], 3))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    store = load(args.measurements)
    result = {
        "settings": {"minRowCount": MIN_ROW_COUNT, "pcaComponents": PCA_COMPONENTS,
                     "randomPartitions": RANDOM_PARTITIONS, "groupBootstrap": GROUP_BOOTSTRAP,
                     "ridge": RIDGE, "seed": SEED, "earlyAges": EARLY, "lateAges": LATE},
        "hoel": hoel(store, (32, 64, 128), (4, 8, 16), (1, 4)),
        "rosas": rosas(store, (1, 4)),
    }
    args.output.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
