"""TT-Lang probes for compact Lenia spatial kernels.

This module intentionally starts with whole-tile 1x1 shifts. It validates the
packed plane layout, source-channel routing, toroidal tile indexing, and scalar
weights without pretending to solve sub-tile Lenia convolution yet.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttlang.shape_bridge import (
    PlaneMatrixShape,
    lenia_state_to_plane_matrix,
    plane_matrix_to_lenia_state,
    require_tiled_matrix_shape,
)

try:
    import ttl
    import ttnn
except ImportError as exc:
    raise SystemExit(
        "ttlang/compact_spatial.py requires a TT-Lang environment with importable ttl and ttnn."
    ) from exc


TILE_SIZE = 32


@dataclass(frozen=True)
class TileShift1x1Kernel:
    source_channel: int
    row_shift_tiles: int
    col_shift_tiles: int
    weight: float


def tile_shift_1x1_weight_matrix(kernels: tuple[TileShift1x1Kernel, ...]) -> np.ndarray:
    if not kernels:
        raise ValueError("Expected at least one tile-shift kernel.")
    values = np.asarray([kernel.weight for kernel in kernels], dtype=np.float32)
    matrix = np.empty((len(kernels) * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = value
    return matrix


def tile_shift_1x1_reference(
    state: np.ndarray,
    kernels: tuple[TileShift1x1Kernel, ...],
) -> np.ndarray:
    if state.ndim != 4:
        raise ValueError(f"Expected Lenia state [batch, sx, sy, channels], got {state.shape}.")
    _, sx, sy, channels = state.shape
    out = np.zeros((*state.shape[:3], len(kernels)), dtype=np.float32)
    for kernel_index, kernel in enumerate(kernels):
        if kernel.source_channel < 0 or kernel.source_channel >= channels:
            raise ValueError(f"source_channel={kernel.source_channel} outside 0..{channels - 1}")
        row_shift = kernel.row_shift_tiles * TILE_SIZE
        col_shift = kernel.col_shift_tiles * TILE_SIZE
        plane = state[..., kernel.source_channel]
        shifted = np.roll(np.roll(plane, -row_shift, axis=1), -col_shift, axis=2)
        out[..., kernel_index] = shifted * np.float32(kernel.weight)
    return out


def kernels_from_tile_shifts(
    *,
    source_channels: tuple[int, ...],
    row_shift_tiles: tuple[int, ...],
    col_shift_tiles: tuple[int, ...],
    weights: tuple[float, ...],
) -> tuple[TileShift1x1Kernel, ...]:
    lengths = {len(source_channels), len(row_shift_tiles), len(col_shift_tiles), len(weights)}
    if len(lengths) != 1:
        raise ValueError(
            "source_channels, row_shift_tiles, col_shift_tiles, and weights must have equal lengths."
        )
    return tuple(
        TileShift1x1Kernel(
            source_channel=int(source_channel),
            row_shift_tiles=int(row_shift),
            col_shift_tiles=int(col_shift),
            weight=float(weight),
        )
        for source_channel, row_shift, col_shift, weight in zip(
            source_channels,
            row_shift_tiles,
            col_shift_tiles,
            weights,
            strict=True,
        )
    )


def make_tile_shift_1x1_compact(
    kernels: tuple[TileShift1x1Kernel, ...],
    *,
    channels: int,
):
    if channels <= 0:
        raise ValueError(f"Expected channels > 0, got {channels}.")
    if not kernels:
        raise ValueError("Expected at least one tile-shift kernel.")
    if len(kernels) > 4:
        raise ValueError("The tile-shift TT-Lang scaffold currently supports up to 4 kernels.")
    for kernel in kernels:
        if kernel.source_channel < 0 or kernel.source_channel >= channels:
            raise ValueError(f"source_channel={kernel.source_channel} outside 0..{channels - 1}")

    num_kernels = len(kernels)
    # TT-Lang thread closures currently capture scalar constants, not tuples.
    # Keep each kernel field as an explicit compile-time scalar.
    source_channel0 = int(kernels[0].source_channel)
    row_shift0 = int(kernels[0].row_shift_tiles)
    col_shift0 = int(kernels[0].col_shift_tiles)
    row_add0 = row_shift0 if row_shift0 > 0 else 0
    row_back0 = -row_shift0 if row_shift0 < 0 else 0
    row_wrap0 = 1 if row_shift0 < 0 else 0
    col_add0 = col_shift0 if col_shift0 > 0 else 0
    col_back0 = -col_shift0 if col_shift0 < 0 else 0
    col_wrap0 = 1 if col_shift0 < 0 else 0
    source_channel1 = int(kernels[1].source_channel) if num_kernels > 1 else 0
    row_shift1 = int(kernels[1].row_shift_tiles) if num_kernels > 1 else 0
    col_shift1 = int(kernels[1].col_shift_tiles) if num_kernels > 1 else 0
    row_add1 = row_shift1 if row_shift1 > 0 else 0
    row_back1 = -row_shift1 if row_shift1 < 0 else 0
    row_wrap1 = 1 if row_shift1 < 0 else 0
    col_add1 = col_shift1 if col_shift1 > 0 else 0
    col_back1 = -col_shift1 if col_shift1 < 0 else 0
    col_wrap1 = 1 if col_shift1 < 0 else 0
    source_channel2 = int(kernels[2].source_channel) if num_kernels > 2 else 0
    row_shift2 = int(kernels[2].row_shift_tiles) if num_kernels > 2 else 0
    col_shift2 = int(kernels[2].col_shift_tiles) if num_kernels > 2 else 0
    row_add2 = row_shift2 if row_shift2 > 0 else 0
    row_back2 = -row_shift2 if row_shift2 < 0 else 0
    row_wrap2 = 1 if row_shift2 < 0 else 0
    col_add2 = col_shift2 if col_shift2 > 0 else 0
    col_back2 = -col_shift2 if col_shift2 < 0 else 0
    col_wrap2 = 1 if col_shift2 < 0 else 0
    source_channel3 = int(kernels[3].source_channel) if num_kernels > 3 else 0
    row_shift3 = int(kernels[3].row_shift_tiles) if num_kernels > 3 else 0
    col_shift3 = int(kernels[3].col_shift_tiles) if num_kernels > 3 else 0
    row_add3 = row_shift3 if row_shift3 > 0 else 0
    row_back3 = -row_shift3 if row_shift3 < 0 else 0
    row_wrap3 = 1 if row_shift3 < 0 else 0
    col_add3 = col_shift3 if col_shift3 > 0 else 0
    col_back3 = -col_shift3 if col_shift3 < 0 else 0
    col_wrap3 = 1 if col_shift3 < 0 else 0

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def compact_tile_shift_1x1(
        mass: ttnn.Tensor,
        weights: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        batch = mass.shape[0] // mass.shape[1] // channels
        rows = batch * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(weights, shape=(1, 1), block_count=2)
        out_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            for _ in range(num_kernels):
                                with mass_dfb.wait() as mass_blk, weight_dfb.wait() as weight_blk:
                                    with out_dfb.reserve() as out_blk:
                                        out_blk.store(mass_blk * weight_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    batch_index = row // sx_tiles
                    out_spatial_row = row - batch_index * sx_tiles
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_plane = batch_index * channels + source_channel0
                            source_tile_row = source_plane * sx_tiles + source_row
                            with (
                                mass_dfb.reserve() as mass_blk,
                                weight_dfb.reserve() as weight_blk,
                            ):
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_weight = ttl.copy(weights[0, 0], weight_blk)
                                tx_mass.wait()
                                tx_weight.wait()
                            if num_kernels > 1:
                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_plane = batch_index * channels + source_channel1
                                source_tile_row = source_plane * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    weight_dfb.reserve() as weight_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_weight = ttl.copy(weights[1, 0], weight_blk)
                                    tx_mass.wait()
                                    tx_weight.wait()
                            if num_kernels > 2:
                                source_row = (out_spatial_row + row_add2 + row_wrap2 * sx_tiles - row_back2) % sx_tiles
                                source_col = (col + col_add2 + col_wrap2 * sy_tiles - col_back2) % sy_tiles
                                source_plane = batch_index * channels + source_channel2
                                source_tile_row = source_plane * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    weight_dfb.reserve() as weight_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_weight = ttl.copy(weights[2, 0], weight_blk)
                                    tx_mass.wait()
                                    tx_weight.wait()
                            if num_kernels > 3:
                                source_row = (out_spatial_row + row_add3 + row_wrap3 * sx_tiles - row_back3) % sx_tiles
                                source_col = (col + col_add3 + col_wrap3 * sy_tiles - col_back3) % sy_tiles
                                source_plane = batch_index * channels + source_channel3
                                source_tile_row = source_plane * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    weight_dfb.reserve() as weight_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_weight = ttl.copy(weights[3, 0], weight_blk)
                                    tx_mass.wait()
                                    tx_weight.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    batch_index = row // sx_tiles
                    out_spatial_row = row - batch_index * sx_tiles
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            for kernel_index in range(num_kernels):
                                out_plane = batch_index * num_kernels + kernel_index
                                out_tile_row = out_plane * sx_tiles + out_spatial_row
                                with out_dfb.wait() as out_blk:
                                    tx = ttl.copy(out_blk, out[out_tile_row, col])
                                    tx.wait()

    return compact_tile_shift_1x1


def _to_device_matrix(matrix: np.ndarray, *, device, dtype):
    return ttnn.from_torch(
        torch.from_numpy(matrix),
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
        device=device,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
    )


def _make_demo_state(*, sx: int, sy: int, channels: int) -> np.ndarray:
    rng = np.random.default_rng(19)
    rows = np.arange(sx, dtype=np.float32).reshape(1, sx, 1)
    cols = np.arange(sy, dtype=np.float32).reshape(1, 1, sy)
    state = np.empty((1, sx, sy, channels), dtype=np.float32)
    for channel in range(channels):
        noise = rng.uniform(-0.01, 0.01, size=(1, sx, sy)).astype(np.float32)
        state[..., channel] = 0.01 * rows + 0.001 * cols + 0.25 * channel + noise
    return state


def run_smoke(
    *,
    sx: int,
    sy: int,
    channels: int,
    device_id: int,
    dtype_name: str,
    warmup: int,
    runs: int,
) -> None:
    if sx != sy:
        raise ValueError(f"compact_tile_shift_1x1 currently expects square grids, got {sx}x{sy}.")
    if sx % TILE_SIZE != 0 or sy % TILE_SIZE != 0:
        raise ValueError(f"Expected dimensions divisible by {TILE_SIZE}, got {sx}x{sy}.")
    if channels < 2:
        raise ValueError("The smoke uses two source channels; pass --channels 2 or larger.")
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True

    kernels = kernels_from_tile_shifts(
        source_channels=(0, 1, 0),
        row_shift_tiles=(0, 1, -1),
        col_shift_tiles=(0, -1, 1),
        weights=(1.0, 0.5, -0.25),
    )
    state = _make_demo_state(sx=sx, sy=sy, channels=channels)
    expected = tile_shift_1x1_reference(state, kernels)
    mass_matrix, _ = lenia_state_to_plane_matrix(state)
    expected_shape = PlaneMatrixShape(batch=1, sx=sx, sy=sy, channels=len(kernels))
    out_matrix = np.zeros(expected_shape.matrix_shape, dtype=np.float32)
    weights_matrix = tile_shift_1x1_weight_matrix(kernels)
    require_tiled_matrix_shape(mass_matrix, row_block_tiles=1, col_block_tiles=1, tile_size=TILE_SIZE)
    require_tiled_matrix_shape(out_matrix, row_block_tiles=1, col_block_tiles=1, tile_size=TILE_SIZE)

    dtype = ttnn.float32 if dtype_name == "float32" else ttnn.bfloat16
    device = ttnn.open_device(device_id=device_id)
    try:
        mass_tt = _to_device_matrix(mass_matrix, device=device, dtype=dtype)
        weights_tt = _to_device_matrix(weights_matrix, device=device, dtype=dtype)
        out_tt = _to_device_matrix(out_matrix, device=device, dtype=dtype)
        kernel = make_tile_shift_1x1_compact(kernels, channels=channels)
        for _ in range(warmup):
            kernel(mass_tt, weights_tt, out_tt)
            ttnn.synchronize_device(device)
        started_at = time.perf_counter()
        for _ in range(runs):
            kernel(mass_tt, weights_tt, out_tt)
        ttnn.synchronize_device(device)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
        actual_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
        actual = plane_matrix_to_lenia_state(actual_matrix, expected_shape)
        max_abs = float(np.max(np.abs(actual - expected)))
        mean_abs = float(np.mean(np.abs(actual - expected)))
        tolerance = 1.0e-5 if dtype_name == "float32" else 2.5e-2
        print(
            f"tt-lang compact_tile_shift_1x1 smoke: state={state.shape} kernels={len(kernels)} "
            f"dtype={dtype_name} warmup={warmup} runs={runs} mean_elapsed={mean_elapsed_ms:.3f}ms "
            f"max_abs={max_abs:.6g} mean_abs={mean_abs:.6g}"
        )
        if max_abs > tolerance:
            raise SystemExit(f"compact_tile_shift_1x1 failed: max_abs={max_abs} > {tolerance}")
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TT-Lang tile-shift compact convolution scaffold.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--dtype", choices=["float32", "bfloat16"], default="bfloat16")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.tt_visible_devices is not None:
        os.environ["TT_VISIBLE_DEVICES"] = args.tt_visible_devices
    run_smoke(
        sx=args.sx,
        sy=args.sy,
        channels=args.channels,
        device_id=args.device_id,
        dtype_name=args.dtype,
        warmup=args.warmup,
        runs=args.runs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
