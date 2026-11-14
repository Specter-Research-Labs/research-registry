import dataclasses
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


PROVISIONAL_JSON = json.loads(json.dumps(dataclasses.asdict(cd.PROVISIONAL)))


def write_assessment(path, arena, border, passes, *, engine="engine-a", thresholds=None):
    bodies = [
        {"body": b, "arena": arena, "border": border, "intrinsic_creature": p}
        for b, p in passes.items()
    ]
    data = {
        "engine": engine,
        "thresholds": PROVISIONAL_JSON if thresholds is None else thresholds,
        "core_level": cd.CORE_LEVEL,
        "bodies": bodies,
    }
    path.write_text(json.dumps(data))
    return path


def test_ensemble_labels_creature_unstable_and_non_creature(tmp_path):
    small = write_assessment(tmp_path / "a.json", 256, "torus", {"A": True, "B": True, "C": False})
    large = write_assessment(tmp_path / "b.json", 512, "torus", {"A": True, "B": False, "C": False})
    result = cd.classify_ensemble(assessments=[small, large], output_path=tmp_path / "out.json")
    out = json.loads((tmp_path / "out.json").read_text())
    assert [out["bodies"][b]["verdict"] for b in "ABC"] == ["creature", "unstable", "not_creature"]
    assert (result["creature"], result["unstable"], result["not_creature"]) == (1, 1, 1)
    assert (out["engine"], out["thresholds"], out["core_level"]) == (
        "engine-a",
        PROVISIONAL_JSON,
        cd.CORE_LEVEL,
    )


def test_ensemble_rejects_walled_runs_and_single_size(tmp_path):
    torus = write_assessment(tmp_path / "a.json", 256, "torus", {"A": True})
    wall = write_assessment(tmp_path / "b.json", 512, "wall", {"A": True})
    with pytest.raises(ValueError):
        cd.classify_ensemble(assessments=[torus, wall], output_path=tmp_path / "out.json")
    with pytest.raises(ValueError):
        cd.classify_ensemble(assessments=[torus], output_path=tmp_path / "out.json")


def test_ensemble_refuses_ambiguous_joins(tmp_path):
    small = write_assessment(tmp_path / "a.json", 256, "torus", {"A": True})
    large = write_assessment(tmp_path / "b.json", 512, "torus", {"A": True})
    twice = tmp_path / "twice.json"
    data = json.loads(large.read_text())
    data["bodies"].append({**data["bodies"][0], "intrinsic_creature": False})
    twice.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="assessed more than once"):
        cd.classify_ensemble(assessments=[small, twice], output_path=tmp_path / "out.json")
    loose = {**PROVISIONAL_JSON, "min_captured": 0.9}
    other_thresholds = write_assessment(
        tmp_path / "c.json", 512, "torus", {"A": True}, thresholds=loose
    )
    with pytest.raises(ValueError, match="other thresholds"):
        cd.classify_ensemble(
            assessments=[small, other_thresholds], output_path=tmp_path / "out.json"
        )
    other_engine = write_assessment(tmp_path / "d.json", 512, "torus", {"A": True}, engine="engine-b")
    with pytest.raises(ValueError, match="engine engine-b, not engine-a"):
        cd.classify_ensemble(assessments=[small, other_engine], output_path=tmp_path / "out.json")


def test_ensemble_names_the_engine_of_legacy_assessments_only_when_told(tmp_path):
    paths = []
    for name, arena in (("a.json", 256), ("b.json", 512)):
        path = write_assessment(tmp_path / name, arena, "torus", {"A": True})
        data = json.loads(path.read_text())
        del data["engine"]
        path.write_text(json.dumps(data))
        paths.append(path)
    with pytest.raises(ValueError, match="pass --engine-id"):
        cd.classify_ensemble(assessments=paths, output_path=tmp_path / "out.json")
    result = cd.classify_ensemble(
        assessments=paths, output_path=tmp_path / "out.json", legacy_engine_id="legacy"
    )
    assert result["engine"] == "legacy"
    current = write_assessment(tmp_path / "c.json", 512, "torus", {"A": True})
    with pytest.raises(ValueError, match="contradicts"):
        cd.classify_ensemble(
            assessments=[paths[0], current],
            output_path=tmp_path / "out.json",
            legacy_engine_id="legacy",
        )


def replay_campaigns(root, manifests):
    campaigns = []
    for i, manifest in enumerate(manifests):
        campaign = root / "campaigns" / f"{i:04d}"
        campaign.mkdir(parents=True)
        (campaign / "replay-manifest.json").write_text(json.dumps(manifest))
        campaigns.append(campaign)
    return campaigns


