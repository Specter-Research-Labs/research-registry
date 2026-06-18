"""Stage 2: the anatomical compiler itself, a conditional invertible neural network
that inverts phenotype to genotype.

The forward map collapses a roughly 26-dimensional genotype manifold onto a
6-dimensional phenotype manifold, so the inverse of a phenotype is a fat
(~20-dimensional) fiber, not a point. A cINN models p(genotype | phenotype): it
learns a bijection between the genotype and a latent of equal dimension, made to be
standard normal and conditioned on the phenotype descriptor, so fixing the
descriptor and sampling the latent draws from the whole fiber. This is the
data-efficient choice for a small genotype and a few-thousand-sample training set,
and unlike a point regressor it cannot average distinct fiber points into an
invalid mean.

Training and sampling are pure torch/FrEIA. Validation is real: sampled genotypes
are pushed back through the forward-simulation harness and checked for stability,
descriptor reproduction, and fiber spread, so a sample is only trusted if it
actually re-simulates to the requested phenotype.

Requires the optional `inverse` extra (torch, FrEIA).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from FrEIA.framework import SequenceINN
from FrEIA.modules import AllInOneBlock

from lenia_swarm_analysis.anatomical_compiler._codec import (
    PHENOTYPE_FIELDS,
    GenotypeCodec,
    Standardizer,
    clamp_params,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator


def _build_cinn(genotype_dim: int, cond_dim: int, *, blocks: int, hidden: int) -> SequenceINN:
    def subnet(channels_in: int, channels_out: int) -> nn.Module:
        final = nn.Linear(hidden, channels_out)
        nn.init.zeros_(final.weight)
        nn.init.zeros_(final.bias)
        return nn.Sequential(
            nn.Linear(channels_in, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            final,
        )

    inn = SequenceINN(genotype_dim)
    for _ in range(blocks):
        inn.append(
            AllInOneBlock,
            cond=0,
            cond_shape=(cond_dim,),
            subnet_constructor=subnet,
            permute_soft=True,
        )
    return inn


def _nll(inn: SequenceINN, x: torch.Tensor, c: torch.Tensor) -> torch.Tensor:
    z, log_jac = inn(x, c=[c])
    return 0.5 * z.pow(2).sum(dim=1).mean() - log_jac.mean()


def train(
    inn: SequenceINN,
    genotype: torch.Tensor,
    condition: torch.Tensor,
    val_genotype: torch.Tensor,
    val_condition: torch.Tensor,
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    noise_std: float,
    patience: int,
    device: torch.device,
) -> dict[str, Any]:
    """Train by maximum likelihood with Gaussian noise augmentation, which keeps
    the flow from putting unbounded density on the lower-dimensional genotype
    manifold (the cause of the train-likelihood-up, test-likelihood-blows-up
    failure), plus weight decay and early stopping on a held-out split.
    """
    optimizer = torch.optim.Adam(
        inn.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    count = genotype.shape[0]
    generator = torch.Generator(device="cpu").manual_seed(0)
    val_x = val_genotype.to(device)
    val_c = val_condition.to(device)
    history: list[float] = []
    best_val = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    since_best = 0
    for _ in range(epochs):
        inn.train()
        permutation = torch.randperm(count, generator=generator)
        for start in range(0, count, batch_size):
            index = permutation[start : start + batch_size]
            x = genotype[index].to(device)
            x = x + noise_std * torch.randn_like(x)
            c = condition[index].to(device)
            loss = _nll(inn, x, c)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(inn.parameters(), 10.0)
            optimizer.step()
        inn.eval()
        with torch.no_grad():
            val_nll = _nll(inn, val_x + noise_std * torch.randn_like(val_x), val_c).item()
        history.append(val_nll)
        if val_nll < best_val:
            best_val = val_nll
            best_state = {k: v.detach().clone() for k, v in inn.state_dict().items()}
            since_best = 0
        else:
            since_best += 1
            if since_best >= patience:
                break
    if best_state is not None:
        inn.load_state_dict(best_state)
    return {"valHistory": history, "bestValNll": best_val}


def sample(
    inn: SequenceINN,
    condition_row: np.ndarray,
    cond_std: Standardizer,
    geno_std: Standardizer,
    *,
    count: int,
    device: torch.device,
    seed: int,
) -> np.ndarray:
    inn.eval()
    with torch.no_grad():
        c = torch.tensor(
            np.repeat(cond_std.forward(condition_row[None, :]), count, axis=0),
            dtype=torch.float32,
            device=device,
        )
        generator = torch.Generator(device="cpu").manual_seed(seed)
        z = torch.randn(count, geno_std.mean.shape[0], generator=generator).to(device)
        x, _ = inn(z, c=[c], rev=True)
        standardized = x.cpu().numpy()
    return geno_std.inverse(standardized)


def save_checkpoint(
    path: Path, inn: SequenceINN, geno_std: Standardizer, cond_std: Standardizer,
    *, genotype_dim: int, cond_dim: int, blocks: int, hidden: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": {k: v.cpu() for k, v in inn.state_dict().items()},
            "geno_mean": geno_std.mean, "geno_std": geno_std.std,
            "cond_mean": cond_std.mean, "cond_std": cond_std.std,
            "genotype_dim": genotype_dim, "cond_dim": cond_dim,
            "blocks": blocks, "hidden": hidden,
            "phenotype_fields": list(PHENOTYPE_FIELDS),
        },
        path,
    )


def load_checkpoint(
    path: Path, device: torch.device
) -> tuple[SequenceINN, Standardizer, Standardizer]:
    bundle = torch.load(path, map_location=device, weights_only=False)
    inn = _build_cinn(
        bundle["genotype_dim"], bundle["cond_dim"],
        blocks=bundle["blocks"], hidden=bundle["hidden"],
    )
    inn.load_state_dict(bundle["state_dict"])
    inn.to(device)
    geno_std = Standardizer(mean=bundle["geno_mean"], std=bundle["geno_std"])
    cond_std = Standardizer(mean=bundle["cond_mean"], std=bundle["cond_std"])
    return inn, geno_std, cond_std


def _resim_validate(
    inn: SequenceINN,
    codec: GenotypeCodec,
    geno_std: Standardizer,
    cond_std: Standardizer,
    targets: np.ndarray,
    train_phenotype: np.ndarray,
    train_genotype: np.ndarray,
    *,
    simulator: ForwardSimulator,
    ranges: dict[str, list[float]],
    samples_per_target: int,
    device: torch.device,
) -> dict[str, Any]:
    cond_std_phenotype = cond_std.forward(train_phenotype)
    per_target: list[dict[str, Any]] = []
    for target_index in range(targets.shape[0]):
        target = targets[target_index]
        genotypes = sample(
            inn, target, cond_std, geno_std,
            count=samples_per_target, device=device, seed=target_index,
        )
        target_std = cond_std.forward(target[None, :])[0]
        resim_errors: list[float] = []
        stable = 0
        clamp_total = 0
        for row in genotypes:
            params, clamped = clamp_params(codec.unflatten(row), ranges)
            clamp_total += clamped
            phenotype = simulator.evaluate(params)
            if not phenotype.get("is_stable"):
                continue
            stable += 1
            values = np.array(
                [float(phenotype[f]) if phenotype.get(f) is not None else np.nan
                 for f in PHENOTYPE_FIELDS]
            )
            if np.isnan(values).any():
                continue
            resim_std = cond_std.forward(values[None, :])[0]
            resim_errors.append(float(np.linalg.norm(resim_std - target_std)))

        neighbor = np.argsort(
            np.linalg.norm(cond_std_phenotype - target_std[None, :], axis=1)
        )[:samples_per_target]
        empirical_spread = float(
            np.mean(np.std(geno_std.forward(train_genotype[neighbor]), axis=0))
        )
        sampled_spread = float(np.mean(np.std(geno_std.forward(genotypes), axis=0)))

        empirical_errors: list[float] = []
        for neighbor_index in neighbor:
            params, _ = clamp_params(codec.unflatten(train_genotype[neighbor_index]), ranges)
            phenotype = simulator.evaluate(params)
            values = np.array(
                [float(phenotype[f]) if phenotype.get(f) is not None else np.nan
                 for f in PHENOTYPE_FIELDS]
            )
            if not phenotype.get("is_stable") or np.isnan(values).any():
                continue
            resim_std = cond_std.forward(values[None, :])[0]
            empirical_errors.append(float(np.linalg.norm(resim_std - target_std)))
        per_target.append(
            {
                "stableFraction": stable / samples_per_target,
                "resimDescriptorError": (
                    float(np.mean(resim_errors)) if resim_errors else None
                ),
                "sampledFiberSpread": sampled_spread,
                "empiricalFiberSpread": empirical_spread,
                "empiricalResimError": (
                    float(np.mean(empirical_errors)) if empirical_errors else None
                ),
                "clampsPerSample": clamp_total / samples_per_target,
            }
        )

    def _mean(key: str) -> float | None:
        values = [t[key] for t in per_target if t[key] is not None]
        return float(np.mean(values)) if values else None

    return {
        "targets": int(targets.shape[0]),
        "samplesPerTarget": samples_per_target,
        "meanStableFraction": _mean("stableFraction"),
        "meanResimDescriptorError": _mean("resimDescriptorError"),
        "meanSampledFiberSpread": _mean("sampledFiberSpread"),
        "meanEmpiricalFiberSpread": _mean("empiricalFiberSpread"),
        "meanEmpiricalResimError": _mean("empiricalResimError"),
        "meanClampsPerSample": _mean("clampsPerSample"),
        "perTarget": per_target,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--output", default="outputs/anatomical-compiler/stage2_cinn.json")
    parser.add_argument("--checkpoint", default="outputs/anatomical-compiler/cinn.pt")
    parser.add_argument("--blocks", type=int, default=8)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--noise-std", type=float, default=0.08)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--test-size", type=int, default=400)
    parser.add_argument("--val-size", type=int, default=400)
    parser.add_argument("--resim-targets", type=int, default=6)
    parser.add_argument("--resim-samples", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    torch.manual_seed(args.seed)
    root = Path.cwd()
    dataset_path = (root / args.dataset).resolve()
    codec, genotype, phenotype = load_dataset(dataset_path)

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(genotype.shape[0])
    test_index = order[: args.test_size]
    val_index = order[args.test_size : args.test_size + args.val_size]
    train_index = order[args.test_size + args.val_size :]
    train_geno, test_geno = genotype[train_index], genotype[test_index]
    train_phen, test_phen = phenotype[train_index], phenotype[test_index]
    val_geno, val_phen = genotype[val_index], phenotype[val_index]

    geno_std = Standardizer.fit(train_geno)
    cond_std = Standardizer.fit(train_phen)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    inn = _build_cinn(codec.dim, len(PHENOTYPE_FIELDS), blocks=args.blocks, hidden=args.hidden)
    inn.to(device)
    x = torch.tensor(geno_std.forward(train_geno), dtype=torch.float32)
    c = torch.tensor(cond_std.forward(train_phen), dtype=torch.float32)
    val_x = torch.tensor(geno_std.forward(val_geno), dtype=torch.float32)
    val_c = torch.tensor(cond_std.forward(val_phen), dtype=torch.float32)
    training = train(
        inn, x, c, val_x, val_c,
        epochs=args.epochs, batch_size=args.batch_size,
        learning_rate=args.learning_rate, weight_decay=args.weight_decay,
        noise_std=args.noise_std, patience=args.patience, device=device,
    )

    with torch.no_grad():
        xt = torch.tensor(geno_std.forward(test_geno), dtype=torch.float32, device=device)
        ct = torch.tensor(cond_std.forward(test_phen), dtype=torch.float32, device=device)
        noise = args.noise_std * torch.randn_like(xt)
        test_nll = float(_nll(inn, xt + noise, ct))

    base_config = json.loads((root / args.base).read_text(encoding="utf-8"))
    ranges = base_config["params"]["ranges"]
    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, init_seed=0,
    )
    validation = _resim_validate(
        inn, codec, geno_std, cond_std,
        test_phen[: args.resim_targets], train_phen, train_geno,
        simulator=simulator, ranges=ranges,
        samples_per_target=args.resim_samples, device=device,
    )

    report = {
        "dataset": str(dataset_path),
        "genotypeDim": codec.dim,
        "conditionDim": len(PHENOTYPE_FIELDS),
        "trainSize": int(train_geno.shape[0]),
        "testSize": int(test_geno.shape[0]),
        "epochsRun": len(training["valHistory"]),
        "bestValNll": training["bestValNll"],
        "testNll": test_nll,
        "validation": validation,
    }
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    checkpoint_path = (root / args.checkpoint).resolve()
    save_checkpoint(
        checkpoint_path, inn, geno_std, cond_std,
        genotype_dim=codec.dim, cond_dim=len(PHENOTYPE_FIELDS),
        blocks=args.blocks, hidden=args.hidden,
    )
    print(f"saved checkpoint {checkpoint_path}")

    print(f"genotype_dim={codec.dim} condition_dim={len(PHENOTYPE_FIELDS)} "
          f"train={train_geno.shape[0]} test={test_geno.shape[0]}")
    print(f"epochs={len(training['valHistory'])} best val NLL={training['bestValNll']:.3f}  "
          f"test NLL={test_nll:.3f}")
    v = validation
    print(f"re-sim validation ({v['targets']} targets x {v['samplesPerTarget']} samples):")
    print(f"  mean stable fraction      = {v['meanStableFraction']}")
    print(f"  cINN re-sim descr. error  = {v['meanResimDescriptorError']}")
    print(f"  empirical floor (best)    = {v['meanEmpiricalResimError']}")
    print(f"  sampled fiber spread      = {v['meanSampledFiberSpread']}")
    print(f"  empirical fiber spread    = {v['meanEmpiricalFiberSpread']}")
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
