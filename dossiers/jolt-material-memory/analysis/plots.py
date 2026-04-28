from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BACKGROUND = "#f6efe4"
PANEL = "#fffaf3"
GRID = "#d7c8b2"
TEXT = "#243036"
MUTED = "#6f736c"
MODE_COLORS = {
    "on": "#2e8ca6",
    "off": "#c86a3b",
    "inertial_control": "#7a8a74",
}


def _group_label(row: dict[str, Any], group_keys: list[str]) -> str:
    return ":".join(str(row[key]) for key in group_keys)


def _mode_color(label: str) -> str:
    return MODE_COLORS.get(label, "#6f736c")


def _style_axes(fig: plt.Figure, ax: plt.Axes) -> None:
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=TEXT, labelcolor=TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)
    ax.grid(axis="x", color=GRID, linewidth=0.9, alpha=0.65)
    ax.set_axisbelow(True)


def plot_tau_distributions(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    _style_axes(fig, ax)

    labels: list[str] = []
    values: list[pd.Series] = []
    for (scenario, memory_mode), group in df[
        (df["policy"] == "directed")
    ].groupby(["scenario", "memory_mode"], sort=True):
        labels.append(f"{scenario}:{memory_mode}")
        values.append(group["tau_proxy"])

    ax.boxplot(
        values,
        tick_labels=labels,
        showfliers=False,
        patch_artist=True,
        boxprops={"facecolor": "#e9dfcf", "edgecolor": TEXT},
        medianprops={"color": "#b84b3e", "linewidth": 2},
        whiskerprops={"color": TEXT},
        capprops={"color": TEXT},
    )
    ax.set_title("Tau Proxy Distribution by Scenario/Memory")
    ax.set_ylabel("tau_proxy (lower is better)")
    ax.tick_params(axis="x", labelrotation=35)
    fig.tight_layout()

    out_path = out_dir / "tau_proxy_boxplot.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_hysteresis_curves(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = df[(df["scenario"] == "hysteresis") & (df["policy"] == "directed")]

    fig, ax = plt.subplots(figsize=(7, 5))
    _style_axes(fig, ax)
    for memory_mode, group in source.groupby("memory_mode", sort=True):
        grouped = group.groupby("seed", sort=True).first()
        ax.scatter(
            grouped["tau_proxy"],
            grouped["hla"],
            s=72,
            alpha=0.75,
            color=_mode_color(str(memory_mode)),
            edgecolors=PANEL,
            linewidths=0.8,
            label=f"memory {memory_mode}",
        )

    ax.set_title("Hysteresis Scenario: tau_proxy vs HLA")
    ax.set_xlabel("tau_proxy")
    ax.set_ylabel("hysteresis loop area")
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels)
    fig.tight_layout()

    out_path = out_dir / "hysteresis_scatter.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_mri(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = df[(df["scenario"] == "imprint") & (df["policy"] == "directed")]

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    _style_axes(fig, ax)
    means = source.groupby("memory_mode", sort=True)["mri"].mean()
    labels = means.index.tolist()
    values = means.to_numpy()
    y = np.arange(len(labels), dtype=float)
    colors = [_mode_color(label) for label in labels]
    ax.barh(y, values, color=colors, height=0.58)
    for idx, value in enumerate(values):
        ax.text(
            value + 0.02,
            y[idx],
            f"{value:.3f}",
            va="center",
            ha="left",
            color=TEXT,
            fontsize=10,
        )
    ax.set_yticks(y, labels)
    ax.set_title("Imprint Retention Index")
    ax.set_ylabel("MRI")
    ax.set_xlabel("mean MRI")
    fig.tight_layout()

    out_path = out_dir / "imprint_mri_bar.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_damage_recovery(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = df[(df["scenario"] == "damage") & (df["policy"] == "directed")]

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    _style_axes(fig, ax)
    means = source.groupby("memory_mode", sort=True)["dri"].mean()
    labels = means.index.tolist()
    values = means.to_numpy()
    y = np.arange(len(labels), dtype=float)
    colors = [_mode_color(label) for label in labels]
    ax.barh(y, values, color=colors, height=0.58)
    ax.axvline(0.0, color=MUTED, linewidth=1.0, alpha=0.8)
    for idx, value in enumerate(values):
        ha = "left" if value >= 0 else "right"
        offset = 0.02 if value >= 0 else -0.02
        ax.text(value + offset, y[idx], f"{value:.3f}", va="center", ha=ha, color=TEXT, fontsize=10)
    ax.set_yticks(y, labels)
    ax.set_title("Damage Recovery Index")
    ax.set_xlabel("mean DRI")
    fig.tight_layout()

    out_path = out_dir / "damage_recovery_bar.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_competing_overwrite(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = df[(df["scenario"] == "competing_targets") & (df["policy"] == "directed")]

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    _style_axes(fig, ax)
    if source.empty:
        ax.text(0.5, 0.5, "No competing_targets data", ha="center", va="center")
        ax.set_axis_off()
    else:
        means = source.groupby("memory_mode", sort=True)["overwrite_index"].mean()
        labels = means.index.tolist()
        values = means.to_numpy()
        y = np.arange(len(labels), dtype=float)
        colors = [_mode_color(label) for label in labels]
        ax.barh(y, values, color=colors, height=0.58)
        ax.axvline(0.0, color=MUTED, linewidth=1.0, alpha=0.8)
        for idx, value in enumerate(values):
            ax.text(
                value + 0.02,
                y[idx],
                f"{value:.3f}",
                va="center",
                ha="left",
                color=TEXT,
                fontsize=10,
            )
        ax.set_yticks(y, labels)
        ax.set_title("Competing-Target Overwrite Index")
        ax.set_xlabel("mean overwrite index")
    fig.tight_layout()

    out_path = out_dir / "competing_overwrite_bar.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_delta_k_controls(summary: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = summary["groups"]
    group_keys = summary["group_keys"]
    labels = [_group_label(row, group_keys) for row in rows]

    on_vs_off = np.array([row["delta_k_on_vs_off"]["median"] for row in rows], dtype=float)
    on_vs_off_low = np.array(
        [row["delta_k_on_vs_off"]["median"] - row["delta_k_on_vs_off"]["low"] for row in rows],
        dtype=float,
    )
    on_vs_off_high = np.array(
        [row["delta_k_on_vs_off"]["high"] - row["delta_k_on_vs_off"]["median"] for row in rows],
        dtype=float,
    )

    on_vs_inertial = np.array(
        [
            (
                float("nan")
                if row["delta_k_on_vs_inertial_control"] is None
                else row["delta_k_on_vs_inertial_control"]["median"]
            )
            for row in rows
        ],
        dtype=float,
    )
    on_vs_inertial_low = np.array(
        [
            (
                float("nan")
                if row["delta_k_on_vs_inertial_control"] is None
                else row["delta_k_on_vs_inertial_control"]["median"]
                - row["delta_k_on_vs_inertial_control"]["low"]
            )
            for row in rows
        ],
        dtype=float,
    )
    on_vs_inertial_high = np.array(
        [
            (
                float("nan")
                if row["delta_k_on_vs_inertial_control"] is None
                else row["delta_k_on_vs_inertial_control"]["high"]
                - row["delta_k_on_vs_inertial_control"]["median"]
            )
            for row in rows
        ],
        dtype=float,
    )

    fig_height = 1.4 + 0.62 * len(labels)
    fig, ax = plt.subplots(figsize=(10.4, fig_height))
    _style_axes(fig, ax)
    y = np.arange(len(labels), dtype=float)[::-1]
    pretty_labels = [label.replace(":", " / ") for label in labels]
    ax.errorbar(
        on_vs_off,
        y + 0.14,
        xerr=np.vstack([on_vs_off_low, on_vs_off_high]),
        fmt="o",
        color=_mode_color("off"),
        ecolor=_mode_color("off"),
        elinewidth=1.6,
        capsize=4,
        markersize=7,
        label="on vs off",
    )
    inertial_mask = np.isfinite(on_vs_inertial)
    if np.any(inertial_mask):
        ax.errorbar(
            on_vs_inertial[inertial_mask],
            y[inertial_mask] - 0.14,
            xerr=np.vstack(
                [on_vs_inertial_low[inertial_mask], on_vs_inertial_high[inertial_mask]]
            ),
            fmt="o",
            color=_mode_color("inertial_control"),
            ecolor=_mode_color("inertial_control"),
            elinewidth=1.6,
            capsize=4,
            markersize=7,
            label="on vs inertial_control",
        )
    ax.axvline(0.0, color=MUTED, linewidth=1.0, alpha=0.9)
    ax.set_title("Delta K Control Separation")
    ax.set_xlabel("delta_k (higher favors memory)")
    ax.set_yticks(y, pretty_labels)
    ax.legend(frameon=False, labelcolor=TEXT, loc="lower right")
    fig.tight_layout()

    out_path = out_dir / "delta_k_controls.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path
