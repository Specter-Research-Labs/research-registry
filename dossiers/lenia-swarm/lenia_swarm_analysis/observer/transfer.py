"""Transfer geometry: what creature b's held-out dynamics cost under creature a's learner.

L[a, b] is a's cross-entropy (bits per sample) on b's held-out stream. Raw L is dominated by
mismatched value marginals (how much near-empty area, how mass spreads over bins), so each learner's
output bias is also refit to the target stream: L_dyn[a, b] keeps a's learned dependence on the
neighbourhood and gives it b's marginal. The refit is convex, one parameter per bin on n_eval
samples, and is applied on the diagonal too, so its small in-sample optimism cancels in
D_dyn[a, b] = L_dyn[a, b] - L_dyn[b, b].

Writes transfer_<observer>.npz (L, L_dyn, campaigns) into the measure directory.

Usage: lenia-swarm-observer transfer --measure <measure dir> --observer <name> --device mps
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .prequential import logits
from .run import MeasureRun

LEARNER_CHUNK = 64
STREAM_CHUNK = 16
REFIT_ITERATIONS = 50


def pair_losses(params: list[torch.Tensor], x: torch.Tensor, target: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Raw and bias-refit bits per sample of G learners on M streams: x [M, N, inputs] -> two [G, M]."""
    groups = params[0].shape[0]
    m, n, d = x.shape
    with torch.no_grad():
        out = logits(params, x.reshape(1, m * n, d).expand(groups, -1, -1)).reshape(groups, m, n, -1)
    labels = target.reshape(1, m, n).expand(groups, -1, -1)

    def ce(bias: torch.Tensor) -> torch.Tensor:
        return F.cross_entropy((out + bias).permute(0, 3, 1, 2), labels, reduction="none").mean(-1)

    bias = torch.zeros(groups, m, 1, out.shape[-1], device=out.device, requires_grad=True)
    opt = torch.optim.LBFGS([bias], max_iter=REFIT_ITERATIONS, line_search_fn="strong_wolfe")

    def closure() -> torch.Tensor:
        opt.zero_grad()
        loss = ce(bias).sum()
        loss.backward()
        return loss

    opt.step(closure)
    with torch.no_grad():
        raw = ce(torch.zeros_like(bias))
        refit = ce(bias)
    return raw / math.log(2), refit / math.log(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lenia-swarm-observer transfer", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--measure", type=Path, required=True)
    parser.add_argument("--observer", required=True)
    parser.add_argument("--device", required=True, choices=["mps", "cuda", "cpu"])
    args = parser.parse_args(argv)

    run = MeasureRun.open(args.measure)
    observer = run.observer(args.observer)
    out_path = args.measure / f"transfer_{observer.name}.npz"
    if out_path.exists():
        raise FileExistsError(out_path)
    eval_x, eval_t = run.held_out()
    params = run.params(observer.name, args.device)
    n = len(run.campaigns)
    raw = np.zeros((n, n), np.float32)
    refit = np.zeros((n, n), np.float32)
    for b0 in range(0, n, STREAM_CHUNK):
        b = slice(b0, min(n, b0 + STREAM_CHUNK))
        x = observer.inputs(torch.from_numpy(np.array(eval_x[b])).to(args.device),
                            run.config.mass_edges[0])
        t = torch.from_numpy(np.array(eval_t[b])).to(args.device)
        for a0 in range(0, n, LEARNER_CHUNK):
            a = slice(a0, min(n, a0 + LEARNER_CHUNK))
            r, f = pair_losses([p[a] for p in params], x, t)
            raw[a, b], refit[a, b] = r.cpu().numpy(), f.cpu().numpy()
        print(f"transfer {b.stop}/{n}", flush=True)
    np.savez(out_path, L=raw, L_dyn=refit, campaigns=np.array(run.campaigns))
    return 0
