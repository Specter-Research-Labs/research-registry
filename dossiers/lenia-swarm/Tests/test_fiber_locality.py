from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.anatomical_compiler.fiber_locality import (
    KERNEL_WIDTH,
    Cohort,
    Symmetry,
    _rule_vectors,
    locality,
    mle_dimension,
    phenotype_neighbours,
    pinning,
    quotient_distance,
    rule_floor,
    twonn,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fiber_locality_rule_2c10.json")
                     .read_text())


def _cohort(raw: np.ndarray, shape: np.ndarray) -> Cohort:
    n = raw.shape[0]
    return Cohort(np.arange(n), raw.astype(np.float32), raw.astype(np.float32), shape,
                  np.zeros((n, 2)), np.ones(n, dtype=bool))


def _apply(rule: np.ndarray, symmetry: Symmetry, relabel: tuple[int, ...],
           rng: np.random.Generator) -> np.ndarray:
    kernels = rule[:-1].reshape(-1, KERNEL_WIDTH)
    out = np.empty_like(kernels)
    for (source, target), index in symmetry.blocks.items():
        out[symmetry.blocks[(relabel[source], relabel[target])]] = kernels[rng.permutation(index)]
    return np.append(out.ravel(), rule[-1])


def test_symmetry_reads_engine_wiring() -> None:
    symmetry = Symmetry.from_connectivity([[3, 2], [2, 3]])
    assert [list(v) for v in symmetry.blocks.values()] == [[0, 1, 2], [3, 4], [5, 6], [7, 8, 9]]
    assert symmetry.relabelings == ((0, 1), (1, 0))
    assert Symmetry.from_connectivity([[3, 1], [2, 3]]).relabelings == ((0, 1),)
    assert len(Symmetry.from_connectivity([[3, 1, 1], [1, 3, 1], [1, 1, 3]]).relabelings) == 6


def test_quotient_distance_is_blind_to_the_rule_symmetry() -> None:
    rng = np.random.default_rng(0)
    symmetry = Symmetry.from_connectivity(FIXTURE["connectivity"])
    raw, _ = _rule_vectors(FIXTURE, FIXTURE["ranges"])
    moved = _apply(raw, symmetry, (1, 0), rng)
    other = rng.uniform(0.0, 1.0, raw.shape)

    d = quotient_distance(np.stack([raw, raw]), np.stack([moved, other]), symmetry)

    assert d[0] == pytest.approx(0.0, abs=1e-12)
    assert np.linalg.norm(raw - moved) > 1.0
    assert 0.0 < d[1] <= np.linalg.norm(raw - other)


def test_rule_vectors_recover_the_stored_canonical_descriptor() -> None:
    raw, canonical = _rule_vectors(FIXTURE, FIXTURE["ranges"])
    lo, hi = FIXTURE["ranges"]["m"]
    assert raw[1] == pytest.approx((FIXTURE["params"]["m"][0] - lo) / (hi - lo))
    assert sorted(raw.tolist()) == pytest.approx(sorted(canonical.tolist()))

    tampered = copy.deepcopy(FIXTURE)
    tampered["params"]["m"][0] += 0.01
    with pytest.raises(SystemExit, match="not a kernel permutation"):
        _rule_vectors(tampered, FIXTURE["ranges"])


def test_phenotype_neighbours_drop_the_anchor_among_identical_bodies() -> None:
    phenotype = np.zeros((6, 2))
    index, distance = phenotype_neighbours(phenotype, np.arange(6), 3)
    assert index.shape == (6, 3)
    assert not np.any(index == np.arange(6)[:, None])
    assert np.all(distance == 0.0)


def test_locality_separates_an_informative_body_from_noise() -> None:
    rng = np.random.default_rng(1)
    raw = rng.uniform(0.0, 1.0, (3000, 2 * KERNEL_WIDTH + 1))
    symmetry = Symmetry.from_connectivity([[1, 0], [0, 1]])
    informative = _cohort(raw, raw[:, :4])
    blind = _cohort(raw, rng.normal(0.0, 1.0, (3000, 4)))
    anchors = np.arange(500)

    near = locality(informative, informative.shape, anchors, ("raw", "quotient"), symmetry, rng)
    null = locality(blind, blind.shape, anchors, ("raw",), symmetry, rng)

    # Four of 27 coordinates fully pinned move the ratio only to about 0.92: the ratio is
    # diluted by every coordinate the body ignores.
    assert near["raw"]["ratio"]["5"] < 0.95
    assert near["quotient"]["ratio"]["5"] < 0.95
    assert null["raw"]["ratio"]["5"] == pytest.approx(1.0, abs=0.02)
    assert near["raw"]["per_anchor"].shape == (500, 100)


def test_pinning_finds_the_coordinate_the_body_reads() -> None:
    rng = np.random.default_rng(2)
    raw = rng.uniform(0.0, 1.0, (4000, 2 * KERNEL_WIDTH + 1))
    cohort = _cohort(raw, raw[:, -1:])

    out = pinning(cohort, cohort.shape, np.arange(4000))

    assert out["invariants"]["R"] > 0.99
    assert next(iter(out["coordinates_top"])) == "R"
    assert out["invariants"]["mean_m"] == pytest.approx(out["null"], abs=0.1)


def test_intrinsic_dimension_of_a_flat_sheet() -> None:
    rng = np.random.default_rng(3)
    sheet = np.zeros((4000, 10))
    sheet[:, :3] = rng.uniform(0.0, 1.0, (4000, 3))
    assert twonn(sheet) == pytest.approx(3.0, abs=0.4)
    assert mle_dimension(sheet) == pytest.approx(3.0, abs=0.4)
    with pytest.raises(ValueError, match="duplicate"):
        twonn(np.zeros((20, 3)))


def test_rule_floor_is_reached_when_the_body_is_the_rule() -> None:
    rng = np.random.default_rng(4)
    raw = rng.uniform(0.0, 1.0, (2000, 2 * KERNEL_WIDTH + 1))
    symmetry = Symmetry.from_connectivity([[1, 0], [0, 1]])
    mirror = _cohort(raw, raw)
    anchors = np.arange(300)

    near = locality(mirror, mirror.shape, anchors, ("raw",), symmetry, rng)
    floor = rule_floor(mirror, anchors, "raw").mean(axis=0) / near["raw"]["random_pair_distance"]

    assert floor[4] == pytest.approx(near["raw"]["ratio"]["5"], rel=1e-9)
    assert floor[0] < near["raw"]["ratio"]["5"] < 1.0
