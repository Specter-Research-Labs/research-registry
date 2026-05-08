from __future__ import annotations

from pathlib import Path

import imageio.v3 as iio
import numpy as np
from PIL import Image

from .probes import PROBE_FPS, PROBE_FRAMES, PROBE_HEIGHT, PROBE_WIDTH
from .tribe_client import StimulusTensor


def _resize(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        frame = np.stack([frame, frame, frame], axis=-1)
    elif frame.shape[-1] == 4:
        frame = frame[..., :3]
    img = Image.fromarray(frame.astype(np.uint8))
    img = img.resize((PROBE_WIDTH, PROBE_HEIGHT), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


def load_video_as_stimulus(
    path: Path,
    *,
    name: str | None = None,
    stimulus_class: str = "lenia",
) -> StimulusTensor:
    """Load an MP4 and resample to PROBE_FRAMES evenly spaced frames at PROBE_HEIGHT x PROBE_WIDTH.

    invariant: we treat Lenia time as arbitrary — the brain doesn't know what one Lenia
    timestep means in seconds, so the entire source clip is compressed to PROBE_SECONDS.
    Different source clip lengths produce comparable TRIBE inputs (32 frames @ 8 fps).
    """
    frames_iter = list(iio.imiter(path))
    if not frames_iter:
        raise ValueError(f"video {path} has zero frames")
    n_source = len(frames_iter)
    if n_source < PROBE_FRAMES:
        raise ValueError(
            f"video {path} has {n_source} source frames; need at least {PROBE_FRAMES} "
            "to fill the TRIBE probe window without duplication"
        )
    indices = np.linspace(0, n_source - 1, PROBE_FRAMES).round().astype(int)
    sampled = np.stack([_resize(np.asarray(frames_iter[i])) for i in indices], axis=0)
    return StimulusTensor(
        name=name if name is not None else path.stem,
        stimulus_class=stimulus_class,
        video=sampled,
        duration_seconds=float(PROBE_FRAMES) / PROBE_FPS,
    )


def discover_videos(root: Path, glob_pattern: str = "*.mp4") -> list[Path]:
    paths = sorted(root.rglob(glob_pattern))
    if not paths:
        raise FileNotFoundError(
            f"no videos matching {glob_pattern!r} under {root}; aborting before TRIBE setup"
        )
    return paths
