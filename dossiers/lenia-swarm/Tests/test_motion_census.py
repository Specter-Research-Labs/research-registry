import base64
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.morphospace import motion_census as mc
from lenia_swarm_analysis.trace_codec import state_patch


def blob(n: int, y: float, x: float, sigma: float = 2.0) -> np.ndarray:
    """A torus Gaussian of mass at (y, x)."""
    d = np.arange(n)
    dy = (d[:, None] - y + n / 2) % n - n / 2
    dx = (d[None, :] - x + n / 2) % n - n / 2
    return np.exp(-(dy**2 + dx**2) / (2 * sigma**2)).astype(np.float32)


def trace_row(step: int, mass: np.ndarray) -> dict:
    """What the replay writes: the linear centroid and the mass recentred on it, peak-normalised, as f16."""
    n = mass.shape[0]
    cells = np.arange(n, dtype=np.float32) + np.float32(0.5)
    total = mass.sum(dtype=np.float32)
    cy = np.float32((mass.sum(axis=1) * cells).sum(dtype=np.float32) / total)
    cx = np.float32((mass.sum(axis=0) * cells).sum(dtype=np.float32) / total)
    half = np.float32(n) * np.float32(0.5)
    shift_y, shift_x = mc._swift_round(half - cy), mc._swift_round(half - cx)
    field = np.roll(mass, (shift_y, shift_x), axis=(0, 1))
    field = (field / field.max()).astype("<f2")
    return {
        "step": step,
        "width": n,
        "height": n,
        "centerX": float(cx),
        "centerY": float(cy),
        "fieldResolution": n,
        "fieldF16Base64": base64.b64encode(field.tobytes()).decode(),
    }


def test_torus_centre_survives_the_seam_where_the_linear_centroid_fails():
    row = trace_row(0, blob(64, 1.0, 62.5))
    assert abs(row["centerX"] - 62.5) > 10
    y, x = mc.torus_centre(row)
    assert y == pytest.approx(1.0, abs=0.05) and x == pytest.approx(62.5, abs=0.05)


def test_torus_centre_refuses_a_resampled_field():
    row = {**trace_row(0, blob(16, 8, 8)), "width": 32, "height": 32}
    with pytest.raises(ValueError, match="unresampled"):
        mc.torus_centre(row)


def test_unwrap_crosses_the_seam_and_refuses_ambiguous_jumps():
    track = np.array([[10.0, 60.0], [10.0, 63.0], [10.0, 2.0]])
    np.testing.assert_allclose(mc.unwrap(track, 64)[:, 1], [60.0, 63.0, 66.0])
    with pytest.raises(ValueError, match="ambiguous"):
        mc.unwrap(np.array([[0.0, 0.0], [0.0, 20.0]]), 64)


def test_concentration_separates_one_body_from_mass_spread_round_the_torus():
    assert mc.concentration(trace_row(0, blob(64, 1.0, 62.5))) > 0.9
    spread = blob(64, 16, 16) + blob(64, 16, 48) + blob(64, 48, 16) + blob(64, 48, 48)
    assert mc.concentration(trace_row(0, spread)) < 0.05


def test_metrics_separate_a_glider_from_a_jittering_body():
    steps = np.arange(20000, 40001, 400)
    t = (steps - steps[0]) / 400
    glider = np.stack([0.1 * np.sin(t), 0.8 * t], axis=1)
    m = mc.motion_metrics(steps, glider)
    assert m["H"] == pytest.approx(1.0, abs=1e-3) and m["D"] == pytest.approx(40.0, abs=0.2)
    assert mc.motion_class(m, mc.PROVISIONAL_MOTION) == "translating"
    jitter = np.stack([0.3 * np.sin(t), 0.3 * np.cos(t)], axis=1)
    m = mc.motion_metrics(steps, jitter)
    assert m["H"] is None
    assert mc.motion_class(m, mc.PROVISIONAL_MOTION) == "stationary"
    circle = np.stack([8 * np.sin(t / 8), 8 * np.cos(t / 8)], axis=1)
    assert (
        mc.motion_class(mc.motion_metrics(steps, circle), mc.PROVISIONAL_MOTION) == "other_motion"
    )


def test_metrics_refuse_traces_missing_segment_boundaries():
    steps = np.arange(20000, 40001, 3000)
    with pytest.raises(ValueError, match="segment boundary"):
        mc.motion_metrics(steps, np.zeros((len(steps), 2)))


