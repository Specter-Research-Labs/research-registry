"""Check the SFPU engine against the float64 Metal-semantics reference on one N300 card.

Usage:
    python devtools/validate.py --input INDEX.jsonl --card 0

Every stage of one step is compared for each body, and a short rollout for the first few. The
float32 reference runs alongside as the yardstick: the largest device error of each quantity
must stay within RATIO times the largest error an IEEE float32 implementation of the same
equations makes, which is also the class in which Metal builds differ from each other.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.device import on_cards
from tt_lenia.numpy_ref import metal
from tt_lenia.sfpu.replay import Body, engine_inputs, load_index

STAGES = ("potential", "affinity", "flow", "mass")
ROLLOUT_BODIES = 4
RATIO = 3.0


def relative_rms(actual: np.ndarray, expected: np.ndarray) -> float:
    err = np.sqrt(np.mean((actual.astype(np.float64) - expected) ** 2))
    return float(err / np.sqrt(np.mean(np.square(expected, dtype=np.float64))))


def reference(body: Body) -> tuple[metal.MetalKernels, metal.MetalStepConfig]:
    spec = body.spec
    kernels = metal.MetalKernels(
        spectra=body.spectra,
        c0=np.array(spec.c0),
        output_weights=np.array(spec.output_weights, np.float32),
        m=body.m,
        s=body.s,
        h=body.h,
    )
    cfg = metal.MetalStepConfig(
        dt=spec.dt,
        dd=spec.dd,
        sigma=spec.sigma,
        theta_a=spec.theta_a,
        n=spec.n,
        clip_flow=False,
    )
    return kernels, cfg


def _validate(card: int, bodies: list[Body], steps: int) -> dict:
    from tt_lenia.device import close_card, open_card
    from tt_lenia.sfpu.engine import LANES, SfpuEngine

    mesh = open_card()
    try:
        mass, params = engine_inputs(bodies, LANES * int(mesh.get_num_devices()))
        spec = bodies[0].spec
        engine = SfpuEngine(mesh, spec, mass, params, capture=True)
        engine.step()
        got = engine.captured() | {"mass": engine.mass()}
        rollout = SfpuEngine(mesh, spec, mass, params, capture=False)
        rollout.step(steps)
        rolled = rollout.mass()
    finally:
        close_card(mesh)
    step_rows = []
    for i, body in enumerate(bodies):
        kernels, cfg = reference(body)
        ref = metal.step(body.mass[None].astype(np.float64), kernels, cfg)
        ref32 = metal.step(body.mass[None], kernels, cfg, dtype=np.float32)
        step_rows.append(
            {
                name: {
                    "device": relative_rms(got[name][i : i + 1], ref[name]),
                    "float32": relative_rms(ref32[name], ref[name]),
                }
                for name in STAGES
            }
        )
    rollout_rows = []
    for i, body in enumerate(bodies[:ROLLOUT_BODIES]):
        kernels, cfg = reference(body)
        ref = metal.rollout(body.mass[None], kernels, cfg, steps)
        ref32 = metal.rollout(body.mass[None], kernels, cfg, steps, dtype=np.float32)
        rollout_rows.append(
            {
                "device": relative_rms(rolled[i : i + 1], ref),
                "float32": relative_rms(ref32, ref),
            }
        )
    return {"step": step_rows, "rollout": rollout_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="LeniaCLI export index.jsonl")
    parser.add_argument("--card", type=int, required=True, help="N300 card index")
    parser.add_argument("--bodies", type=int, default=64)
    parser.add_argument("--steps", type=int, default=16, help="rollout length")
    args = parser.parse_args()
    bodies = load_index(args.input)[: args.bodies]
    result = on_cards(_validate, {args.card: (bodies, args.steps)})[args.card]

    passed = True
    checks = [(f"{name} one step", [row[name] for row in result["step"]]) for name in STAGES]
    checks.append((f"mass after {args.steps} steps", result["rollout"]))
    for label, rows in checks:
        device = [row["device"] for row in rows]
        float32 = [row["float32"] for row in rows]
        ok = max(device) <= RATIO * max(float32)
        passed &= ok
        print(
            f"{'PASS' if ok else 'FAIL'} {label}, {len(rows)} bodies, relative RMS vs float64: "
            f"device median {np.median(device):.2e} max {max(device):.2e}, "
            f"float32 median {np.median(float32):.2e} max {max(float32):.2e}"
        )
    print(json.dumps({"input": str(args.input), "steps": args.steps, **result}))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
