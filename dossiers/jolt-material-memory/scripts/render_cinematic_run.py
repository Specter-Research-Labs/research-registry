from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.artist import Artist

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKGROUND_TOP = np.array([246, 240, 230], dtype=float) / 255.0
BACKGROUND_BOTTOM = np.array([223, 235, 230], dtype=float) / 255.0
GROUND_COLOR = "#e3d7c5"
SHADOW_COLOR = "#6d6357"
LINK_GLOW = "#f3b36b"
LINK_COLOR = "#2f3a3f"
TRAIL_COLOR = "#c86a3b"
GOAL_COLOR = "#b84b3e"
TEXT_COLOR = "#243036"
BODY_PALETTE = [
    "#f2c97d",
    "#efb16c",
    "#e69063",
    "#d86e5a",
    "#c65855",
    "#a94d57",
    "#7f6272",
    "#5f7e8c",
    "#4f90a0",
    "#48a5a6",
    "#6fb8a5",
    "#98c59f",
]


@dataclass(frozen=True)
class CameraSpec:
    yaw_deg: float
    pitch_deg: float
    distance: float
    focal_length: float


@dataclass(frozen=True)
class RenderSpec:
    fps: int
    stride: int
    trail: int
    width: int
    height: int
    camera: CameraSpec
    title: str | None
    subtitle: str | None
    frame_index: int | None
    show_footer: bool = True


@dataclass(frozen=True)
class RenderableRun:
    meta: dict[str, object]
    sampled_steps: list[dict[str, object]]
    frames: list[np.ndarray]
    centers: np.ndarray
    goals: np.ndarray
    drive_signals: np.ndarray
    extent: tuple[float, float, float, float]
    body_colors: np.ndarray


def _load_records(ndjson_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    meta: dict[str, object] | None = None
    steps: list[dict[str, object]] = []
    with ndjson_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            if record.get("record_type") == "meta" and meta is None:
                meta = record
            elif record.get("record_type") == "step":
                steps.append(record)
    if meta is None:
        raise ValueError(f"No meta record found in {ndjson_path}")
    if not steps:
        raise ValueError(f"No step records found in {ndjson_path}")
    return meta, steps


def _positions_from_record(record: dict[str, object]) -> np.ndarray:
    values = record.get("body_positions")
    if not isinstance(values, list):
        raise ValueError("step record missing body_positions")
    arr = np.asarray(values, dtype=float)
    if arr.size % 3 != 0:
        raise ValueError("body_positions length must be divisible by 3")
    return arr.reshape((-1, 3))


def _float_field(record: dict[str, object], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"step record missing numeric {key}")
    return float(value)


def _int_like(value: object, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(float(value))
    return fallback


def _build_rotation(camera: CameraSpec) -> np.ndarray:
    yaw = math.radians(camera.yaw_deg)
    pitch = math.radians(camera.pitch_deg)
    rot_y = np.array(
        [
            [math.cos(yaw), 0.0, math.sin(yaw)],
            [0.0, 1.0, 0.0],
            [-math.sin(yaw), 0.0, math.cos(yaw)],
        ]
    )
    rot_x = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(pitch), -math.sin(pitch)],
            [0.0, math.sin(pitch), math.cos(pitch)],
        ]
    )
    return rot_x @ rot_y


def _project(
    points: np.ndarray,
    rotation: np.ndarray,
    camera: CameraSpec,
) -> tuple[np.ndarray, np.ndarray]:
    rotated = points @ rotation.T
    depth = rotated[:, 2] + camera.distance
    if np.any(depth <= 0.1):
        raise ValueError("camera distance is too small for the projected scene")
    scale = camera.focal_length / depth
    projected = np.column_stack([rotated[:, 0] * scale, rotated[:, 1] * scale])
    return projected, depth


