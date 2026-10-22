"""Replay LeniaCLI export bundles on the SFPU engine and write classify-creatures campaigns.

The input is the index.jsonl that `LeniaCLI publish replay --input` reads. Each body becomes a
campaign directory with config.json, replay-manifest.json and development-trace.jsonl, whose
rows follow morphospaceDevelopmentSample with the field at the arena side, so
assess-creatures and classify-creatures read TT replays and Metal replays alike.

Each N300 card runs one engine on its (1, 2) mesh in its own process. Bodies are split evenly
across cards; lanes past the last body of a card hold zero-mass filler bodies, which stay at
zero and are never written out.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import multiprocessing as mp
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import compile_kernels, load_config, resolve_connectivity, resolve_params
from .codegen import PassSpec
from .engine import LANES, BodyParams

ENGINE = "tt-sfpu-fp32"
MESH_SHAPE = (1, 2)
VALIDATED_MODE = "flowlenia_2022_paper_equations"
CONFIG_KEYS = {
    "backend",
    "channels",
    "connectivity",
    "flow",
    "grid",
    "implementation",
    "init",
    "interventions",
    "parameter_embedding",
    "params",
    "profile",
    "reintegration",
    "run",
}
F32 = np.float32


@dataclass(frozen=True)
class Body:
    campaign: str
    creature_id: str
    export_dir: str
    config: dict
    mass: np.ndarray
    spectra: np.ndarray
    m: np.ndarray
    s: np.ndarray
    h: np.ndarray
    spec: PassSpec


def _check_config(raw: dict, name: str) -> None:
    """Refuse every config feature the SFPU engine was not validated against Metal for."""
    problems = []
    if set(raw) != CONFIG_KEYS:
        problems.append(f"keys {sorted(set(raw) ^ CONFIG_KEYS)} differ from the validated set")
    if raw["implementation"] != {"mode": VALIDATED_MODE}:
        problems.append(f"implementation {raw['implementation']}")
    if raw["reintegration"]["border"] != "torus":
        problems.append(f"border {raw['reintegration']['border']}")
    if raw["parameter_embedding"]["enabled"]:
        problems.append("parameter embedding")
    if raw["interventions"]:
        problems.append("interventions")
    if raw["params"]["mode"] != "explicit":
        problems.append(f"params mode {raw['params']['mode']}")
    init = raw["init"]
    if init["patches"] or init["a_uniform"] != {"low": 0, "high": 0}:
        problems.append("random init patches")
    if init.get("state_patch", {}).get("encoding") != "f32le":
        problems.append("no f32le state patch")
    if problems:
        raise ValueError(f"{name}: unsupported config: {'; '.join(problems)}")


def initial_mass(raw: dict) -> np.ndarray:
    """The state patch placed as LeniaCLI places it: x0 = cx - width / 2 along the first axis."""
    grid, patch = raw["grid"], raw["init"]["state_patch"]
    sx, sy, channels = grid["sx"], grid["sy"], raw["channels"]
    if patch["channels"] != channels:
        raise ValueError(f"state patch has {patch['channels']} channels, config has {channels}")
    w, h = patch["width"], patch["height"]
    values = np.frombuffer(base64.b64decode(patch["data"]), dtype="<f4")
    if values.size != w * h * channels:
        raise ValueError(f"state patch holds {values.size} values, expected {w * h * channels}")
    cx, cy = patch["center"]
    x0, y0 = cx - w // 2, cy - h // 2
    if x0 < 0 or y0 < 0 or x0 + w > sx or y0 + h > sy:
        raise ValueError(f"state patch at {patch['center']} size {w}x{h} leaves the {sx}x{sy} grid")
    mass = np.zeros((sx, sy, channels), F32)
    mass[x0 : x0 + w, y0 : y0 + h] = values.reshape(w, h, channels)
    return mass


def load_body(base_config: Path, campaign: str, creature_id: str, export_dir: str) -> Body:
    config, raw = load_config(base_config)
    _check_config(raw, campaign)
    c0, c1 = resolve_connectivity(raw)
    kernels = compile_kernels(resolve_params(raw, config.nb_k), config, c0, c1)
    fk = kernels.fK[0]
    if np.abs(fk.imag).max() > 1e-5 * np.abs(fk.real).max():
        raise ValueError(f"{campaign}: kernel spectra are not real")
    spec = PassSpec(
        sx=config.sx,
        sy=config.sy,
        channels=config.channels,
        c0=tuple(int(c) for c in kernels.c0_idxs),
        output_weights=tuple(tuple(int(w) for w in row) for row in kernels.c1_mask),
        dt=config.dt,
        dd=config.dd,
        sigma=config.sigma,
        theta_a=config.theta_a,
        n=config.n,
    )
    return Body(
        campaign=campaign,
        creature_id=creature_id,
        export_dir=export_dir,
        config=raw,
        mass=initial_mass(raw),
        spectra=fk.real.astype(F32),
        m=kernels.m,
        s=kernels.s,
        h=kernels.h,
        spec=spec,
    )


def load_index(index: Path) -> list[Body]:
    """Campaigns are named as LeniaCLI names them: ordinal, export name, lowercased id prefix.

    Export directories are found next to the index by name, because the absolute paths recorded
    in it belong to the machine that wrote it."""
    bodies = []
    for ordinal, line in enumerate(index.read_text().splitlines(), start=1):
        entry = json.loads(line)
        campaign = f"{ordinal:04d}-{entry['name']}-{entry['creatureId'][:8].lower()}"
        base = index.parent / Path(entry["exportDir"]).name / "base.json"
        bodies.append(load_body(base, campaign, entry["creatureId"], entry["exportDir"]))
    specs = {b.spec for b in bodies}
    if len(specs) != 1:
        raise ValueError(f"{index}: bodies need one shared pass spec, found {len(specs)}")
    return bodies


def _swift_round(x: F32) -> int:
    """Swift's round() rounds half away from zero; numpy rounds half to even."""
    v = float(x)
    return int(math.copysign(math.floor(abs(v) + 0.5), v))


