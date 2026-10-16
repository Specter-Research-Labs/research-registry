"""Algotype clustering on a recorded per-swap trajectory, scored against a label-permutation null.

The max of C(t) over a long noisy trajectory sits well above the random-mixing baseline even
for identical algorithms, so the raw max is not evidence of clustering. The null shuffles which
values carry which algotype label and rescores the same value trajectory, holding trajectory
length and sorting dynamics fixed and asking only whether the cells that end up adjacent depend
on their type.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

N_PERMUTATIONS = 200


def adjacent_match_fraction(labels: Sequence[object]) -> float:
    matches = sum(1 for i in range(len(labels) - 1) if labels[i] == labels[i + 1])
    return matches / (len(labels) - 1)


def exact_mixing_null(labels: Sequence[object]) -> float:
    n = len(labels)
    counts = [labels.count(label) for label in set(labels)]
    return sum(k * (k - 1) for k in counts) / (n * (n - 1))


def _clustering_curves(value_trajectory: np.ndarray, label_of_value: np.ndarray) -> np.ndarray:
    labels = label_of_value[value_trajectory]
    return (labels[..., :-1] == labels[..., 1:]).mean(axis=-1)


def score_trajectory(
    value_trajectory: list[list[int]],
    value_labels: dict[int, object],
    *,
    permutation_seed: int,
) -> dict[str, float]:
    """Score clustering on `value_trajectory` (one row of cell values per recorded state).

    Values must be the distinct integers 0..n-1, which is what every clustering experiment here
    uses, so that a label assignment is an array indexed by value.
    """
    trajectory = np.asarray(value_trajectory, dtype=np.int64)
    n = trajectory.shape[1]
    if sorted(value_labels) != list(range(n)):
        raise ValueError("value_labels must cover exactly the values 0..n-1")
    label_names = sorted({str(label) for label in value_labels.values()})
    label_of_value = np.array(
        [label_names.index(str(value_labels[v])) for v in range(n)], dtype=np.int64
    )

    observed = _clustering_curves(trajectory, label_of_value)
    rng = np.random.default_rng(permutation_seed)
    null_max = np.empty(N_PERMUTATIONS)
    null_mean = np.empty(N_PERMUTATIONS)
    for k in range(N_PERMUTATIONS):
        curve = _clustering_curves(trajectory, rng.permutation(label_of_value))
        null_max[k] = curve.max()
        null_mean[k] = curve.mean()

    observed_max = float(observed.max())
    observed_mean = float(observed.mean())
    return {
        "n_states": int(trajectory.shape[0]),
        "max_clustering": observed_max,
        "mean_clustering": observed_mean,
        "exact_mixing_null": exact_mixing_null(list(label_of_value)),
        "perm_null_max": float(null_max.mean()),
        "perm_null_mean": float(null_mean.mean()),
        "excess_max": observed_max - float(null_max.mean()),
        "excess_mean": observed_mean - float(null_mean.mean()),
        "perm_p_max": float((1 + np.sum(null_max >= observed_max)) / (1 + N_PERMUTATIONS)),
    }
