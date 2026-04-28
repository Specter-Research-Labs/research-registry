"""Frame-sequence export helpers for Lenia Studio playback."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def project_mass_to_u8(
    mass: np.ndarray,
    *,
    projection: str = "matter",
    batch_index: int = 0,
) -> np.ndarray:
    """Project a batched Lenia mass tensor to Studio's raw grayscale byte plane."""
    if mass.ndim != 4:
        raise ValueError(f"Expected mass shape (batch, sx, sy, channels), got {mass.shape}")
    if not 0 <= batch_index < mass.shape[0]:
        raise ValueError(f"batch_index={batch_index} is outside batch size {mass.shape[0]}")

    sample = mass[batch_index].astype(np.float32, copy=False)
    if projection == "matter":
        field = sample.sum(axis=2)
    elif projection.startswith("channel:"):
        channel = int(projection.split(":", 1)[1])
        if not 0 <= channel < sample.shape[2]:
            raise ValueError(f"channel={channel} is outside channel count {sample.shape[2]}")
        field = sample[:, :, channel]
    else:
        raise ValueError("projection must be 'matter' or 'channel:N'")

    clipped = np.clip(field, 0.0, 1.0)
    return (clipped * 255.0).astype(np.uint8, copy=False)


@dataclass
class FrameSequenceWriter:
    """Write Studio-playable raw r8 frames and a compact manifest."""

    output_dir: Path
    backend: str
    config_path: str
    steps: int
    frame_every: int
    projection: str = "matter"
    batch_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame_every <= 0:
            raise ValueError("frame_every must be > 0")
        self.output_dir = Path(self.output_dir)
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._frames: list[dict[str, Any]] = []
        self._width: int | None = None
        self._height: int | None = None
        self._channels: int | None = None

    def write_frame(self, step: int, mass: np.ndarray) -> None:
        if step < 0:
            raise ValueError("step must be >= 0")
        if mass.ndim != 4:
            raise ValueError(f"Expected mass shape (batch, sx, sy, channels), got {mass.shape}")
        _, sx, sy, channels = mass.shape
        if self._width is None:
            self._width = sy
            self._height = sx
            self._channels = channels
        elif (self._height, self._width, self._channels) != (sx, sy, channels):
            raise ValueError(
                "Frame shape changed from "
                f"{self._height}x{self._width}x{self._channels} to {sx}x{sy}x{channels}"
            )

        frame = project_mass_to_u8(
            mass,
            projection=self.projection,
            batch_index=self.batch_index,
        )
        relative_path = Path("frames") / f"frame_{step:06d}.r8"
        (self.output_dir / relative_path).write_bytes(frame.tobytes(order="C"))
        self._frames.append({"step": int(step), "path": relative_path.as_posix()})

    def write_manifest(self, *, final_mass_path: str = "mass_final.npy") -> Path:
        if self._width is None or self._height is None or self._channels is None:
            raise ValueError("Cannot write manifest before at least one frame")

        manifest = {
            "manifest_version": 1,
            "kind": "lenia_tt_frame_sequence",
            "backend": self.backend,
            "config_path": self.config_path,
            "steps": int(self.steps),
            "frame_every": int(self.frame_every),
            "width": int(self._width),
            "height": int(self._height),
            "channels": int(self._channels),
            "projection": self.projection,
            "batch_index": int(self.batch_index),
            "dtype": "uint8",
            "storage": "raw_r8",
            "final_mass_path": final_mass_path,
            "metadata": self.metadata,
            "frames": self._frames,
        }
        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest_path
