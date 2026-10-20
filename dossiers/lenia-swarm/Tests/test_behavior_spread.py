from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.anatomical_compiler.behavior_spread import (
    BEHAVIOR_KEYS,
    analyze_run,
    behavior_matrix,
    chaos_floor,
    form_predictability,
    interior_matrix,
    paired_floor,
    pooled_floor,
    residual_shape,
    rule_predictability,
    spread,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "behavior_spread_b4331.json").read_text())
DOMAINS = {"locomotion": ["log_displacement", "log_speed"], "energy": ["log_energy"],
           "response": ["log_lesion_drift"]}


def _row(row: dict) -> dict:
    return {"init_seed": row["init_seed"], "metrics": row["metrics"],
            "descriptor_bundle": {"genotype": {"hash12": row["hash12"]}, "terminal": row["terminal"]}}


def _write_run(root: Path, arms: dict[str, list[dict]]) -> Path:
    base = FIXTURE["base"]
    plan = {
        "design": {"bases": [base, 1], "measure_seeds": FIXTURE["measure_seeds"],
                   "replicate_seeds": FIXTURE["replicate_seeds"]},
        "analysis": {"domains": DOMAINS, "bootstrap": 40, "ci": 0.9, "rng_seed": 3,
                     "support_lower": 1.0, "falsify_upper": 1.25},
    }
    (root / "results").mkdir(parents=True)
    (root / "plan.json").write_text(json.dumps(plan))
    (root / "results" / "scale.json").write_text(json.dumps({"scale": FIXTURE["scale"]}))
    (root / "results" / f"base-{base}.json").write_text(json.dumps({
        "status": "measured", "tau": FIXTURE["tau"], "mates": FIXTURE["mates"],
        "neighbours": FIXTURE["neighbours"], "u0": FIXTURE["u0"]}))
    (root / "results" / "base-1.json").write_text(json.dumps({"status": "insufficient-mates"}))
    for tag, rows in arms.items():
        out = root / "rollouts" / f"b{base}-measure-{tag}" / "eval" / "evaluate-0"
        out.mkdir(parents=True)
        (out / "results.jsonl").write_text("".join(json.dumps(_row(r)) + "\n" for r in rows))
    return root


def test_behavior_matrix_reads_recorded_rollouts() -> None:
    sham = [r["metrics"] for r in FIXTURE["arms"]["mates-sham"]]
    lesion = [r["metrics"] for r in FIXTURE["arms"]["mates-lesion"]]
    out = behavior_matrix(sham, lesion)
    m, les = sham[0], lesion[0]
    drift = np.mean([abs(m[k] - les[k]) / abs(m[k])
                     for k in ("occupancy_mean", "gyration", "largest_component_fraction")])
    expected = [np.log(m["displacement"]), np.log(m["speed_mean"]),
                np.log(m["path_length"] / m["displacement"]), np.log(m["energy_mean"]),
                np.log(m["variance_mean"]), np.log(drift)]
    assert out.shape == (len(sham), len(BEHAVIOR_KEYS))
    np.testing.assert_allclose(out[0], expected)


def test_behavior_matrix_refuses_a_dead_sham_rollout() -> None:
    sham = [dict(r["metrics"]) for r in FIXTURE["arms"]["mates-sham"][:1]]
    lesion = [r["metrics"] for r in FIXTURE["arms"]["mates-lesion"][:1]]
    sham[0]["occupancy_mean"] = 0.0
    with pytest.raises(ValueError, match="zero occupancy"):
        behavior_matrix(sham, lesion)


def test_interior_matrix_is_blind_to_heading() -> None:
    row = _row(FIXTURE["arms"]["mates-sham"][0])
    grid = np.frombuffer(base64.b64decode(row["descriptor_bundle"]["terminal"]["fingerprintU8"]),
                         dtype=np.uint8).reshape(32, 32)
    turned = copy.deepcopy(row)
    turned["descriptor_bundle"]["terminal"]["fingerprintU8"] = base64.b64encode(
        np.ascontiguousarray(np.rot90(grid)).tobytes()).decode()

    out = interior_matrix([row, turned])

    np.testing.assert_allclose(out[0], out[1])
    assert out[0][:9].sum() == pytest.approx(1.0)


