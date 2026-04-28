from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TW = 32
MAX_ROW_ELEMS = 128


@dataclass(frozen=True)
class CompactSpatialKernel:
    source_channel: int
    row_offset: int
    col_offset: int
    weights: np.ndarray


def spatial_kernels_from_frequency(fK: np.ndarray) -> np.ndarray:
    if fK.ndim != 4 or fK.shape[0] != 1:
        raise ValueError(f"Expected spectral kernels with shape [1, sx, sy, nb_k], got {fK.shape}")
    sx, sy = fK.shape[1], fK.shape[2]
    spatial = np.fft.ifft2(fK[0], axes=(0, 1)).real.astype(np.float32, copy=False)
    return np.roll(np.roll(spatial, sx // 2, axis=0), sy // 2, axis=1).astype(np.float32, copy=False)


def compact_spatial_kernels(
    fK: np.ndarray,
    c0_idxs: np.ndarray,
    *,
    threshold: float = 1.0e-6,
) -> tuple[CompactSpatialKernel, ...]:
    spatial = spatial_kernels_from_frequency(fK)
    center_row = spatial.shape[0] // 2
    center_col = spatial.shape[1] // 2
    compact: list[CompactSpatialKernel] = []
    for kernel_index in range(spatial.shape[2]):
        kernel = spatial[:, :, kernel_index]
        support = np.argwhere(np.abs(kernel) > threshold)
        if support.size == 0:
            support = np.array([[center_row, center_col]], dtype=np.int64)
        row_min, col_min = support.min(axis=0)
        row_max, col_max = support.max(axis=0)
        weights = kernel[row_min : row_max + 1, col_min : col_max + 1].astype(np.float32, copy=True)
        compact.append(
            CompactSpatialKernel(
                source_channel=int(c0_idxs[kernel_index]),
                row_offset=int(row_min - center_row),
                col_offset=int(col_min - center_col),
                weights=weights,
            )
        )
    return tuple(compact)


def convolve_compact_spatial_numpy(
    mass: np.ndarray,
    kernels: tuple[CompactSpatialKernel, ...],
) -> np.ndarray:
    if mass.ndim != 4:
        raise ValueError(f"Expected mass with shape [batch, sx, sy, channels], got {mass.shape}")
    batch, sx, sy, _ = mass.shape
    out = np.zeros((batch, sx, sy, len(kernels)), dtype=np.float32)
    for kernel_index, kernel in enumerate(kernels):
        weights = kernel.weights
        height, width = weights.shape
        for batch_index in range(batch):
            plane = mass[batch_index, :, :, kernel.source_channel]
            for row in range(height):
                row_shift = kernel.row_offset + row
                rolled_row = np.roll(plane, -row_shift, axis=0)
                for col in range(width):
                    col_shift = kernel.col_offset + col
                    out[batch_index, :, :, kernel_index] += (
                        weights[row, col] * np.roll(rolled_row, -col_shift, axis=1)
                    )
    return out