def test_replay_engine_reads_tt_manifests_or_the_receipt(tmp_path):
    tt = tmp_path / "tt"
    campaigns = replay_campaigns(tt, [{"sourceCreatureId": "A", "engine": "tt-sfpu-fp32"}] * 2)
    assert cd.replay_engine(tt, campaigns, legacy_engine_id=None) == "tt-sfpu-fp32"
    with pytest.raises(ValueError, match="contradicts"):
        cd.replay_engine(tt, campaigns, legacy_engine_id="other")

    mixed = tmp_path / "mixed"
    campaigns = replay_campaigns(
        mixed, [{"sourceCreatureId": "A", "engine": "tt-sfpu-fp32"}, {"sourceCreatureId": "B"}]
    )
    with pytest.raises(ValueError, match="disagree"):
        cd.replay_engine(mixed, campaigns, legacy_engine_id=None)

    metal = tmp_path / "metal"
    campaigns = replay_campaigns(metal, [{"sourceCreatureId": "A"}])
    with pytest.raises(ValueError, match="pass --engine-id"):
        cd.replay_engine(metal, campaigns, legacy_engine_id=None)
    assert cd.replay_engine(metal, campaigns, legacy_engine_id="legacy") == "legacy"
    (metal / "receipt.json").write_text(
        json.dumps({"receipt_version": 1, "engine_id": "e-metal", "build": {"source_commit": "a"}})
    )
    assert cd.replay_engine(metal, campaigns, legacy_engine_id=None) == "e-metal"

    (tt / "receipt.json").write_text((metal / "receipt.json").read_text())
    with pytest.raises(ValueError, match="one engine record"):
        cd.replay_engine(tt, sorted((tt / "campaigns").iterdir()), legacy_engine_id=None)


def sweep_body(body, arena, radius_slope):
    """A body whose radius creeps at `radius_slope` per step while every other descriptor holds."""
    steps = np.arange(400, 40001, 400, dtype=float)
    flat = np.ones_like(steps)
    series = {
        "captured": 0.99 * flat,
        "body_share": 0.9 * flat,
        "body_radius": 9.6 + radius_slope * steps,
        "captured_radius95": 15.0 * flat,
        "substantial_bodies": flat,
        "second_moment": 50.0 * flat,
    }
    record = {
        "body": body,
        "arena": arena,
        "border": "torus",
        "field_scale": 1.0,
        "steps": steps.astype(int).tolist(),
        "series": {k: v.tolist() for k, v in series.items()},
    }
    record["intrinsic_creature"] = cd._intrinsic_pass(record, cd.PROVISIONAL)
    return record


def test_sweep_reports_stable_bodies_and_where_others_flip(tmp_path):
    paths = []
    for arena in (256, 512):
        path = tmp_path / f"a{arena}.json"
        bodies = [sweep_body("steady", arena, 0.0), sweep_body("creeping", arena, 2.08e-5)]
        path.write_text(
            json.dumps(
                {
                    "engine": "engine-a",
                    "thresholds": PROVISIONAL_JSON,
                    "core_level": cd.CORE_LEVEL,
                    "bodies": bodies,
                }
            )
        )
        paths.append(path)
    summary = cd.sweep_thresholds(assessments=paths, output_path=tmp_path / "sweep.json")
    assert summary["provisional"] == {"creature": 2, "unstable": 0, "not_creature": 0}
    assert summary["settings"] == sum(len(v) for v in cd.SWEEP_GRID.values())
    assert summary["stable"] == 1
    out = json.loads((tmp_path / "sweep.json").read_text())
    assert out["bodies"]["steady"] == {
        "provisional": "creature",
        "flips": 0,
        "stable": True,
        "flipped_settings": [],
    }
    assert out["bodies"]["creeping"]["flipped_settings"] == [
        {"knob": "min_lifetime_runs", "value": 7.5, "verdict": "not_creature"},
        {"knob": "min_lifetime_runs", "value": 10.0, "verdict": "not_creature"},
    ]
    assert out["engine"] == "engine-a"

    data = json.loads(paths[1].read_text())
    data["bodies"][1]["intrinsic_creature"] = False
    paths[1].write_text(json.dumps(data))
    with pytest.raises(ValueError, match="no longer reproduces"):
        cd.sweep_thresholds(assessments=paths, output_path=tmp_path / "sweep.json")


def test_lifetime_is_time_to_lose_half_at_adult_rate():
    steps = np.arange(400, 40001, 400, dtype=float)
    flat = {k: np.ones_like(steps) for k in cd.DESCRIPTORS}
    leaking = {**flat, "captured": 1.0 - steps * 1e-6}
    adult = cd.adult_phase(steps, leaking, cd.PROVISIONAL)
    assert adult["lifetime_runs"]["captured"] == pytest.approx(0.5 * 0.97 / 1e-6 / 40000, rel=0.02)
    assert adult["lifetime_runs"]["body_radius"] > 1e6
