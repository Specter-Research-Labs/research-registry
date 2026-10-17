"""Epiplexity S and time-bounded entropy H of every replayed creature, for a set of local observers.

Each observer codes the creature's own local dynamics: the quantized total mass of a cell at t+1
from a patch of its neighbourhood at t. Observers differ in radius, capacity (linear or MLP) and view
(channel-summed or per-channel patch), and all of them see the same sampled stream of a creature.

A transition runs from a source frame to the frame `lag` trace samples later; sources are every
`stride`-th frame, so one dense replay serves several lags on the same developmental schedule.
Sources are split by interleaving (every `eval_every`-th is held out), so training and held-out
data cover the same developmental period. The held-out patches and trained learners are saved for
`transfer` and `conditional`.

Usage: lenia-swarm-observer measure --replay <replay batch dir> --config <config.json> --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .prequential import epiplexity, init_params, prequential
from .states import Quantizer, States, Transitions, load_states, patches, sample_transitions

EVAL_STREAM, TRAIN_STREAM, FRAME_ORDER = 0, 1, 2


@dataclass(frozen=True)
class Observer:
    name: str
    radius: int
    hidden: int
    view: str

    def __post_init__(self) -> None:
        if self.view not in ("sum", "channels"):
            raise ValueError(f"observer {self.name}: view must be 'sum' or 'channels'")

    def inputs(self, patches: torch.Tensor, mass_scale: float) -> torch.Tensor:
        """Mass patches [..., 2R+1, 2R+1, C] sampled at the config radius R -> flat observer input.
        Inputs are log1p(mass / mass_scale) because the target edges are roughly geometric: on raw
        mass the bins below a few tenths are indistinguishable at initialisation and the learners
        underfit a centre-cell lookup table by more than a bit at one step."""
        r = (patches.shape[-2] - 1) // 2
        crop = patches[..., r - self.radius:r + self.radius + 1, r - self.radius:r + self.radius + 1, :]
        if self.view == "sum":
            crop = crop.sum(-1, keepdim=True)
        return torch.log1p(crop.flatten(-3).float() / mass_scale)

    def input_size(self, channels: int) -> int:
        return (2 * self.radius + 1) ** 2 * (1 if self.view == "sum" else channels)


@dataclass(frozen=True)
class Config:
    seed: int
    mass_edges: tuple[float, ...]
    frame_order: str
    stride: int
    lag: int
    eval_every: int
    n_train: int
    n_eval: int
    batch: int
    lr: float
    tail: float
    group: int
    observers: tuple[Observer, ...]

    @classmethod
    def from_dict(cls, raw: dict) -> Config:
        fields: dict[str, Any] = {**raw, "mass_edges": tuple(raw["mass_edges"]),
                                  "observers": tuple(Observer(**o) for o in raw["observers"])}
        config = cls(**fields)
        if config.frame_order not in ("real", "shuffled"):
            raise ValueError("frame_order must be 'real' or 'shuffled'")
        return config

    @property
    def radius(self) -> int:
        return max(o.radius for o in self.observers)

    @property
    def quantizer(self) -> Quantizer:
        return Quantizer(self.mass_edges)


def campaign_key(campaign: str) -> int:
    """Seed component that follows the campaign, not its position, so subsets resample identically."""
    return int.from_bytes(hashlib.sha256(campaign.encode()).digest()[:8], "big")


def rng(config: Config, campaign: str, purpose: int) -> np.random.Generator:
    return np.random.default_rng([config.seed, campaign_key(campaign), purpose])


def split(states: States, config: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (values in coding order, source frames, held-out mask over sources). A shuffled frame order keeps
    each frame's texture and destroys its dynamics, the control for texture-only structure."""
    values = states.values
    if config.frame_order == "shuffled":
        values = values[rng(config, states.campaign, FRAME_ORDER).permutation(len(values))]
    sources = np.arange(0, len(values) - config.lag, config.stride)
    held_out = np.arange(len(sources)) % config.eval_every == config.eval_every - 1
    return values, sources, held_out


def stream(states: States, config: Config, which: int) -> Transitions:
    """The training (TRAIN_STREAM) or held-out (EVAL_STREAM) sample stream of one creature."""
    values, sources, held_out = split(states, config)
    t = sources[held_out if which == EVAL_STREAM else ~held_out]
    n = config.n_eval if which == EVAL_STREAM else config.n_train
    return sample_transitions(values, t, lag=config.lag, n=n, quantizer=config.quantizer,
                              rng=rng(config, states.campaign, which))


