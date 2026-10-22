"""Measure SFPU engine throughput per N300 card, on several cards at once.

Usage:
    python devtools/bench.py --input INDEX.jsonl --cards 0,1,2,3 --batches 256,3584

Bodies from the index are repeated to fill each batch. Cards run concurrently, so the box
rate is the sum of the per-card rates for the same batch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.device import on_cards
from tt_lenia.sfpu.replay import Body, engine_inputs, load_index

WARMUP_STEPS = 2


def _bench(card: int, bodies: list[Body], batches: list[int], steps: int) -> list[dict]:
    from tt_lenia.device import close_card, open_card
    from tt_lenia.sfpu.engine import LANES, SfpuEngine

    mesh = open_card()
    rows = []
    try:
        lanes = LANES * int(mesh.get_num_devices())
        for batch in batches:
            if batch % lanes:
                raise ValueError(f"batch {batch} is not a multiple of {lanes} lanes")
            mass, params = engine_inputs([bodies[i % len(bodies)] for i in range(batch)], lanes)
            engine = SfpuEngine(mesh, bodies[0].spec, mass, params, capture=False)
            engine.step(WARMUP_STEPS)
            engine.synchronize()
            t0 = time.perf_counter()
            engine.step(steps)
            engine.synchronize()
            step_s = (time.perf_counter() - t0) / steps
            stage_ms = {}
            for stage in ("p1", "p2", "p3", "p4", "p5"):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="LeniaCLI export index.jsonl")
    parser.add_argument("--cards", required=True, help="comma-separated N300 card indices")
    parser.add_argument("--batches", required=True, help="comma-separated bodies per card")
    parser.add_argument("--steps", type=int, default=32)
    args = parser.parse_args()
    bodies = load_index(args.input)
    cards = [int(c) for c in args.cards.split(",")]
    batches = [int(b) for b in args.batches.split(",")]
    results = on_cards(_bench, {card: (bodies, batches, args.steps) for card in cards})
    for i, batch in enumerate(batches):
        box = sum(results[card][i]["bodyStepsPerSecond"] for card in cards)
        print(
            f"{bodies[0].spec.sx}^2 batch {batch} per card on {len(cards)} cards: {box:.0f} body-steps/s"
        )
    print(json.dumps({"input": str(args.input), "steps": args.steps, "cards": results}))


if __name__ == "__main__":
    main()