def _short(x: F32) -> float:
    return float(repr(F32(x)).removeprefix("np.float32(").removesuffix(")"))


def trace_row(step: int, state: np.ndarray) -> dict:
    """morphospaceDevelopmentSample of a [rows, cols, channels] state with the field at the
    arena side. Sums run sequentially in float32 in Swift's order so centres match bit for bit."""
    rows, cols, channels = state.shape
    matter = state[..., 0].copy()
    for c in range(1, channels):
        matter = matter + state[..., c]
    flat = matter.ravel()
    total = np.add.accumulate(flat)[-1]
    if not total > F32(1e-8):
        raise ValueError(f"step {step}: empty field")
    xs = np.tile(np.arange(cols, dtype=F32) + F32(0.5), rows)
    ys = np.repeat(np.arange(rows, dtype=F32) + F32(0.5), cols)
    center_x = np.add.accumulate(flat * xs)[-1] / total
    center_y = np.add.accumulate(flat * ys)[-1] / total
    shift_x = _swift_round(F32(cols) * F32(0.5) - center_x)
    shift_y = _swift_round(F32(rows) * F32(0.5) - center_y)
    centered = np.roll(matter, (shift_y, shift_x), axis=(0, 1))
    peak = centered.max()
    if not peak > F32(1e-8):
        raise ValueError(f"step {step}: empty field")
    field = (centered / peak).astype("<f2")
    return {
        "step": step,
        "centerX": _short(center_x),
        "centerY": _short(center_y),
        "width": cols,
        "height": rows,
        "fieldResolution": cols,
        "fieldF16Base64": base64.b64encode(field.tobytes()).decode(),
        "stateSha256": hashlib.sha256(np.ascontiguousarray(state, "<f4").tobytes()).hexdigest(),
    }