def learner_seeds(config: Config, campaigns: list[str]) -> list[int]:
    return [(config.seed * 1_000_003 + campaign_key(c)) % 2**63 for c in campaigns]


def held_out_patches(stream: Transitions, config: Config) -> np.ndarray:
    """Float16 [n, 2R+1, 2R+1, C] at the config radius R, kept because raw states are retired."""
    return patches(stream.frames[None], stream.cells[None], config.radius)[0].half().numpy()


def train(
    observer: Observer, config: Config, params: list[torch.Tensor], streams: list[Transitions],
    device: str,
) -> np.ndarray:
    """Prequential run of one learner per stream, training `params` in place; returns loss curves."""
    frames = torch.stack([s.frames for s in streams]).to(device)
    cells = torch.stack([s.cells for s in streams]).to(device)
    target = torch.stack([s.target for s in streams]).to(device)
    return prequential(params, cells, target, batch=config.batch, lr=config.lr,
                       encode=lambda c: observer.inputs(patches(frames, c, observer.radius),
                                                        config.mass_edges[0]))


def describe(states: States, config: Config) -> dict:
    mass = states.values.sum(-1)
    return {
        "campaign": states.campaign,
        "frames": len(states.steps),
        "first_step": int(states.steps[0]),
        "last_step": int(states.steps[-1]),
        "state_digest": hashlib.sha256(states.values.tobytes()).hexdigest(),
        "occupancy": float((mass >= config.mass_edges[0]).mean()),
        "top_bin_fraction": float((mass >= config.mass_edges[-1]).mean()),
        "frame_change": float(np.abs(np.diff(mass, axis=0)).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lenia-swarm-observer measure", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=["mps", "cuda", "cpu"])
    args = parser.parse_args(argv)

    config = Config.from_dict(json.loads(args.config.read_text()))
    campaign_dirs = sorted(d for d in (args.replay / "campaigns").iterdir() if d.is_dir())
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "config.json").write_text(json.dumps(
        {"replay": str(args.replay.resolve()), "device": args.device, **asdict(config)}, indent=1))

    side = 2 * config.radius + 1
    channels = load_states(campaign_dirs[0]).values.shape[-1]
    eval_x = np.lib.format.open_memmap(args.out / "eval_x.npy", mode="w+", dtype=np.float16,
                                       shape=(len(campaign_dirs), config.n_eval, side, side, channels))
    eval_t = np.lib.format.open_memmap(args.out / "eval_t.npy", mode="w+", dtype=np.int64,
                                       shape=(len(campaign_dirs), config.n_eval))
    params: dict[str, list[list[np.ndarray]]] = {o.name: [] for o in config.observers}
    curves: dict[str, list[np.ndarray]] = {o.name: [] for o in config.observers}
    with (args.out / "creatures.jsonl").open("w") as fh:
        for g0 in range(0, len(campaign_dirs), config.group):
            group = [load_states(d) for d in campaign_dirs[g0:g0 + config.group]]
            if any(s.values.shape[-1] != channels for s in group):
                raise ValueError("all campaigns of one measurement must have the same channel count")
            names = [s.campaign for s in group]
            streams = [stream(s, config, TRAIN_STREAM) for s in group]
            for i, s in enumerate(group):
                held_out = stream(s, config, EVAL_STREAM)
                eval_x[g0 + i], eval_t[g0 + i] = held_out_patches(held_out, config), held_out.target.numpy()
            rows = [describe(s, config) for s in group]
            for observer in config.observers:
                p = init_params(learner_seeds(config, names), observer.input_size(channels),
                                config.quantizer.bins, observer.hidden, args.device)
                curve = train(observer, config, p, streams, args.device)
                s_bits, h_bits = epiplexity(curve, batch=config.batch, tail=config.tail)
                params[observer.name].append([w.detach().cpu().numpy() for w in p])
                curves[observer.name].append(curve)
                for row, s_val, h_val in zip(rows, s_bits, h_bits, strict=True):
                    row[observer.name] = {"S": float(s_val), "H": float(h_val)}
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(f"measured {g0 + len(group)}/{len(campaign_dirs)}", flush=True)
    eval_x.flush()
    eval_t.flush()
    for name, chunks in params.items():
        np.savez(args.out / f"params_{name}.npz",
                 *[np.concatenate([c[i] for c in chunks]) for i in range(len(chunks[0]))])
    np.savez(args.out / "curves.npz", allow_pickle=False,
             **{k: np.concatenate(v) for k, v in curves.items()})
    return 0
