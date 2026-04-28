from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _normalize_path(path_like: str | Path) -> Path:
    p = Path(path_like)
    if p.is_absolute():
        return p
    return ROOT / p


def main() -> int:
    from analysis.plots import (
        plot_competing_overwrite,
        plot_damage_recovery,
        plot_delta_k_controls,
        plot_hysteresis_curves,
        plot_mri,
        plot_tau_distributions,
    )
    from analysis.summarize import build_metrics_table, write_summary

    parser = argparse.ArgumentParser(description="Analyze jolt-material-memory campaign outputs")
    parser.add_argument("--manifest", required=True, help="Path to campaign_manifest.json")
    parser.add_argument(
        "--out-dir",
        default="",
        help="Optional analysis output directory (default: <manifest dir>/analysis)",
    )
    args = parser.parse_args()

    manifest_path = _normalize_path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    out_dir = _normalize_path(args.out_dir) if args.out_dir else manifest_path.parent / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_df = build_metrics_table(manifest)
    metrics_csv = out_dir / "metrics_table.csv"
    metrics_df.to_csv(metrics_csv, index=False)

    summary_path = out_dir / "analysis_summary.json"
    summary = write_summary(metrics_df, summary_path)

    plots_dir = out_dir / "plots"
    tau_plot = plot_tau_distributions(metrics_df, plots_dir)
    hysteresis_plot = plot_hysteresis_curves(metrics_df, plots_dir)
    mri_plot = plot_mri(metrics_df, plots_dir)
    dri_plot = plot_damage_recovery(metrics_df, plots_dir)
    competing_plot = plot_competing_overwrite(metrics_df, plots_dir)
    delta_k_plot = plot_delta_k_controls(summary, plots_dir)

    print(f"Metrics table: {metrics_csv}")
    print(f"Summary: {summary_path}")
    print(f"Plot: {tau_plot}")
    print(f"Plot: {hysteresis_plot}")
    print(f"Plot: {mri_plot}")
    print(f"Plot: {dri_plot}")
    print(f"Plot: {competing_plot}")
    print(f"Plot: {delta_k_plot}")
    print(f"Acceptance: {summary['acceptance']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
