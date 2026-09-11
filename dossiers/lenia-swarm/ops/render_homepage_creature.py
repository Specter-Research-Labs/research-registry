"""Render the homepage's Quadrium study or package a selected native replay.

Run from the repository root:
  python dossiers/lenia-swarm/ops/render_homepage_creature.py
Requires NumPy, SciPy, Pillow and ffmpeg. This illustrative higher-grid run is
separate from the measured report cohorts; its spatial refinement changes the
simulation discretization. It is not an upscaled recording of a report result.

For native replays, see ops/docs/report-layout.md. --media-root packages the
CLI's full-world density frames without rerunning or refining the simulation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import fft
from scipy.ndimage import label, sum_labels, zoom

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(
    "dossiers/lenia-swarm/Sources/LeniaStudio/Resources/Organisms/track1_quadrium_gyrans.json"
)
OUTPUT = Path("site/home-prototype/assets")
PALETTE = np.array(
    [
        [244, 241, 232],
        [226, 235, 222],
        [193, 222, 202],
        [135, 195, 175],
        [77, 153, 137],
        [46, 122, 111],
        [31, 98, 91],
        [27, 77, 76],
    ]
)
KNOTS = [0, 0.06, 0.2, 0.35, 0.5, 0.7, 0.85, 1]


def video_writer(output: Path, size: int, crf: int, fps: int = 30) -> subprocess.Popen:
    return subprocess.Popen(
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
            f"{size}x{size}",
            "-framerate",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        stdin=subprocess.PIPE,
    )


def render() -> None:
    source_bytes = (ROOT / SOURCE).read_bytes()
    config = json.loads(source_bytes)
    assert config["implementation"] == {
        "growth_profile": "quad4",
        "kernel_profile": "qd24_quad4_v1",
        "mode": "qd24_additive_v1",
    }
    assert config["channels"] == 1
    params = config["params"]
    patch = config["init"]["state_patch"]
    n = config["grid"]["sx"]
    state = np.zeros((n, n), dtype=np.float64)
    h, w = patch["height"], patch["width"]
    seed = np.frombuffer(base64.b64decode(patch["data"]), "<f4").reshape(h, w)
    state[n // 2 - h // 2 : n // 2 - h // 2 + h, n // 2 - w // 2 : n // 2 - w // 2 + w] = seed
    state = zoom(state, 4, order=1)
    n *= 4
    y, x = np.mgrid[-n // 2 : n // 2, -n // 2 : n // 2]
    beta = np.asarray(params["b"][0])
    radius = np.hypot(x, y) / (params["R"] * 4 * params["r"][0]) * len(beta)
    fractional = radius % 1
    kernel = np.where(
        radius < len(beta),
        beta[np.minimum(radius.astype(int), len(beta) - 1)]
        * np.maximum(0, 4 * fractional * (1 - fractional)) ** 4,
        0,
    )
    kernel_fft = fft.fft2(fft.ifftshift(kernel / kernel.sum()))
    output = ROOT / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    process = video_writer(output / "quadrium-study.mp4", 960, 20)
    masses = []
    outside = []
    for step in range(900):
        if step >= 300 and step % 2 == 0:
            # Fixed framing preserves translation and deformation; no camera tracking.
            crop = state[n // 2 - 170 : n // 2 + 150, n // 2 - 140 : n // 2 + 180]
            field = np.clip(zoom(crop, 3, order=1), 0, 1)
            rgb = np.stack([np.interp(field, KNOTS, PALETTE[:, c]) for c in range(3)], -1).astype(
                "uint8"
            )
            process.stdin.write(rgb.tobytes())
            masses.append(float(state.sum()))
            outside.append(float((state.sum() - crop.sum()) / state.sum()))
            if step == 300:
                Image.fromarray(rgb).save(output / "quadrium-poster.webp", quality=96)
        potential = fft.ifft2(fft.fft2(state) * kernel_fft).real
        normalized = (potential - params["m"][0]) / (3 * params["s"][0])
        growth = (2 * np.maximum(0, 1 - normalized**2) ** 4 - 1) * params["h"][0]
        state = np.clip(state + config["flow"]["dt"] * growth, 0, 1)
    process.stdin.close()
    if process.wait():
        raise RuntimeError("ffmpeg encoding failed")
    if max(outside) > 0.001:
        raise ValueError("Fixed frame clips more than 0.1% of the simulated density")
    metadata = {
        "title": "Quadrium-derived Lenia study",
        "purpose": "Illustrative homepage simulation; not a measured report cohort or new research result.",
        "source_config": str(SOURCE),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "seed_provenance": config["provenance"],
        "renderer": "dossiers/lenia-swarm/ops/render_homepage_creature.py",
        "equations": "Single-channel additive Lenia; quad4 kernel and growth matching FlowLenia.swift formulas. NumPy/SciPy float64 FFT implementation; not numerical parity certification of the native runtime.",
        "grid": [n, n],
        "spatial_refinement": 4,
        "refinement": "Bilinear seed interpolation on 768x768 grid, interaction radius 36 to 144, original time step 0.1. Spatial refinement changes the discretization and creates a new simulation.",
        "recorded_steps": {"first": 300, "last": 898, "stride": 2},
        "video": {"width": 960, "height": 960, "frames": 300, "fps": 30},
        "render": "Fixed 320x320 crop centered at row 374, column 404; bilinear display interpolation. Color maps scalar density, with no lighting, geometry, motion interpolation, or generated image content.",
        "density_palette": {"values": KNOTS, "rgb": PALETTE.tolist()},
        "mass_range": [min(masses), max(masses)],
        "max_density_fraction_outside_crop": max(outside),
        "loop": "Playback restarts the recorded segment; endpoint is not claimed to be periodic.",
    }
    (output / "quadrium-study.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        json.dumps(
            {
                "frames": 300,
                "mass_range": metadata["mass_range"],
                "max_density_fraction_outside_crop": max(outside),
            }
        )
    )


def package_replay(media_root: Path, campaign: Path, output: Path, title: str, steps: int) -> None:
    records = json.loads((media_root / "index.json").read_text())
    if len(records) != 1:
        raise ValueError("Select one specimen per media export")
    record = records[0]
    files = sorted(Path(record["framesPath"]).glob("frame_*.png"))
    fields = np.stack([np.asarray(Image.open(path).convert("L")) for path in files])
    frame_count = len(fields)
    if frame_count != record["frames"] or record["fps"] <= 0 or steps < frame_count:
        raise ValueError(
            "Supply the capture step count and a complete frame sequence with its original playback rate"
        )
    config_bytes = (campaign / "config.json").read_bytes()
    config = json.loads(config_bytes)
    search = json.loads((campaign / "search.json").read_text())
    manifest = json.loads((campaign / "replay-manifest.json").read_text())
    warmup = min(max(search["warmup_steps"], 0), steps - frame_count)
    stride = max(1, (steps - warmup) // frame_count)
    first_step = (warmup // stride + 1) * stride

    # Use the entire trajectory to choose one fixed square: camera tracking would hide movement.
    rows, cols = np.where((fields > 2).any(axis=0))
    side = int(np.ceil(max(np.ptp(rows), np.ptp(cols)) * 1.4))
    top = int((rows.min() + rows.max() - side) // 2)
    left = int((cols.min() + cols.max() - side) // 2)
    masses = fields.sum(axis=(1, 2))
    coherence = []
    for field in fields:
        components, count = label(field > 2, np.ones((3, 3)))
        parts = sum_labels(field, components, range(1, count + 1))
        coherence.append(float(max(parts, default=0) / max(field.sum(), 1)))
    if min(coherence) < 0.95:
        raise ValueError(
            f"Replay loses coherence: minimum connected mass fraction {min(coherence):.3f}"
        )

    y, x = np.indices(fields.shape[1:])
    centers = np.array(
        [
            [(field * x).sum() / mass, (field * y).sum() / mass]
            for field, mass in zip(fields, masses, strict=True)
        ]
    )
    travel = float(np.linalg.norm(centers[-1] - centers[0]))
    if travel < side * 0.12:
        raise ValueError(f"Replay lacks visible travel: {travel:.2f} cells in a {side}-cell frame")

    output.parent.mkdir(parents=True, exist_ok=True)
    video = output.with_suffix(".mp4")
    encoder = video_writer(video, 1024, 16, record["fps"])
    outside = []
    for index, field in enumerate(fields):
        cropped = Image.fromarray(field).crop((left, top, left + side, top + side))
        outside.append(float(1 - np.asarray(cropped).sum() / max(field.sum(), 1)))
        enlarged = np.asarray(cropped.resize((1024, 1024), Image.Resampling.BILINEAR)) / 255
        rgb = np.stack([np.interp(enlarged, KNOTS, PALETTE[:, c]) for c in range(3)], -1).astype(
            "uint8"
        )
        encoder.stdin.write(rgb.tobytes())
        if index == 0:
            Image.fromarray(rgb).save(output.with_suffix(".webp"), lossless=True)
    encoder.stdin.close()
    if encoder.wait():
        raise RuntimeError("ffmpeg encoding failed")
    if max(outside) > 0.001:
        raise ValueError("Fixed frame clips more than 0.1% of the recorded density")
    receipt = {
        "title": title,
        "source_creature_id": manifest["sourceCreatureId"],
        "source_campaign": manifest["campaignId"],
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "implementation": config["implementation"],
        "simulation_grid": config["grid"],
        "recorded_steps": {
            "first": first_step,
            "last": first_step + (frame_count - 1) * stride,
            "stride": stride,
        },
        "video": {"width": 1024, "height": 1024, "frames": frame_count, "fps": record["fps"]},
        "renderer": "dossiers/lenia-swarm/ops/render_homepage_creature.py",
        "native_capture": f"LeniaCLI publish media --steps {steps} --frame-budget {frame_count} --fps {record['fps']} --render-mode body",
        "simulation_recentering": False,
        "presentation": "Native full-world 8-bit total-density frames, using the CLI's shared recording scale. Fixed square crop; bilinear display interpolation; no simulation-grid refinement or camera tracking. Channels are summed.",
        "crop": {"left": left, "top": top, "side": side},
        "density_palette": {"values": KNOTS, "rgb": PALETTE.tolist()},
        "screen": {
            "centroid_displacement_cells": travel,
            "centroid_displacement_crop_fraction": travel / side,
            "minimum_connected_mass_fraction": min(coherence),
            "max_to_min_recorded_mass": float(max(masses) / min(masses)),
            "max_density_fraction_outside_crop": max(outside),
        },
        "frames_sha256": hashlib.sha256(
            b"".join(hashlib.sha256(p.read_bytes()).digest() for p in files)
        ).hexdigest(),
        "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "loop": "Playback restarts the recording; the endpoint is not claimed to be periodic.",
    }
    output.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"title": title, "video": str(video), "screen": receipt["screen"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--output", type=Path, help="Output basename, without extension")
    parser.add_argument("--title")
    parser.add_argument(
        "--steps", type=int, default=3600, help="Step count passed to native media capture"
    )
    args = parser.parse_args()
    if any((args.media_root, args.campaign, args.output, args.title)):
        if not all((args.media_root, args.campaign, args.output, args.title)):
            parser.error("Replay packaging requires --media-root, --campaign, --output and --title")
        package_replay(args.media_root, args.campaign, args.output, args.title, args.steps)
    else:
        render()
