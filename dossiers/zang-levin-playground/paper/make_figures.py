"""Generate paper figures (PDF + PNG) from small JSON summaries in paper/results/.

Usage:
  uv run python paper/make_figures.py

Outputs:
  paper/figures/fig1_temporal_vs_clustering.{pdf,png}
  paper/figures/fig2_clustering_ablation.{pdf,png}
  paper/figures/fig3_2d_success_heatmaps.{pdf,png}
  paper/figures/fig4_dip_trajectories.{pdf,png}
  paper/figures/fig5_h1_bar.{pdf,png}
  paper/figures/fig6_k_values.{pdf,png}
  paper/figures/fig7_selection_factorization.{pdf,png}
  paper/figures/fig8_substrate_work.{pdf,png}
  paper/figures/fig9_timing_interventions.{pdf,png}
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from adjustText import adjust_text
from cycler import cycler
from matplotlib import colors as mcolors
from matplotlib import font_manager

REPO_ROOT = Path(__file__).resolve().parents[3]
SPECTER_FONT_DIR = REPO_ROOT / "addenda" / "typst-field-manual" / "assets" / "fonts"
SPECTER_PLOT_STYLE = REPO_ROOT / "addenda" / "typst-field-manual" / "paper-plot.mplstyle"

INK = "#1a1a1a"
MUTED = "#616161"
RULE = "#c7c7c7"
PANEL = "#f9f9f9"
ACCENT = "#1f4555"
ACCENT_WARM = "#8c4f2e"
ACCENT_OLIVE = "#5b7a3b"
ACCENT_ROSE = "#b35340"
ACCENT_SLATE = "#6c697a"

BASE_PALETTE = (
    ACCENT,
    ACCENT_WARM,
    ACCENT_OLIVE,
    ACCENT_ROSE,
    ACCENT_SLATE,
)

ALGO_COLORS = {
    "Bubble": ACCENT,
    "Selection": ACCENT_WARM,
    "Insertion": ACCENT_OLIVE,
    "Gnome": ACCENT_SLATE,
    "Shaker": ACCENT_ROSE,
    "Selection-adaptive": ACCENT_WARM,
    "Selection-stubborn": ACCENT_ROSE,
    "long_range_rerouting": ACCENT_WARM,
    "long_range_stubborn": ACCENT_ROSE,
    "adjacent_rerouting": ACCENT,
    "adjacent_stubborn": ACCENT_SLATE,
}

HEATMAP_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "specter_heatmap",
    [PANEL, "#d8e2e6", ACCENT],
)


def _configure_matplotlib() -> None:
    if not SPECTER_PLOT_STYLE.is_file():
        raise FileNotFoundError(f"missing plot style file: {SPECTER_PLOT_STYLE}")
    if not SPECTER_FONT_DIR.is_dir():
        raise FileNotFoundError(f"missing font dir: {SPECTER_FONT_DIR}")

    for font_path in sorted(SPECTER_FONT_DIR.glob("*.ttf")):
        font_manager.fontManager.addfont(str(font_path))

    plt.style.use(str(SPECTER_PLOT_STYLE))
    plt.rcParams["axes.prop_cycle"] = cycler(color=BASE_PALETTE)


def _palette(n: int) -> list[str]:
    return [BASE_PALETTE[i % len(BASE_PALETTE)] for i in range(n)]


def _note(ax: plt.Axes, text: str, *, x: float = 0.02, y: float = 0.98) -> None:
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color=MUTED,
    )


_configure_matplotlib()


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. These figure inputs live in paper/results/ and are generated "
            "by running the corresponding experiments or paper-local summary scripts."
        )
    return json.loads(path.read_text())


def _save(fig: plt.Figure, out_base: Path) -> None:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out_base.with_suffix(".png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_fig1(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig1_temporal_vs_clustering.json")
    rows = obj["rows"]
    r = float(obj["pearson_r"])

    x = np.array([row["temporal_separation"] for row in rows], dtype=float)
    y = np.array([row["clustering_increase_mean"] for row in rows], dtype=float)
    ci_lo = np.array([row["clustering_increase_ci_lo"] for row in rows], dtype=float)
    ci_hi = np.array([row["clustering_increase_ci_hi"] for row in rows], dtype=float)
    yerr = np.array([y - ci_lo, ci_hi - y])
    labels = [row["pair"] for row in rows]

    fig, ax = plt.subplots(
        figsize=(8.0, 5.8)
    )  # Increased from 7.2x5.2 for more breathing room
    ax.errorbar(
        x,
        y,
        yerr=yerr,
        fmt="o",
        color=ACCENT,
        markersize=7.5,
        markerfacecolor=ACCENT,
        markeredgecolor="white",
        markeredgewidth=0.8,
        capsize=4,
        capthick=1.2,
        elinewidth=1.2,
    )

    if len(x) >= 2:
        std_err = (yerr[0] + yerr[1]) / 2.0
        weights = 1.0 / (std_err**2 + 1e-8)
        m, b = np.polyfit(x, y, 1, w=weights)
        xs = np.linspace(float(x.min()), float(x.max()), 100)
        ax.plot(xs, m * xs + b, linewidth=2, color=ACCENT_WARM, label="Weighted fit")
        ax.legend()

    texts = []
    for xi, yi, lab in zip(x, y, labels, strict=True):
        texts.append(ax.text(xi, yi, lab, fontsize=8.5, color=INK))
    adjust_text(texts, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5))

    ax.set_title("Temporal separation vs. clustering", loc="left")
    _note(ax, f"Pearson r = {r:.3f}", x=0.66)
    ax.set_xlabel("Temporal separation (|mean move time_a - mean move time_b|)")
    ax.set_ylabel("Clustering increase (max clustering - baseline)")
    ax.grid(True, alpha=0.45)

    # Expand y-limits slightly to prevent tight cutoff
    ax.set_ylim(bottom=float(y.min() - 0.04), top=float(y.max() + 0.04))
    # Expand x-limits to give text room to spread out
    ax.set_xlim(left=float(x.min() - 0.05), right=float(x.max() + 0.05))

    _save(fig, figures_dir / "fig1_temporal_vs_clustering")


def make_fig2(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig2_clustering_ablation.json")
    rows = obj["rows"]

    labels = [r["label"] for r in rows]
    clustering = [float(r["clustering"]) for r in rows]
    type2_time = [float(r["type2_avg_time"]) for r in rows]

    has_std = all("clustering_std" in r for r in rows)
    yerr = [float(r["clustering_std"]) for r in rows] if has_std else None

    # Slightly taller figure to accommodate the tall error bars + text
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    bars = ax.bar(
        range(len(labels)),
        clustering,
        yerr=yerr,
        capsize=4 if yerr else 0,
        color=_palette(len(labels)),
        edgecolor=INK,
        linewidth=1.2,
    )

    text_offset = 0.015  # Increased offset to prevent overlapping the error bar line
    for i, (bar, t) in enumerate(zip(bars, type2_time, strict=True)):
        # place text ABOVE the top of the error bar if it exists, not just above the bar
        y_pos = bar.get_height() + (yerr[i] if yerr else 0) + text_offset
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y_pos,
            f"type2 time={t:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color=MUTED,
        )

    # Adjust y-limit to ensure the highest text annotation is fully visible
    max_height = max(bar.get_height() + (yerr[i] if yerr else 0) for i, bar in enumerate(bars))
    ax.set_ylim(top=max_height + 0.04)

    ax.set_title("Clustering ablation", loc="left")
    ax.set_ylabel("Clustering increase (max - baseline)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(True, axis="y", alpha=0.45)

    _save(fig, figures_dir / "fig2_clustering_ablation")


def _plot_success_heatmap(
    ax: plt.Axes,
    matrix: np.ndarray,
    frozen: list[int],
    title: str,
) -> object:
    im = ax.imshow(matrix, vmin=0.0, vmax=1.0, cmap=HEATMAP_CMAP, aspect="auto")

    ax.set_title(title, loc="left")
    ax.set_xlabel("Frozen cells")
    ax.set_xticks(range(len(frozen)))
    ax.set_xticklabels([str(f) for f in frozen])

    ax.set_yticks([0, 1])
    ax.set_yticklabels(["conn=4", "conn=8"])

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            color = "k" if val >= 0.5 else "w"
            ax.text(
                j,
                i,
                f"{int(round(100 * val))}%",
                ha="center",
                va="center",
                fontsize=9,
                color=color,
            )

    return im


def make_fig3(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig3_2d_success_heatmaps.json")
    succ = obj["success_2d"]

    grid6_frozen = succ["grid6_conn4"]["frozen"]
    grid8_frozen = succ["grid8_conn4"]["frozen"]

    bubble6 = np.array([succ["grid6_conn4"]["Bubble2D"], succ["grid6_conn8"]["Bubble2D"]])
    sel6 = np.array([succ["grid6_conn4"]["Selection2D"], succ["grid6_conn8"]["Selection2D"]])

    bubble8 = np.array([succ["grid8_conn4"]["Bubble2D"], succ["grid8_conn8"]["Bubble2D"]])
    sel8 = np.array([succ["grid8_conn4"]["Selection2D"], succ["grid8_conn8"]["Selection2D"]])

    fig, axs = plt.subplots(2, 2, figsize=(10.6, 6.2), constrained_layout=True)

    im0 = _plot_success_heatmap(axs[0, 0], bubble6, grid6_frozen, "Bubble2D, 6x6")
    _plot_success_heatmap(axs[0, 1], sel6, grid6_frozen, "Selection2D, 6x6")
    _plot_success_heatmap(axs[1, 0], bubble8, grid8_frozen, "Bubble2D, 8x8")
    _plot_success_heatmap(axs[1, 1], sel8, grid8_frozen, "Selection2D, 8x8")

    fig.colorbar(im0, ax=axs.ravel().tolist(), shrink=0.92, label="Success rate")

    _save(fig, figures_dir / "fig3_2d_success_heatmaps")


def _shade_dips(ax: plt.Axes, dips: list[dict]) -> None:
    for d in dips:
        ax.axvspan(int(d["start_idx"]), int(d["end_idx"]), color=ACCENT, alpha=0.08)


def make_fig4(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig4_dip_trajectories.json")

    fig, axs = plt.subplots(2, 2, figsize=(12.0, 6.6), constrained_layout=True)

    b1 = obj["1d"]["bubble"]
    s1 = obj["1d"]["selection"]

    b2 = obj["2d"]["bubble"]
    s2 = obj["2d"]["selection"]

    dip_grid = b2.get("grid_size", 6)
    dip_frozen = b2.get("n_frozen", 3)
    dip_connectivity = b2.get("connectivity", 4)

    axs[0, 0].plot(b1["trajectory"], linewidth=1.8, color=ACCENT)
    _shade_dips(axs[0, 0], b1["dips"])
    axs[0, 0].set_title("1D Bubble", loc="left")
    _note(axs[0, 0], f"frozen={b1['n_frozen']} · success={b1['success']}")

    axs[0, 1].plot(s1["trajectory"], linewidth=1.8, color=ACCENT_WARM)
    _shade_dips(axs[0, 1], s1["dips"])
    axs[0, 1].set_title("1D Selection", loc="left")
    _note(axs[0, 1], f"frozen={s1['n_frozen']} · success={s1['success']}")

    axs[1, 0].plot(b2["trajectory"], linewidth=1.8, color=ACCENT)
    _shade_dips(axs[1, 0], b2["dips"])
    b2_sorted = b2["sorted"]
    axs[1, 0].set_title("2D Bubble", loc="left")
    _note(
        axs[1, 0],
        f"grid={dip_grid} · conn={dip_connectivity} · frozen={dip_frozen} · sorted={b2_sorted}",
    )

    axs[1, 1].plot(s2["trajectory"], linewidth=1.8, color=ACCENT_WARM)
    _shade_dips(axs[1, 1], s2["dips"])
    s2_sorted = s2["sorted"]
    axs[1, 1].set_title("2D Selection", loc="left")
    _note(
        axs[1, 1],
        f"grid={dip_grid} · conn={dip_connectivity} · frozen={dip_frozen} · sorted={s2_sorted}",
    )

    for ax in axs.flat:
        ax.set_xlabel("Swap step")
        ax.set_ylabel("Monotonicity errors / inversions")
        ax.grid(True, alpha=0.4)

    _save(fig, figures_dir / "fig4_dip_trajectories")


def make_fig5(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig5_h1_bar.json")
    flow_obj = _load_json(results_dir / "fig5_directed_flow.json")

    h1_1d = obj["h1_1d"]
    h1_2d = obj["h1_2d"]

    fig, axs = plt.subplots(1, 3, figsize=(16.2, 4.6), constrained_layout=True)

    labels_1d = [r["label"] for r in h1_1d]
    means_1d = [float(r["mean"]) for r in h1_1d]
    stds_1d = [float(r["std"]) for r in h1_1d]

    axs[0].bar(
        range(len(labels_1d)),
        means_1d,
        yerr=stds_1d,
        capsize=5,
        color=_palette(len(labels_1d)),
        edgecolor=INK,
        linewidth=1.2,
    )
    axs[0].set_title("1D H1 profile", loc="left")
    axs[0].set_ylabel("H1 feature count")
    axs[0].set_xticks(range(len(labels_1d)))
    axs[0].set_xticklabels(labels_1d, rotation=25, ha="right")
    axs[0].grid(True, axis="y", alpha=0.45)

    labels_2d = [r["label"] for r in h1_2d]
    means_2d = [float(r["mean"]) for r in h1_2d]
    stds_2d = [float(r["std"]) for r in h1_2d]
    success_2d = [float(r["success"]) for r in h1_2d]

    bars = axs[1].bar(
        range(len(labels_2d)),
        means_2d,
        yerr=stds_2d,
        capsize=5,
        color=_palette(len(labels_2d)),
        edgecolor=INK,
        linewidth=1.2,
    )
    axs[1].set_title("2D H1 profile", loc="left")
    axs[1].set_ylabel("H1 feature count")
    axs[1].set_xticks(range(len(labels_2d)))
    axs[1].set_xticklabels(labels_2d)
    axs[1].grid(True, axis="y", alpha=0.45)

    for i, (bar, s) in enumerate(zip(bars, success_2d, strict=True)):
        y_pos = bar.get_height() + stds_2d[i] + 0.5
        axs[1].text(
            bar.get_x() + bar.get_width() / 2,
            y_pos,
            f"success={int(round(100 * s))}%",
            ha="center",
            va="bottom",
            fontsize=9,
            color=MUTED,
        )

    # Panel 3: Directed flow
    labels_flow = ["2d_bubble", "2d_selection"]
    flow_ratios = [flow_obj[label]["ratio"] for label in labels_flow]
    axs[2].bar(
        range(len(labels_flow)),
        flow_ratios,
        color=_palette(len(labels_flow)),
        edgecolor=INK,
        linewidth=1.2,
    )
    axs[2].set_title("Directed flow", loc="left")
    axs[2].set_ylabel("Directed Flow Score (forward / max(backward, 1))")
    axs[2].set_yscale("log")
    axs[2].set_xticks(range(len(labels_flow)))
    axs[2].set_xticklabels(["Bubble2D", "Selection2D"])
    axs[2].grid(True, axis="y", alpha=0.45)

    # annotations
    for i, ratio in enumerate(flow_ratios):
        forward = int(flow_obj[labels_flow[i]]["forward"])
        backward = int(flow_obj[labels_flow[i]]["backward"])
        axs[2].text(
            i,
            ratio * 1.2,
            f"{ratio:.1f}\n({forward}/{backward})",
            ha="center",
            va="bottom",
            fontsize=9,
            color=MUTED,
        )

    _save(fig, figures_dir / "fig5_h1_bar")

def make_fig6(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "fig6_k_values.json")

    conditions = obj["conditions"]
    frozen_counts = obj["frozen_counts"]
    baseline_variants = [
        "long_range_rerouting",
        "long_range_stubborn",
        "adjacent_rerouting",
        "adjacent_stubborn",
    ]
    baseline_labels = [
        "Long+reroute",
        "Long+stubborn",
        "Adj+reroute",
        "Adj+stubborn",
    ]

    fig, axs = plt.subplots(1, 2, figsize=(13.0, 5.0), constrained_layout=True)

    baseline_k = [conditions[variant]["0"]["k_lower"] for variant in baseline_variants]
    baseline_ci_lo = [conditions[variant]["0"]["k_ci_lo"] for variant in baseline_variants]
    baseline_ci_hi = [conditions[variant]["0"]["k_ci_hi"] for variant in baseline_variants]
    baseline_yerr = np.array([
        [k - lo for k, lo in zip(baseline_k, baseline_ci_lo)],
        [hi - k for k, hi in zip(baseline_k, baseline_ci_hi)],
    ])
    colors = [ALGO_COLORS[variant] for variant in baseline_variants]

    axs[0].bar(
        range(len(baseline_variants)),
        baseline_k,
        yerr=baseline_yerr,
        capsize=5,
        color=colors,
        edgecolor=INK,
        linewidth=1.2,
    )
    axs[0].set_title("Matched state-space K at frozen=0", loc="left")
    axs[0].set_ylabel(
        r"$K_{\mathrm{state}} = \log_{10}(\tau_{\mathrm{blind}}^{\mathrm{state}} / "
        r"\tau_{\mathrm{agent}}^{\mathrm{eff}})$"
    )
    axs[0].set_xticks(range(len(baseline_variants)))
    axs[0].set_xticklabels(baseline_labels, rotation=25, ha="right")
    axs[0].grid(True, axis="y", alpha=0.45)
    axs[0].axhline(
        y=0,
        color=MUTED,
        linestyle="--",
        linewidth=1.0,
        label=r"State-space null ($K_{\mathrm{state}}=0$)",
    )
    axs[0].legend(fontsize=9, loc="lower left")
    _note(axs[0], "Immovable factorization trials; distance-weighted operator cost", x=0.02, y=1.06)

    line_variants = [
        ("long_range_rerouting", "Long+reroute"),
        ("long_range_stubborn", "Long+stubborn"),
        ("adjacent_rerouting", "Adj+reroute"),
        ("adjacent_stubborn", "Adj+stubborn"),
    ]
    for variant, label in line_variants:
        frozen_data = conditions[variant]
        k_vals = [frozen_data[str(f)]["k_lower"] for f in frozen_counts]
        k_lo = [frozen_data[str(f)]["k_ci_lo"] for f in frozen_counts]
        k_hi = [frozen_data[str(f)]["k_ci_hi"] for f in frozen_counts]

        valid = [not (np.isnan(v)) for v in k_vals]
        fc = [f for f, v in zip(frozen_counts, valid) if v]
        kv = [k for k, v in zip(k_vals, valid) if v]
        kl = [lo for lo, v in zip(k_lo, valid) if v]
        kh = [hi for hi, v in zip(k_hi, valid) if v]

        if not fc:
            continue

        yerr_line = np.array([
            [k - lo for k, lo in zip(kv, kl)],
            [hi - k for k, hi in zip(kv, kh)],
        ])

        axs[1].errorbar(
            fc, kv, yerr=yerr_line,
            marker="o", capsize=4, capthick=1.2, elinewidth=1.2,
            label=label, color=ALGO_COLORS[variant],
        )

    axs[1].set_title("Matched state-space K under immovable frozen indices", loc="left")
    axs[1].set_xlabel("Number of frozen cells")
    axs[1].set_ylabel(r"$K_{\mathrm{state}}$")
    axs[1].grid(True, alpha=0.45)
    axs[1].axhline(
        y=0,
        color=MUTED,
        linestyle="--",
        linewidth=1.0,
        label=r"State-space null ($K_{\mathrm{state}}=0$)",
    )
    axs[1].legend(fontsize=9, loc="lower left")
    _note(
        axs[1],
        "Adjacent family has 0/30 reachable trials at frozen 3/6/9; no K points shown there.",
        x=0.02,
        y=1.06,
    )

    _save(fig, figures_dir / "fig6_k_values")


def _success_heatmap_matrix(
    summary: dict[str, dict[str, dict[str, float]]],
    variants: list[str],
    frozen_counts: list[int],
) -> np.ndarray:
    return np.array(
        [
            [float(summary[variant][str(frozen)]["success_rate"]) for frozen in frozen_counts]
            for variant in variants
        ]
    )


def _annotated_heatmap(
    ax: plt.Axes,
    matrix: np.ndarray,
    row_labels: list[str],
    col_labels: list[str],
    title: str,
) -> object:
    im = ax.imshow(matrix, vmin=0.0, vmax=1.0, cmap=HEATMAP_CMAP, aspect="auto")
    ax.set_title(title, loc="left")
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_xlabel("Frozen count")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            color = INK if val < 0.62 else "white"
            ax.text(
                j,
                i,
                f"{int(round(100 * val))}%",
                ha="center",
                va="center",
                fontsize=9,
                color=color,
            )
    return im


def make_fig7(results_dir: Path, figures_dir: Path) -> None:
    immovable = _load_json(
        results_dir / "exp25_selection_factorization_aggregate_n30_t5_immovable.json"
    )
    movable = _load_json(
        results_dir / "exp25_selection_factorization_aggregate_n30_t5_movable.json"
    )

    immovable_summary = immovable["summary"]["immovable"]
    movable_summary = movable["summary"]["movable"]
    variants = [
        "long_range_rerouting",
        "long_range_stubborn",
        "adjacent_rerouting",
        "adjacent_stubborn",
    ]
    variant_labels = [
        "Long+reroute",
        "Long+stubborn",
        "Adj+reroute",
        "Adj+stubborn",
    ]
    immovable_frozen = [0, 3, 6, 9]
    movable_frozen = [0, 1, 2, 3]

    fig, axs = plt.subplots(1, 2, figsize=(11.4, 5.0), constrained_layout=True)

    im = _annotated_heatmap(
        axs[0],
        _success_heatmap_matrix(immovable_summary, variants, immovable_frozen),
        variant_labels,
        [str(v) for v in immovable_frozen],
        "Immovable semantics",
    )
    _annotated_heatmap(
        axs[1],
        _success_heatmap_matrix(movable_summary, variants, movable_frozen),
        variant_labels,
        [str(v) for v in movable_frozen],
        "Movable semantics",
    )

    axs[0].set_ylabel("Selection variant")
    axs[1].set_ylabel("")
    _note(axs[0], "n=30 trials per condition", x=0.02, y=1.06)
    _note(axs[1], "n=15 trials per condition", x=0.02, y=1.06)
    fig.colorbar(im, ax=axs.ravel().tolist(), shrink=0.92, label="Success rate")

    _save(fig, figures_dir / "fig7_selection_factorization")


def make_fig8(results_dir: Path, figures_dir: Path) -> None:
    trio = _load_json(
        results_dir / "exp26_original_trio_aggregate_n30_t3_frozen1_3_budget200k.json"
    )
    selection_family = _load_json(
        results_dir / "exp26_selection_family_aggregate_n30_t3_budget200k.json"
    )

    trio_algos = ["Bubble", "Insertion", "Selection"]
    trio_labels = ["Bubble", "Insertion", "Selection"]
    frozen_counts_trio = ["1", "3"]
    trio_ratios = {
        frozen: [
            float(
                trio["algorithms"][algo]["threaded_cellview"][frozen][
                    "avg_compare_and_swap_count"
                ]
            )
            / float(
                trio["algorithms"][algo]["sequential_cellview"][frozen][
                    "avg_compare_and_swap_count"
                ]
            )
            for algo in trio_algos
        ]
        for frozen in frozen_counts_trio
    }

    family_frozen = [0, 1, 3, 6, 9]
    family_algos = [
        ("Selection", "Published Selection", ACCENT_WARM),
        ("StubbornSelection", "Stubborn", ACCENT_ROSE),
        ("AdjacentSelection", "Adjacent reroute", ACCENT),
        ("AdjacentStubbornSelection", "Adjacent stubborn", ACCENT_SLATE),
    ]

    fig, axs = plt.subplots(1, 2, figsize=(12.8, 4.8), constrained_layout=True)

    width = 0.35
    x = np.arange(len(trio_labels))
    axs[0].bar(
        x - width / 2,
        trio_ratios["1"],
        width=width,
        color=ACCENT,
        edgecolor=INK,
        linewidth=1.1,
        label="frozen=1",
    )
    axs[0].bar(
        x + width / 2,
        trio_ratios["3"],
        width=width,
        color=ACCENT_WARM,
        edgecolor=INK,
        linewidth=1.1,
        label="frozen=3",
    )
    axs[0].set_title("Threaded / sequential work ratio", loc="left")
    axs[0].set_ylabel("Compare-and-swap ratio")
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(trio_labels)
    axs[0].set_yscale("log")
    axs[0].grid(True, axis="y", alpha=0.45)
    axs[0].legend(fontsize=9)

    for idx, frozen in enumerate(frozen_counts_trio):
        xs = x - width / 2 if frozen == "1" else x + width / 2
        for xi, ratio in zip(xs, trio_ratios[frozen], strict=True):
            axs[0].text(
                xi,
                ratio * 1.12,
                f"{ratio:.1f}x",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color=MUTED,
            )

    for algo_key, label, color in family_algos:
        threaded = [
            float(
                selection_family["algorithms"][algo_key]["threaded_cellview"][str(frozen)][
                    "avg_compare_and_swap_count"
                ]
            )
            for frozen in family_frozen
        ]
        sequential = [
            float(
                selection_family["algorithms"][algo_key]["sequential_cellview"][str(frozen)][
                    "avg_compare_and_swap_count"
                ]
            )
            for frozen in family_frozen
        ]
        axs[1].plot(
            family_frozen,
            threaded,
            color=color,
            linewidth=2.0,
            marker="o",
            label=f"{label} (threaded)",
        )
        axs[1].plot(
            family_frozen,
            sequential,
            color=color,
            linewidth=1.5,
            linestyle="--",
            marker="o",
            alpha=0.85,
            label=f"{label} (sequential)",
        )

    axs[1].set_title("Selection-family work by substrate", loc="left")
    axs[1].set_xlabel("Frozen count")
    axs[1].set_ylabel("Average compare-and-swap count")
    axs[1].set_xticks(family_frozen)
    axs[1].set_yscale("log")
    axs[1].grid(True, alpha=0.45)
    axs[1].legend(fontsize=8, ncol=2, loc="upper left")

    _save(fig, figures_dir / "fig8_substrate_work")


def make_fig9(results_dir: Path, figures_dir: Path) -> None:
    obj = _load_json(results_dir / "exp27_timing_interventions_aggregate.json")
    row_map = {row["pair"]: row for row in obj["rows"]}
    pair_order = [
        "Bubble+InsertionNoWait",
        "Bubble+BubbleClone",
        "Bubble+DelayedBubble",
        "Gnome+GnomeClone",
        "Gnome+DelayedGnome",
        "Bubble+Insertion",
    ]
    pair_labels = [
        "Bubble+\nInsertionNoWait",
        "Bubble+\nBubbleClone",
        "Bubble+\nDelayedBubble",
        "Gnome+\nGnomeClone",
        "Gnome+\nDelayedGnome",
        "Bubble+\nInsertion",
    ]
    synthetic_pairs = {"Bubble+DelayedBubble", "Gnome+DelayedGnome"}
    colors = [
        ACCENT if pair in synthetic_pairs else ACCENT_SLATE
        for pair in pair_order
    ]
    x = np.arange(len(pair_order))

    clustering = np.array([float(row_map[pair]["clustering_increase_mean"]) for pair in pair_order])
    ci_lo = np.array([float(row_map[pair]["clustering_increase_ci_lo"]) for pair in pair_order])
    ci_hi = np.array([float(row_map[pair]["clustering_increase_ci_hi"]) for pair in pair_order])
    clustering_yerr = np.vstack([clustering - ci_lo, ci_hi - clustering])

    separation = np.array([float(row_map[pair]["temporal_separation"]) for pair in pair_order])
    separation_ci_lo = np.array(
        [float(row_map[pair]["temporal_separation_ci_lo"]) for pair in pair_order]
    )
    separation_ci_hi = np.array(
        [float(row_map[pair]["temporal_separation_ci_hi"]) for pair in pair_order]
    )
    separation_yerr = np.vstack([separation - separation_ci_lo, separation_ci_hi - separation])

    fig, axs = plt.subplots(1, 2, figsize=(12.6, 4.8), constrained_layout=True)

    axs[0].bar(
        x,
        clustering,
        color=colors,
        edgecolor=INK,
        linewidth=1.1,
        yerr=clustering_yerr,
        capsize=4,
    )
    axs[0].set_title("Clustering increase", loc="left")
    axs[0].set_ylabel(r"$\Delta C$")
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(pair_labels)
    axs[0].grid(True, axis="y", alpha=0.45)

    for xi, value in zip(x, clustering, strict=True):
        axs[0].text(
            xi,
            value + 0.008,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=MUTED,
        )

    axs[1].bar(
        x,
        separation,
        color=colors,
        edgecolor=INK,
        linewidth=1.1,
        yerr=separation_yerr,
        capsize=4,
    )
    axs[1].set_title("Temporal separation", loc="left")
    axs[1].set_ylabel("Mean normalized swap-time gap")
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(pair_labels)
    axs[1].grid(True, axis="y", alpha=0.45)

    for xi, value in zip(x, separation, strict=True):
        axs[1].text(
            xi,
            value + 0.006,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=MUTED,
        )

    _note(axs[0], "Synthetic waiting gates are highlighted", x=0.02, y=1.06)
    _note(axs[1], f"n={obj['n_trials_total_per_pair']} trials per pair", x=0.02, y=1.06)

    _save(fig, figures_dir / "fig9_timing_interventions")


def main() -> None:
    here = Path(__file__).resolve().parent
    results_dir = here / "results"
    figures_dir = here / "figures"

    make_fig1(results_dir, figures_dir)
    make_fig2(results_dir, figures_dir)
    make_fig3(results_dir, figures_dir)
    make_fig4(results_dir, figures_dir)
    make_fig5(results_dir, figures_dir)
    make_fig6(results_dir, figures_dir)
    make_fig7(results_dir, figures_dir)
    make_fig8(results_dir, figures_dir)
    make_fig9(results_dir, figures_dir)


if __name__ == "__main__":
    main()
