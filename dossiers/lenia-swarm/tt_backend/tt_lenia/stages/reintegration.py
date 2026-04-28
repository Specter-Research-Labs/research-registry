"""Stage 6: Reintegration — gather-based bilinear splatting.

This is the most compute-intensive stage and the primary candidate for
TT-Lang kernels when TTNN dispatch overhead or DRAM round trips are too high.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os

import numpy as np

_SHIFT_BATCH_TARGET_BYTES = 192 << 20
_SHIFT_BATCH_TEMP_TENSORS = 6
_SHIFT_BATCH_MAX = 16
_SHIFT_WORKER_MAX = 8


def build_pos_grid(sx: int, sy: int) -> np.ndarray:
    """Build position grid: [1, sx, sy, 2, 1] with (y+0.5, x+0.5)."""
    coords_x = np.arange(sx, dtype=np.float32)
    coords_y = np.arange(sy, dtype=np.float32)
    X, Y = np.meshgrid(coords_x, coords_y, indexing="ij")
    pos = np.stack([Y, X], axis=-1) + 0.5
    return pos[np.newaxis, :, :, :, np.newaxis]


def _choose_shift_batch(X: np.ndarray, total_shifts: int) -> int:
    bytes_per_shift = int(np.prod(X.shape, dtype=np.int64)) * X.dtype.itemsize
    if bytes_per_shift <= 0:
        return 1
    budget = _SHIFT_BATCH_TARGET_BYTES // (_SHIFT_BATCH_TEMP_TENSORS * bytes_per_shift)
    return max(1, min(total_shifts, _SHIFT_BATCH_MAX, int(budget)))


def _choose_shift_workers(num_chunks: int) -> int:
    if num_chunks <= 1:
        return 1
    cpu_count = os.cpu_count() or 1
    return max(1, min(num_chunks, cpu_count, _SHIFT_WORKER_MAX))


def reintegrate(
    X: np.ndarray,
    F: np.ndarray,
    *,
    pos_grid: np.ndarray,
    dt: float,
    dd: int,
    sigma: float,
    use_torus: bool,
    sx: int,
    sy: int,
    shift_batch: int | None = None,
) -> np.ndarray:
    """Mass-conserving advection via reintegration tracking.

    X: [batch, sx, sy, channels]
    F: [batch, sx, sy, 2, channels]
    pos_grid: [1, sx, sy, 2, 1]
    """
    ma = float(dd) - sigma
    clip_max = min(1.0, 2.0 * sigma)
    area_scale = 1.0 / (4.0 * sigma * sigma)
    total_shifts = (2 * dd + 1) ** 2
    batch_size = _choose_shift_batch(X, total_shifts) if shift_batch is None else int(shift_batch)
    if batch_size <= 0:
        raise ValueError(f"shift_batch must be > 0, got {batch_size}")

    # The hot loop is shift-major, so batching shifts keeps the exact gather semantics
    # while replacing 121 Python-level elementwise passes with a small number of large
    # contiguous NumPy kernels.
    dtF = np.clip(dt * F, -ma, ma)
    pos_y = pos_grid[:, :, :, 0, :].astype(np.float32, copy=False)
    pos_x = pos_grid[:, :, :, 1, :].astype(np.float32, copy=False)
    mu_y = pos_y + dtF[:, :, :, 0, :]
    mu_x = pos_x + dtF[:, :, :, 1, :]

    if not use_torus:
        mu_y = np.clip(mu_y, sigma, sy - sigma)
        mu_x = np.clip(mu_x, sigma, sx - sigma)

    row_base = np.arange(sx, dtype=np.int32)
    col_base = np.arange(sy, dtype=np.int32)
    pos_y_local = pos_y[:, np.newaxis, :, :, :]
    pos_x_local = pos_x[:, np.newaxis, :, :, :]
    shifts = [(dx, dy) for dx in range(-dd, dd + 1) for dy in range(-dd, dd + 1)]

    chunk_plans = []
    for start in range(0, len(shifts), batch_size):
        chunk = shifts[start : start + batch_size]
        dxs = np.array([dx for dx, _ in chunk], dtype=np.int32)
        dys = np.array([dy for _, dy in chunk], dtype=np.int32)
        rows = (row_base[None, :] + dxs[:, None]) % sx
        cols = (col_base[None, :] + dys[:, None]) % sy
        chunk_plans.append((rows[:, :, None], cols[:, None, :]))

    def evaluate_chunk(chunk_plan: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        row_idx, col_idx = chunk_plan
        Xr = X[:, row_idx, col_idx, :]
        mu_y_r = mu_y[:, row_idx, col_idx, :]
        mu_x_r = mu_x[:, row_idx, col_idx, :]

        dy_abs = np.abs(pos_y_local - mu_y_r)
        dx_abs = np.abs(pos_x_local - mu_x_r)
        if use_torus:
            dy_abs = np.minimum(dy_abs, sy - dy_abs)
            dx_abs = np.minimum(dx_abs, sx - dx_abs)

        sz_y = np.clip(0.5 - dy_abs + sigma, 0.0, clip_max)
        sz_x = np.clip(0.5 - dx_abs + sigma, 0.0, clip_max)
        return np.sum(Xr * sz_y * sz_x, axis=1)

    out = np.zeros_like(X)
    worker_count = _choose_shift_workers(len(chunk_plans))
    if worker_count == 1:
        for chunk_plan in chunk_plans:
            out += evaluate_chunk(chunk_plan)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for partial in executor.map(evaluate_chunk, chunk_plans):
                out += partial

    return (out * area_scale).astype(np.float32, copy=False)
