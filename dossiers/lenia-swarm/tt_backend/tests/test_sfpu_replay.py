from __future__ import annotations

import base64
import copy
import hashlib
import json

import numpy as np
import pytest

from tt_lenia.sfpu import replay
from tt_lenia.sfpu.codegen import PassSpec

F32 = np.float32


def _patch_config(
    sx: int, sy: int, channels: int, w: int, h: int, center: list[int]
) -> tuple[dict, np.ndarray]:
    values = np.arange(w * h * channels, dtype="<f4") + 1
    raw = {
        "channels": channels,
        "grid": {"sx": sx, "sy": sy},
        "init": {
            "state_patch": {
                "channels": channels,
                "width": w,
                "height": h,
                "center": center,
                "encoding": "f32le",
                "data": base64.b64encode(values.tobytes()).decode(),
            }
        },
    }
    return raw, values.reshape(w, h, channels)


def test_initial_mass_places_patch_like_leniacli() -> None:
    raw, patch = _patch_config(32, 48, 2, 5, 6, [10, 20])
    mass = replay.initial_mass(raw)
    assert mass.shape == (32, 48, 2)
    np.testing.assert_array_equal(mass[8:13, 17:23], patch)
    assert mass.sum() == patch.sum()


def test_initial_mass_refuses_patch_outside_grid() -> None:
    raw, _ = _patch_config(32, 32, 1, 8, 8, [2, 16])
    with pytest.raises(ValueError, match="leaves the 32x32 grid"):
        replay.initial_mass(raw)


@pytest.mark.parametrize(
    ("x", "expected"), [(0.5, 1), (-0.5, -1), (1.5, 2), (2.5, 3), (-2.5, -3), (2.4, 2)]
)
def test_swift_round_rounds_half_away_from_zero(x: float, expected: int) -> None:
    assert replay._swift_round(F32(x)) == expected


def test_trace_row_centres_a_point_mass() -> None:
    state = np.zeros((16, 24, 2), F32)
    state[3, 5, 0] = 0.25
    state[3, 5, 1] = 0.75
    row = replay.trace_row(7, state)
    assert (row["step"], row["centerX"], row["centerY"]) == (7, 5.5, 3.5)
    assert (row["width"], row["height"], row["fieldResolution"]) == (24, 16, 24)
    field = np.frombuffer(base64.b64decode(row["fieldF16Base64"]), "<f2").reshape(16, 24)
    assert field[8, 12] == 1 and field.sum() == 1
    assert row["stateSha256"] == hashlib.sha256(state.astype("<f4").tobytes()).hexdigest()


def test_trace_row_refuses_empty_field() -> None:
    with pytest.raises(ValueError, match="empty field"):
        replay.trace_row(1, np.zeros((8, 8, 1), F32))


@pytest.fixture
def export_config(paper_config_path) -> dict:
    raw = json.loads(paper_config_path.read_text())
    del raw["chemotaxis"]
    raw["params"] = {"mode": "explicit"}
    raw["init"] = {
        "patches": [],
        "a_uniform": {"low": 0, "high": 0},
        "state_patch": {"encoding": "f32le"},
    }
    return raw


def test_check_config_accepts_export(export_config: dict) -> None:
    replay._check_config(export_config, "body")


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("reintegration", "border"), "wall", "border wall"),
        (("parameter_embedding", "enabled"), True, "parameter embedding"),
        (("interventions",), [{"kind": "cut"}], "interventions"),
        (("implementation",), {"mode": "other"}, "implementation"),
        (("init", "a_uniform"), {"low": 0, "high": 1}, "random init patches"),
    ],
)
def test_check_config_refuses_unvalidated_features(
    export_config: dict, path, value, message: str
) -> None:
    raw = copy.deepcopy(export_config)
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=message):
        replay._check_config(raw, "body")


