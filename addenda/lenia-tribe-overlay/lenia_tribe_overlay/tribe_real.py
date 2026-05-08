from __future__ import annotations

import hashlib
import os
from pathlib import Path

import imageio.v3 as iio
import numpy as np

from . import paths
from .tribe_client import StimulusTensor, TribePrediction

CHECKPOINT_DIR = "facebook/tribev2"
SUPPORTED_DEVICES = {"auto", "cpu", "cuda", "accelerate"}


def _cache_folder() -> Path:
    return paths.ensure(paths.runtime_root() / "tribe-cache")


def _encode_mp4(stimulus: StimulusTensor, fps: int) -> Path:
    digest = hashlib.sha256(stimulus.video.tobytes()).hexdigest()[:16]
    out_dir = paths.ensure(paths.runtime_root() / "probes")
    out = out_dir / f"{stimulus.name}.{digest}.mp4"
    if out.exists():
        return out
    iio.imwrite(out, stimulus.video, fps=fps, codec="libx264", macro_block_size=1)
    return out


class RealTribeClient:
    """Adapter from StimulusTensor -> TRIBE v2 forward pass.

    invariant: time-aggregation is mean-over-timesteps. The gate cares about
    per-stimulus average activation, not per-timestep dynamics. If a future
    analysis stage needs the temporal axis, expose it as a separate method
    rather than threading it through this client.
    """

    def __init__(
        self,
        device: str = "auto",
        probe_fps: int = 8,
        cache_folder: Path | None = None,
    ) -> None:
        from tribev2 import TribeModel  # imported lazily to keep import-time cost off the gate

        if device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"unsupported device {device!r}; supported: {sorted(SUPPORTED_DEVICES)}."
            )

        cache = cache_folder if cache_folder is not None else _cache_folder()
        os.environ.setdefault("HF_HOME", str(cache))
        self._model = TribeModel.from_pretrained(
            CHECKPOINT_DIR,
            cache_folder=str(cache),
            device=device,
        )
        self._probe_fps = probe_fps
        self._device = device
        self._checkpoint_revision = CHECKPOINT_DIR

    @property
    def checkpoint_revision(self) -> str:
        return self._checkpoint_revision

    @property
    def n_voxels(self) -> int:
        return 20484

    def predict(self, stimulus: StimulusTensor) -> TribePrediction:
        video_path = _encode_mp4(stimulus, fps=self._probe_fps)
        events = self._model.get_events_dataframe(video_path=str(video_path))
        preds, _segments = self._model.predict(events=events, verbose=False)
        if preds.ndim != 2:
            raise ValueError(
                f"unexpected TRIBE output shape {preds.shape}; expected (n_timesteps, n_vertices)"
            )
        if preds.shape[0] == 0:
            raise ValueError(
                f"TRIBE produced zero timesteps for stimulus {stimulus.name!r} "
                f"(duration {stimulus.duration_seconds}s); probe is too short for the model TR"
            )
        voxels = preds.mean(axis=0).astype(np.float32)
        return TribePrediction(stimulus_name=stimulus.name, voxels=voxels)
