from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_steps(ndjson_path: Path) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    with ndjson_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            if record.get("record_type") == "step":
                steps.append(record)
    if not steps:
        raise ValueError(f"No step records found in {ndjson_path}")
    return steps


def _positions_from_record(record: dict[str, object]) -> np.ndarray:
    values = record.get("body_positions")
    if not isinstance(values, list):
        raise ValueError("step record missing body_positions")
    arr = np.array(values, dtype=float)
    if arr.size % 3 != 0:
        raise ValueError("body_positions length must be divisible by 3")
    return arr.reshape((-1, 3))


def _resolve_writer(fmt: str, fps: int) -> animation.AbstractMovieWriter:
    if fmt == "mp4":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required for mp4 output but was not found")
        return animation.FFMpegWriter(fps=fps, bitrate=2200)
    if fmt == "gif":
        return animation.PillowWriter(fps=fps)
    raise ValueError(f"Unsupported format: {fmt}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a 3D animation from a run NDJSON")
    parser.add_argument("--ndjson", required=True, help="Path to run NDJSON")
    parser.add_argument("--out", required=True, help="Output file path (.mp4 or .gif)")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--trail", type=int, default=24, help="Number of prior frames for trails")
    args = parser.parse_args()

    ndjson_path = Path(args.ndjson)
    out_path = Path(args.out)
    if args.stride <= 0:
        raise ValueError("--stride must be positive")
    if args.fps <= 0:
        raise ValueError("--fps must be positive")

    steps = _load_steps(ndjson_path)
    sampled_steps = steps[:: args.stride]
    if len(sampled_steps) < 2:
        raise ValueError("Not enough sampled frames; reduce stride")

    frames = [_positions_from_record(step) for step in sampled_steps]
    body_count = frames[0].shape[0]

    stacked = np.stack(frames, axis=0)
    x_min, y_min, z_min = np.min(stacked, axis=(0, 1))
    x_max, y_max, z_max = np.max(stacked, axis=(0, 1))

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_title("Jolt Material Memory Run")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")

    pad = 0.25
    ax.set_xlim(x_min - pad, x_max + pad)
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_zlim(z_min - pad, z_max + pad)

    cmap = plt.get_cmap("viridis", body_count)
    scat = ax.scatter([], [], [], s=50)

    trails = [
        ax.plot([], [], [], color=cmap(i), alpha=0.45, linewidth=1.2)[0] for i in range(body_count)
    ]

    metadata = ax.text2D(0.02, 0.94, "", transform=ax.transAxes)

    def _update(frame_idx: int):
        points = frames[frame_idx]
        scat._offsets3d = (points[:, 0], points[:, 1], points[:, 2])
        scat.set_array(np.linspace(0.0, 1.0, body_count))
        scat.set_cmap("viridis")

        start = max(0, frame_idx - args.trail)
        for i in range(body_count):
            segment = stacked[start : frame_idx + 1, i, :]
            trails[i].set_data(segment[:, 0], segment[:, 1])
            trails[i].set_3d_properties(segment[:, 2])

        step_value = sampled_steps[frame_idx]["step"]
        goal = sampled_steps[frame_idx]["goal_x"]
        memory_mode = sampled_steps[frame_idx]["memory_mode"]
        backend = sampled_steps[frame_idx]["backend"]
        metadata.set_text(
            f"step={step_value}  goal_x={goal:.3f}  memory={memory_mode}  backend={backend}"
        )
        return [scat, metadata, *trails]

    anim = animation.FuncAnimation(
        fig,
        _update,
        frames=len(frames),
        interval=1000 / args.fps,
        blit=False,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = out_path.suffix.lstrip(".").lower()
    writer = _resolve_writer(fmt, args.fps)
    anim.save(out_path, writer=writer)
    plt.close(fig)

    print(f"Rendered {len(frames)} frames to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