def _body(campaign: str = "c") -> replay.Body:
    spec = PassSpec(
        sx=128,
        sy=128,
        channels=1,
        c0=(0, 0),
        output_weights=((1, 1),),
        dt=0.2,
        dd=5,
        sigma=0.65,
        theta_a=1.0,
        n=2,
    )
    return replay.Body(
        campaign=campaign,
        creature_id="id",
        export_dir="e",
        config={
            "channels": 1,
            "grid": {"sx": 128, "sy": 128},
            "init": {"state_patch": {}},
            "run": {"steps": 1},
        },
        mass=np.ones((128, 128, 1), F32),
        spectra=np.full((128, 128, 2), 2, F32),
        m=np.full(2, 0.1, F32),
        s=np.full(2, 0.2, F32),
        h=np.full(2, 0.3, F32),
        spec=spec,
    )


def test_engine_inputs_pads_lanes_with_zero_mass_filler() -> None:
    members = [replay.Member.of(_body(), seed) for seed in (0, 1, 2)]
    mass, params = replay.engine_inputs(members, 4)
    assert mass.shape == (4, 128, 128, 1) and params.spectra.shape == (4, 128, 128, 2)
    assert mass[0].min() == 1 and mass[3].max() == 0 and params.spectra[3].max() == 0
    assert params.s[3].tolist() == [1, 1] and params.m[3].tolist() == [0, 0]
    assert mass[1].tobytes() != mass[0].tobytes()


def test_members_are_named_and_perturbed_by_seed() -> None:
    body = _body("0001-x-abcd")
    zero, one = replay.Member.of(body, 0), replay.Member.of(body, 1)
    assert (zero.campaign, one.campaign) == ("0001-x-abcd-u0", "0001-x-abcd-u1")
    assert zero.mass.tobytes() == body.mass.tobytes()
    assert (one.mass != body.mass).sum() == round(0.01 * 128 * 128)


@pytest.mark.parametrize(
    ("text", "seeds"), [("0", [0]), ("1-8", list(range(1, 9))), ("0,3-5", [0, 3, 4, 5])]
)
def test_parse_seeds(text: str, seeds: list[int]) -> None:
    assert replay.parse_seeds(text) == seeds


def test_parse_seeds_refuses_repeats() -> None:
    with pytest.raises(ValueError, match="repeat"):
        replay.parse_seeds("1-3,2")


@pytest.mark.parametrize(
    ("count", "cards", "batch"),
    [(963, [0, 1, 2, 3], 4096), (856, [0, 1, 2, 3], 128), (64, [0, 1, 2, 3], 4096), (1, [3], 64)],
)
def test_plan_rounds_covers_the_queue_with_tail_filler_only(count, cards, batch) -> None:
    plan = replay.plan_rounds(count, cards, batch)
    assert plan[0].start == 0 and plan[-1].stop == count
    assert all(a.stop == b.start for a, b in zip(plan, plan[1:]))
    assert all(r.size % replay.UNIT == 0 and 0 < r.size <= batch for r in plan)
    assert all(r.stop - r.start == r.size for r in plan[:-1])
    assert plan[-1].size - (plan[-1].stop - plan[-1].start) < replay.UNIT
    per_card = [sum(r.card == c for r in plan) for c in cards]
    assert max(per_card) - min(per_card) <= 1
    assert sorted((r.card, r.index) for r in plan) == sorted({(r.card, r.index) for r in plan})


def test_plan_rounds_balances_units() -> None:
    plan = replay.plan_rounds(963, [0, 1, 2, 3], 4096)
    assert [r.size for r in plan] == [256, 256, 256, 256]
    assert plan[-1].stop - plan[-1].start == 963 - 768


def test_plan_rounds_refuses_partial_units() -> None:
    with pytest.raises(ValueError, match="multiple of 64"):
        replay.plan_rounds(10, [0], 96)


def test_slot_splits_groups_across_chips() -> None:
    assert replay.slot(0, 256) == {"chip": 0, "group": 0, "lane": 0}
    assert replay.slot(33, 256) == {"chip": 0, "group": 1, "lane": 1}
    assert replay.slot(128, 256) == {"chip": 1, "group": 0, "lane": 0}
    assert replay.slot(255, 256) == {"chip": 1, "group": 3, "lane": 31}


def test_member_config_reproduces_the_member_field() -> None:
    member = replay.Member.of(_body(), 2)
    config = replay._member_config(member, 400)
    assert config["run"]["steps"] == 400
    assert replay.initial_mass(config).tobytes() == member.mass.tobytes()
