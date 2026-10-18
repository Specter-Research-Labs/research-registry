"""Prequential coding with independent learners trained in lockstep.

Every learner scores each batch before training on it, so its summed loss is a prequential
codelength for its stream. Following Finzi et al. (2026), the final loss level is the time-bounded
entropy H (bits per sample) and the area of the loss curve above that level is the structural
information the learner absorbed, epiplexity S (bits over the whole stream). Both are properties of
the observer (input, architecture, budget) as much as of the data.

G learners share nothing but the step schedule, so a group of creatures or pairs is measured with one
batched matmul per layer.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import torch
import torch.nn.functional as F

Params = list[torch.Tensor]

# Samples per encode call: amortizes the per-call cost of encoding while keeping a group's encoded
# chunk (and a patch gather's index) far below the per-tensor element limit of MPS.
ENCODE_CHUNK = 4096


def init_params(seeds: list[int], inputs: int, classes: int, hidden: int, device: str) -> Params:
    """Weights and biases for one MLP per seed (hidden == 0 is a linear softmax model), stacked on
    a leading group axis. Each learner is drawn on the CPU from its own seed, so its initial weights
    depend neither on the device nor on which other learners share its group."""
    dims = [inputs, classes] if hidden == 0 else [inputs, hidden, hidden, classes]
    generators = [torch.Generator().manual_seed(seed) for seed in seeds]
    params = []
    for fan_in, fan_out in zip(dims[:-1], dims[1:], strict=True):
        for shape in ((fan_in, fan_out), (1, fan_out)):
            w = torch.stack([torch.rand(shape, generator=g) for g in generators])
            params.append(((w * 2 - 1) / math.sqrt(fan_in)).to(device).requires_grad_())
    return params


def logits(params: Params, x: torch.Tensor) -> torch.Tensor:
    """x: [G, N, inputs] -> [G, N, classes]."""
    for i in range(0, len(params), 2):
        x = torch.baddbmm(params[i + 1], x, params[i])
        if i + 2 < len(params):
            x = F.gelu(x)
    return x


def prequential(
    params: Params, x: torch.Tensor, target: torch.Tensor, *, batch: int, lr: float,
    encode: Callable[[torch.Tensor], torch.Tensor],
) -> np.ndarray:
    """Train `params` in place on the stream x [G, N, ...], target [G, N] (class ids) in order.
    `encode` maps a slice x[:, a:b] to learner inputs [G, b - a, inputs] on the learners' device, so
    the stream can stay compact: encoded whole, a group of long patch streams exceeds the per-tensor
    element limit of MPS.
    Returns the per-step loss curve [G, N // batch] in bits per sample, each step scored before its
    update. Invariant: N is a multiple of batch, so every step codes the same number of samples."""
    groups, n = target.shape
    if n % batch:
        raise ValueError(f"stream length {n} is not a multiple of batch {batch}")
    classes = params[-1].shape[-1]
    # The multi-tensor Adam kernels are several times slower than the per-tensor loop on MPS for
    # these small stacked learners.
    opt = torch.optim.Adam(params, lr=lr, foreach=False)
    chunk = max(batch, ENCODE_CHUNK // batch * batch)
    curve = []
    for c in range(0, n, chunk):
        inputs = encode(x[:, c:c + chunk])
        for s in range(0, inputs.shape[1], batch):
            out = logits(params, inputs[:, s:s + batch])
            loss = F.cross_entropy(
                out.reshape(-1, classes), target[:, c + s:c + s + batch].reshape(-1), reduction="none"
            ).reshape(groups, -1).mean(1)
            curve.append(loss.detach())
            opt.zero_grad()
            loss.sum().backward()
            opt.step()
    return (torch.stack(curve, 1) / math.log(2)).cpu().numpy()


def epiplexity(curve: np.ndarray, *, batch: int, tail: float) -> tuple[np.ndarray, np.ndarray]:
    """(S, H) per learner from a loss curve [G, steps]. H is the mean loss over the last `tail`
    fraction of steps; S sums the excess over H across every coded sample."""
    n_tail = max(1, int(curve.shape[1] * tail))
    h = curve[:, -n_tail:].mean(1)
    s = (curve - h[:, None]).sum(1) * batch
    return s, h