def _rounded_segments(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    starts = points[:-1]
    ends = points[1:]
    return starts, ends


def _background_image() -> np.ndarray:
    size = 700
    y = np.linspace(0.0, 1.0, size)[:, None]
    x = np.linspace(0.0, 1.0, size)[None, :]
    vertical = BACKGROUND_TOP * (1.0 - y) + BACKGROUND_BOTTOM * y
    glow_center = np.array([0.14, 0.22])
    radius = np.sqrt((x - glow_center[0]) ** 2 + (y - glow_center[1]) ** 2)
    glow = np.clip(1.0 - radius / 0.9, 0.0, 1.0)[..., None]
    warm = np.array([252, 224, 177], dtype=float) / 255.0
    image = vertical + 0.16 * glow * (warm - vertical)
    return np.clip(image, 0.0, 1.0)


def _body_colors(body_count: int) -> np.ndarray:
    cmap = mcolors.LinearSegmentedColormap.from_list("substrate", BODY_PALETTE)
    return cmap(np.linspace(0.0, 1.0, body_count))


def _compute_extent(
    frames: list[np.ndarray],
    goals: np.ndarray,
    camera: CameraSpec,
) -> tuple[float, float, float, float]:
    rotation = _build_rotation(camera)
    all_projected: list[np.ndarray] = []
    for positions in frames:
        projected, _ = _project(positions, rotation, camera)
        all_projected.append(projected)

        shadows = positions.copy()
        shadows[:, 1] = np.min(positions[:, 1]) - 0.22
        projected_shadows, _ = _project(shadows, rotation, camera)
        all_projected.append(projected_shadows)

    goal_points = np.column_stack([goals, np.zeros_like(goals), np.zeros_like(goals)])
    goal_projected, _ = _project(goal_points, rotation, camera)
    all_projected.append(goal_projected)

    stacked = np.vstack(all_projected)
    x_min, y_min = np.min(stacked, axis=0)
    x_max, y_max = np.max(stacked, axis=0)
    x_pad = 0.18 * max(1.0, x_max - x_min)
    y_pad = 0.22 * max(1.0, y_max - y_min)
    return x_min - x_pad, x_max + x_pad, y_min - y_pad, y_max + y_pad


def _timeline_windows(
    meta: dict[str, object],
    total_steps: int,
) -> tuple[list[tuple[float, float, str]], list[tuple[float, str]]]:
    params_value = meta.get("scenario_params")
    if not isinstance(params_value, dict) or total_steps <= 0:
        return [], []
    params: dict[str, object] = {str(key): value for key, value in params_value.items()}

    windows: list[tuple[float, float, str]] = []
    markers: list[tuple[float, str]] = []
    scenario = str(meta.get("scenario", ""))

    def normalized(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        step = float(value)
        if step < 0:
            return None
        return step / float(total_steps)

    def add_window(start_key: str, end_key: str, label: str) -> None:
        start = normalized(params.get(start_key))
        end = normalized(params.get(end_key))
        if start is None or end is None or end <= start:
            return
        windows.append((start, end, label))

    add_window("pulse_start_step", "pulse_end_step", "pulse")
    add_window("second_pulse_start_step", "second_pulse_end_step", "pulse")
    damage = normalized(params.get("damage_step"))
    if scenario == "damage" and damage is not None:
        markers.append((damage, "damage"))
    return windows, markers


def load_renderable_run(ndjson_path: Path, spec: RenderSpec) -> RenderableRun:
    meta, steps = _load_records(ndjson_path)
    if spec.stride <= 0:
        raise ValueError("--stride must be positive")
    if spec.fps <= 0:
        raise ValueError("--fps must be positive")

    sampled_steps = steps[:: spec.stride]
    frames = [_positions_from_record(step) for step in sampled_steps]
    goals = np.asarray([_float_field(step, "goal_x") for step in sampled_steps], dtype=float)
    drive_signals = np.asarray(
        [_float_field(step, "drive_signal") for step in sampled_steps],
        dtype=float,
    )
    centers = np.asarray([positions.mean(axis=0) for positions in frames], dtype=float)
    extent = _compute_extent(frames, goals, spec.camera)
    body_colors = _body_colors(frames[0].shape[0])
    return RenderableRun(
        meta=meta,
        sampled_steps=sampled_steps,
        frames=frames,
        centers=centers,
        goals=goals,
        drive_signals=drive_signals,
        extent=extent,
        body_colors=body_colors,
    )


def union_extent(runs: list[RenderableRun]) -> tuple[float, float, float, float]:
    if not runs:
        raise ValueError("at least one renderable run is required")
    extents = np.asarray([run.extent for run in runs], dtype=float)
    return (
        float(np.min(extents[:, 0])),
        float(np.max(extents[:, 1])),
        float(np.min(extents[:, 2])),
        float(np.max(extents[:, 3])),
    )


def _draw_timeline(
    ax: plt.Axes,
    run: RenderableRun,
    frame_idx: int,
    *,
    title: str | None,
) -> None:
    inset = ax.inset_axes((0.05, 0.05, 0.34, 0.12))
    inset.set_facecolor((1.0, 1.0, 1.0, 0.35))
    for spine in inset.spines.values():
        spine.set_visible(False)
    inset.set_xticks([])
    inset.set_yticks([])

    if len(run.drive_signals) == 0:
        return

    xs = np.linspace(0.0, 1.0, len(run.drive_signals))
    max_signal = max(1.0, float(np.max(np.abs(run.drive_signals))))
    ys = run.drive_signals / max_signal
    inset.axhline(0.0, color=TEXT_COLOR, linewidth=0.8, alpha=0.25)

    total_steps = _int_like(run.meta.get("steps"), fallback=len(run.sampled_steps))
    windows, markers = _timeline_windows(run.meta, total_steps)
    for start, end, _label in windows:
        inset.axvspan(start, end, color=GOAL_COLOR, alpha=0.08)
    for x_value, label in markers:
        inset.axvline(x_value, color=GOAL_COLOR, linewidth=1.1, alpha=0.5)
        if label == "damage":
            inset.text(
                x_value,
                1.05,
                "damage",
                color=GOAL_COLOR,
                fontsize=6,
                ha="center",
                va="bottom",
                transform=inset.transData,
            )

    inset.plot(xs, ys, color=LINK_COLOR, linewidth=1.6, alpha=0.9)
    current_x = xs[frame_idx]
    current_y = ys[frame_idx]
    inset.scatter([current_x], [current_y], s=16, color=GOAL_COLOR, zorder=3)
    inset.set_xlim(0.0, 1.0)
    inset.set_ylim(-1.15, 1.2)

    if title:
        inset.text(
            0.0,
            1.05,
            title,
            color=TEXT_COLOR,
            fontsize=7,
            fontweight="bold",
            ha="left",
            va="bottom",
            transform=inset.transAxes,
        )


def draw_cinematic_frame(
    ax: plt.Axes,
    run: RenderableRun,
    spec: RenderSpec,
    frame_idx: int,
    *,
    extent_override: tuple[float, float, float, float] | None = None,
    title_override: str | None = None,
    subtitle_override: str | None = None,
    show_timeline: bool = False,
) -> list[Artist]:
    rotation = _build_rotation(spec.camera)
    extent = run.extent if extent_override is None else extent_override
    bg_image = _background_image()
    frame_index = max(0, min(frame_idx, len(run.frames) - 1))
    ax.clear()
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_axis_off()
    ax.imshow(bg_image, extent=extent, aspect="auto", zorder=0)

    floor_y = extent[2] + 0.18 * (extent[3] - extent[2])
    ax.fill_between(
        [extent[0], extent[1]],
        floor_y,
        extent[2],
        color=GROUND_COLOR,
        alpha=0.38,
        zorder=0.1,
    )

    positions = run.frames[frame_index]
    shadows = positions.copy()
    shadows[:, 1] = np.min(positions[:, 1]) - 0.22
    shadow_projected, shadow_depth = _project(shadows, rotation, spec.camera)
    order_shadow = np.argsort(shadow_depth)
    shadow_sizes = (spec.camera.focal_length / shadow_depth) * 1050.0
    ax.scatter(
        shadow_projected[order_shadow, 0] + 0.03,
        shadow_projected[order_shadow, 1] - 0.015,
        s=shadow_sizes[order_shadow],
        c=SHADOW_COLOR,
        alpha=0.13,
        linewidths=0,
        zorder=0.2,
    )

    trail_start = max(0, frame_index - spec.trail)
    trail_positions = run.centers[trail_start : frame_index + 1]
    trail_projected, _ = _project(trail_positions, rotation, spec.camera)
    if len(trail_projected) > 1:
        ax.plot(
            trail_projected[:, 0],
            trail_projected[:, 1],
            color=TRAIL_COLOR,
            linewidth=8.0,
            alpha=0.10,
            solid_capstyle="round",
            zorder=0.35,
        )
        ax.plot(
            trail_projected[:, 0],
            trail_projected[:, 1],
            color=TRAIL_COLOR,
            linewidth=2.6,
            alpha=0.55,
            solid_capstyle="round",
            zorder=0.4,
        )

    body_projected, depth = _project(positions, rotation, spec.camera)
    starts, ends = _rounded_segments(body_projected)
    link_depth = 0.5 * (depth[:-1] + depth[1:])
    link_order = np.argsort(link_depth)
    link_width = 6.0 * (spec.camera.focal_length / link_depth)
    for idx in link_order:
        ax.plot(
            [starts[idx, 0], ends[idx, 0]],
            [starts[idx, 1], ends[idx, 1]],
            color=LINK_GLOW,
            linewidth=link_width[idx] * 2.1,
            alpha=0.10,
            solid_capstyle="round",
            zorder=0.5 + 0.001 * idx,
        )
        ax.plot(
            [starts[idx, 0], ends[idx, 0]],
            [starts[idx, 1], ends[idx, 1]],
            color=LINK_COLOR,
            linewidth=link_width[idx],
            alpha=0.93,
            solid_capstyle="round",
            zorder=0.55 + 0.001 * idx,
        )

    goal_height = float(np.max(positions[:, 1]) + 1.4)
    goal_points = np.array(
        [
            [run.goals[frame_index], np.min(positions[:, 1]) - 0.25, 0.0],
            [run.goals[frame_index], goal_height, 0.0],
        ]
    )
    goal_projected, _ = _project(goal_points, rotation, spec.camera)
    ax.plot(
        goal_projected[:, 0],
        goal_projected[:, 1],
        color=GOAL_COLOR,
        linewidth=9.0,
        alpha=0.15,
        solid_capstyle="round",
        zorder=0.6,
    )
    ax.plot(
        goal_projected[:, 0],
        goal_projected[:, 1],
        color=GOAL_COLOR,
        linewidth=2.2,
        alpha=0.92,
        solid_capstyle="round",
        zorder=0.7,
    )

    order = np.argsort(depth)
    sizes = (spec.camera.focal_length / depth) * 1700.0
    ax.scatter(
        body_projected[order, 0],
        body_projected[order, 1],
        s=sizes[order] * 1.9,
        c="#fff7e8",
        alpha=0.08,
        linewidths=0,
        zorder=0.9,
    )
    ax.scatter(
        body_projected[order, 0],
        body_projected[order, 1],
        s=sizes[order],
        c=run.body_colors[order],
        edgecolors="#fdfcf8",
        linewidths=1.2,
        alpha=0.98,
        zorder=1.0,
    )

    title = spec.title if title_override is None else title_override
    subtitle = spec.subtitle if subtitle_override is None else subtitle_override
    if title:
        ax.text(
            0.05,
            0.92,
            title,
            transform=ax.transAxes,
            fontsize=22,
            fontweight="bold",
            color=TEXT_COLOR,
            family="DejaVu Serif",
            ha="left",
            va="top",
        )
    if subtitle:
        ax.text(
            0.05,
            0.87,
            subtitle,
            transform=ax.transAxes,
            fontsize=11,
            color=TEXT_COLOR,
            family="DejaVu Sans",
            ha="left",
            va="top",
            alpha=0.85,
        )

    if show_timeline:
        _draw_timeline(ax, run, frame_index, title=None)

    if spec.show_footer:
        scenario = str(run.meta["scenario"]).replace("_", " ")
        memory_mode = str(run.sampled_steps[frame_index]["memory_mode"]).replace("_", " ")
        footer = f"{scenario}  |  {memory_mode}  |  step {run.sampled_steps[frame_index]['step']}"
        ax.text(
            0.05,
            0.06,
            footer,
            transform=ax.transAxes,
            fontsize=10,
            color=TEXT_COLOR,
            family="DejaVu Sans",
            ha="left",
            va="bottom",
            alpha=0.72,
        )
    return []


def render_cinematic_run(
    ndjson_path: Path,
    out_path: Path,
    spec: RenderSpec,
) -> Path:
    run = load_renderable_run(ndjson_path, spec)

    fig = plt.figure(figsize=(spec.width / 160.0, spec.height / 160.0), dpi=160)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))

    def draw(frame_idx: int) -> list[Artist]:
        return draw_cinematic_frame(ax, run, spec, frame_idx)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        frame_index = spec.frame_index if spec.frame_index is not None else len(run.frames) - 1
        frame_index = max(0, min(frame_index, len(run.frames) - 1))
        draw(frame_index)
        fig.savefig(out_path, dpi=160)
        plt.close(fig)
        return out_path

    if suffix == ".gif":
        writer: animation.AbstractMovieWriter = animation.PillowWriter(fps=spec.fps)
    elif suffix == ".mp4":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required for mp4 output but was not found")
        writer = animation.FFMpegWriter(
            fps=spec.fps,
            bitrate=2800,
            codec="libx264",
            extra_args=["-pix_fmt", "yuv420p"],
        )
    else:
        raise ValueError(f"Unsupported output format: {out_path.suffix}")

    anim = animation.FuncAnimation(
        fig,
        draw,
        frames=len(run.frames),
        interval=1000 / spec.fps,
        blit=False,
    )
    anim.save(out_path, writer=writer, dpi=160)
    plt.close(fig)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render an article-grade still or video from run NDJSON"
    )
    parser.add_argument("--ndjson", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--trail", type=int, default=28)
    parser.add_argument("--yaw", type=float, default=-36.0)
    parser.add_argument("--pitch", type=float, default=20.0)
    parser.add_argument("--distance", type=float, default=18.0)
    parser.add_argument("--focal-length", type=float, default=16.0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--title")
    parser.add_argument("--subtitle")
    parser.add_argument("--frame-index", type=int)
    parser.add_argument("--hide-footer", action="store_true")
    args = parser.parse_args()

    spec = RenderSpec(
        fps=args.fps,
        stride=args.stride,
        trail=args.trail,
        width=args.width,
        height=args.height,
        camera=CameraSpec(
            yaw_deg=args.yaw,
            pitch_deg=args.pitch,
            distance=args.distance,
            focal_length=args.focal_length,
        ),
        title=args.title,
        subtitle=args.subtitle,
        frame_index=args.frame_index,
        show_footer=not args.hide_footer,
    )
    render_cinematic_run(Path(args.ndjson), Path(args.out), spec)
    print(f"Rendered cinematic asset to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
