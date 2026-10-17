"""Raw replay states and the local transitions an observer codes.

`LeniaCLI publish replay --development-trace --development-state` writes, per campaign,
`development-state.f32` (little-endian Float32 [samples, height, width, channels], world frame,
unnormalized) next to `development-trace.jsonl`, whose rows carry the SHA-256 of each frame.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

# Patch centres include empty cells this close to the body, so that the observer has to code growth
# and motion into empty space, not only the evolution of already-occupied cells.
SUPPORT_MARGIN = 3



@dataclass(frozen=True)
class States:
    campaign: str
    steps: np.ndarray
    values: np.ndarray
    """Float32 [T, H, W, C]."""


@dataclass(frozen=True)
class Quantizer:
    """Bins between ascending mass edges. Bin 0 (below the first edge) is empty space. Flow Lenia
    mass is conserved, not bounded, and piles up heavy-tailed in a few cells, so uniform bins would
    leave most of the body in one bin; edges set from pooled quantiles of occupied cells avoid that
    while staying fixed across creatures, so every learner predicts in the same units."""

    edges: tuple[float, ...]

    def __post_init__(self) -> None:
        if list(self.edges) != sorted(set(self.edges)) or self.edges[0] <= 0:
            raise ValueError(f"mass edges must be positive and strictly ascending: {self.edges}")

    @property
    def bins(self) -> int:
        return len(self.edges) + 1

    def __call__(self, mass: torch.Tensor) -> torch.Tensor:
        return torch.bucketize(mass, torch.tensor(self.edges, dtype=mass.dtype), right=True)


def load_states(campaign_dir: Path) -> States:
    manifest = json.loads((campaign_dir / "replay-manifest.json").read_text())
    if manifest.get("developmentStatePath") is None:
        raise ValueError(f"{campaign_dir}: replay has no raw state; rerun with --development-state")
    shape = tuple(manifest["developmentStateShape"])
    values = np.fromfile(campaign_dir / "development-state.f32", dtype="<f4").reshape(shape)
    rows = [json.loads(line) for line in (campaign_dir / "development-trace.jsonl").read_text().splitlines()]
    if len(rows) != shape[0]:
        raise ValueError(f"{campaign_dir}: {len(rows)} trace rows for {shape[0]} state frames")
    for row, frame in zip(rows, values, strict=True):
        if hashlib.sha256(frame.tobytes()).hexdigest() != row["stateSha256"]:
            raise ValueError(f"{campaign_dir}: state at step {row['step']} does not match its hash")
    return States(campaign_dir.name, np.array([r["step"] for r in rows]), values)


@dataclass(frozen=True)
class Transitions:
    """A sampled stream of one creature: cells of its source frames, each with the quantized total
    mass the same cell holds `lag` samples later. Patches are gathered from `frames` on demand, so a
    long stream costs a few bytes per sample instead of a full patch."""

    frames: torch.Tensor
    """Float32 [T, H, W, C], the source frames that `cells` index."""
    cells: torch.Tensor
    """Int64 [n, 3]: (source frame, row, column)."""
    target: torch.Tensor
    """Int64 [n]."""


def sample_transitions(
    values: np.ndarray,
    transitions: np.ndarray,
    *,
    lag: int,
    n: int,
    quantizer: Quantizer,
    rng: np.random.Generator,
) -> Transitions:
    """n cells drawn uniformly from the body support of frames `transitions` (either the frame or the
    one `lag` later not in the lowest bin, widened by SUPPORT_MARGIN on the torus)."""
    x = torch.from_numpy(values[transitions])
    y_mass = torch.from_numpy(values[transitions + lag]).sum(-1)
    occupied = (quantizer(x.sum(-1)) > 0) | (quantizer(y_mass) > 0)
    k = 2 * SUPPORT_MARGIN + 1
    wrapped = F.pad(occupied[:, None].float(), (SUPPORT_MARGIN,) * 4, mode="circular")
    support = torch.nonzero(F.max_pool2d(F.max_pool2d(wrapped, (k, 1), 1), (1, k), 1)[:, 0] > 0)
    if len(support) == 0:
        raise ValueError("no occupied cells in the requested transitions")
    cells = support[torch.from_numpy(rng.integers(0, len(support), n))]
    return Transitions(x, cells, quantizer(y_mass[cells[:, 0], cells[:, 1], cells[:, 2]]))


def patches(frames: torch.Tensor, cells: torch.Tensor, radius: int) -> torch.Tensor:
    """Torus-wrapped (2r+1)^2 patches around `cells` [G, n, 3] of `frames` [G, T, H, W, C], gathered
    on the frames' device -> [G, n, 2r+1, 2r+1, C]."""
    groups, steps, height, width, channels = frames.shape
    offsets = torch.arange(-radius, radius + 1, device=cells.device)
    rows = (cells[..., 1, None] + offsets) % height
    cols = (cells[..., 2, None] + offsets) % width
    frame = torch.arange(groups, device=cells.device)[:, None] * steps + cells[..., 0]
    index = ((frame[..., None] * height + rows)[..., :, None] * width + cols[..., None, :])
    return frames.reshape(-1, channels)[index]
