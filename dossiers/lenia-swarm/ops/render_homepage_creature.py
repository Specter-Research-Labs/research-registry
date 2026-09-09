"""Render the homepage's Quadrium-derived Lenia study from a committed seed.

Run from the repository root:
  python dossiers/lenia-swarm/ops/render_homepage_creature.py
Requires NumPy, SciPy, Pillow and ffmpeg. This illustrative higher-grid run is
separate from the measured report cohorts; its spatial refinement changes the
simulation discretization. It is not an upscaled recording of a report result.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import fft
from scipy.ndimage import zoom

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
            "960x960",
            "-framerate",
            "30",
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output / "quadrium-study.mp4"),
        ],
        stdin=subprocess.PIPE,
    )
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


if __name__ == "__main__":
    render()
