from __future__ import annotations

import json
from pathlib import Path

from analysis.summarize import build_metrics_table, summarize_results


def _write_ndjson(
    path: Path,
    scenario: str,
    policy: str,
    memory_mode: str,
    tau_proxy: float,
    *,
    backend: str = "cpu",
    seed: int = 1,
    layout: str = "line",
    memory_variant: str = "baseline",
) -> None:
    if scenario == "damage":
        steps = [
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.1},
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.1},
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.8},
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.7},
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.3},
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.12},
        ]
    elif scenario == "competing_targets":
        steps = [
            {
                "record_type": "step",
                "drive_signal": 1.0,
                "goal_x": 2.0,
                "com_x": 0.3,
                "goal_distance": 1.7,
            },
            {
                "record_type": "step",
                "drive_signal": 1.0,
                "goal_x": 2.0,
                "com_x": 1.7,
                "goal_distance": 0.3,
            },
            {
                "record_type": "step",
                "drive_signal": 0.0,
                "goal_x": 0.0,
                "com_x": 0.1,
                "goal_distance": 0.1,
            },
            {
                "record_type": "step",
                "drive_signal": -1.0,
                "goal_x": -2.0,
                "com_x": -1.6,
                "goal_distance": 0.4,
            },
            {
                "record_type": "step",
                "drive_signal": -1.0,
                "goal_x": -2.0,
                "com_x": -1.9,
                "goal_distance": 0.1,
            },
            {
                "record_type": "step",
                "drive_signal": 0.0,
                "goal_x": -2.0,
                "com_x": -1.95,
                "goal_distance": 0.05,
            },
        ]
    else:
        steps = [
            {"record_type": "step", "drive_signal": 1.0, "com_x": 0.5, "goal_distance": 0.2},
        ]
    meta = {
        "record_type": "meta",
        "layout": layout,
        "memory_variant": memory_variant,
        "memory_params": {
            "plastic_gain": 0.03,
            "plastic_decay": 0.985,
            "max_plastic": 5.0,
        },
        "scenario_params": {
            "damage_step": 2,
            "competing_first_goal_x": 2.0,
            "competing_second_goal_x": -2.0,
        },
    }
    summary = {
        "record_type": "summary",
        "run_id": path.stem,
        "seed": seed,
        "scenario": scenario,
        "policy": policy,
        "memory_mode": memory_mode,
        "backend": backend,
        "tau_proxy": tau_proxy,
        "tau_time": 2.0,
        "reached_goal": True,
    }
    payload_rows = [json.dumps(meta), *[json.dumps(step) for step in steps], json.dumps(summary)]
    payload = "\n".join(payload_rows) + "\n"
    path.write_text(payload, encoding="utf-8")


def test_build_metrics_table_and_summary(tmp_path: Path) -> None:
    blind = tmp_path / "blind.ndjson"
    control = tmp_path / "control.ndjson"
    memory = tmp_path / "memory.ndjson"
    inertial = tmp_path / "inertial.ndjson"
    blind_metal = tmp_path / "blind_metal.ndjson"
    control_metal = tmp_path / "control_metal.ndjson"
    memory_metal = tmp_path / "memory_metal.ndjson"
    inertial_metal = tmp_path / "inertial_metal.ndjson"

    _write_ndjson(blind, "damage", "blind", "off", tau_proxy=20.0)
    _write_ndjson(control, "damage", "directed", "off", tau_proxy=10.0)
    _write_ndjson(memory, "damage", "directed", "on", tau_proxy=5.0)
    _write_ndjson(inertial, "damage", "directed", "inertial_control", tau_proxy=8.0)

    _write_ndjson(blind_metal, "damage", "blind", "off", tau_proxy=25.0, backend="metal")
    _write_ndjson(control_metal, "damage", "directed", "off", tau_proxy=12.0, backend="metal")
    _write_ndjson(memory_metal, "damage", "directed", "on", tau_proxy=6.0, backend="metal")
    _write_ndjson(
        inertial_metal,
        "damage",
        "directed",
        "inertial_control",
        tau_proxy=9.0,
        backend="metal",
    )

    manifest = {
        "runs": [
            {
                "run_id": "blind",
                "return_code": 0,
                "ndjson_path": str(blind),
            },
            {
                "run_id": "control",
                "return_code": 0,
                "ndjson_path": str(control),
            },
            {
                "run_id": "memory",
                "return_code": 0,
                "ndjson_path": str(memory),
            },
            {
                "run_id": "inertial",
                "return_code": 0,
                "ndjson_path": str(inertial),
            },
            {
                "run_id": "blind_metal",
                "return_code": 0,
                "ndjson_path": str(blind_metal),
            },
            {
                "run_id": "control_metal",
                "return_code": 0,
                "ndjson_path": str(control_metal),
            },
            {
                "run_id": "memory_metal",
                "return_code": 0,
                "ndjson_path": str(memory_metal),
            },
            {
                "run_id": "inertial_metal",
                "return_code": 0,
                "ndjson_path": str(inertial_metal),
            },
        ]
    }

    table = build_metrics_table(manifest)
    assert len(table) == 8

    summary = summarize_results(table)
    assert summary["rows"] == 8
    assert len(summary["groups"]) == 2
    assert summary["group_keys"] == ["scenario", "backend"]
    assert summary["acceptance"]["delta_k_on_vs_off_low_gt_zero_group_count"] == 2
    assert summary["acceptance"]["delta_k_on_vs_off_target_met"] is True
    assert summary["acceptance"]["delta_k_on_vs_inertial_low_gt_zero_group_count"] == 2
    assert summary["acceptance"]["delta_k_on_vs_inertial_target_met"] is True
    assert summary["acceptance"]["primary_gate_met"] is False
    assert summary["groups"][0]["k_inertial_control"] is not None
    assert summary["groups"][0]["delta_k_on_vs_inertial_control"] is not None
    assert summary["groups"][0]["delta_k_on_vs_off"]["kind"] == "exact"
    assert summary["groups"][0]["dri_directed_on"] is not None
    assert summary["stochasticity"]["exact_metric_count"] > 0


def test_competing_targets_overwrite_summary(tmp_path: Path) -> None:
    blind = tmp_path / "blind.ndjson"
    control = tmp_path / "control.ndjson"
    memory = tmp_path / "memory.ndjson"
    inertial = tmp_path / "inertial.ndjson"

    _write_ndjson(blind, "competing_targets", "blind", "off", tau_proxy=18.0)
    _write_ndjson(control, "competing_targets", "directed", "off", tau_proxy=10.0)
    _write_ndjson(memory, "competing_targets", "directed", "on", tau_proxy=9.0)
    _write_ndjson(
        inertial,
        "competing_targets",
        "directed",
        "inertial_control",
        tau_proxy=11.0,
    )

    manifest = {
        "runs": [
            {"run_id": "blind", "return_code": 0, "ndjson_path": str(blind)},
            {"run_id": "control", "return_code": 0, "ndjson_path": str(control)},
            {"run_id": "memory", "return_code": 0, "ndjson_path": str(memory)},
            {"run_id": "inertial", "return_code": 0, "ndjson_path": str(inertial)},
        ]
    }

    table = build_metrics_table(manifest)
    assert len(table) == 4
    assert table["overwrite_index"].notna().sum() == 4

    summary = summarize_results(table)
    assert summary["overwrite_index"] is not None
    assert summary["groups"][0]["overwrite_index_directed_on"] is not None
    assert summary["groups"][0]["overwrite_index_inertial_control"] is not None
    assert summary["groups"][0]["delta_overwrite_index_on_vs_off"] is not None
