from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from render_cinematic_plate import PlatePanel, render_cinematic_plate
from render_cinematic_run import CameraSpec, RenderSpec, render_cinematic_run

DOSSIER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DOSSIER_ROOT.parents[1]
SITE_ASSET_DIR = REPO_ROOT / "site" / "assets" / "blog" / "jolt-material-memory"


def _run_analysis(manifest_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(DOSSIER_ROOT / "scripts" / "analyze_campaign.py"),
            "--manifest",
            str(manifest_path),
        ],
        check=True,
    )


def _copy(src: Path, dest_name: str) -> None:
    dest = SITE_ASSET_DIR / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _render_video(src: Path, dest_name: str, spec: RenderSpec) -> None:
    render_cinematic_run(src, SITE_ASSET_DIR / dest_name, spec)


def build_assets() -> None:
    SITE_ASSET_DIR.mkdir(parents=True, exist_ok=True)

    _run_analysis(DOSSIER_ROOT / "data" / "paper_track_v1" / "campaign_manifest.json")
    _run_analysis(DOSSIER_ROOT / "data" / "damage_ablation_v1" / "campaign_manifest.json")
    _run_analysis(DOSSIER_ROOT / "data" / "layout_generalization_v1" / "campaign_manifest.json")
    _run_analysis(DOSSIER_ROOT / "data" / "competing_targets_v1" / "campaign_manifest.json")

    _copy(
        DOSSIER_ROOT / "data" / "paper_track_v1" / "analysis" / "plots" / "imprint_mri_bar.png",
        "fig-imprint-mri.png",
    )
    _copy(
        DOSSIER_ROOT / "data" / "paper_track_v1" / "analysis" / "plots" / "damage_recovery_bar.png",
        "fig-damage-recovery.png",
    )
    _copy(
        DOSSIER_ROOT
        / "data"
        / "damage_ablation_v1"
        / "analysis"
        / "plots"
        / "damage_recovery_bar.png",
        "fig-damage-ablation-recovery.png",
    )
    _copy(
        DOSSIER_ROOT
        / "data"
        / "layout_generalization_v1"
        / "analysis"
        / "plots"
        / "delta_k_controls.png",
        "fig-layout-delta-k-controls.png",
    )
    _copy(
        DOSSIER_ROOT / "data" / "paper_track_v1" / "analysis" / "plots" / "delta_k_controls.png",
        "fig-delta-k-controls.png",
    )
    _copy(
        DOSSIER_ROOT
        / "data"
        / "layout_generalization_v1"
        / "analysis"
        / "plots"
        / "hysteresis_scatter.png",
        "fig-layout-hysteresis.png",
    )
    _copy(
        DOSSIER_ROOT
        / "data"
        / "competing_targets_v1"
        / "analysis"
        / "plots"
        / "competing_overwrite_bar.png",
        "fig-competing-overwrite.png",
    )

    render_cinematic_run(
        DOSSIER_ROOT / "data" / "viewer" / "imprint_cpu_on_seed41000_connected.ndjson",
        SITE_ASSET_DIR / "fig-hero-substrate.png",
        RenderSpec(
            fps=24,
            stride=1,
            trail=24,
            width=1600,
            height=900,
            camera=CameraSpec(yaw_deg=-36.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=220,
            show_footer=False,
        ),
    )

    render_cinematic_plate(
        [
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "imprint_cpu_directed_off_seed41000.ndjson",
                label="memory off",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "imprint_cpu_directed_inertial_control_seed41000.ndjson",
                label="inertial control",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "imprint_cpu_directed_on_seed41000.ndjson",
                label="memory on",
            ),
        ],
        SITE_ASSET_DIR / "fig-imprint-memory-plate.png",
        RenderSpec(
            fps=24,
            stride=2,
            trail=22,
            width=560,
            height=360,
            camera=CameraSpec(yaw_deg=-36.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
        frame_ratio=0.94,
        supertitle="Imprint Comparison",
        subtitle="Matched late-stage frames with shared camera and event timeline",
    )

    render_cinematic_plate(
        [
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "damage_cpu_directed_off_seed41000.ndjson",
                label="memory off",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "damage_cpu_directed_inertial_control_seed41000.ndjson",
                label="inertial control",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "paper_track_v1"
                / "runs"
                / "damage_cpu_directed_on_seed41000.ndjson",
                label="memory on",
            ),
        ],
        SITE_ASSET_DIR / "fig-damage-memory-plate.png",
        RenderSpec(
            fps=24,
            stride=4,
            trail=22,
            width=560,
            height=360,
            camera=CameraSpec(yaw_deg=-32.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
        frame_ratio=0.90,
        supertitle="Damage Comparison",
        subtitle="Matched post-perturbation frames with shared camera and event timeline",
    )

    render_cinematic_plate(
        [
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "competing_targets_v1"
                / "runs"
                / "competing_targets_cpu_line_baseline_directed_off_seed61000.ndjson",
                label="memory off",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "competing_targets_v1"
                / "runs"
                / "competing_targets_cpu_line_baseline_directed_inertial_control_seed61000.ndjson",
                label="inertial control",
            ),
            PlatePanel(
                path=DOSSIER_ROOT
                / "data"
                / "competing_targets_v1"
                / "runs"
                / "competing_targets_cpu_line_baseline_directed_on_seed61000.ndjson",
                label="memory on",
            ),
        ],
        SITE_ASSET_DIR / "fig-competing-memory-plate.png",
        RenderSpec(
            fps=24,
            stride=2,
            trail=24,
            width=560,
            height=360,
            camera=CameraSpec(yaw_deg=-34.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
        frame_ratio=0.93,
        supertitle="Competing Targets Comparison",
        subtitle="Matched late frames after the second pulse with shared camera and event timeline",
    )

    _render_video(
        DOSSIER_ROOT / "data" / "viewer" / "imprint_cpu_on_seed41000_connected.ndjson",
        "video-imprint-line-on.mp4",
        RenderSpec(
            fps=24,
            stride=2,
            trail=24,
            width=1600,
            height=900,
            camera=CameraSpec(yaw_deg=-36.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
    )
    _render_video(
        DOSSIER_ROOT
        / "data"
        / "paper_track_v1"
        / "runs"
        / "damage_cpu_directed_on_seed41000.ndjson",
        "video-damage-line-on.mp4",
        RenderSpec(
            fps=24,
            stride=3,
            trail=26,
            width=1600,
            height=900,
            camera=CameraSpec(yaw_deg=-32.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
    )
    _render_video(
        DOSSIER_ROOT
        / "data"
        / "layout_generalization_v1"
        / "runs"
        / "hysteresis_cpu_staggered_baseline_directed_on_seed52000.ndjson",
        "video-hysteresis-staggered-on.mp4",
        RenderSpec(
            fps=24,
            stride=2,
            trail=22,
            width=1600,
            height=900,
            camera=CameraSpec(yaw_deg=-42.0, pitch_deg=24.0, distance=17.0, focal_length=15.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
    )
    _render_video(
        DOSSIER_ROOT
        / "data"
        / "competing_targets_v1"
        / "runs"
        / "competing_targets_cpu_line_baseline_directed_on_seed61000.ndjson",
        "video-competing-targets-line-on.mp4",
        RenderSpec(
            fps=24,
            stride=2,
            trail=26,
            width=1600,
            height=900,
            camera=CameraSpec(yaw_deg=-34.0, pitch_deg=20.0, distance=18.0, focal_length=16.0),
            title=None,
            subtitle=None,
            frame_index=None,
            show_footer=False,
        ),
    )


def main() -> int:
    build_assets()
    print(f"Staged article assets in {SITE_ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
