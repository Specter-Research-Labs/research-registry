from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.k_metric import k_score
from analysis.metrics import (
    damage_recovery_index,
    hysteresis_loop_area,
    memory_retention_index,
    overwrite_index,
)


def test_k_score_expected_value() -> None:
    value = k_score(1000.0, 10.0)
    assert np.isclose(value, 2.0)


def test_memory_retention_index_positive_when_tail_retained() -> None:
    steps = pd.DataFrame(
        {
            "drive_signal": [0, 0, 0, 5, 5, 5, 0, 0, 0, 0],
            "com_x": [0.0, 0.02, 0.0, 1.8, 2.0, 2.2, 1.0, 1.1, 1.0, 1.0],
        }
    )
    mri = memory_retention_index(steps)
    assert mri > 0.3


def test_hysteresis_loop_area_nonzero_for_loop() -> None:
    drive = np.array([-1, -0.5, 0, 0.5, 1, 0.5, 0, -0.5, -1], dtype=float)
    response = np.array([-0.8, -0.3, 0.1, 0.7, 1.0, 0.2, -0.2, -0.6, -0.8], dtype=float)
    steps = pd.DataFrame({"drive_signal": drive, "com_x": response})
    area = hysteresis_loop_area(steps)
    assert area > 0.01


def test_damage_recovery_index_positive_when_tail_recovers() -> None:
    steps = pd.DataFrame(
        {
            "goal_distance": [0.1, 0.1, 0.1, 0.1, 0.9, 0.8, 0.7, 0.4, 0.2, 0.12],
        }
    )
    meta = {"scenario_params": {"damage_step": 4}}
    dri = damage_recovery_index(steps, meta)
    assert dri > 0.5


def test_overwrite_index_positive_when_tail_favors_second_target() -> None:
    steps = pd.DataFrame(
        {
            "com_x": [0.0, 0.3, 1.8, 2.0, 0.2, -1.5, -1.9, -2.0, -1.95, -1.9],
        }
    )
    meta = {
        "scenario_params": {
            "competing_first_goal_x": 2.0,
            "competing_second_goal_x": -2.0,
        }
    }
    oi = overwrite_index(steps, meta)
    assert oi > 0.7