def test_form_predictability_finds_behavior_written_in_the_form() -> None:
    rng = np.random.default_rng(3)
    n, k = 40, 8
    hidden = rng.normal(0.0, 1.0, (n, 1, 1))
    behavior = np.repeat(hidden, k, axis=1) + rng.normal(0.0, 0.1, (n, k, len(BEHAVIOR_KEYS)))
    written = np.concatenate([hidden + rng.normal(0.0, 0.1, (n, k, 1)),
                              rng.normal(0.0, 1.0, (n, k, 3)), np.ones((n, k, 1))], axis=2)
    blind = rng.normal(0.0, 1.0, (n, k, 4))

    out = form_predictability(behavior, {"written": written, "blind": blind})

    assert all(v > 0.8 for v in out["written"].values())
    assert all(v < 0.2 for v in out["blind"].values())


def test_paired_floor_ignores_shared_seed_effects() -> None:
    rng = np.random.default_rng(0)
    genotype = rng.normal(0.0, 1.0, (30, 1, 2))
    noise = rng.normal(0.0, 0.5, (30, 8, 2))
    seed = rng.normal(0.0, 5.0, (1, 8, 2))
    values = genotype + noise + seed

    np.testing.assert_allclose(paired_floor(values), paired_floor(genotype + noise))
    assert np.all(pooled_floor(values) > 3 * paired_floor(values))
    np.testing.assert_allclose(paired_floor(values), 0.5 / np.sqrt(8), rtol=0.2)
    np.testing.assert_allclose(chaos_floor(noise[0], 8), noise[0].std(axis=0, ddof=1) / np.sqrt(8))


def test_residual_shape_removes_the_shape_explained_spread() -> None:
    rng = np.random.default_rng(1)
    n, k, features = 300, 8, len(BEHAVIOR_KEYS)
    shape = np.zeros((n, k, 12))
    shape[:, :, 0] = rng.normal(0.0, 1.0, (n, 1))
    behavior = np.repeat(4.0 * shape[:, :, :1], features, axis=2) + rng.normal(0.0, 1.0, (n, k, features))
    floor = np.full(features, 1.0 / np.sqrt(k))

    out = residual_shape(behavior, shape, floor, np.ones(12), DOMAINS, 50, 0.9, rng)

    assert out["R_base_all"] > 5.0
    assert out["R_base_at_zero"] == pytest.approx(1.0, abs=0.3)


def test_rule_predictability_recovers_a_linear_knob() -> None:
    rng = np.random.default_rng(2)
    u0 = np.full(5, 0.5)
    units = u0 + rng.normal(0.0, 0.05, (40, 5))
    signal = (units - u0) @ np.array([20.0, 0.0, 0.0, 0.0, 0.0])
    behavior = signal[:, None, None] + rng.normal(0.0, 0.05, (40, 8, len(BEHAVIOR_KEYS)))

    out = rule_predictability(behavior, units, u0)

    assert all(v > 0.9 for v in out["loo_r2"].values())
    assert all(v > 0.9 for v in out["split_half_r"].values())


def test_analyze_run_on_recorded_rows(tmp_path: Path) -> None:
    run = _write_run(tmp_path, FIXTURE["arms"])

    out = analyze_run(run)

    base = out["bases"][str(FIXTURE["base"])]
    assert out["not_measured"] == {"1": "insufficient-mates"}
    assert base["n_mates"] == 3
    assert set(base["R_base"]) == {"replicates", "pooled_mates", "paired"}
    assert set(out["paired_verdicts"]["replicate_floor"].values()) <= {"supports", "falsifies", "inconclusive"}
    k = len(FIXTURE["measure_seeds"])
    mates = behavior_matrix([r["metrics"] for r in FIXTURE["arms"]["mates-sham"]],
                            [r["metrics"] for r in FIXTURE["arms"]["mates-lesion"]]).reshape(3, k, -1)
    reps = behavior_matrix([r["metrics"] for r in FIXTURE["arms"]["replicates-sham"]],
                           [r["metrics"] for r in FIXTURE["arms"]["replicates-lesion"]])
    expected = spread(mates) / chaos_floor(reps, k)
    np.testing.assert_allclose([base["R_a"][f] for f in BEHAVIOR_KEYS], expected)


def test_analyze_run_refuses_rows_out_of_seed_order(tmp_path: Path) -> None:
    arms = dict(FIXTURE["arms"])
    arms["mates-sham"] = list(reversed(arms["mates-sham"]))
    run = _write_run(tmp_path, arms)

    with pytest.raises(SystemExit, match="genotype-major"):
        analyze_run(run)
