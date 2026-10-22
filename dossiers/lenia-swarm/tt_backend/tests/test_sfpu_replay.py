from __future__ import annotations

import base64
import copy
import hashlib
import json

import numpy as np
import pytest

from tt_lenia.sfpu import replay

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
