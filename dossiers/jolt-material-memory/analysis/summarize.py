from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .k_metric import bootstrap_ci, k_score
from .metrics import compute_run_metrics


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _float_or_nan(value: object) -> float:
    if not isinstance(value, int | float | str):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _meta_dict(meta: dict[str, Any], key: str) -> dict[str, Any]:
    value = meta.get(key)
    if isinstance(value, dict):
        return value
    return {}


def build_metrics_table(manifest: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for run in manifest["runs"]:
        if int(run["return_code"]) != 0:
            continue
        run_file = Path(run["ndjson_path"])
        records = _read_ndjson(run_file)
        meta_rows = [r for r in records if r.get("record_type") == "meta"]
        step_rows = [r for r in records if r.get("record_type") == "step"]
        summary_rows = [r for r in records if r.get("record_type") == "summary"]
        if len(summary_rows) != 1:
            raise ValueError(f"expected one summary row in {run_file}")
        if len(meta_rows) > 1:
            raise ValueError(f"expected at most one meta row in {run_file}")

        meta = meta_rows[0] if meta_rows else {}
        steps = pd.DataFrame(step_rows)
        summary = summary_rows[0]
        metrics = compute_run_metrics(steps, summary, meta)
        memory_params = _meta_dict(meta, "memory_params")

        rows.append(
            {
                "run_id": run["run_id"],
                "scenario": summary["scenario"],
                "backend": summary["backend"],
                "policy": summary["policy"],
                "memory_mode": summary["memory_mode"],
                "seed": int(summary["seed"]),
                "layout": str(meta.get("layout", run.get("layout", "line"))),
                "memory_variant": str(
                    meta.get("memory_variant", run.get("memory_variant", "baseline"))
                ),
                "plastic_gain": _float_or_nan(memory_params.get("plastic_gain")),
                "plastic_decay": _float_or_nan(memory_params.get("plastic_decay")),
                "max_plastic": _float_or_nan(memory_params.get("max_plastic")),
                "tau_proxy": metrics.tau_proxy,
                "tau_time": metrics.tau_time,
                "reached_goal": metrics.reached_goal,
                "mri": metrics.mri,
                "hla": metrics.hla,
                "dri": metrics.dri,
                "overwrite_index": metrics.overwrite_index,
            }
        )

    if not rows:
        raise ValueError("no successful runs found in manifest")

    return pd.DataFrame(rows)


def _distribution_summary(values: np.ndarray) -> dict[str, Any]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("cannot summarize an empty array")

    distinct_count = int(np.unique(np.round(finite, 12)).size)
    median = float(np.median(finite))
    std = float(np.std(finite))
    if np.allclose(finite, finite[0], rtol=0.0, atol=1e-12):
        return {
            "kind": "exact",
            "count": int(finite.size),
            "distinct_count": distinct_count,
            "std": std,
            "median": median,
            "low": median,
            "high": median,
        }

    ci = bootstrap_ci(finite)
    return {
        "kind": "bootstrap",
        "count": int(finite.size),
        "distinct_count": distinct_count,
        "std": std,
        "median": ci.median,
        "low": ci.low,
        "high": ci.high,
    }


def _k_frame(group: pd.DataFrame, blind_ref: float) -> pd.DataFrame:
    ordered = group[["seed", "tau_proxy"]].sort_values("seed").copy()
    ordered["metric"] = ordered["tau_proxy"].map(
        lambda tau_proxy: k_score(blind_ref, float(tau_proxy))
    )
    return ordered[["seed", "metric"]]


def _metric_frame(group: pd.DataFrame, column: str) -> pd.DataFrame:
    ordered = group[["seed", column]].dropna().sort_values("seed").copy()
    ordered["metric"] = ordered[column].astype(float)
    return ordered[["seed", "metric"]]


def _paired_delta(left: pd.DataFrame, right: pd.DataFrame) -> np.ndarray:
    shared = np.intersect1d(left["seed"].to_numpy(), right["seed"].to_numpy())
    if shared.size > 0:
        left_metric = (
            left[left["seed"].isin(shared)]
            .sort_values("seed")["metric"]
            .to_numpy(dtype=float)
        )
        right_metric = (
            right[right["seed"].isin(shared)]
            .sort_values("seed")["metric"]
            .to_numpy(dtype=float)
        )
        return left_metric - right_metric

    min_len = min(len(left), len(right))
    return (
        left["metric"].to_numpy(dtype=float)[:min_len]
        - right["metric"].to_numpy(dtype=float)[:min_len]
    )


def _active_group_keys(df: pd.DataFrame) -> list[str]:
    keys = ["scenario", "backend"]
    for column in ("layout", "memory_variant"):
        if column in df and int(df[column].nunique(dropna=False)) > 1:
            keys.append(column)
    return keys


def _group_descriptor(group_keys: list[str], key: object) -> dict[str, Any]:
    values = key if isinstance(key, tuple) else (key,)
    return {column: value for column, value in zip(group_keys, values, strict=True)}


def _record_exact_metric(
    exact_metrics: list[dict[str, Any]],
    descriptor: dict[str, Any],
    name: str,
    summary: dict[str, Any] | None,
) -> None:
    if summary is None or summary["kind"] != "exact":
        return
    exact_metrics.append({**descriptor, "metric": name})


def summarize_results(df: pd.DataFrame) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    exact_metrics: list[dict[str, Any]] = []
    delta_k_on_vs_off_low_positive_count = 0
    delta_k_on_vs_inertial_low_positive_count = 0

    group_keys = _active_group_keys(df)
    grouped = df.groupby(group_keys, sort=True)

    for key in grouped.groups.keys():
        descriptor = _group_descriptor(group_keys, key)
        group = grouped.get_group(key)
        blind = group[(group["policy"] == "blind") & (group["memory_mode"] == "off")]["tau_proxy"]
        directed_off = group[(group["policy"] == "directed") & (group["memory_mode"] == "off")]
        directed_on = group[(group["policy"] == "directed") & (group["memory_mode"] == "on")]
        inertial_control = group[
            (group["policy"] == "directed") & (group["memory_mode"] == "inertial_control")
        ]

        if blind.empty or directed_off.empty or directed_on.empty:
            continue

        blind_ref = float(np.median(blind.to_numpy(dtype=float)))

        k_off_frame = _k_frame(directed_off, blind_ref)
        k_on_frame = _k_frame(directed_on, blind_ref)
        k_inertial_frame = (
            _k_frame(inertial_control, blind_ref) if not inertial_control.empty else pd.DataFrame()
        )

        k_off_summary = _distribution_summary(k_off_frame["metric"].to_numpy(dtype=float))
        k_on_summary = _distribution_summary(k_on_frame["metric"].to_numpy(dtype=float))
        delta_on_vs_off_summary = _distribution_summary(_paired_delta(k_on_frame, k_off_frame))

        if delta_on_vs_off_summary["low"] > 0:
            delta_k_on_vs_off_low_positive_count += 1

        if k_inertial_frame.empty:
            k_inertial_summary = None
            delta_on_vs_inertial_summary = None
        else:
            k_inertial_summary = _distribution_summary(
                k_inertial_frame["metric"].to_numpy(dtype=float)
            )
            delta_on_vs_inertial_summary = _distribution_summary(
                _paired_delta(k_on_frame, k_inertial_frame)
            )
            if delta_on_vs_inertial_summary["low"] > 0:
                delta_k_on_vs_inertial_low_positive_count += 1

        entry: dict[str, Any] = {
            **descriptor,
            "blind_tau_ref": blind_ref,
            "k_directed_off": k_off_summary,
            "k_directed_on": k_on_summary,
            "k_inertial_control": k_inertial_summary,
            "delta_k_on_vs_off": delta_on_vs_off_summary,
            "delta_k_on_vs_inertial_control": delta_on_vs_inertial_summary,
        }

        if descriptor["scenario"] == "damage":
            dri_off_frame = _metric_frame(directed_off, "dri")
            dri_on_frame = _metric_frame(directed_on, "dri")
            dri_inertial_frame = (
                _metric_frame(inertial_control, "dri")
                if not inertial_control.empty
                else pd.DataFrame()
            )

            if not dri_off_frame.empty and not dri_on_frame.empty:
                entry["dri_directed_off"] = _distribution_summary(
                    dri_off_frame["metric"].to_numpy(dtype=float)
                )
                entry["dri_directed_on"] = _distribution_summary(
                    dri_on_frame["metric"].to_numpy(dtype=float)
                )
                entry["delta_dri_on_vs_off"] = _distribution_summary(
                    _paired_delta(dri_on_frame, dri_off_frame)
                )
            else:
                entry["dri_directed_off"] = None
                entry["dri_directed_on"] = None
                entry["delta_dri_on_vs_off"] = None

            if dri_inertial_frame.empty or dri_on_frame.empty:
                entry["dri_inertial_control"] = None
                entry["delta_dri_on_vs_inertial_control"] = None
            else:
                entry["dri_inertial_control"] = _distribution_summary(
                    dri_inertial_frame["metric"].to_numpy(dtype=float)
                )
                entry["delta_dri_on_vs_inertial_control"] = _distribution_summary(
                    _paired_delta(dri_on_frame, dri_inertial_frame)
                )
        else:
            entry["dri_directed_off"] = None
            entry["dri_directed_on"] = None
            entry["dri_inertial_control"] = None
            entry["delta_dri_on_vs_off"] = None
            entry["delta_dri_on_vs_inertial_control"] = None

        if descriptor["scenario"] == "competing_targets":
            oi_off_frame = _metric_frame(directed_off, "overwrite_index")
            oi_on_frame = _metric_frame(directed_on, "overwrite_index")
            oi_inertial_frame = (
                _metric_frame(inertial_control, "overwrite_index")
                if not inertial_control.empty
                else pd.DataFrame()
            )

            if not oi_off_frame.empty and not oi_on_frame.empty:
                entry["overwrite_index_directed_off"] = _distribution_summary(
                    oi_off_frame["metric"].to_numpy(dtype=float)
                )
                entry["overwrite_index_directed_on"] = _distribution_summary(
                    oi_on_frame["metric"].to_numpy(dtype=float)
                )
                entry["delta_overwrite_index_on_vs_off"] = _distribution_summary(
                    _paired_delta(oi_on_frame, oi_off_frame)
                )
            else:
                entry["overwrite_index_directed_off"] = None
                entry["overwrite_index_directed_on"] = None
                entry["delta_overwrite_index_on_vs_off"] = None

            if oi_inertial_frame.empty or oi_on_frame.empty:
                entry["overwrite_index_inertial_control"] = None
                entry["delta_overwrite_index_on_vs_inertial_control"] = None
            else:
                entry["overwrite_index_inertial_control"] = _distribution_summary(
                    oi_inertial_frame["metric"].to_numpy(dtype=float)
                )
                entry["delta_overwrite_index_on_vs_inertial_control"] = _distribution_summary(
                    _paired_delta(oi_on_frame, oi_inertial_frame)
                )
        else:
            entry["overwrite_index_directed_off"] = None
            entry["overwrite_index_directed_on"] = None
            entry["overwrite_index_inertial_control"] = None
            entry["delta_overwrite_index_on_vs_off"] = None
            entry["delta_overwrite_index_on_vs_inertial_control"] = None

        for metric_name in (
            "k_directed_off",
            "k_directed_on",
            "k_inertial_control",
            "delta_k_on_vs_off",
            "delta_k_on_vs_inertial_control",
            "dri_directed_off",
            "dri_directed_on",
            "dri_inertial_control",
            "delta_dri_on_vs_off",
            "delta_dri_on_vs_inertial_control",
            "overwrite_index_directed_off",
            "overwrite_index_directed_on",
            "overwrite_index_inertial_control",
            "delta_overwrite_index_on_vs_off",
            "delta_overwrite_index_on_vs_inertial_control",
        ):
            _record_exact_metric(exact_metrics, descriptor, metric_name, entry[metric_name])

        groups.append(entry)

    imprint_memory = df[
        (df["scenario"] == "imprint")
        & (df["policy"] == "directed")
        & (df["memory_mode"] == "on")
    ]["mri"].dropna()
    hysteresis_memory = df[
        (df["scenario"] == "hysteresis")
        & (df["policy"] == "directed")
        & (df["memory_mode"] == "on")
    ]["hla"].dropna()
    damage_memory = df[
        (df["scenario"] == "damage")
        & (df["policy"] == "directed")
        & (df["memory_mode"] == "on")
    ]["dri"].dropna()
    competing_memory = df[
        (df["scenario"] == "competing_targets")
        & (df["policy"] == "directed")
        & (df["memory_mode"] == "on")
    ]["overwrite_index"].dropna()

    mri_summary = (
        None
        if imprint_memory.empty
        else _distribution_summary(imprint_memory.to_numpy(dtype=float))
    )
    hla_summary = (
        None
        if hysteresis_memory.empty
        else _distribution_summary(hysteresis_memory.to_numpy(dtype=float))
    )
    dri_summary = (
        None if damage_memory.empty else _distribution_summary(damage_memory.to_numpy(dtype=float))
    )
    competing_summary = (
        None
        if competing_memory.empty
        else _distribution_summary(competing_memory.to_numpy(dtype=float))
    )

    _record_exact_metric(exact_metrics, {"scope": "global"}, "mri", mri_summary)
    _record_exact_metric(exact_metrics, {"scope": "global"}, "hla", hla_summary)
    _record_exact_metric(exact_metrics, {"scope": "global"}, "dri", dri_summary)
    _record_exact_metric(exact_metrics, {"scope": "global"}, "overwrite_index", competing_summary)

    acceptance = {
        "hysteresis_ci_low_gt_zero": bool(hla_summary is not None and hla_summary["low"] > 0.0),
        "mri_ci_low_gt_zero": bool(mri_summary is not None and mri_summary["low"] > 0.0),
        "delta_k_on_vs_off_low_gt_zero_group_count": int(delta_k_on_vs_off_low_positive_count),
        "delta_k_on_vs_off_low_gt_zero_group_count_target": 2,
        "delta_k_on_vs_inertial_low_gt_zero_group_count": int(
            delta_k_on_vs_inertial_low_positive_count
        ),
        "delta_k_on_vs_inertial_low_gt_zero_group_count_target": 2,
    }
    acceptance["delta_k_on_vs_off_target_met"] = (
        acceptance["delta_k_on_vs_off_low_gt_zero_group_count"]
        >= acceptance["delta_k_on_vs_off_low_gt_zero_group_count_target"]
    )
    acceptance["delta_k_on_vs_inertial_target_met"] = (
        acceptance["delta_k_on_vs_inertial_low_gt_zero_group_count"]
        >= acceptance["delta_k_on_vs_inertial_low_gt_zero_group_count_target"]
    )
    acceptance["primary_gate_met"] = (
        acceptance["hysteresis_ci_low_gt_zero"]
        and acceptance["mri_ci_low_gt_zero"]
        and acceptance["delta_k_on_vs_off_target_met"]
    )
    acceptance["control_separation_gate_met"] = acceptance["delta_k_on_vs_inertial_target_met"]

    return {
        "rows": int(len(df)),
        "group_keys": group_keys,
        "groups": groups,
        "scenario_backend": groups,
        "mri": mri_summary,
        "hla": hla_summary,
        "dri": dri_summary,
        "overwrite_index": competing_summary,
        "stochasticity": {
            "exact_metric_count": len(exact_metrics),
            "exact_metrics": exact_metrics,
        },
        "acceptance": acceptance,
    }


def write_summary(df: pd.DataFrame, out_path: Path) -> dict[str, Any]:
    summary = summarize_results(df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
