from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlaneMatrixShape:
    batch: int
    sx: int
    sy: int
    channels: int

    @property
    def matrix_shape(self) -> tuple[int, int]:
        return (self.batch * self.channels * self.sx, self.sy)


def lenia_state_to_plane_matrix(state: np.ndarray) -> tuple[np.ndarray, PlaneMatrixShape]:
    if state.ndim != 4:
        raise ValueError(f"Expected Lenia state [batch, sx, sy, channels], got {state.shape}.")
    batch, sx, sy, channels = (int(value) for value in state.shape)
    if batch <= 0 or sx <= 0 or sy <= 0 or channels <= 0:
        raise ValueError(f"Lenia state dimensions must be non-empty, got {state.shape}.")
    shape = PlaneMatrixShape(batch=batch, sx=sx, sy=sy, channels=channels)
    matrix = (
        state.astype(np.float32, copy=False)
        .transpose(0, 3, 1, 2)
        .reshape(shape.matrix_shape)
        .astype(np.float32, copy=False)
    )
    return np.ascontiguousarray(matrix), shape


def plane_matrix_to_lenia_state(matrix: np.ndarray, shape: PlaneMatrixShape) -> np.ndarray:
    if matrix.shape != shape.matrix_shape:
        raise ValueError(f"Expected plane matrix {shape.matrix_shape}, got {matrix.shape}.")
    return (
        matrix.astype(np.float32, copy=False)
        .reshape(shape.batch, shape.channels, shape.sx, shape.sy)
        .transpose(0, 2, 3, 1)
        .astype(np.float32, copy=False)
    )


def require_tiled_matrix_shape(
    matrix: np.ndarray,
    *,
    row_block_tiles: int,
    col_block_tiles: int,
    tile_size: int = 32,
) -> None:
    row_block = tile_size * row_block_tiles
    col_block = tile_size * col_block_tiles
    if matrix.shape[0] % row_block != 0 or matrix.shape[1] % col_block != 0:
        raise ValueError(
            f"Packed matrix shape {matrix.shape} must be divisible by "
            f"{row_block}x{col_block}."
        )
