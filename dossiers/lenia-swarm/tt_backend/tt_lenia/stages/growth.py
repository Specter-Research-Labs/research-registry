"""Stage 4: Growth function and channel routing — NumPy + TTNN."""
from __future__ import annotations

import numpy as np


def growth_bell(
    UK: np.ndarray, m: np.ndarray, s: np.ndarray, h: np.ndarray
) -> np.ndarray:
    """Gaussian bell growth: G(x) = (2*exp(-0.5*((x-m)/s)^2) - 1) * h.

    UK: [batch, sx, sy, nb_k]
    m, s, h: [nb_k]
    Returns: [batch, sx, sy, nb_k]
    """
    m_b = m.reshape(1, 1, 1, -1)
    s_b = s.reshape(1, 1, 1, -1)
    h_b = h.reshape(1, 1, 1, -1)
    diff = (UK - m_b) / s_b
    bell = np.exp(-0.5 * diff * diff)
    return (2.0 * bell - 1.0) * h_b


def growth_reduce(G: np.ndarray, c1_mask: np.ndarray) -> np.ndarray:
    """Route growth to channels: U = G @ c1_mask^T.

    G: [batch, sx, sy, nb_k]
    c1_mask: [channels, nb_k]
    Returns U: [batch, sx, sy, channels]
    """
    return np.einsum("bxyk,ck->bxyc", G, c1_mask)


def compile_channel_routes(c1_mask: np.ndarray) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(np.flatnonzero(c1_mask[channel]).tolist()) for channel in range(c1_mask.shape[0]))


def ttnn_growth_bell(UK, m, s, h):
    """Gaussian bell growth on TTNN device tensors.

    All inputs must be TTNN tensors on device.
    UK: [batch, sx, sy, nb_k] on device
    m, s, h: [1, 1, 1, nb_k] on device (pre-broadcast)
    """
    import ttnn
    diff = ttnn.multiply(ttnn.subtract(UK, m), ttnn.reciprocal(s))
    bell = ttnn.exp(ttnn.multiply(ttnn.multiply(diff, diff), -0.5))
    return ttnn.multiply(ttnn.subtract(ttnn.multiply(bell, 2.0), 1.0), h)


def ttnn_growth_reduce(G, c1_weights):
    """Route per-kernel growth to channels on device.

    G: [batch, sx, sy, nb_k]
    c1_weights: [1, 1, nb_k, channels]
    """
    import ttnn

    return ttnn.matmul(G, c1_weights)


def ttnn_route_channels(G, routes: tuple[tuple[int, ...], ...]):
    import ttnn

    batch, sx, sy, nb_k = (int(dim) for dim in G.shape)
    if nb_k == 0:
        raise ValueError("TTNN channel routing requires at least one kernel channel.")

    zero_template = ttnn.multiply(ttnn.slice(G, (0, 0, 0, 0), (batch, sx, sy, 1)), 0.0)
    outputs = []
    for route in routes:
        if not route:
            outputs.append(zero_template)
            continue
        terms = [
            ttnn.slice(G, (0, 0, 0, kernel_idx), (batch, sx, sy, kernel_idx + 1))
            for kernel_idx in route
        ]
        acc = terms[0]
        for term in terms[1:]:
            next_acc = ttnn.add(acc, term)
            ttnn.deallocate(acc)
            ttnn.deallocate(term)
            acc = next_acc
        outputs.append(acc)
    if len(outputs) == 1:
        return outputs[0]
    return ttnn.concat(outputs, dim=3)
