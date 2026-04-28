from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RunMetrics:
    tau_proxy: float
    tau_time: float
    reached_goal: bool
    mri: float
    hla: float
    dri: float
    overwrite_index: float


def _safe_mean(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.mean(values))


def memory_retention_index(steps: pd.DataFrame) -> float:
    if steps.empty:
        return float("nan")

    abs_drive = steps["drive_signal"].abs().to_numpy()
    if np.all(abs_drive <= 1e-8):
        return float("nan")

    threshold = 0.5 * float(np.max(abs_drive))
    pulse_mask = abs_drive >= threshold
    if not np.any(pulse_mask):
        return float("nan")

    pulse_indices = np.flatnonzero(pulse_mask)
    pulse_start = int(pulse_indices[0])
    pulse_end = int(pulse_indices[-1])

    baseline_end = max(1, pulse_start)
    tail_start = min(len(steps) - 1, pulse_end + 1)
    tail_end = min(len(steps), tail_start + max(4, int(0.2 * len(steps))))

    com = steps["com_x"].to_numpy(dtype=float)
    baseline = _safe_mean(com[:baseline_end])
    pulse = _safe_mean(com[pulse_start : pulse_end + 1])
    tail = _safe_mean(com[tail_start:tail_end])

    pulse_delta = pulse - baseline
    if math.isclose(pulse_delta, 0.0, abs_tol=1e-8):
        return 0.0
    return float((tail - baseline) / pulse_delta)


def hysteresis_loop_area(steps: pd.DataFrame) -> float:
    if steps.empty:
        return float("nan")

    drive = steps["drive_signal"].to_numpy(dtype=float)
    response = steps["com_x"].to_numpy(dtype=float)
    if drive.size < 3:
        return float("nan")

    # Discrete contour integral around the parametric loop (drive(t), response(t)).
    signed_area = 0.0
    for i in range(drive.size - 1):
        signed_area += 0.5 * (response[i] + response[i + 1]) * (drive[i + 1] - drive[i])

    force_span = float(np.max(drive) - np.min(drive))
    response_span = float(np.max(response) - np.min(response))
    scale = force_span * response_span
    if scale <= 1e-8:
        return 0.0
    return abs(float(signed_area)) / scale


def damage_recovery_index(steps: pd.DataFrame, meta: dict[str, Any] | None) -> float:
    if steps.empty or "goal_distance" not in steps:
        return float("nan")
    if meta is None:
        return float("nan")

    scenario_params = meta.get("scenario_params")
    if not isinstance(scenario_params, dict):
        return float("nan")
    damage_step_raw = scenario_params.get("damage_step")
    if not isinstance(damage_step_raw, int | float):
        return float("nan")

    damage_step = int(damage_step_raw)
    if damage_step < 1 or damage_step >= len(steps) - 1:
        return float("nan")

    goal_distance = steps["goal_distance"].to_numpy(dtype=float)
    window = max(4, int(0.08 * len(steps)))
    tail_window = max(4, int(0.15 * len(steps)))

    baseline_start = max(0, damage_step - window)
    baseline = _safe_mean(goal_distance[baseline_start:damage_step])
    spike_end = min(len(steps), damage_step + window)
    spike = _safe_mean(goal_distance[damage_step:spike_end])
    tail = _safe_mean(goal_distance[-tail_window:])

    spike_delta = spike - baseline
    if math.isclose(spike_delta, 0.0, abs_tol=1e-8):
        return 0.0
    return float((spike - tail) / spike_delta)


def overwrite_index(steps: pd.DataFrame, meta: dict[str, Any] | None) -> float:
    if steps.empty:
        return float("nan")
    if meta is None:
        return float("nan")

    scenario_params = meta.get("scenario_params")
    if not isinstance(scenario_params, dict):
        return float("nan")

    first_goal_raw = scenario_params.get("competing_first_goal_x")
    second_goal_raw = scenario_params.get("competing_second_goal_x")
    if not isinstance(first_goal_raw, int | float) or not isinstance(second_goal_raw, int | float):
        return float("nan")

    com_x = steps["com_x"].to_numpy(dtype=float)
    if com_x.size == 0:
        return float("nan")

    tail_window = max(4, int(0.15 * len(steps)))
    tail = _safe_mean(com_x[-tail_window:])
    distance_first = abs(tail - float(first_goal_raw))
    distance_second = abs(tail - float(second_goal_raw))
    total_distance = distance_first + distance_second
    if math.isclose(total_distance, 0.0, abs_tol=1e-8):
        return 0.0
    return float((distance_first - distance_second) / total_distance)


def compute_run_metrics(
    steps: pd.DataFrame, summary: dict[str, object], meta: dict[str, Any] | None = None
) -> RunMetrics:
    scenario = str(summary["scenario"])
    mri = memory_retention_index(steps) if scenario == "imprint" else float("nan")
    hla = hysteresis_loop_area(steps) if scenario == "hysteresis" else float("nan")
    dri = damage_recovery_index(steps, meta) if scenario == "damage" else float("nan")
    oi = overwrite_index(steps, meta) if scenario == "competing_targets" else float("nan")

    tau_proxy = float(cast(float | int | str, summary["tau_proxy"]))
    tau_time = float(cast(float | int | str, summary["tau_time"]))
    reached_goal = bool(cast(bool | int | str, summary["reached_goal"]))

    return RunMetrics(
        tau_proxy=tau_proxy,
        tau_time=tau_time,
        reached_goal=reached_goal,
        mri=mri,
        hla=hla,
        dri=dri,
        overwrite_index=oi,
    )
