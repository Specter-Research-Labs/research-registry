"""Replay LeniaCLI export bundles on the SFPU engine and write classify-creatures campaigns.

The input is the index.jsonl that `LeniaCLI publish replay --input` reads. Each body becomes a
campaign directory with config.json, replay-manifest.json and development-trace.jsonl, whose
rows follow morphospaceDevelopmentSample with the field at the arena side, so
assess-creatures and classify-creatures read TT replays and Metal replays alike.

Every body runs as an ensemble of members, one per seed, built by the one-ulp perturbation of
lenia_swarm_analysis with role index 0; seed 0 is the unperturbed body. Each member is its own
campaign, named with a `-u<seed>` suffix, whose config.json carries the member's exact initial
field as a full-grid state patch.

Members form one queue, cut into rounds of whole 64-lane units and dealt round-robin to the N300
cards, each of which runs its rounds one engine at a time on its (1, 2) mesh in its own process.
Lanes share no data, so a member's trajectory does not depend on its slot or its neighbours, and
only the last unit of the queue holds filler: zero-mass, zero-spectrum lanes that are checked to
stay zero and are never written out. summary.json lists every filler slot.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lenia_swarm_analysis.perturbation import one_ulp_member

from ..config import compile_kernels, load_config, resolve_connectivity, resolve_params
from ..device import MESH_SHAPE, on_cards
from .codegen import PassSpec
from .engine import LANES, BodyParams

ENGINE = "tt-sfpu-fp32"
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
ROLE_INDEX = 0
PERTURBATION = "lenia_swarm_analysis.perturbation.one_ulp_member"
UNIT = LANES * MESH_SHAPE[0] * MESH_SHAPE[1]


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


@dataclass(frozen=True)
class Member:
    body: Body
    seed: int
    mass: np.ndarray

    @classmethod
    def of(cls, body: Body, seed: int) -> Member:
        return cls(body, seed, one_ulp_member(body.mass, seed, ROLE_INDEX))

    @property
    def campaign(self) -> str:
        return f"{self.body.campaign}-u{self.seed}"


@dataclass(frozen=True)
class Round:
    card: int
    index: int
    start: int
    stop: int
    size: int


def _sha256(state: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(state, "<f4").tobytes()).hexdigest()


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
        "stateSha256": _sha256(state),
    }


def parse_seeds(text: str) -> list[int]:
    """Comma-separated seeds and inclusive ranges, such as `0`, `1-8` or `0,3-5`."""
    seeds = []
    for part in text.split(","):
        first, _, last = part.partition("-")
        seeds += list(range(int(first), int(last or first) + 1))
    if len(set(seeds)) != len(seeds) or min(seeds) < 0:
        raise ValueError(f"seeds {text!r} repeat or are negative")
    return seeds


def plan_rounds(count: int, cards: list[int], batch: int) -> list[Round]:
    """Cut a queue of `count` members into rounds of at most `batch` lanes, as even as whole
    units allow, so that every card gets the same number of rounds and filler only ever pads
    the queue's last unit."""
    if batch <= 0 or batch % UNIT:
        raise ValueError(f"batch {batch} must be a positive multiple of {UNIT}")
    units = -(-count // UNIT)
    rounds = min(units, len(cards) * -(-units // (len(cards) * (batch // UNIT))))
    base, extra = divmod(units, rounds)
    plan, unit = [], 0
    for r in range(rounds):
        n = base + (r < extra)
        start = unit * UNIT
        plan.append(
            Round(
                cards[r % len(cards)],
                r // len(cards),
                start,
                min(start + n * UNIT, count),
                n * UNIT,
            )
        )
        unit += n
    return plan


def slot(lane: int, size: int) -> dict:
    """Where batch position `lane` of a round of `size` lanes sits on the card."""
    per_chip = size // (MESH_SHAPE[0] * MESH_SHAPE[1])
    return {"chip": lane // per_chip, "group": lane % per_chip // LANES, "lane": lane % LANES}


def _member_config(member: Member, steps: int) -> dict:
    raw = member.body.config
    sx, sy, channels = member.mass.shape
    patch = {
        "center": [sx // 2, sy // 2],
        "channels": channels,
        "width": sx,
        "height": sy,
        "encoding": "f32le",
        "data": base64.b64encode(np.ascontiguousarray(member.mass, "<f4").tobytes()).decode(),
    }
    return {
        **raw,
        "init": {**raw["init"], "state_patch": patch},
        "run": {**raw["run"], "steps": steps},
    }


def _write_campaign(
    out: Path, member: Member, where: dict, index: Path, steps: int, interval: int
) -> None:
    body = member.body
    campaign = out / "campaigns" / member.campaign
    campaign.mkdir(parents=True)
    config = _member_config(member, steps)
    if not np.array_equal(initial_mass(config), member.mass):
        raise AssertionError(f"{member.campaign}: config does not reproduce the member field")
    (campaign / "config.json").write_text(json.dumps(config, indent=2))
    manifest = {
        "campaignId": member.campaign,
        "capturedSteps": list(range(interval, steps + 1, interval)),
        "engine": ENGINE,
        "inputPath": str(index),
        "recordEvery": interval,
        "sourceCreatureId": body.creature_id,
        "sourceExportDir": body.export_dir,
        "sourceCampaignId": body.campaign,
        "seed": member.seed,
        "roleIndex": ROLE_INDEX,
        "perturbation": PERTURBATION,
        "inputFieldSha256": _sha256(member.mass),
        "slot": where,
    }
    (campaign / "replay-manifest.json").write_text(json.dumps(manifest, indent=2))


def engine_inputs(members: list[Member], size: int) -> tuple[np.ndarray, BodyParams]:
    """Stacked engine inputs; lanes past the last member hold zero-mass, zero-spectrum filler."""
    if len(members) > size:
        raise ValueError(f"{len(members)} members exceed the {size} lanes")
    spec = members[0].body.spec
    mass = np.zeros((size, spec.sx, spec.sy, spec.channels), F32)
    spectra = np.zeros((size, spec.sx, spec.sy, spec.kernels), F32)
    m = np.zeros((size, spec.kernels), F32)
    s = np.ones((size, spec.kernels), F32)
    h = np.zeros((size, spec.kernels), F32)
    for i, member in enumerate(members):
        body = member.body
        mass[i], spectra[i], m[i], s[i], h[i] = member.mass, body.spectra, body.m, body.s, body.h
    return mass, BodyParams(spectra, m, s, h)


def _card_worker(
    card: int, rounds: list[tuple[Round, list[Member]]], out: Path, steps: int, interval: int
) -> None:
    from ..device import close_card, open_card
    from .engine import SfpuEngine

    mesh = open_card()
    try:
        done, t0 = 0, time.perf_counter()
        for rnd, members in rounds:
            mass, params = engine_inputs(members, rnd.size)
            engine = SfpuEngine(mesh, members[0].body.spec, mass, params, capture=False)
            traces = [out / "campaigns" / m.campaign / "development-trace.jsonl" for m in members]
            for step in range(interval, steps + 1, interval):
                engine.step(interval)
                state = engine.mass()
                if state[len(members) :].any():
                    raise AssertionError(f"card {card} round {rnd.index}: filler lanes left zero")
                for i, path in enumerate(traces):
                    with path.open("a") as f:
                        f.write(json.dumps(trace_row(step, state[i])) + "\n")
                rate = (done + step * len(members)) / (time.perf_counter() - t0)
                print(
                    f"card {card} round {rnd.index}: step {step}/{steps}, {rate:.0f} body-steps/s",
                    flush=True,
                )
            done += steps * len(members)
            del engine
    finally:
        close_card(mesh)


def replay(
    index: Path,
    out: Path,
    steps: int,
    interval: int,
    cards: list[int],
    seeds: list[int],
    batch: int,
) -> dict:
    if steps % interval:
        raise ValueError(f"steps {steps} must be a multiple of the trace interval {interval}")
    if out.exists():
        raise ValueError(f"{out} exists; replays never write into an existing directory")
    members = [Member.of(body, seed) for body in load_index(index) for seed in seeds]
    plan = plan_rounds(len(members), cards, batch)
    jobs: dict[int, list] = {card: [] for card in cards}
    filler = []
    for rnd in plan:
        share = members[rnd.start : rnd.stop]
        for lane, member in enumerate(share):
            where = {"card": rnd.card, "round": rnd.index, **slot(lane, rnd.size)}
            _write_campaign(out, member, where, index, steps, interval)
        for lane in range(len(share), rnd.size):
            filler.append({"card": rnd.card, "round": rnd.index, **slot(lane, rnd.size)})
        jobs[rnd.card].append((rnd, share))
    t0 = time.perf_counter()
    on_cards(_card_worker, {card: (r, out, steps, interval) for card, r in jobs.items() if r})
    elapsed = time.perf_counter() - t0
    summary = {
        "engine": ENGINE,
        "inputPath": str(index),
        "inputSha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        "steps": steps,
        "recordEvery": interval,
        "seeds": seeds,
        "roleIndex": ROLE_INDEX,
        "perturbation": PERTURBATION,
        "batch": batch,
        "rounds": [
            {
                "card": r.card,
                "round": r.index,
                "lanes": r.size,
                "campaigns": [m.campaign for m in members[r.start : r.stop]],
            }
            for r in plan
        ],
        "filler": {"count": len(filler), "slots": filler},
        "members": len(members),
        "elapsedSeconds": elapsed,
        "bodyStepsPerSecond": len(members) * steps / elapsed,
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
    parser.add_argument("--seeds", required=True, help="ensemble seeds per body, such as 0-8")
    parser.add_argument(
        "--batch", type=int, required=True, help=f"lanes per round, a multiple of {UNIT}"
    )
    args = parser.parse_args()
    cards = [int(c) for c in args.cards.split(",")]
    seeds = parse_seeds(args.seeds)
    summary = replay(
        args.input, args.output, args.steps, args.trace_interval, cards, seeds, args.batch
    )
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rounds", "filler")}, indent=2))
    print(f"filler lanes: {summary['filler']['count']}")


if __name__ == "__main__":
    main()
