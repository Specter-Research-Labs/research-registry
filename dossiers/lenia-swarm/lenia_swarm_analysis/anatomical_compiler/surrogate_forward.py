"""A differentiable surrogate of the forward map, for gradient-based refinement.

Autodiff through the real 1200-step Flow-Lenia is impractical: gradients vanish or
explode well before the attractor forms (the sensorimotor-Lenia work hit the same
wall at about 50 steps), so a faithful differentiable simulator cannot reach a
terminal-shape target. The pragmatic substitute is to learn the forward map,
genotype to shape descriptor, as a small differentiable network and use its
gradients. This is exact-derivative inverse design against a smooth proxy, with
every proposed genotype still verified by a real simulation.

The surrogate delivers two things the finite-difference work could only approximate:
a fast gradient refiner (one real simulation per target to verify, instead of the
cross-entropy refiner's hundreds), and an analytic Jacobian, a fourth, smooth
estimate of the fiber dimension to set beside TwoNN, MLE, and finite differences.

Requires the optional `inverse` extra (torch).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from lenia_swarm_analysis.anatomical_compiler.cinn_inverse import (
    PHENOTYPE_FIELDS,
    Standardizer,
    _clamp_params,
    _load,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator


class Surrogate(nn.Module):
    def __init__(self, genotype_dim: int, descriptor_dim: int, hidden: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(genotype_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Linear(hidden, descriptor_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def _train(
    net: Surrogate,
    x: torch.Tensor,
    y: torch.Tensor,
    x_val: torch.Tensor,
    y_val: torch.Tensor,
    *,
    epochs: int,
    batch_size: int,
    device: torch.device,
) -> float:
    optimizer = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    count = x.shape[0]
    generator = torch.Generator(device="cpu").manual_seed(0)
    best = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    since = 0
    for _ in range(epochs):
        net.train()
        permutation = torch.randperm(count, generator=generator)
        for start in range(0, count, batch_size):
            index = permutation[start : start + batch_size]
            optimizer.zero_grad()
            loss = loss_fn(net(x[index].to(device)), y[index].to(device))
            loss.backward()
            optimizer.step()
        net.eval()
        with torch.no_grad():
            val = float(loss_fn(net(x_val.to(device)), y_val.to(device)))
        if val < best:
            best = val
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            since = 0
        else:
            since += 1
            if since >= 20:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    return best


def _r2(net: Surrogate, x: torch.Tensor, y: torch.Tensor, device: torch.device) -> float:
    net.eval()
    with torch.no_grad():
        pred = net(x.to(device)).cpu().numpy()
    truth = y.numpy()
    ss_res = float(np.sum((truth - pred) ** 2))
    ss_tot = float(np.sum((truth - truth.mean(axis=0)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def _jacobian_rank(net: Surrogate, points: torch.Tensor, device: torch.device) -> dict[str, float]:
    net.eval()
    participations: list[float] = []
    thresholds: list[float] = []
    for row in points:
        x = row.to(device).clone().requires_grad_(True)
        jac = torch.autograd.functional.jacobian(lambda v: net(v), x)
        singular = np.linalg.svd(jac.detach().cpu().numpy(), compute_uv=False)
        eigen = singular**2
        positive = eigen[eigen > 1e-18]
        participations.append(
            float(np.sum(positive) ** 2 / np.sum(positive**2)) if positive.size else 0.0
        )
        thresholds.append(int(np.sum(singular > singular.max() * 0.05)))
    return {
        "participationRank": float(np.mean(participations)),
        "thresholdRank": float(np.mean(thresholds)),
    }


def _gradient_refine(
    net: Surrogate,
    target_std: np.ndarray,
    start_std: np.ndarray,
    *,
    device: torch.device,
    steps: int,
    learning_rate: float,
) -> np.ndarray:
    target = torch.tensor(target_std, dtype=torch.float32, device=device)
    x = torch.tensor(start_std, dtype=torch.float32, device=device).clone().requires_grad_(True)
    optimizer = torch.optim.Adam([x], lr=learning_rate)
    for _ in range(steps):
        optimizer.zero_grad()
        prediction = net(x)
        # stay where the surrogate is trustworthy: penalize leaving the data box
        boundary = torch.relu(x.abs() - 3.0).pow(2).mean()
        loss = (prediction - target).pow(2).mean() + 1e-2 * boundary
        loss.backward()
        optimizer.step()
    return x.detach().cpu().numpy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--refine-steps", type=int, default=400)
    parser.add_argument("--refine-lr", type=float, default=0.05)
    parser.add_argument("--targets", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/stage3_surrogate.json"
    )
    args = parser.parse_args(argv)

    torch.manual_seed(args.seed)
    root = Path.cwd()
    codec, genotype, phenotype = _load((root / args.dataset).resolve())
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(genotype.shape[0])
    target_index = order[: args.targets]
    val_index = order[args.targets : args.targets + 400]
    train_index = order[args.targets + 400 :]

    geno_std = Standardizer.fit(genotype[train_index])
    cond_std = Standardizer.fit(phenotype[train_index])
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    net = Surrogate(codec.dim, len(PHENOTYPE_FIELDS), args.hidden).to(device)
    x = torch.tensor(geno_std.forward(genotype[train_index]), dtype=torch.float32)
    y = torch.tensor(cond_std.forward(phenotype[train_index]), dtype=torch.float32)
    x_val = torch.tensor(geno_std.forward(genotype[val_index]), dtype=torch.float32)
    y_val = torch.tensor(cond_std.forward(phenotype[val_index]), dtype=torch.float32)
    _train(net, x, y, x_val, y_val, epochs=args.epochs, batch_size=256, device=device)
    r2 = _r2(net, x_val, y_val, device)
    rank = _jacobian_rank(net, x_val[:64], device)

    ranges = json.loads((root / args.base).read_text(encoding="utf-8"))["params"]["ranges"]
    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, init_seed=0, timeout_seconds=600.0,
    )

    results: list[dict[str, Any]] = []
    for index in target_index:
        target_phenotype = simulator.evaluate(codec.unflatten(genotype[index]), init_seed=0)
        target_values = np.array([float(target_phenotype[f]) for f in PHENOTYPE_FIELDS])
        target_std = cond_std.forward(target_values[None, :])[0]
        start_std = geno_std.forward(
            genotype[train_index[rng.integers(train_index.shape[0])]][None, :]
        )[0]
        refined_std = _gradient_refine(
            net, target_std, start_std,
            device=device, steps=args.refine_steps, learning_rate=args.refine_lr,
        )
        refined_genotype = geno_std.inverse(refined_std[None, :])[0]
        params, _ = _clamp_params(codec.unflatten(refined_genotype), ranges)
        achieved = simulator.evaluate(params, init_seed=0)
        if not achieved.get("is_stable"):
            results.append({"refinedError": None, "stable": False})
            continue
        achieved_values = np.array([float(achieved[f]) for f in PHENOTYPE_FIELDS])
        error = float(np.linalg.norm(cond_std.forward(achieved_values[None, :])[0] - target_std))
        results.append({"refinedError": error, "stable": True})
        print(f"target {int(index)}: refined re-sim error {error:.2f}")

    errors = [r["refinedError"] for r in results if r["refinedError"] is not None]
    report = {
        "surrogateR2": r2,
        "surrogateJacobianRank": rank,
        "phenotypeDim": len(PHENOTYPE_FIELDS),
        "targets": len(results),
        "stableFraction": float(np.mean([1.0 if r["stable"] else 0.0 for r in results])),
        "meanRefinedError": float(np.mean(errors)) if errors else None,
        "realSimsPerTarget": 2,
        "perTarget": results,
    }
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"\nsurrogate fit R2={r2:.3f} (val)")
    print(f"surrogate Jacobian rank: participation {rank['participationRank']:.2f}, "
          f"threshold {rank['thresholdRank']:.1f} (vs phenotype dim {len(PHENOTYPE_FIELDS)})")
    print(f"gradient-refined re-sim error = {report['meanRefinedError']:.2f} "
          f"(stable {report['stableFraction']:.0%}), ~2 real sims/target vs CEM's ~140")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
