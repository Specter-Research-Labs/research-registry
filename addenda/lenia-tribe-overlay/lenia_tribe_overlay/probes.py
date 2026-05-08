from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from .tribe_client import StimulusTensor

PROBE_HEIGHT = 224
PROBE_WIDTH = 224
PROBE_FPS = 8
PROBE_SECONDS = 4
PROBE_FRAMES = PROBE_FPS * PROBE_SECONDS


def _blank(rng: np.random.Generator, value: int) -> np.ndarray:
    frame = np.full((PROBE_HEIGHT, PROBE_WIDTH, 3), value, dtype=np.uint8)
    return np.repeat(frame[None, ...], PROBE_FRAMES, axis=0)


def _white_noise(rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, 256, size=(PROBE_FRAMES, PROBE_HEIGHT, PROBE_WIDTH, 3), dtype=np.uint8)


def _drifting_grating(rng: np.random.Generator) -> np.ndarray:
    x = np.arange(PROBE_WIDTH)
    frames = []
    for t in range(PROBE_FRAMES):
        phase = 2 * np.pi * (x / 32.0 + t / 8.0)
        row = ((np.sin(phase) + 1.0) * 127.5).astype(np.uint8)
        frame = np.broadcast_to(row[None, :, None], (PROBE_HEIGHT, PROBE_WIDTH, 3)).copy()
        frames.append(frame)
    return np.stack(frames, axis=0)


def _bouncing_disk(rng: np.random.Generator) -> np.ndarray:
    yy, xx = np.mgrid[0:PROBE_HEIGHT, 0:PROBE_WIDTH]
    radius = 18
    frames = []
    cy = PROBE_HEIGHT // 2
    cx = radius + 4
    vx = 6
    for _ in range(PROBE_FRAMES):
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius * radius
        frame = np.zeros((PROBE_HEIGHT, PROBE_WIDTH, 3), dtype=np.uint8)
        frame[mask] = 255
        frames.append(frame)
        cx += vx
        if cx + radius >= PROBE_WIDTH or cx - radius <= 0:
            vx = -vx
            cx += 2 * vx
    return np.stack(frames, axis=0)


def _scrambled_disk(rng: np.random.Generator) -> np.ndarray:
    base = _bouncing_disk(rng)
    perm = rng.permutation(PROBE_FRAMES)
    return base[perm]


def _point_light_walker(rng: np.random.Generator) -> np.ndarray:
    """Schematic biological motion: a small set of dots moving with phase relations
    consistent with limb articulation around a translating body. This is a stand-in
    for a real point-light walker stimulus and is replaced before publication."""
    n_dots = 13
    frames = np.zeros((PROBE_FRAMES, PROBE_HEIGHT, PROBE_WIDTH, 3), dtype=np.uint8)
    body_y = np.linspace(80, 80, PROBE_FRAMES)
    body_x = np.linspace(40, PROBE_WIDTH - 40, PROBE_FRAMES)
    offsets = rng.uniform(-1.0, 1.0, size=(n_dots, 2)) * np.array([30.0, 12.0])
    phases = rng.uniform(0, 2 * np.pi, size=n_dots)
    for t in range(PROBE_FRAMES):
        for i in range(n_dots):
            limb = np.sin(2 * np.pi * t / PROBE_FPS + phases[i])
            y = int(body_y[t] + offsets[i, 0] + 8 * limb)
            x = int(body_x[t] + offsets[i, 1] + 4 * limb)
            if 2 <= y < PROBE_HEIGHT - 2 and 2 <= x < PROBE_WIDTH - 2:
                frames[t, y - 2:y + 2, x - 2:x + 2] = 255
    return frames


def probe_set(seed: int = 0) -> Iterator[StimulusTensor]:
    rng = np.random.default_rng(seed)
    duration = float(PROBE_SECONDS)
    yield StimulusTensor("static_black", "static", _blank(rng, 0), duration)
    yield StimulusTensor("static_gray", "static", _blank(rng, 128), duration)
    yield StimulusTensor("white_noise", "noise", _white_noise(rng), duration)
    yield StimulusTensor("drifting_grating", "grating", _drifting_grating(rng), duration)
    yield StimulusTensor("bouncing_disk", "rigid_motion", _bouncing_disk(rng), duration)
    yield StimulusTensor("scrambled_disk", "scrambled", _scrambled_disk(rng), duration)
    yield StimulusTensor("point_light_walker", "biomotion_positive", _point_light_walker(rng), duration)
