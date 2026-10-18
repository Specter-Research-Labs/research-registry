import json

import numpy as np
import pytest

from lenia_swarm_analysis.morphospace import creature_definition as cd


def blob(n: int, centre: tuple[float, float], sigma: float) -> np.ndarray:
    y, x = np.mgrid[:n, :n]
    return np.exp(-((y - centre[0]) ** 2 + (x - centre[1]) ** 2) / (2 * sigma**2))


def series(fields: list[np.ndarray], reach: float) -> dict[str, np.ndarray]:
    frames = [cd.frame_measures(f, reach=reach, border="torus", arena=None) for f in fields]
    return {k: np.array([f[k] for f in frames]) for k in frames[0]}


def test_kernel_reach_uses_outermost_weighted_ring():
    params = {"R": 10.0, "r": [0.5, 1.0], "a": [[0.9, 0.2]], "b": [[1.0, 0.0]], "w": [[0.1, 0.5]]}
    params["a"].append([0.5, 0.9])
    params["b"].append([1.0, 0.0])
    params["w"].append([0.1, 0.3])
    assert cd.kernel_reach(params) == pytest.approx(10.0 * 1.0 * (0.5 + 3 * 0.1))


def test_haze_outside_reach_is_not_captured():
    f = blob(128, (64, 64), 3.0)
    f[5, 5] = f.sum() / 9
    m = cd.frame_measures(f, reach=10.0, border="torus", arena=None)
    assert m["captured"] == pytest.approx(0.9, abs=1e-3)
    assert m["substantial_bodies"] == 2


def test_lobes_within_reach_form_one_body_and_wrap_on_torus():
    f = blob(128, (64, 1), 2.0) + blob(128, (64, 127), 2.0) + blob(128, (64, 10), 2.0)
    m = cd.frame_measures(f, reach=12.0, border="torus", arena=None)
    assert m["substantial_bodies"] == 1
    assert m["captured"] == pytest.approx(1.0)


def test_wall_field_requires_arena_mask():
    with pytest.raises(ValueError):
        cd.frame_measures(blob(32, (16, 16), 2.0), reach=4.0, border="wall", arena=None)


def test_wall_clearance_counts_from_capture_zone():
    arena = np.zeros((64, 64), dtype=bool)
    arena[:, 10:] = True
    m = cd.frame_measures(blob(64, (32, 30), 1.0), reach=5.0, border="wall", arena=arena)
    assert 13 <= m["wall_clearance"] <= 16


def test_stationary_body_settles_and_spreading_body_does_not():
    steps = np.arange(400, 40001, 400, dtype=float)
    still = series([blob(96, (48, 48), 3.0) for _ in steps], reach=10.0)
    spread = series(
        [blob(96, (48, 48), 3.0) + blob(96, (48, 48), 3.0 + 0.05 * i) for i, _ in enumerate(steps)],
        reach=10.0,
    )
    adult = cd.adult_phase(steps, still, cd.PROVISIONAL)
    assert adult["onset_step"] == 400
    assert min(adult["lifetime_runs"].values()) > 100
    assert cd.adult_phase(steps, spread, cd.PROVISIONAL)["onset_step"] != 400


def test_adult_phase_rejects_uneven_cadence():
    steps = np.array([0.0, 1.0, 3.0])
    with pytest.raises(ValueError):
        cd.adult_phase(steps, {k: np.zeros(3) for k in cd.DESCRIPTORS}, cd.PROVISIONAL)


def write_assessment(path, arena, border, passes):
    bodies = [
        {"body": b, "arena": arena, "border": border, "intrinsic_creature": p}
        for b, p in passes.items()
    ]
    path.write_text(json.dumps({"bodies": bodies}))
    return path


def test_ensemble_labels_creature_unstable_and_non_creature(tmp_path):
    small = write_assessment(tmp_path / "a.json", 256, "torus", {"A": True, "B": True, "C": False})
    large = write_assessment(tmp_path / "b.json", 512, "torus", {"A": True, "B": False, "C": False})
    result = cd.classify_ensemble(assessments=[small, large], output_path=tmp_path / "out.json")
    verdicts = json.loads((tmp_path / "out.json").read_text())["bodies"]
    assert [verdicts[b]["verdict"] for b in "ABC"] == ["creature", "unstable", "not_creature"]
    assert (result["creature"], result["unstable"], result["not_creature"]) == (1, 1, 1)


def test_ensemble_rejects_walled_runs_and_single_size(tmp_path):
    torus = write_assessment(tmp_path / "a.json", 256, "torus", {"A": True})
    wall = write_assessment(tmp_path / "b.json", 512, "wall", {"A": True})
    with pytest.raises(ValueError):
        cd.classify_ensemble(assessments=[torus, wall], output_path=tmp_path / "out.json")
    with pytest.raises(ValueError):
        cd.classify_ensemble(assessments=[torus], output_path=tmp_path / "out.json")


def test_lifetime_is_time_to_lose_half_at_adult_rate():
    steps = np.arange(400, 40001, 400, dtype=float)
    flat = {k: np.ones_like(steps) for k in cd.DESCRIPTORS}
    leaking = {**flat, "captured": 1.0 - steps * 1e-6}
    adult = cd.adult_phase(steps, leaking, cd.PROVISIONAL)
    assert adult["lifetime_runs"]["captured"] == pytest.approx(0.5 * 0.97 / 1e-6 / 40000, rel=0.02)
    assert adult["lifetime_runs"]["body_radius"] > 1e6
