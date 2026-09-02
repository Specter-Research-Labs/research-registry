"""Render publication assets for a paired trajectory-inverse experiment."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

PARAMETERS = ("m", "s", "R")
COLORS = {
    "initial": "#f15b43",
    "target": "#d6ff3f",
    "coarse": "#f2b84b",
    "still": "#39b7a2",
    "trajectory": "#7f8cff",
}
DISPLAY_NAMES = {
    "initial": "initial",
    "target": "native",
    "coarse": "broad pass",
    "still": "refined still",
    "trajectory": "refined trajectory",
}


def scalar(params: dict[str, Any], name: str) -> float:
    value = params[name]
    return float(value[0] if isinstance(value, list) else value)


def zoom_frame(source: Path, destination: Path, crop_size: int = 72, size: int = 720) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        cx, cy = image.width // 2, image.height // 2
        half = crop_size // 2
        crop = image.crop((cx - half, cy - half, cx + half, cy + half))
        crop.resize((size, size), Image.Resampling.LANCZOS).save(destination, optimize=True)


def render_video(frames: Path, destination: Path, crop_size: int = 72) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", "30", "-pattern_type", "glob", "-i", str(frames / "*.png"),
        "-vf", f"crop={crop_size}:{crop_size}:(iw-{crop_size})/2:(ih-{crop_size})/2,scale=640:640:flags=lanczos",
        "-c:v", "libx264", "-preset", "slow", "-crf", "25", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(destination),
    ]
    subprocess.run(command, check=True)


def parameter_svg(
    destination: Path,
    ranges: dict[str, list[float]],
    values: dict[str, dict[str, float]],
) -> None:
    width, height = 960, 450
    x0, x1 = 250, 860
    rows = {"m": 125, "s": 230, "R": 335}
    labels = {"m": "growth center m", "s": "growth width s", "R": "interaction scale R"}
    marker_y = {"initial": -28, "target": -14, "coarse": 0, "still": 14, "trajectory": 28}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Orbium rule recovery</title>',
        '<desc id="desc">Initial, native, final-frame, and trajectory parameter values for growth center, growth width, and interaction scale.</desc>',
        f'<rect width="{width}" height="{height}" fill="#111521"/>',
        '<text x="54" y="48" fill="#d6ff3f" font-family="ui-monospace,monospace" font-size="15" font-weight="800">RULE RECOVERY INSIDE THE ADDITIVE ORBIUM FAMILY</text>',
    ]
    for name, color in COLORS.items():
        x = 55 + list(COLORS).index(name) * 176
        parts += [
            f'<circle cx="{x}" cy="78" r="6" fill="{color}"/>',
            f'<text x="{x + 13}" y="82" fill="#e9e7df" font-family="ui-monospace,monospace" font-size="10">{html.escape(DISPLAY_NAMES[name])}</text>',
        ]
    for parameter in PARAMETERS:
        low, high = ranges[parameter]
        y = rows[parameter]
        parts += [
            f'<text x="54" y="{y + 5}" fill="#f4f0e7" font-family="ui-monospace,monospace" font-size="14" font-weight="700">{labels[parameter]}</text>',
            f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#596071" stroke-width="2"/>',
            f'<text x="{x0}" y="{y + 48}" fill="#9299aa" font-family="ui-monospace,monospace" font-size="10">{low:g}</text>',
            f'<text x="{x1}" y="{y + 48}" text-anchor="end" fill="#9299aa" font-family="ui-monospace,monospace" font-size="10">{high:g}</text>',
        ]
        for name, color in COLORS.items():
            value = values[name][parameter]
            x = x0 + (value - low) / (high - low) * (x1 - x0)
            yy = y + marker_y[name]
            parts += [
                f'<line x1="{x:.1f}" y1="{y - 27}" x2="{x:.1f}" y2="{y + 27}" stroke="{color}" stroke-opacity=".24"/>',
                f'<circle cx="{x:.1f}" cy="{yy}" r="7" fill="{color}" stroke="#111521"/>',
                f'<text x="{x + 11:.1f}" y="{yy + 4}" fill="{color}" font-family="ui-monospace,monospace" font-size="10">{value:.4g}</text>',
            ]
    parts.append("</svg>\n")
    destination.write_text("\n".join(parts), encoding="utf-8")


def render(
    experiment_root: Path,
    target_config: Path,
    media_root: Path,
    output: Path,
    refinement_root: Path | None = None,
    refinement_media_root: Path | None = None,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((experiment_root / "experiment.json").read_text())
    target = json.loads(target_config.read_text())["params"]
    still_es = json.loads((experiment_root / "still-es.json").read_text())
    trajectory_es = json.loads((experiment_root / "trajectory-es.json").read_text())
    if (still_es["generations"], still_es["population"]) != (
        trajectory_es["generations"], trajectory_es["population"]
    ):
        raise ValueError("paired searches must use the same generations and population")
    coarse_still = json.loads((experiment_root / "still-run/best.json").read_text())
    coarse_trajectory = json.loads((experiment_root / "trajectory-run/best.json").read_text())
    if refinement_root is not None:
        still_refinement_es = json.loads((refinement_root / "refine-es.json").read_text())
        trajectory_refinement_es = json.loads(
            (refinement_root / "trajectory-refine-es.json").read_text()
        )
        if (
            still_refinement_es["generations"],
            still_refinement_es["population"],
        ) != (
            trajectory_refinement_es["generations"],
            trajectory_refinement_es["population"],
        ):
            raise ValueError("paired refinements must use the same generations and population")
        still = json.loads((refinement_root / "refine-run/best.json").read_text())
        trajectory = json.loads((refinement_root / "trajectory-refine-run/best.json").read_text())
    else:
        still_refinement_es = None
        still = coarse_still
        trajectory = coarse_trajectory
    values = {
        "initial": {name: float(manifest["initial_parameters"][name]) for name in PARAMETERS},
        "target": {name: scalar(target, name) for name in PARAMETERS},
        "coarse": {name: scalar(coarse_still["params"], name) for name in PARAMETERS},
        "still": {name: scalar(still["params"], name) for name in PARAMETERS},
        "trajectory": {name: scalar(trajectory["params"], name) for name in PARAMETERS},
    }

    source_frames = {
        "target": media_root / "target-dense" / "frames_color",
        "still": (
            refinement_media_root / "refined-dense" / "frames_color"
            if refinement_media_root is not None
            else media_root / "still-dense" / "frames_color"
        ),
    }
    for label, frames in source_frames.items():
        render_video(frames, output / f"orbium-{label}-zoom.mp4")
        for step in (100, 300, 600, 1200):
            zoom_frame(frames / f"frame_{step:06d}.png", output / f"orbium-{label}-{step}.png")

    initial_frames = media_root / "initial-dense" / "frames_color"
    zoom_frame(initial_frames / "frame_000600.png", output / "orbium-initial-600.png")
    parameter_svg(output / "orbium-rule-recovery.svg", manifest["parameter_ranges"], values)

    coarse_rollouts = still_es["generations"] * still_es["population"]
    refinement_rollouts = (
        still_refinement_es["generations"] * still_refinement_es["population"]
        if still_refinement_es is not None
        else 0
    )
    summary = {
        "known": manifest["known"],
        "hidden": manifest["hidden"],
        "observed_step": 600,
        "held_out_steps": [100, 300, 1200],
        "generations": still_es["generations"] + (
            still_refinement_es["generations"] if still_refinement_es is not None else 0
        ),
        "population": still_es["population"],
        "candidate_rollouts": coarse_rollouts + refinement_rollouts,
        "stages": {
            "coarse": {
                "generations": still_es["generations"],
                "population": still_es["population"],
                "sigma": still_es["sigma"],
                "candidate_rollouts": coarse_rollouts,
                "fitness": coarse_still["fitness"],
                "best_generation": coarse_still["generation"],
            },
            "refinement": {
                "generations": still_refinement_es["generations"]
                if still_refinement_es is not None
                else 0,
                "population": still_refinement_es["population"]
                if still_refinement_es is not None
                else 0,
                "sigma": still_refinement_es["sigma"]
                if still_refinement_es is not None
                else None,
                "candidate_rollouts": refinement_rollouts,
                "fitness": still["fitness"],
                "best_generation": still["generation"],
            },
        },
        "values": values,
        "fitness": {"still": still["fitness"], "trajectory": trajectory["fitness"]},
        "best_generation": {"still": still["generation"], "trajectory": trajectory["generation"]},
    }
    (output / "orbium-inverse-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", required=True, type=Path)
    parser.add_argument("--target-config", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--refinement-root", type=Path)
    parser.add_argument("--refinement-media-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = render(
        args.experiment_root,
        args.target_config,
        args.media_root,
        args.output,
        refinement_root=args.refinement_root,
        refinement_media_root=args.refinement_media_root,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
