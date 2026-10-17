"""Read access to a `measure` output directory, shared by `transfer` and `conditional`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from .measure import Config, Observer


@dataclass(frozen=True)
class MeasureRun:
    path: Path
    config: Config
    replay: Path
    campaigns: list[str]

    @classmethod
    def open(cls, path: Path) -> MeasureRun:
        raw = json.loads((path / "config.json").read_text())
        replay = Path(raw.pop("replay"))
        raw.pop("device")
        config = Config.from_dict(raw)
        campaigns = [json.loads(line)["campaign"] for line in (path / "creatures.jsonl").read_text().splitlines()]
        return cls(path, config, replay, campaigns)

    def observer(self, name: str) -> Observer:
        matches = [o for o in self.config.observers if o.name == name]
        if not matches:
            raise ValueError(f"observer {name} is not part of {self.path}")
        return matches[0]

    def params(self, name: str, device: str) -> list[torch.Tensor]:
        stored = np.load(self.path / f"params_{name}.npz")
        return [torch.from_numpy(stored[f"arr_{i}"]).to(device) for i in range(len(stored.files))]

    def held_out(self) -> tuple[np.ndarray, np.ndarray]:
        return np.load(self.path / "eval_x.npy", mmap_mode="r"), np.load(self.path / "eval_t.npy", mmap_mode="r")

    def curves(self, name: str) -> np.ndarray:
        return np.load(self.path / "curves.npz")[name]
