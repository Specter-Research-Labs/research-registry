"""Measure SFPU engine throughput per N300 card, on several cards at once.

Usage:
    python devtools/bench.py --input INDEX.jsonl --cards 0,1,2,3 --batches 256,3584
    python devtools/bench.py --input INDEX.jsonl --cards 0 --batches 4096 --profile /repo/tmp/prof

Bodies from the index are repeated to fill each batch. Cards run concurrently, so the box
rate is the sum of the per-card rates for the same batch.

With --profile the device profiler records every pass separately instead: device time per
pass, the busy time of each RISC, and the device zones the kernels declare, averaged over
cores and repetitions. The raw marker log stays under the given directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.device import on_cards
from tt_lenia.sfpu.replay import Body, Member, engine_inputs, load_index

WARMUP_STEPS = 2
STAGES = ("p1", "p2", "p3", "p4", "p5")
KERNEL_ZONES = {"BRISC-KERNEL", "NCRISC-KERNEL", "TRISC-KERNEL"}


def _engine(mesh, bodies: list[Body], batch: int):
    from tt_lenia.sfpu.engine import LANES, SfpuEngine

    lanes = LANES * int(mesh.get_num_devices())
    if batch % lanes:
        raise ValueError(f"batch {batch} is not a multiple of {lanes} lanes")
    members = [Member.of(bodies[i % len(bodies)], 0) for i in range(batch)]
    mass, params = engine_inputs(members, batch)
    return SfpuEngine(mesh, bodies[0].spec, mass, params, capture=False)


def _bench(card: int, bodies: list[Body], batches: list[int], steps: int) -> list[dict]:
    from tt_lenia.device import close_card, open_card

    mesh = open_card()
    rows = []
    try:
        for batch in batches:
            engine = _engine(mesh, bodies, batch)
            engine.step(WARMUP_STEPS)
            engine.synchronize()
            t0 = time.perf_counter()
            engine.step(steps)
            engine.synchronize()
            step_s = (time.perf_counter() - t0) / steps
            stage_ms = {}
            for stage in STAGES:
                t0 = time.perf_counter()
                for _ in range(steps):
                    engine.run_stage(stage)
                engine.synchronize()
                stage_ms[stage] = (time.perf_counter() - t0) / steps * 1e3
            rows.append(
                {
                    "batch": batch,
                    "msPerStep": step_s * 1e3,
                    "bodyStepsPerSecond": batch / step_s,
                    "stageMs": stage_ms,
                    "loadAverage": os.getloadavg()[0],
                }
            )
            print(
                f"card {card}: {bodies[0].spec.sx}^2 batch {batch}: {step_s * 1e3:.2f} ms/step, "
                f"{batch / step_s:.0f} body-steps/s, stages "
                + " ".join(f"{k} {v:.2f}" for k, v in stage_ms.items()),
                flush=True,
            )
            del engine
    finally:
        close_card(mesh)
    return rows


def _profile(card: int, bodies: list[Body], batches: list[int], reps: int, out: str) -> list:
    """One program per marker read, because a core's marker buffer holds only a few programs."""
    log_dir = Path(out) / f"card{card}"
    os.environ["TT_METAL_DEVICE_PROFILER"] = "1"
    os.environ["TT_METAL_PROFILER_SUM"] = "1"
    os.environ["TT_METAL_PROFILER_DIR"] = str(log_dir)
    import ttnn

    from tt_lenia.device import close_card, open_card

    mesh = open_card()
    labels: list[tuple[int, str]] = []
    try:
        for batch in batches:
            engine = _engine(mesh, bodies, batch)
            for stage in STAGES:
                for _ in range(reps + 1):
                    engine.run_stage(stage)
                    engine.synchronize()
                    ttnn.ReadDeviceProfiler(mesh)
                    labels.append((batch, stage))
            del engine
    finally:
        close_card(mesh)
    return _summarize(log_dir / ".logs" / "profile_log_device.csv", labels)


