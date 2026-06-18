"""Lyapunov / sensitivity diagnostic: does a small perturbation grow exponentially
through the 1200-step rollout?

This is the step-zero measurement before committing to a gradient strategy. If a tiny
genotype perturbation makes the form-trajectory diverge exponentially, the rollout
Jacobian has a positive Lyapunov exponent, backpropagated gradients of the terminal
form w.r.t. the rule explode (the regime of Metz et al. 2021), and the smoothed /
evolution-strategy route is forced. If divergence stays bounded or sub-exponential,
exact-gradient methods (implicit / adjoint) remain admissible.

We perturb the genotype by a small step along several random directions at a fixed
initial condition, capture the developmental trajectory through the 12 morphology axes
for the perturbed and the reference run, and measure the per-step distance d(t). The
finite-time Lyapunov exponent is the slope of log d(t) while it rises. A small-vs-large
perturbation check confirms we are in the tangent regime. A second pass perturbs the
initial condition (a different seed) instead of the genotype, to separate
state-sensitivity from parameter-sensitivity.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler._codec import (
    clamp_params,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator
from lenia_swarm_analysis.morphospace.common_morphology import AXIS_IDS


def _axis_matrix(path: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    steps = np.array([p["step"] for p in path], dtype=np.int64)
    axes = np.array(
        [[float(p["axes"][a]) for a in AXIS_IDS] for p in path], dtype=np.float64
    )
    return steps, axes


def _divergence(
    ref_steps: np.ndarray,
    ref_axes: np.ndarray,
    per_steps: np.ndarray,
    per_axes: np.ndarray,
    axis_std: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    common = np.intersect1d(ref_steps, per_steps)
    ref_index = {int(s): i for i, s in enumerate(ref_steps)}
    per_index = {int(s): i for i, s in enumerate(per_steps)}
    distances = []
    for s in common:
        delta = (ref_axes[ref_index[int(s)]] - per_axes[per_index[int(s)]]) / axis_std
        distances.append(float(np.linalg.norm(delta)))
    return common, np.asarray(distances, dtype=np.float64)


def _ftle(steps: np.ndarray, distances: np.ndarray) -> dict[str, Any]:
    positive = distances > 1e-9
    if positive.sum() < 3:
        return {"lambdaPerStep": None, "saturationStep": None, "terminal": None}
    logd = np.log(distances[positive])
    s = steps[positive].astype(np.float64)
    peak = int(np.argmax(logd))
    rise = slice(0, max(2, peak + 1))
    slope = float(np.polyfit(s[rise], logd[rise], 1)[0]) if peak >= 1 else None
    return {
        "lambdaPerStep": slope,
        "saturationStep": int(s[peak]),
        "terminal": float(distances[-1]),
    }


def run(
    dataset_path: Path,
    base_config_path: Path,
    search_config_path: Path,
    *,
    bases: int,
    directions: int,
    epsilons: tuple[float, float],
    stride: int,
    steps: int,
    seed: int,
) -> dict[str, Any]:
    codec, genotype, _ = load_dataset(dataset_path)
    rng = np.random.default_rng(seed)
    base_index = rng.permutation(genotype.shape[0])[:bases]
    geno_std = genotype.std(axis=0)
    root = Path.cwd()
    ranges = json.loads(base_config_path.read_text(encoding="utf-8"))["params"]["ranges"]
    simulator = ForwardSimulator(
        base_config_path, search_config_path, dossier_root=root,
        steps=steps, init_seed=0, timeout_seconds=600.0,
    )

    pooled: list[np.ndarray] = []
    runs: list[dict[str, Any]] = []
    for bi in base_index:
        base_vec = genotype[bi]
        base_params, _ = clamp_params(codec.unflatten(base_vec), ranges)
        ref = simulator.developmental_trajectory(base_params, init_seed=0, stride=stride)
        ref_steps, ref_axes = _axis_matrix(ref["path"])
        pooled.append(ref_axes)

        # parameter perturbations
        param_runs: list[dict[str, Any]] = []
        for _ in range(directions):
            direction = rng.standard_normal(base_vec.shape[0])
            direction /= np.linalg.norm(direction)
            for eps in epsilons:
                pert_vec = base_vec + eps * geno_std * direction
                pert_params, _ = clamp_params(codec.unflatten(pert_vec), ranges)
                pert = simulator.developmental_trajectory(pert_params, init_seed=0, stride=stride)
                p_steps, p_axes = _axis_matrix(pert["path"])
                pooled.append(p_axes)
                param_runs.append({"epsilon": eps, "steps": p_steps, "axes": p_axes})

        # initial-condition perturbation (state sensitivity): same genotype, different seed
        state = simulator.developmental_trajectory(base_params, init_seed=1, stride=stride)
        s_steps, s_axes = _axis_matrix(state["path"])
        pooled.append(s_axes)
        runs.append({
            "ref_steps": ref_steps, "ref_axes": ref_axes,
            "param_runs": param_runs, "state": (s_steps, s_axes),
        })

    axis_std = np.concatenate(pooled, axis=0).std(axis=0)
    axis_std[axis_std < 1e-8] = 1.0

    param_lambdas: list[float] = []
    param_terminals: list[float] = []
    state_lambdas: list[float] = []
    state_terminals: list[float] = []
    per_base: list[dict[str, Any]] = []
    for r in runs:
        ref_steps, ref_axes = r["ref_steps"], r["ref_axes"]
        small: list[dict[str, Any]] = []
        large: list[dict[str, Any]] = []
        for pr in r["param_runs"]:
            steps_c, dist = _divergence(ref_steps, ref_axes, pr["steps"], pr["axes"], axis_std)
            ftle = _ftle(steps_c, dist)
            target = small if pr["epsilon"] == min(epsilons) else large
            target.append({"divergence": [float(x) for x in dist], **ftle})
            if ftle["lambdaPerStep"] is not None:
                param_lambdas.append(ftle["lambdaPerStep"])
                param_terminals.append(ftle["terminal"])
        s_steps, s_axes = r["state"]
        steps_c, dist = _divergence(ref_steps, ref_axes, s_steps, s_axes, axis_std)
        sftle = _ftle(steps_c, dist)
        if sftle["lambdaPerStep"] is not None:
            state_lambdas.append(sftle["lambdaPerStep"])
            state_terminals.append(sftle["terminal"])
        per_base.append({"paramSmall": small, "paramLarge": large, "state": sftle})

    def _m(values: list[float]) -> float | None:
        return float(np.mean(values)) if values else None

    param_lambda = _m(param_lambdas)
    return {
        "bases": int(base_index.shape[0]),
        "directions": directions,
        "epsilons": list(epsilons),
        "stride": stride,
        "steps": steps,
        "paramLambdaPerStep": param_lambda,
        "paramGrowthOver50": (
            float(np.exp(param_lambda * 50)) if param_lambda is not None else None
        ),
        "paramTerminalDivergence": _m(param_terminals),
        "stateLambdaPerStep": _m(state_lambdas),
        "stateTerminalDivergence": _m(state_terminals),
        "perBase": per_base,
    }


def _verdict(report: dict[str, Any]) -> str:
    lam = report["paramLambdaPerStep"]
    term = report["paramTerminalDivergence"]
    horizon = report["steps"]
    if lam is None:
        return "inconclusive (no rising divergence captured)"
    g50 = math.exp(lam * 50)
    g200 = math.exp(lam * 200)
    gfull = math.exp(lam * horizon)
    bounded_terminal = term is not None and term < 5.0
    chaotic_full = lam > 0 and gfull > 20.0
    lines = [
        f"parameter sensitivity: lambda/step = {lam:.4f}; perturbation amplification "
        f"x{g50:.1f} over 50 steps, x{g200:.0f} over 200, x{gfull:.0f} over {horizon}; "
        f"terminal divergence {term:.2f}",
    ]
    if chaotic_full:
        lines.append(
            "VERDICT: lambda is positive, so the rollout is weakly chaotic. Amplification "
            "is mild over the first ~50 steps (why backprop survives that far) but large "
            "over the full horizon, so backpropagating gradients through the whole rollout "
            "explodes. Do not unroll; use evolution strategies (smoothed gradient)."
        )
    else:
        lines.append(
            "VERDICT: amplification over the full horizon is modest, so exact-gradient "
            "(implicit/adjoint) methods may be admissible; verify Jacobian conditioning."
        )
    if bounded_terminal:
        lines.append(
            "The terminal divergence saturates (bounded), so the terminal form-vs-rule "
            "map has finite sensitivity: finite-difference and evolution-strategy gradients "
            "of the TERMINAL form are usable, consistent with the stable finite-difference "
            "Jacobian already measured. The positive lambda also warns that a symmetry-reduced "
            "DEQ would face a near-marginal Jacobian."
        )
    slam = report["stateLambdaPerStep"]
    if slam is not None:
        lines.append(
            f"(state sensitivity, different initial field: lambda/step = {slam:.4f}, "
            f"x{math.exp(slam * horizon):.0f} over {horizon})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--stride", type=int, default=50)
    parser.add_argument("--bases", type=int, default=3)
    parser.add_argument("--directions", type=int, default=3)
    parser.add_argument("--eps-small", type=float, default=0.002)
    parser.add_argument("--eps-large", type=float, default=0.008)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/lyapunov_diagnostic.json"
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    report = run(
        (root / args.dataset).resolve(),
        (root / args.base).resolve(),
        (root / args.search).resolve(),
        bases=args.bases, directions=args.directions,
        epsilons=(args.eps_small, args.eps_large), stride=args.stride,
        steps=args.steps, seed=args.seed,
    )
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(_verdict(report))
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
