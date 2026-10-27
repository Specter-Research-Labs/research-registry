import base64
import json
import math

import numpy as np
import pytest

from lenia_swarm_analysis.morphospace.regeneration import (
    circular_centre,
    cut_state,
    reshape_state,
    retire_restart_fields,
)


def _body_across_seam(n=64):
    rng = np.random.default_rng(0)
    state = np.zeros((n, n, 2), dtype=np.float32)
    rows = (np.arange(-6, 7) + n) % n
    cols = np.arange(20, 34)
    state[np.ix_(rows, cols)] = rng.uniform(0.1, 1.0, (len(rows), len(cols), 2))
    return state


def test_cut_removes_target_fraction_on_the_far_side_of_a_body_split_by_the_seam():
    state = _body_across_seam()
    cut, removed = cut_state(state, 0.0, 0.25)
    mass = state.sum(axis=-1)
    assert abs(removed - 0.25) <= mass.max() / mass.sum()
    zeroed = (mass > 0) & (cut.sum(axis=-1) == 0)
    assert set(np.flatnonzero(zeroed.any(axis=1))) <= {3, 4, 5, 6}
    np.testing.assert_array_equal(cut[~zeroed], state[~zeroed])


def test_opposite_cuts_remove_opposite_sides():
    state = _body_across_seam()
    plus = cut_state(state, math.pi / 2, 0.5)[0].sum(axis=-1) == 0
    minus = cut_state(state, -math.pi / 2, 0.5)[0].sum(axis=-1) == 0
    occupied = state.sum(axis=-1) > 0
    assert not (plus & minus & occupied).any()
    assert np.flatnonzero((plus & occupied).any(axis=0)).min() > np.flatnonzero((minus & occupied).any(axis=0)).max() - 1


def _gyration_and_axis(field):
    mass = field.sum(axis=-1, dtype=np.float64)
    offsets = [(np.arange(n) - c + n / 2) % n - n / 2 for n, c in zip(mass.shape, circular_centre(mass), strict=True)]
    d0, d1 = np.meshgrid(*offsets, indexing="ij")
    w = mass / mass.sum()
    cov = np.array([[np.sum(w * a * b) for b in (d0, d1)] for a in (d0, d1)])
    values, vectors = np.linalg.eigh(cov)
    return math.sqrt(np.trace(cov)), vectors[:, int(np.argmax(values))], values.max() / values.min()


@pytest.mark.parametrize("profile", ["gauss", "ellipse"])
def test_reshape_keeps_channel_mass_centre_size_and_axis(profile):
    state = _body_across_seam(128)
    shaped = reshape_state(state, profile, 3.0)
    np.testing.assert_allclose(shaped.sum(axis=(0, 1)), state.sum(axis=(0, 1)), rtol=1e-5)
    np.testing.assert_allclose(circular_centre(shaped.sum(axis=-1)), circular_centre(state.sum(axis=-1)), atol=0.5)
    size, axis, ratio = _gyration_and_axis(shaped)
    body_size, body_axis, _ = _gyration_and_axis(state)
    assert abs(size - body_size) / body_size < 0.05
    assert abs(abs(axis @ body_axis) - 1) < 1e-3
    assert abs(math.sqrt(ratio) - 3.0) < 0.3
    visible = shaped.sum(axis=-1) > shaped.sum(axis=-1).max() / 255
    ratios = shaped[visible, 0] / shaped[visible, 1]
    assert ratios.std() < 1e-4 * ratios.mean()


def test_ellipse_is_flat_and_gauss_peaks():
    state = _body_across_seam(128)
    flat = reshape_state(state, "ellipse", 2.0).sum(axis=-1)
    peaked = reshape_state(state, "gauss", 2.0).sum(axis=-1)
    assert np.unique(flat[flat > 0].round(5)).size == 1
    assert peaked.max() > 4 * np.median(peaked[peaked > peaked.max() / 255])


def _restart_cell(root, restarts):
    for i, (body, _) in enumerate(restarts):
        d = root / "campaigns" / f"{i + 1:04d}-{body}"
        d.mkdir(parents=True)
        (d / "replay-manifest.json").write_text(json.dumps({"sourceCreatureId": body}))
        field = base64.b64encode(np.zeros(16, dtype="<f2").tobytes()).decode()
        frames = [{"step": s, "stateSha256": f"{body}-{s}", "fieldResolution": 4, "fieldF16Base64": field} for s in (400, 800)]
        (d / "development-trace.jsonl").write_text("".join(json.dumps(f) + "\n" for f in frames))
    shapes = root / "shapes.npz"
    np.savez(shapes, body=np.array([b for b, _ in restarts]), condition=np.array([c for _, c in restarts]),
             state_sha256=np.array([[f"{b}-400", f"{b}-800"] for b, _ in restarts]))
    return shapes


def test_retire_restart_fields_strips_measured_traces_and_keeps_named_restarts(tmp_path):
    shapes = _restart_cell(tmp_path, [("A", "control"), ("A", "cut-a0-f0.5")])
    kept = (tmp_path / "campaigns/0002-A/development-trace.jsonl").read_bytes()
    summary = retire_restart_fields(replay_root=tmp_path, shapes=shapes, keep=["A:cut-a0-f0.5"],
                                    manifest_path=tmp_path / "manifest.json", apply=True)
    assert (summary["stripped"], summary["kept"]) == (1, 1)
    assert (tmp_path / "campaigns/0002-A/development-trace.jsonl").read_bytes() == kept
    frames = [json.loads(line) for line in (tmp_path / "campaigns/0001-A/development-trace.jsonl").read_text().splitlines()]
    assert "fieldF16Base64" not in frames[0] and "fieldF16Base64" in frames[1]
    assert all("fieldF16Sha256" in f for f in frames)


def test_retire_restart_fields_refuses_unmeasured_traces(tmp_path):
    shapes = _restart_cell(tmp_path, [("A", "control")])
    trace = tmp_path / "campaigns/0001-A/development-trace.jsonl"
    frames = [json.loads(line) for line in trace.read_text().splitlines()]
    frames[1]["stateSha256"] = "other"
    trace.write_text("".join(json.dumps(f) + "\n" for f in frames))
    with pytest.raises(ValueError, match="do not match"):
        retire_restart_fields(replay_root=tmp_path, shapes=shapes, keep=[],
                              manifest_path=tmp_path / "manifest.json", apply=True)
