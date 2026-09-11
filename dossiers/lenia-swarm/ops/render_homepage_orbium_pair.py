"""Recolor the original paired Orbium experiment's scalar frame exports.

python dossiers/lenia-swarm/ops/render_homepage_orbium_pair.py \
  --native-frames PATH/target-dense/frames \
  --recovered-frames PATH/refined-dense/frames

The source frames remain unchanged. This creates a shared fixed crop and palette,
not a new simulation or a reconstruction of detail absent from the 8-bit exports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from render_homepage_creature import KNOTS, PALETTE, ROOT


def render_pair(native: Path, recovered: Path) -> None:
    output = ROOT / "site/home-prototype/assets"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "title": "Native and recovered Orbium, original experiment recordings",
        "renderer": "dossiers/lenia-swarm/ops/render_homepage_orbium_pair.py",
        "source_precision": "Original 192x192 single-channel 8-bit grayscale PNG exports; Engine.frameDataFromMassMap clamps each density to [0,1] and multiplies by 255. No per-frame normalization.",
        "simulation": "No simulation rerun or resolution change; recolors the exact original paired experiment frames.",
        "rendering": "Same fixed central 36x36 crop for both sequences, bilinear scalar display interpolation to 720x720, then the homepage density palette. No motion interpolation, camera tracking, or individual contrast adjustment.",
        "crop_xywh": [78, 78, 36, 36],
        "density_palette": {"values": KNOTS, "rgb": PALETTE.tolist()},
        "recorded_steps": {"first": 4, "last": 1200, "stride": 4},
        "video": {"width": 720, "height": 720, "fps": 30, "frames": 300, "seconds": 10},
        "fit_step": 600,
        "other_displayed_steps": [100, 300, 1200],
        "recovery": "Best refined final-frame fit from orbium-system-id-v6-refine; target recording from orbium-system-id-v5. Matches the anatomical compiler report pair.",
        "runs": {},
    }
    for label, directory in [("native", native), ("recovered", recovered)]:
        frames = sorted(directory.glob("frame_*.png"))
        steps = [int(p.stem.split("_")[-1]) for p in frames]
        if steps != list(range(4, 1201, 4)):
            raise ValueError(f"{label}: expected exactly steps 4..1200 every 4")
        process = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                "720x720",
                "-framerate",
                "30",
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output / f"orbium-{label}.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
        hashes = []
        for path, step in zip(frames, steps, strict=True):
            with Image.open(path) as image:
                if image.mode != "L" or image.size != (192, 192):
                    raise ValueError(f"{label}: wrong source frame format")
                field = np.asarray(image)
                crop = field[78:114, 78:114]
                if int(field.sum()) != int(crop.sum()):
                    raise ValueError(f"{label}: crop loses nonzero density at {step}")
                scalar = np.asarray(
                    Image.fromarray(crop.astype(np.float32) / 255).resize(
                        (720, 720), Image.Resampling.BILINEAR
                    )
                )
            rgb = np.stack([np.interp(scalar, KNOTS, PALETTE[:, c]) for c in range(3)], -1).astype(
                "uint8"
            )
            process.stdin.write(rgb.tobytes())
            if step in (100, 300, 600, 1200):
                Image.fromarray(rgb).save(output / f"orbium-{label}-{step}.webp", quality=96)
            hashes.append(
                {"frame": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
        process.stdin.close()
        if process.wait():
            raise RuntimeError(f"{label}: ffmpeg failed")
        manifest["runs"][label] = {
            "source_run": "orbium-system-id-v5/media/target-dense"
            if label == "native"
            else "orbium-system-id-v6-refine/media/refined-dense",
            "source_frames": hashes,
            "all_nonzero_source_pixels_preserved": True,
        }
    summary = (
        ROOT / "site/dossiers/lenia-swarm/anatomical-compiler/assets/orbium-inverse-summary.json"
    )
    manifest["experiment_summary"] = {
        "path": "site/dossiers/lenia-swarm/anatomical-compiler/assets/orbium-inverse-summary.json",
        "sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
    }
    (output / "orbium-pair.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Rendered two aligned 300-frame videos and eight original-step stills.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-frames", type=Path, required=True)
    parser.add_argument("--recovered-frames", type=Path, required=True)
    args = parser.parse_args()
    render_pair(args.native_frames, args.recovered_frames)