def export(root: Path, body: str, run: str, value: float) -> dict:
    d = root / body
    d.mkdir(parents=True)
    base = {
        "grid": {"sx": 32, "sy": 32},
        "params": {"R": 12.0, "r": [value]},
        "init": {
            "a_uniform": {"high": 0, "low": 0},
            "patches": [],
            "seed": 0,
            "state_patch": state_patch(
                center=[16, 16],
                width=4,
                height=4,
                channels=1,
                values=np.ones((1, 4, 4), dtype="<f4"),
            ),
        },
        "reintegration": {"border": "torus"},
    }
    (d / "base.json").write_text(json.dumps(base))
    return {"creatureId": body, "runId": run, "exportDir": str(d)}


def replay(root: Path, bodies: dict[str, float], arena: int) -> Path:
    """One replay root whose bodies move along x at the given speed in cells per frame."""
    root.mkdir(parents=True)
    (root / "receipt.json").write_text(
        json.dumps({"receipt_version": 1, "engine_id": "cpu-a", "build": {"source_commit": "a"}})
    )
    for i, (body, speed) in enumerate(bodies.items()):
        c = root / "campaigns" / f"{i:04d}-{body.lower()}"
        c.mkdir(parents=True)
        (c / "replay-manifest.json").write_text(json.dumps({"sourceCreatureId": body}))
        (c / "config.json").write_text(json.dumps({"reintegration": {"border": "torus"}}))
        rows = [
            trace_row(step, blob(arena, arena / 2, (5 + speed * k) % arena))
            for k, step in enumerate(range(20000, 40001, 400))
        ]
        (c / "development-trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return root


def test_census_joins_verdicts_and_keeps_one_panel_body_per_lineage(tmp_path):
    rows = [
        export(tmp_path / "in", "A", "run-1", 0.1),
        export(tmp_path / "in", "B", "run-1", 0.2),
        export(tmp_path / "in", "C", "run-2", 0.3),
        export(tmp_path / "in", "D", "run-3", 0.4),
        export(tmp_path / "in", "E", "run-4", 0.5),
    ]
    index = tmp_path / "index.jsonl"
    index.write_text("".join(json.dumps(r) + "\n" for r in rows))
    speeds = {"A": 1.0, "B": 0.8, "C": 0.0, "D": 0.9, "E": 20.0}
    roots = [replay(tmp_path / "r32", speeds, 32), replay(tmp_path / "r64", speeds, 64)]
    sweep = tmp_path / "sweep.json"
    stable = {"A": True, "B": True, "C": True, "D": False, "E": True}
    sweep.write_text(
        json.dumps(
            {
                "engine": "cpu-a",
                "bodies": {b: {"provisional": "creature", "stable": s} for b, s in stable.items()},
            }
        )
    )
    members = tmp_path / "members.json"
    members.write_text(
        json.dumps({"members": [{"body": "A", "original": {"motion_class": "stationary"}}]})
    )
    out = tmp_path / "motion.json"
    summary = mc.motion_census(
        replay_roots=roots,
        index_path=index,
        sweeps=[sweep],
        members_path=members,
        output_path=out,
        workers=1,
    )
    data = json.loads(out.read_text())
    per_body = {b["body"]: b for b in data["per_body"]}
    assert [per_body[b]["motion_class"] for b in "ABCDE"] == [
        "translating",
        "translating",
        "stationary",
        "translating",
        "untracked",
    ]
    assert per_body["E"]["arenas"]["32"]["metrics"] is None
    assert per_body["E"]["motion_stable"]
    assert summary["panel_candidates"] == ["A"]
    assert data["sweep_stable_creatures"]["translating"] == {
        "bodies": 2,
        "rules": 2,
        "lineages": 1,
        "lineages_hill1": pytest.approx(1.0),
    }
    assert data["prior_vs_native_all"]["stationary"] == {"translating": 1}
    assert data["sweep_stable_creatures"]["untracked"]["bodies"] == 1
    assert data["prior_vs_native_all"]["none_recorded"] == {
        "stationary": 1,
        "translating": 2,
        "untracked": 1,
    }


def test_census_refuses_sweeps_of_another_engine(tmp_path):
    rows = [export(tmp_path / "in", "A", "run-1", 0.1)]
    index = tmp_path / "index.jsonl"
    index.write_text(json.dumps(rows[0]) + "\n")
    roots = [replay(tmp_path / "r32", {"A": 0.0}, 32)]
    sweep = tmp_path / "sweep.json"
    sweep.write_text(
        json.dumps(
            {"engine": "metal-b", "bodies": {"A": {"provisional": "creature", "stable": True}}}
        )
    )
    members = tmp_path / "members.json"
    members.write_text(json.dumps({"members": []}))
    with pytest.raises(ValueError, match="judged engine"):
        mc.motion_census(
            replay_roots=roots,
            index_path=index,
            sweeps=[sweep],
            members_path=members,
            output_path=tmp_path / "m.json",
            workers=1,
        )