def _summarize(path: Path, labels: list[tuple[int, str]]) -> list[dict]:
    """Programs are matched to labels by dispatch order; the first run of each label is a
    warmup that compiles and loads the kernels, and is dropped."""
    with path.open() as f:
        freq_mhz = float(f.readline().split("CHIP_FREQ[MHz]:")[1].split(",")[0])
        rows = list(csv.DictReader(f, skipinitialspace=True))
    zones: dict[tuple, dict[str, int]] = defaultdict(dict)
    sums: dict[tuple, int] = defaultdict(int)
    for r in rows:
        key = (int(r["PCIe slot"]), int(r["run host ID"]))
        core = (int(r["core_x"]), int(r["core_y"]), r["RISC processor type"])
        name, kind, t = r["zone name"], r["type"], int(r["time[cycles since reset]"])
        if kind == "ZONE_START":
            zones[key + core + (name,)]["start"] = t
        elif kind == "ZONE_END":
            zones[key + core + (name,)]["end"] = t
        elif kind == "ZONE_TOTAL":
            sums[key + core + (name,)] += int(r["data"])
        else:
            raise ValueError(f"unexpected marker type {kind!r} in {path}")
    programs = sorted({k[:2] for k in zones})
    kept: dict[tuple[int, str], list[tuple[int, int]]] = defaultdict(list)
    for chip in sorted({chip for chip, _ in programs}):
        runs = sorted(run for c, run in programs if c == chip)
        if len(runs) != len(labels):
            raise ValueError(
                f"{len(runs)} profiled programs on chip {chip} for {len(labels)} dispatches"
            )
        seen: set[tuple[int, str]] = set()
        for run, label in zip(runs, labels, strict=True):
            if label in seen:
                kept[label].append((chip, run))
            seen.add(label)

    def ms(cycles: float) -> float:
        return cycles / freq_mhz / 1e3

    results = []
    for (batch, stage), keep in kept.items():
        spans, busy, zone_sum = [], defaultdict(list), defaultdict(list)
        for program in keep:
            k = {key[2:]: v for key, v in zones.items() if key[:2] == program}
            kern = {c: v for c, v in k.items() if c[3] in KERNEL_ZONES}
            spans.append(
                max(v["end"] for v in kern.values()) - min(v["start"] for v in kern.values())
            )
            for (_, _, risc, name), v in k.items():
                if name in KERNEL_ZONES:
                    busy[risc].append(v["end"] - v["start"])
                elif not name.endswith("-FW"):
                    zone_sum[f"{risc} {name}"].append(v["end"] - v["start"])
            for key, total in sums.items():
                if key[:2] == program:
                    zone_sum[f"{key[4]} {key[5]}"].append(total)
        results.append(
            {
                "batch": batch,
                "stage": stage,
                "programs": len(keep),
                "deviceMs": ms(sum(spans) / len(spans)),
                "riscBusyMs": {r: ms(sum(v) / len(v)) for r, v in sorted(busy.items())},
                "zoneMs": {z: ms(sum(v) / len(v)) for z, v in sorted(zone_sum.items())},
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="LeniaCLI export index.jsonl")
    parser.add_argument("--cards", required=True, help="comma-separated N300 card indices")
    parser.add_argument("--batches", required=True, help="comma-separated bodies per card")
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--profile", type=Path, help="device profiler output directory")
    parser.add_argument("--reps", type=int, default=3, help="profiled runs of each pass")
    args = parser.parse_args()
    bodies = load_index(args.input)
    cards = [int(c) for c in args.cards.split(",")]
    batches = [int(b) for b in args.batches.split(",")]
    if args.profile:
        jobs = {card: (bodies, batches, args.reps, str(args.profile)) for card in cards}
        results = on_cards(_profile, jobs)
        for card in cards:
            for r in results[card]:
                print(
                    f"card {card} batch {r['batch']} {r['stage']}: {r['deviceMs']:.2f} ms, busy "
                    + " ".join(f"{k} {v:.2f}" for k, v in r["riscBusyMs"].items())
                    + "".join(f"\n  {k}: {v:.3f} ms" for k, v in r["zoneMs"].items())
                )
        print(json.dumps({"input": str(args.input), "reps": args.reps, "cards": results}))
        return
    results = on_cards(_bench, {card: (bodies, batches, args.steps) for card in cards})
    for i, batch in enumerate(batches):
        box = sum(results[card][i]["bodyStepsPerSecond"] for card in cards)
        print(
            f"{bodies[0].spec.sx}^2 batch {batch} per card on {len(cards)} cards: {box:.0f} body-steps/s"
        )
    print(json.dumps({"input": str(args.input), "steps": args.steps, "cards": results}))


if __name__ == "__main__":
    main()