def _write_campaign(out: Path, body: Body, index: Path, steps: int, interval: int) -> None:
    campaign = out / "campaigns" / body.campaign
    campaign.mkdir(parents=True)
    config = {**body.config, "run": {**body.config["run"], "steps": steps}}
    (campaign / "config.json").write_text(json.dumps(config, indent=2))
    manifest = {
        "campaignId": body.campaign,
        "capturedSteps": list(range(interval, steps + 1, interval)),
        "engine": ENGINE,
        "inputPath": str(index),
        "recordEvery": interval,
        "sourceCreatureId": body.creature_id,
        "sourceExportDir": body.export_dir,
    }
    (campaign / "replay-manifest.json").write_text(json.dumps(manifest, indent=2))


def _card_worker(card: int, bodies: list[Body], out: Path, steps: int, interval: int) -> None:
    os.environ["TT_VISIBLE_DEVICES"] = str(card)
    from ..device import close_ttnn_device, open_ttnn_device
    from .engine import SfpuEngine

    mesh = open_ttnn_device(mesh_shape=MESH_SHAPE)
    try:
        lanes = LANES * int(mesh.get_num_devices())
        batch = -(-len(bodies) // lanes) * lanes
        spec = bodies[0].spec
        mass = np.zeros((batch, spec.sx, spec.sy, spec.channels), F32)
        spectra = np.zeros((batch, spec.sx, spec.sy, spec.kernels), F32)
        m = np.zeros((batch, spec.kernels), F32)
        s = np.ones((batch, spec.kernels), F32)
        h = np.zeros((batch, spec.kernels), F32)
        for i, body in enumerate(bodies):
            mass[i], spectra[i], m[i], s[i], h[i] = body.mass, body.spectra, body.m, body.s, body.h
        engine = SfpuEngine(mesh, spec, mass, BodyParams(spectra, m, s, h), capture=False)
        traces = [out / "campaigns" / b.campaign / "development-trace.jsonl" for b in bodies]
        t0 = time.perf_counter()
        for step in range(interval, steps + 1, interval):
            engine.step(interval)
            state = engine.mass()
            for i, path in enumerate(traces):
                with path.open("a") as f:
                    f.write(json.dumps(trace_row(step, state[i])) + "\n")
            rate = step * len(bodies) / (time.perf_counter() - t0)
            print(f"card {card}: step {step}/{steps}, {rate:.0f} body-steps/s", flush=True)
    finally:
        close_ttnn_device(mesh)


def replay(index: Path, out: Path, steps: int, interval: int, cards: list[int]) -> dict:
    if steps % interval:
        raise ValueError(f"steps {steps} must be a multiple of the trace interval {interval}")
    if out.exists():
        raise ValueError(f"{out} exists; replays never write into an existing directory")
    bodies = load_index(index)
    per_card = -(-len(bodies) // len(cards))
    shares = [bodies[i * per_card : (i + 1) * per_card] for i in range(len(cards))]
    for body in bodies:
        _write_campaign(out, body, index, steps, interval)
    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    procs = [
        ctx.Process(target=_card_worker, args=(card, share, out, steps, interval))
        for card, share in zip(cards, shares)
        if share
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    failed = [p.name for p in procs if p.exitcode != 0]
    if failed:
        raise RuntimeError(f"card workers failed: {failed}")
    elapsed = time.perf_counter() - t0
    summary = {
        "engine": ENGINE,
        "inputPath": str(index),
        "inputSha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        "steps": steps,
        "recordEvery": interval,
        "cards": {str(card): [b.campaign for b in share] for card, share in zip(cards, shares)},
        "bodies": len(bodies),
        "elapsedSeconds": elapsed,
        "bodyStepsPerSecond": len(bodies) * steps / elapsed,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="LeniaCLI export index.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--trace-interval", type=int, required=True)
    parser.add_argument("--cards", required=True, help="comma-separated N300 card indices")
    args = parser.parse_args()
    cards = [int(c) for c in args.cards.split(",")]
    summary = replay(args.input, args.output, args.steps, args.trace_interval, cards)
    print(json.dumps({k: v for k, v in summary.items() if k != "cards"}, indent=2))


if __name__ == "__main__":
    main()
