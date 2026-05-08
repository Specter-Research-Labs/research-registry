from __future__ import annotations

from pathlib import Path

import imageio.v3 as iio
import numpy as np
import pytest

from lenia_tribe_overlay.corpus import discover_videos, load_video_as_stimulus
from lenia_tribe_overlay.probes import PROBE_FPS, PROBE_FRAMES, PROBE_HEIGHT, PROBE_WIDTH


def _write_dummy_video(path: Path, n_frames: int, h: int, w: int) -> None:
    rng = np.random.default_rng(0)
    frames = rng.integers(0, 256, size=(n_frames, h, w, 3), dtype=np.uint8)
    iio.imwrite(path, frames, fps=PROBE_FPS, codec="libx264", macro_block_size=1)


def test_load_video_resamples_to_probe_window(tmp_path: Path) -> None:
    src = tmp_path / "long.mp4"
    _write_dummy_video(src, n_frames=200, h=512, w=512)
    stim = load_video_as_stimulus(src, name="long")
    assert stim.video.shape == (PROBE_FRAMES, PROBE_HEIGHT, PROBE_WIDTH, 3)
    assert stim.video.dtype == np.uint8
    assert stim.duration_seconds == pytest.approx(PROBE_FRAMES / PROBE_FPS)
    assert stim.stimulus_class == "lenia"


def test_load_video_rejects_too_short(tmp_path: Path) -> None:
    src = tmp_path / "short.mp4"
    _write_dummy_video(src, n_frames=PROBE_FRAMES - 1, h=128, w=128)
    with pytest.raises(ValueError, match="source frames"):
        load_video_as_stimulus(src)


def test_discover_videos_globs_recursively(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _write_dummy_video(tmp_path / "a" / "x.mp4", n_frames=PROBE_FRAMES, h=64, w=64)
    _write_dummy_video(tmp_path / "b" / "y.mp4", n_frames=PROBE_FRAMES, h=64, w=64)
    found = discover_videos(tmp_path)
    assert [p.name for p in found] == ["x.mp4", "y.mp4"]


def test_discover_videos_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no videos"):
        discover_videos(tmp_path)
