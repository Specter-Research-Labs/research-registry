"""Raw replay states.

`LeniaCLI publish replay --development-trace --development-state` writes, per campaign,
`development-state.f32` (little-endian Float32 [frames, height, width, channels], world frame,
unnormalized, one frame per manifest `developmentStateSteps` entry) next to
`development-trace.jsonl`, whose row for each of those steps carries the SHA-256 of its frame.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class States:
    campaign: str
    steps: np.ndarray
    values: np.ndarray
    """Float32 [T, H, W, C]."""


def load_states(campaign_dir: Path) -> States:
    manifest = json.loads((campaign_dir / "replay-manifest.json").read_text())
    if manifest.get("developmentStatePath") is None:
        raise ValueError(f"{campaign_dir}: replay has no raw state; rerun with --development-state --development-raw-steps all")
    shape = tuple(manifest["developmentStateShape"])
    steps = manifest["developmentStateSteps"]
    values = np.fromfile(campaign_dir / "development-state.f32", dtype="<f4").reshape(shape)
    by_step = {row["step"]: row for row in map(json.loads, (campaign_dir / "development-trace.jsonl").read_text().splitlines())}
    if len(steps) != shape[0] or not set(steps) <= by_step.keys():
        raise ValueError(f"{campaign_dir}: state steps {steps} do not match {shape[0]} frames and the trace rows")
    rows = [by_step[step] for step in steps]
    for row, frame in zip(rows, values, strict=True):
        if hashlib.sha256(frame.tobytes()).hexdigest() != row["stateSha256"]:
            raise ValueError(f"{campaign_dir}: state at step {row['step']} does not match its hash")
    return States(campaign_dir.name, np.array([r["step"] for r in rows]), values)
