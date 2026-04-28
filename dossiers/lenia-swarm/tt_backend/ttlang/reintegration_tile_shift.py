"""TT-Lang scaffold for tile-native Lenia reintegration.

This intentionally models only whole-tile toroidal source shifts. The useful
part is the stage math: read source mass/flow tiles, compute Lenia's clipped
bilinear reintegration weights, and accumulate in L1 before one output write.
Real paper configs still need sub-tile row/column windows for dd=5.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttlang.shape_bridge import (
    lenia_state_to_plane_matrix,
    plane_matrix_to_lenia_state,
    require_tiled_matrix_shape,
)

try:
    import ttl
    import ttnn
except ImportError:
    ttl = None
    ttnn = None


TILE_SIZE = 32
MAX_SHIFTS = 4


@dataclass(frozen=True)
class TileReintegrationShift:
    row_shift_tiles: int
    col_shift_tiles: int
    y_distance: float
    x_distance: float


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit(
            "ttlang/reintegration_tile_shift.py requires a TT-Lang environment "
            "with importable ttl and ttnn."
        )


def tile_reintegration_param_matrix(
    shifts: tuple[TileReintegrationShift, ...],
    *,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    if not shifts:
        raise ValueError("Expected at least one tile reintegration shift.")
    if len(shifts) > MAX_SHIFTS:
        raise ValueError(f"Expected at most {MAX_SHIFTS} shifts, got {len(shifts)}.")
    clip_max = min(1.0, 2.0 * float(sigma))
    area_scale = 1.0 / (4.0 * float(sigma) * float(sigma))
    values = [
        *(shift.y_distance for shift in shifts),
        *(shift.x_distance for shift in shifts),
        float(dt),
        float(max_flow),
        -float(max_flow),
        float(sigma) + 0.5,
        clip_max,
        area_scale,
        0.0,
    ]
    matrix = np.empty((len(values) * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = np.float32(value)
    return matrix


def tile_shift_reintegration_reference(
    mass: np.ndarray,
    flow: np.ndarray,
    shifts: tuple[TileReintegrationShift, ...],
    *,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    if mass.ndim != 4:
        raise ValueError(f"Expected mass [batch, sx, sy, channels], got {mass.shape}.")
    if flow.shape != (*mass.shape[:3], 2, mass.shape[3]):
        raise ValueError(
            f"Expected flow shape [batch, sx, sy, 2, channels] compatible with {mass.shape}, "
            f"got {flow.shape}."
        )
    clip_max = np.float32(min(1.0, 2.0 * float(sigma)))
    sigma_plus_half = np.float32(float(sigma) + 0.5)
    area_scale = np.float32(1.0 / (4.0 * float(sigma) * float(sigma)))
    max_flow32 = np.float32(max_flow)
    out = np.zeros_like(mass, dtype=np.float32)
    flow_y = flow[:, :, :, 0, :]
    flow_x = flow[:, :, :, 1, :]
    for shift in shifts:
        row_shift = shift.row_shift_tiles * TILE_SIZE
        col_shift = shift.col_shift_tiles * TILE_SIZE
        source_mass = np.roll(np.roll(mass, -row_shift, axis=1), -col_shift, axis=2)
        source_flow_y = np.roll(np.roll(flow_y, -row_shift, axis=1), -col_shift, axis=2)
        source_flow_x = np.roll(np.roll(flow_x, -row_shift, axis=1), -col_shift, axis=2)
        adv_y = np.clip(np.float32(dt) * source_flow_y, -max_flow32, max_flow32)
        adv_x = np.clip(np.float32(dt) * source_flow_x, -max_flow32, max_flow32)
        wy = np.clip(sigma_plus_half - np.abs(np.float32(shift.y_distance) + adv_y), 0.0, clip_max)
        wx = np.clip(sigma_plus_half - np.abs(np.float32(shift.x_distance) + adv_x), 0.0, clip_max)
        out += source_mass * wy * wx * area_scale
    return out.astype(np.float32, copy=False)


def smoke_tolerance(dtype_name: str, expected: np.ndarray) -> float:
    max_expected = float(np.max(np.abs(expected))) if expected.size else 0.0
    if dtype_name == "float32":
        return max(3.0e-2, 5.0e-3 * max_expected)
    if dtype_name == "bfloat16":
        return max(5.0e-2, 1.5e-2 * max_expected)
    raise ValueError(f"Unsupported dtype {dtype_name!r}.")


def make_tile_shift_reintegration(
    shifts: tuple[TileReintegrationShift, ...],
    *,
    channels: int,
):
    _require_ttlang()
    if channels <= 0:
        raise ValueError(f"Expected channels > 0, got {channels}.")
    if not shifts:
        raise ValueError("Expected at least one tile reintegration shift.")
    if len(shifts) > MAX_SHIFTS:
        raise ValueError(f"Expected at most {MAX_SHIFTS} shifts, got {len(shifts)}.")

    num_shifts = len(shifts)
    row_shift0 = int(shifts[0].row_shift_tiles)
    col_shift0 = int(shifts[0].col_shift_tiles)
    row_add0 = row_shift0 if row_shift0 > 0 else 0
    row_back0 = -row_shift0 if row_shift0 < 0 else 0
    row_wrap0 = 1 if row_shift0 < 0 else 0
    col_add0 = col_shift0 if col_shift0 > 0 else 0
    col_back0 = -col_shift0 if col_shift0 < 0 else 0
    col_wrap0 = 1 if col_shift0 < 0 else 0
    row_shift1 = int(shifts[1].row_shift_tiles) if num_shifts > 1 else 0
    col_shift1 = int(shifts[1].col_shift_tiles) if num_shifts > 1 else 0
    row_add1 = row_shift1 if row_shift1 > 0 else 0
    row_back1 = -row_shift1 if row_shift1 < 0 else 0
    row_wrap1 = 1 if row_shift1 < 0 else 0
    col_add1 = col_shift1 if col_shift1 > 0 else 0
    col_back1 = -col_shift1 if col_shift1 < 0 else 0
    col_wrap1 = 1 if col_shift1 < 0 else 0
    row_shift2 = int(shifts[2].row_shift_tiles) if num_shifts > 2 else 0
    col_shift2 = int(shifts[2].col_shift_tiles) if num_shifts > 2 else 0
    row_add2 = row_shift2 if row_shift2 > 0 else 0
    row_back2 = -row_shift2 if row_shift2 < 0 else 0
    row_wrap2 = 1 if row_shift2 < 0 else 0
    col_add2 = col_shift2 if col_shift2 > 0 else 0
    col_back2 = -col_shift2 if col_shift2 < 0 else 0
    col_wrap2 = 1 if col_shift2 < 0 else 0
    row_shift3 = int(shifts[3].row_shift_tiles) if num_shifts > 3 else 0
    col_shift3 = int(shifts[3].col_shift_tiles) if num_shifts > 3 else 0
    row_add3 = row_shift3 if row_shift3 > 0 else 0
    row_back3 = -row_shift3 if row_shift3 < 0 else 0
    row_wrap3 = 1 if row_shift3 < 0 else 0
    col_add3 = col_shift3 if col_shift3 > 0 else 0
    col_back3 = -col_shift3 if col_shift3 < 0 else 0
    col_wrap3 = 1 if col_shift3 < 0 else 0

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def tile_shift_reintegration(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        params: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        constants_base = num_shifts * 2
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        wy_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        wx_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        scaled_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with acc_dfb.reserve() as acc_blk:
                                acc_blk.store(ttl.math.fill(acc_blk, 0.0))
                            with (
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                            ):
                                for _ in range(num_shifts):
                                    with (
                                        flow_y_dfb.wait() as flow_y_blk,
                                        flow_x_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                    ):
                                        with wy_dfb.reserve() as wy_blk, wx_dfb.reserve() as wx_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy_blk.store(
                                                ttl.math.min(
                                                    ttl.math.max(raw_y, zero_blk),
                                                    clip_max_blk,
                                                )
                                            )
                                            wx_blk.store(
                                                ttl.math.min(
                                                    ttl.math.max(raw_x, zero_blk),
                                                    clip_max_blk,
                                                )
                                            )
                                    with mass_dfb.wait() as mass_blk, wy_dfb.wait() as wy_blk:
                                        with mass_weight_dfb.reserve() as mass_weight_blk:
                                            mass_weight_blk.store(mass_blk * wy_blk)
                                    with mass_weight_dfb.wait() as mass_weight_blk, wx_dfb.wait() as wx_blk:
                                        with scaled_dfb.reserve() as scaled_blk:
                                            scaled_blk.store(mass_weight_blk * wx_blk * area_scale_blk)
                                    with scaled_dfb.wait() as scaled_blk, acc_dfb.wait() as prev:
                                        with acc_dfb.reserve() as acc_blk:
                                            acc_blk.store(prev + scaled_blk)
                            with acc_dfb.wait() as acc_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(acc_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    out_spatial_row = row - plane_index * sx_tiles
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with (
                                dt_dfb.reserve() as dt_blk,
                                max_flow_dfb.reserve() as max_flow_blk,
                                neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                clip_max_dfb.reserve() as clip_max_blk,
                                area_scale_dfb.reserve() as area_scale_blk,
                                zero_dfb.reserve() as zero_blk,
                            ):
                                tx_dt = ttl.copy(params[constants_base, 0], dt_blk)
                                tx_max = ttl.copy(params[constants_base + 1, 0], max_flow_blk)
                                tx_neg = ttl.copy(params[constants_base + 2, 0], neg_max_flow_blk)
                                tx_sigma = ttl.copy(params[constants_base + 3, 0], sigma_plus_half_blk)
                                tx_clip = ttl.copy(params[constants_base + 4, 0], clip_max_blk)
                                tx_area = ttl.copy(params[constants_base + 5, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[constants_base + 6, 0], zero_blk)
                                tx_dt.wait()
                                tx_max.wait()
                                tx_neg.wait()
                                tx_sigma.wait()
                                tx_clip.wait()
                                tx_area.wait()
                                tx_zero.wait()
                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with (
                                mass_dfb.reserve() as mass_blk,
                                flow_y_dfb.reserve() as flow_y_blk,
                                flow_x_dfb.reserve() as flow_x_blk,
                                shift_y_dfb.reserve() as shift_y_blk,
                                shift_x_dfb.reserve() as shift_x_blk,
                            ):
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_shift_y = ttl.copy(params[0, 0], shift_y_blk)
                                tx_shift_x = ttl.copy(params[num_shifts, 0], shift_x_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()
                                tx_shift_y.wait()
                                tx_shift_x.wait()
                            if num_shifts > 1:
                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    flow_y_dfb.reserve() as flow_y_blk,
                                    flow_x_dfb.reserve() as flow_x_blk,
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_shift_y = ttl.copy(params[1, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[num_shifts + 1, 0], shift_x_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_shift_y.wait()
                                    tx_shift_x.wait()
                            if num_shifts > 2:
                                source_row = (out_spatial_row + row_add2 + row_wrap2 * sx_tiles - row_back2) % sx_tiles
                                source_col = (col + col_add2 + col_wrap2 * sy_tiles - col_back2) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    flow_y_dfb.reserve() as flow_y_blk,
                                    flow_x_dfb.reserve() as flow_x_blk,
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_shift_y = ttl.copy(params[2, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[num_shifts + 2, 0], shift_x_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_shift_y.wait()
                                    tx_shift_x.wait()
                            if num_shifts > 3:
                                source_row = (out_spatial_row + row_add3 + row_wrap3 * sx_tiles - row_back3) % sx_tiles
                                source_col = (col + col_add3 + col_wrap3 * sy_tiles - col_back3) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with (
                                    mass_dfb.reserve() as mass_blk,
                                    flow_y_dfb.reserve() as flow_y_blk,
                                    flow_x_dfb.reserve() as flow_x_blk,
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_shift_y = ttl.copy(params[3, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[num_shifts + 3, 0], shift_x_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_shift_y.wait()
                                    tx_shift_x.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with out_dfb.wait() as out_blk:
                                tx = ttl.copy(out_blk, out[row, col])
                                tx.wait()

    return tile_shift_reintegration


def _to_device_matrix(matrix: np.ndarray, *, device, dtype):
    _require_ttlang()
    import torch

    return ttnn.from_torch(
        torch.from_numpy(matrix),
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
        device=device,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
    )


def _make_demo_inputs(*, sx: int, sy: int, channels: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(23)
    rows = np.arange(sx, dtype=np.float32).reshape(1, sx, 1, 1)
    cols = np.arange(sy, dtype=np.float32).reshape(1, 1, sy, 1)
    channel_offsets = np.arange(channels, dtype=np.float32).reshape(1, 1, 1, channels)
    mass = 0.015 * rows + 0.0015 * cols + 0.2 * channel_offsets
    mass += rng.uniform(-0.005, 0.005, size=(1, sx, sy, channels)).astype(np.float32)
    flow_y = rng.uniform(-0.35, 0.35, size=(1, sx, sy, channels)).astype(np.float32)
    flow_x = rng.uniform(-0.35, 0.35, size=(1, sx, sy, channels)).astype(np.float32)
    flow = np.stack([flow_y, flow_x], axis=3)
    return mass.astype(np.float32, copy=False), flow.astype(np.float32, copy=False)


def _make_ramp_mass(*, sx: int, sy: int, channels: int) -> np.ndarray:
    return (
        np.arange(sx * sy * channels, dtype=np.float32).reshape(1, sx, sy, channels)
        / np.float32(1000.0)
    )


def run_smoke(
    *,
    sx: int,
    sy: int,
    channels: int,
    device_id: int,
    dtype_name: str,
    case_name: str,
    warmup: int,
    runs: int,
) -> None:
    _require_ttlang()
    if sx != sy:
        raise ValueError(f"tile_shift_reintegration currently expects square grids, got {sx}x{sy}.")
    if sx % TILE_SIZE != 0 or sy % TILE_SIZE != 0:
        raise ValueError(f"Expected dimensions divisible by {TILE_SIZE}, got {sx}x{sy}.")
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True

    if case_name == "identity":
        shifts = (TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),)
        dt = 0.0
        max_flow = 0.0
        sigma = 0.5
        mass = _make_ramp_mass(sx=sx, sy=sy, channels=channels)
        flow = np.zeros((1, sx, sy, 2, channels), dtype=np.float32)
    elif case_name == "shift":
        shifts = (TileReintegrationShift(row_shift_tiles=1, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),)
        dt = 0.0
        max_flow = 0.0
        sigma = 0.5
        mass = _make_ramp_mass(sx=sx, sy=sy, channels=channels)
        flow = np.zeros((1, sx, sy, 2, channels), dtype=np.float32)
    elif case_name == "weighted":
        shifts = (TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.25, x_distance=-0.15),)
        dt = 0.0
        max_flow = 0.0
        sigma = 0.65
        mass = _make_ramp_mass(sx=sx, sy=sy, channels=channels)
        flow = np.zeros((1, sx, sy, 2, channels), dtype=np.float32)
    elif case_name == "multi":
        shifts = (
            TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),
            TileReintegrationShift(row_shift_tiles=1, col_shift_tiles=0, y_distance=0.25, x_distance=-0.15),
            TileReintegrationShift(row_shift_tiles=-1, col_shift_tiles=1, y_distance=-0.25, x_distance=0.2),
        )
        dt = 0.0
        max_flow = 0.0
        sigma = 0.65
        mass = _make_ramp_mass(sx=sx, sy=sy, channels=channels)
        flow = np.zeros((1, sx, sy, 2, channels), dtype=np.float32)
    elif case_name == "demo":
        shifts = (
            TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),
            TileReintegrationShift(row_shift_tiles=1, col_shift_tiles=0, y_distance=0.25, x_distance=-0.15),
            TileReintegrationShift(row_shift_tiles=-1, col_shift_tiles=1, y_distance=-0.25, x_distance=0.2),
        )
        dt = 0.1
        max_flow = 0.5
        sigma = 0.65
        mass, flow = _make_demo_inputs(sx=sx, sy=sy, channels=channels)
    else:
        raise ValueError(f"Unknown smoke case {case_name!r}.")
    expected = tile_shift_reintegration_reference(
        mass,
        flow,
        shifts,
        dt=dt,
        max_flow=max_flow,
        sigma=sigma,
    )
    mass_matrix, mass_shape = lenia_state_to_plane_matrix(mass)
    flow_y_matrix, _ = lenia_state_to_plane_matrix(flow[:, :, :, 0, :])
    flow_x_matrix, _ = lenia_state_to_plane_matrix(flow[:, :, :, 1, :])
    out_matrix = np.zeros(mass_shape.matrix_shape, dtype=np.float32)
    params_matrix = tile_reintegration_param_matrix(shifts, dt=dt, max_flow=max_flow, sigma=sigma)
    for matrix in (mass_matrix, flow_y_matrix, flow_x_matrix, out_matrix):
        require_tiled_matrix_shape(matrix, row_block_tiles=1, col_block_tiles=1, tile_size=TILE_SIZE)

    dtype = ttnn.float32 if dtype_name == "float32" else ttnn.bfloat16
    device = ttnn.open_device(device_id=device_id)
    try:
        mass_tt = _to_device_matrix(mass_matrix, device=device, dtype=dtype)
        flow_y_tt = _to_device_matrix(flow_y_matrix, device=device, dtype=dtype)
        flow_x_tt = _to_device_matrix(flow_x_matrix, device=device, dtype=dtype)
        params_tt = _to_device_matrix(params_matrix, device=device, dtype=dtype)
        out_tt = _to_device_matrix(out_matrix, device=device, dtype=dtype)
        kernel = make_tile_shift_reintegration(shifts, channels=channels)
        for _ in range(warmup):
            kernel(mass_tt, flow_y_tt, flow_x_tt, params_tt, out_tt)
            ttnn.synchronize_device(device)
        started_at = time.perf_counter()
        for _ in range(runs):
            kernel(mass_tt, flow_y_tt, flow_x_tt, params_tt, out_tt)
        ttnn.synchronize_device(device)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
        actual_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
        actual = plane_matrix_to_lenia_state(actual_matrix, mass_shape)
        max_abs = float(np.max(np.abs(actual - expected)))
        mean_abs = float(np.mean(np.abs(actual - expected)))
        max_expected = float(np.max(np.abs(expected))) if expected.size else 0.0
        tolerance = smoke_tolerance(dtype_name, expected)
        print(
            f"tt-lang tile_shift_reintegration smoke: case={case_name} state={mass.shape} shifts={len(shifts)} "
            f"dtype={dtype_name} warmup={warmup} runs={runs} mean_elapsed={mean_elapsed_ms:.3f}ms "
            f"max_abs={max_abs:.6g} mean_abs={mean_abs:.6g} max_expected={max_expected:.6g} "
            f"tolerance={tolerance:.6g}"
        )
        if max_abs > tolerance:
            raise SystemExit(f"tile_shift_reintegration failed: max_abs={max_abs} > {tolerance}")
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TT-Lang tile-native reintegration scaffold.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--dtype", choices=["float32", "bfloat16"], default="bfloat16")
    parser.add_argument("--case", choices=["demo", "identity", "shift", "weighted", "multi"], default="demo")
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
        case_name=args.case,
        warmup=args.warmup,
        runs=args.runs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
