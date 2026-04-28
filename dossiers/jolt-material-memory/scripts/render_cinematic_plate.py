from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from render_cinematic_run import (
    BACKGROUND_TOP,
    TEXT_COLOR,
    CameraSpec,
    RenderSpec,
    draw_cinematic_frame,
    load_renderable_run,
    union_extent,
)


@dataclass(frozen=True)
class PlatePanel:
    path: Path
    label: str


def render_cinematic_plate(
    panels: list[PlatePanel],
    out_path: Path,
    spec: RenderSpec,
    *,
    frame_ratio: float = 1.0,
    supertitle: str | None = None,
    subtitle: str | None = None,
) -> Path:
    if not panels:
        raise ValueError("at least one panel is required")
    clamped_ratio = max(0.0, min(frame_ratio, 1.0))
    runs = [load_renderable_run(panel.path, spec) for panel in panels]
    shared_extent = union_extent(runs)

    panel_width = spec.width / 160.0
    panel_height = spec.height / 160.0
    figure_height = panel_height + (0.9 if supertitle or subtitle else 0.3)
    fig = plt.figure(figsize=(panel_width * len(panels), figure_height), dpi=160)
    fig.patch.set_facecolor(BACKGROUND_TOP)
    grid = fig.add_gridspec(
        1,
        len(panels),
        left=0.02,
        right=0.98,
        top=0.80 if supertitle or subtitle else 0.96,
        bottom=0.06,
        wspace=0.025,
    )

    if supertitle:
        fig.text(
            0.02,
            0.965,
            supertitle,
            fontsize=16,
            fontweight="bold",
            color=TEXT_COLOR,
            family="DejaVu Serif",
            ha="left",
            va="top",
        )
    if subtitle:
        fig.text(
            0.02,
            0.915,
            subtitle,
            fontsize=9,
            color=TEXT_COLOR,
            family="DejaVu Sans",
            ha="left",
            va="top",
            alpha=0.85,
        )

    for index, (panel, run) in enumerate(zip(panels, runs, strict=True)):
        ax = fig.add_subplot(grid[0, index])
        frame_index = int(round((len(run.frames) - 1) * clamped_ratio))
        draw_cinematic_frame(
            ax,
            run,
            spec,
            frame_index,
            extent_override=shared_extent,
            show_timeline=True,
        )
        ax.text(
            0.05,
            0.93,
            panel.label,
            transform=ax.transAxes,
            fontsize=12,
            fontweight="bold",
            color=TEXT_COLOR,
            family="DejaVu Sans",
            ha="left",
            va="top",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def _parse_panel(value: str) -> PlatePanel:
    if "::" not in value:
        raise argparse.ArgumentTypeError("panel must use '<path>::<label>'")
    path_value, label = value.split("::", 1)
    if not path_value or not label:
        raise argparse.ArgumentTypeError("panel must include both path and label")
    return PlatePanel(path=Path(path_value), label=label)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a cinematic comparison plate from multiple run NDJSON files"
    )
    parser.add_argument("--panel", action="append", type=_parse_panel, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--frame-ratio", type=float, default=1.0)
    parser.add_argument("--supertitle")
    parser.add_argument("--subtitle")
    parser.add_argument("--yaw", type=float, default=-36.0)
    parser.add_argument("--pitch", type=float, default=20.0)
    parser.add_argument("--distance", type=float, default=18.0)
    parser.add_argument("--focal-length", type=float, default=16.0)
    parser.add_argument("--width", type=int, default=560)
    parser.add_argument("--height", type=int, default=360)
    args = parser.parse_args()

    spec = RenderSpec(
        fps=24,
        stride=1,
        trail=24,
        width=args.width,
        height=args.height,
        camera=CameraSpec(
            yaw_deg=args.yaw,
            pitch_deg=args.pitch,
            distance=args.distance,
            focal_length=args.focal_length,
        ),
        title=None,
        subtitle=None,
        frame_index=None,
        show_footer=False,
    )
    render_cinematic_plate(
        panels=args.panel,
        out_path=Path(args.out),
        spec=spec,
        frame_ratio=args.frame_ratio,
        supertitle=args.supertitle,
        subtitle=args.subtitle,
    )
    print(f"Rendered cinematic plate to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
