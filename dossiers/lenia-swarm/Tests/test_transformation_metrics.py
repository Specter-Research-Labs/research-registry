from __future__ import annotations

import numpy as np
import pytest

from lenia_swarm_analysis.transformation_metrics import (
    fingerprint_metrics,
    label_bodies,
    robust_center_scale,
)

ARENA_DEPENDENT = {"centerOffset"}


def _body() -> np.ndarray:
    """A lopsided ring with a tail and a detached blob: two bodies, one hole, no symmetry."""
    image = np.zeros((32, 32), dtype=np.float64)
    image[8:20, 9:21] = 1.0
    image[11:16, 12:18] = 0.0
    image[19:27, 14:16] = 1.0
    image[4:7, 24:28] = 1.0
    ys, xs = np.nonzero(image)
    image[ys, xs] = 40.0 + 7.0 * ((3 * ys + 5 * xs) % 11)
    return image


def _assert_same_shape_metrics(lhs: dict[str, float], rhs: dict[str, float]) -> None:
    assert lhs.keys() == rhs.keys()
    for key in lhs.keys() - ARENA_DEPENDENT:
        assert lhs[key] == pytest.approx(rhs[key], abs=1e-12), key


def test_bodies_are_8_connected_and_holes_4_connected() -> None:
    diagonal = np.zeros((5, 5), dtype=bool)
    diagonal[1, 1] = diagonal[2, 2] = True
    assert label_bodies(diagonal)[1] == 1

    diamond = np.zeros((9, 9), dtype=np.float64)
    for y, x in [(2, 4), (3, 3), (3, 5), (4, 2), (4, 6), (5, 3), (5, 5), (6, 4)]:
        diamond[y, x] = 100.0
    metrics = fingerprint_metrics(diamond, specimen_id="diamond")
    assert metrics["componentCount"] == 1.0
    assert metrics["cavityCount"] == 1.0


def test_reference_body_counts() -> None:
    metrics = fingerprint_metrics(_body(), specimen_id="body")
    assert metrics["componentCount"] == 2.0
    assert metrics["cavityCount"] == 1.0


@pytest.mark.parametrize(
    "pad",
    [((8, 8), (8, 8)), ((32, 32), (32, 32)), ((0, 4), (6, 0)), ((10, 2), (4, 12))],
)
def test_shape_metrics_ignore_surrounding_empty_arena(pad) -> None:
    ys, xs = np.nonzero(_body())
    body = _body()[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    padded = np.pad(body, pad)
    _assert_same_shape_metrics(
        fingerprint_metrics(body, specimen_id="body"),
        fingerprint_metrics(padded, specimen_id="padded"),
    )


@pytest.mark.parametrize("shift", [(3, -2), (-4, 1), (2, 2)])
def test_shape_metrics_ignore_translation(shift) -> None:
    body = _body()
    moved = np.roll(body, shift, axis=(0, 1))
    _assert_same_shape_metrics(
        fingerprint_metrics(body, specimen_id="body"),
        fingerprint_metrics(moved, specimen_id="moved"),
    )


def test_topology_survives_resolution_doubling() -> None:
    body = _body()
    upsampled = np.kron(body, np.ones((2, 2)))
    coarse = fingerprint_metrics(body, specimen_id="coarse")
    fine = fingerprint_metrics(upsampled, specimen_id="fine")
    assert fine["componentCount"] == coarse["componentCount"]
    assert fine["cavityCount"] == coarse["cavityCount"]


def test_empty_fingerprint_is_refused() -> None:
    with pytest.raises(SystemExit, match="empty fingerprint"):
        fingerprint_metrics(np.zeros((32, 32)), specimen_id="empty")


def test_dust_fingerprint_is_refused() -> None:
    dust = np.zeros((32, 32))
    dust[::4, ::4] = 1.0
    with pytest.raises(SystemExit, match="the body is dust"):
        fingerprint_metrics(dust, specimen_id="dust")


def test_robust_scale_records_its_estimator() -> None:
    mad = robust_center_scale([1.0, 2.0, 3.0, 4.0, 10.0])
    assert mad.estimator == "mad"
    assert mad.center == 3.0
    assert mad.scale == pytest.approx(1.4826)

    std = robust_center_scale([0.0, 0.0, 0.0, 0.0, 5.0])
    assert std.estimator == "std"
    assert std.center == 0.0
    assert std.scale == pytest.approx(2.0)

    constant = robust_center_scale([2.5, 2.5, 2.5])
    assert constant == (2.5, 1.0, "constant")
