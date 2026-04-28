from __future__ import annotations

"""TT-Lang primitive for one sub-tile Lenia reintegration contribution."""

# ruff: noqa: E402
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttlang.shape_bridge import (
    PlaneMatrixShape,
    lenia_state_to_plane_matrix,
    plane_matrix_to_lenia_state,
    require_tiled_matrix_shape,
)
from ttlang.subtile_shift import (
    TILE_SIZE,
    _delta_terms,
    smoke_tolerance,
    subtile_part_tile_deltas,
    subtile_shift_reference,
    subtile_shift_selector_matrices,
)

try:
    import ttl
    import ttnn
except ImportError:
    ttl = None
    ttnn = None


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit("ttlang/reintegration_subtile.py requires importable ttl and ttnn.")


def subtile_reintegration_param_matrix(
    *,
    row_offset: int,
    col_offset: int,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    clip_max = min(1.0, 2.0 * float(sigma))
    area_scale = 1.0 / (4.0 * float(sigma) * float(sigma))
    values = [
        float(col_offset),
        float(row_offset),
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


def subtile_reintegration_reference(
    mass: np.ndarray,
    flow_y: np.ndarray,
    flow_x: np.ndarray,
    *,
    row_offset: int,
    col_offset: int,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    if mass.shape != flow_y.shape or mass.shape != flow_x.shape:
        raise ValueError(f"Expected mass/flow shapes to match, got {mass.shape}, {flow_y.shape}, {flow_x.shape}.")
    source_mass = subtile_shift_reference(mass, row_offset=row_offset, col_offset=col_offset)
    source_flow_y = subtile_shift_reference(flow_y, row_offset=row_offset, col_offset=col_offset)
    source_flow_x = subtile_shift_reference(flow_x, row_offset=row_offset, col_offset=col_offset)
    clip_max = np.float32(min(1.0, 2.0 * float(sigma)))
    sigma_plus_half = np.float32(float(sigma) + 0.5)
    area_scale = np.float32(1.0 / (4.0 * float(sigma) * float(sigma)))
    max_flow32 = np.float32(max_flow)
    adv_y = np.clip(np.float32(dt) * source_flow_y, -max_flow32, max_flow32)
    adv_x = np.clip(np.float32(dt) * source_flow_x, -max_flow32, max_flow32)
    wy = np.clip(sigma_plus_half - np.abs(np.float32(col_offset) + adv_y), 0.0, clip_max)
    wx = np.clip(sigma_plus_half - np.abs(np.float32(row_offset) + adv_x), 0.0, clip_max)
    return (source_mass * wy * wx * area_scale).astype(np.float32, copy=False)


def subtile_reintegration_offset_groups(dd: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    if dd < 0:
        raise ValueError(f"Expected dd >= 0, got {dd}.")
    groups: dict[tuple[tuple[int, int], tuple[int, int]], list[tuple[int, int]]] = {}
    for row_offset in range(-dd, dd + 1):
        for col_offset in range(-dd, dd + 1):
            key = (
                subtile_part_tile_deltas(row_offset),
                subtile_part_tile_deltas(col_offset),
            )
            groups.setdefault(key, []).append((row_offset, col_offset))
    return tuple(tuple(offsets) for offsets in groups.values())


def _prepare_group_geometry(offsets: tuple[tuple[int, int], ...]):
    if not offsets:
        raise ValueError("Expected at least one offset for grouped sub-tile reintegration.")
    offsets = tuple((int(row_offset), int(col_offset)) for row_offset, col_offset in offsets)
    row_deltas = subtile_part_tile_deltas(offsets[0][0])
    col_deltas = subtile_part_tile_deltas(offsets[0][1])
    for row_offset, col_offset in offsets:
        if subtile_part_tile_deltas(row_offset) != row_deltas or subtile_part_tile_deltas(col_offset) != col_deltas:
            raise ValueError("Grouped sub-tile reintegration offsets must share source tile deltas.")

    row_delta0, row_delta1 = row_deltas
    col_delta0, col_delta1 = col_deltas
    return (
        offsets,
        row_deltas,
        col_deltas,
        _delta_terms(row_delta0),
        _delta_terms(row_delta1),
        _delta_terms(col_delta0),
        _delta_terms(col_delta1),
    )


def _rectangular_offset_grid(offsets: tuple[tuple[int, int], ...]) -> tuple[int, int]:
    """Return row/column offset counts for row-major rectangular groups."""
    row_offsets = tuple(dict.fromkeys(row_offset for row_offset, _ in offsets))
    col_offsets = tuple(dict.fromkeys(col_offset for _, col_offset in offsets))
    expected = tuple((row_offset, col_offset) for row_offset in row_offsets for col_offset in col_offsets)
    if offsets != expected:
        raise ValueError("Expected grouped offsets to form a row-major rectangular offset grid.")
    return len(row_offsets), len(col_offsets)


def subtile_reintegration_group_selector_matrices(
    offsets: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not offsets:
        raise ValueError("Expected at least one offset for grouped sub-tile reintegration.")
    row_matrices = []
    col_matrices = []
    for row_offset, col_offset in offsets:
        row_selectors, col_selectors = subtile_shift_selector_matrices(
            row_offset=row_offset,
            col_offset=col_offset,
        )
        row_matrices.append(row_selectors)
        col_matrices.append(col_selectors)
    return (
        np.concatenate(row_matrices, axis=0).astype(np.float32, copy=False),
        np.concatenate(col_matrices, axis=0).astype(np.float32, copy=False),
    )


def subtile_reintegration_group_block_selector_matrices(
    offsets: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Return block selectors for R(1x2) @ source(2x2) @ C(2x1)."""
    if not offsets:
        raise ValueError("Expected at least one offset for grouped sub-tile reintegration.")
    row_matrices = []
    col_matrices = []
    for row_offset, col_offset in offsets:
        row_selectors, col_selectors = subtile_shift_selector_matrices(
            row_offset=row_offset,
            col_offset=col_offset,
        )
        row_parts = row_selectors.reshape(2, TILE_SIZE, TILE_SIZE)
        col_parts = col_selectors.reshape(2, TILE_SIZE, TILE_SIZE)
        row_matrices.append(np.concatenate([row_parts[0], row_parts[1]], axis=1))
        col_matrices.append(np.concatenate([col_parts[0], col_parts[1]], axis=0))
    return (
        np.concatenate(row_matrices, axis=0).astype(np.float32, copy=False),
        np.concatenate(col_matrices, axis=0).astype(np.float32, copy=False),
    )


def subtile_reintegration_group_param_matrix(
    offsets: tuple[tuple[int, int], ...],
    *,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    if not offsets:
        raise ValueError("Expected at least one offset for grouped sub-tile reintegration.")
    return np.concatenate(
        [
            subtile_reintegration_param_matrix(
                row_offset=row_offset,
                col_offset=col_offset,
                dt=dt,
                max_flow=max_flow,
                sigma=sigma,
            )
            for row_offset, col_offset in offsets
        ],
        axis=0,
    ).astype(np.float32, copy=False)


def subtile_reintegration_group_reference(
    mass: np.ndarray,
    flow_y: np.ndarray,
    flow_x: np.ndarray,
    offsets: tuple[tuple[int, int], ...],
    *,
    dt: float,
    max_flow: float,
    sigma: float,
) -> np.ndarray:
    out = np.zeros_like(mass, dtype=np.float32)
    for row_offset, col_offset in offsets:
        out += subtile_reintegration_reference(
            mass,
            flow_y,
            flow_x,
            row_offset=row_offset,
            col_offset=col_offset,
            dt=dt,
            max_flow=max_flow,
            sigma=sigma,
        )
    return out.astype(np.float32, copy=False)


def torus_halo_pad_plane_matrix(
    matrix: np.ndarray,
    shape: PlaneMatrixShape,
    offsets: tuple[tuple[int, int], ...],
) -> np.ndarray:
    """Return a one-tile torus halo for a packed Lenia plane matrix."""
    _, row_deltas, col_deltas, *_ = _prepare_group_geometry(offsets)
    if matrix.shape != shape.matrix_shape:
        raise ValueError(f"Expected plane matrix {shape.matrix_shape}, got {matrix.shape}.")
    if shape.sx % TILE_SIZE != 0 or shape.sy % TILE_SIZE != 0:
        raise ValueError(f"Expected tile-aligned spatial shape, got sx={shape.sx} sy={shape.sy}.")

    row_pad_offset = 1 if row_deltas[0] < 0 else 0
    col_pad_offset = 1 if col_deltas[0] < 0 else 0
    sx_tiles = shape.sx // TILE_SIZE
    sy_tiles = shape.sy // TILE_SIZE
    plane_count = shape.batch * shape.channels
    padded = np.empty(
        (plane_count * (shape.sx + TILE_SIZE), shape.sy + TILE_SIZE),
        dtype=np.float32,
    )

    for plane_index in range(plane_count):
        source_plane_row = plane_index * shape.sx
        padded_plane_row = plane_index * (shape.sx + TILE_SIZE)
        for padded_tile_row in range(sx_tiles + 1):
            source_tile_row = (padded_tile_row + sx_tiles - row_pad_offset) % sx_tiles
            source_row = source_plane_row + source_tile_row * TILE_SIZE
            padded_row = padded_plane_row + padded_tile_row * TILE_SIZE
            for padded_tile_col in range(sy_tiles + 1):
                source_tile_col = (padded_tile_col + sy_tiles - col_pad_offset) % sy_tiles
                source_col = source_tile_col * TILE_SIZE
                padded_col = padded_tile_col * TILE_SIZE
                padded[padded_row : padded_row + TILE_SIZE, padded_col : padded_col + TILE_SIZE] = matrix[
                    source_row : source_row + TILE_SIZE,
                    source_col : source_col + TILE_SIZE,
                ]
    return padded.astype(np.float32, copy=False)


def make_subtile_reintegration(*, row_offset: int, col_offset: int):
    _require_ttlang()
    row_delta0, row_delta1 = subtile_part_tile_deltas(row_offset)
    col_delta0, col_delta1 = subtile_part_tile_deltas(col_offset)
    row_add0, row_back0, row_wrap0 = _delta_terms(row_delta0)
    row_add1, row_back1, row_wrap1 = _delta_terms(row_delta1)
    col_add0, col_back0, col_wrap0 = _delta_terms(col_delta0)
    col_add1, col_back1, col_wrap1 = _delta_terms(col_delta1)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with mass_acc_dfb.reserve() as mass_acc_blk:
                                mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                            with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                            with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                            for _ in range(4):
                                with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                    with mass_src_dfb.wait() as mass_src_blk:
                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ mass_src_blk)
                                    with tmp_dfb.wait() as tmp_blk:
                                        with part_dfb.reserve() as part_blk:
                                            part_blk.store(tmp_blk @ col_blk)
                                    with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                        with mass_acc_dfb.reserve() as acc_blk:
                                            acc_blk.store(prev_blk + part_blk)

                                    with flow_y_src_dfb.wait() as flow_y_src_blk:
                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ flow_y_src_blk)
                                    with tmp_dfb.wait() as tmp_blk:
                                        with part_dfb.reserve() as part_blk:
                                            part_blk.store(tmp_blk @ col_blk)
                                    with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                        with flow_y_acc_dfb.reserve() as acc_blk:
                                            acc_blk.store(prev_blk + part_blk)

                                    with flow_x_src_dfb.wait() as flow_x_src_blk:
                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ flow_x_src_blk)
                                    with tmp_dfb.wait() as tmp_blk:
                                        with part_dfb.reserve() as part_blk:
                                            part_blk.store(tmp_blk @ col_blk)
                                    with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                        with flow_x_acc_dfb.reserve() as acc_blk:
                                            acc_blk.store(prev_blk + part_blk)

                            with (
                                flow_y_acc_dfb.wait() as flow_y_blk,
                                flow_x_acc_dfb.wait() as flow_x_blk,
                                shift_y_dfb.wait() as shift_y_blk,
                                shift_x_dfb.wait() as shift_x_blk,
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                            ):
                                with weight_dfb.reserve() as weight_blk:
                                    adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                    adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                    adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                    adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                    raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                    raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                    wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                    wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                    weight_blk.store(wy * wx * area_scale_blk)
                            with mass_acc_dfb.wait() as mass_blk, weight_dfb.wait() as weight_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(mass_blk * weight_blk)

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
                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                            source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()
                                tx_row.wait()
                                tx_col.wait()

                            with (
                                shift_y_dfb.reserve() as shift_y_blk,
                                shift_x_dfb.reserve() as shift_x_blk,
                                dt_dfb.reserve() as dt_blk,
                                max_flow_dfb.reserve() as max_flow_blk,
                                neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                clip_max_dfb.reserve() as clip_max_blk,
                                area_scale_dfb.reserve() as area_scale_blk,
                                zero_dfb.reserve() as zero_blk,
                            ):
                                tx_shift_y = ttl.copy(params[0, 0], shift_y_blk)
                                tx_shift_x = ttl.copy(params[1, 0], shift_x_blk)
                                tx_dt = ttl.copy(params[2, 0], dt_blk)
                                tx_max_flow = ttl.copy(params[3, 0], max_flow_blk)
                                tx_neg_max_flow = ttl.copy(params[4, 0], neg_max_flow_blk)
                                tx_sigma_plus_half = ttl.copy(params[5, 0], sigma_plus_half_blk)
                                tx_clip_max = ttl.copy(params[6, 0], clip_max_blk)
                                tx_area_scale = ttl.copy(params[7, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[8, 0], zero_blk)
                                tx_shift_y.wait()
                                tx_shift_x.wait()
                                tx_dt.wait()
                                tx_max_flow.wait()
                                tx_neg_max_flow.wait()
                                tx_sigma_plus_half.wait()
                                tx_clip_max.wait()
                                tx_area_scale.wait()
                                tx_zero.wait()

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

    return subtile_reintegration


def make_subtile_reintegration_group(offsets: tuple[tuple[int, int], ...]):
    _require_ttlang()
    offsets, _, _, row_terms0, row_terms1, col_terms0, col_terms1 = _prepare_group_geometry(offsets)
    row_add0, row_back0, row_wrap0 = row_terms0
    row_add1, row_back1, row_wrap1 = row_terms1
    col_add0, col_back0, col_wrap0 = col_terms0
    col_add1, col_back1, col_wrap1 = col_terms1
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            with (
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                            ):
                                for _ in range(offset_count):
                                    with mass_acc_dfb.reserve() as mass_acc_blk:
                                        mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                    with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                        flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                    with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                        flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                                    for _ in range(4):
                                        with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                            with mass_src_dfb.wait() as mass_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ mass_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                                with mass_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_y_src_dfb.wait() as flow_y_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_y_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                                with flow_y_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_x_src_dfb.wait() as flow_x_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_x_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                                with flow_x_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                    with (
                                        flow_y_acc_dfb.wait() as flow_y_blk,
                                        flow_x_acc_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                    ):
                                        with weight_dfb.reserve() as weight_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                            wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                            weight_blk.store(wy * wx * area_scale_blk)
                                    with (
                                        mass_acc_dfb.wait() as mass_blk,
                                        weight_dfb.wait() as weight_blk,
                                        total_acc_dfb.wait() as total_blk,
                                    ):
                                        with total_acc_dfb.reserve() as total_acc_blk:
                                            total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

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
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[row, col], prior_acc_blk)
                                tx_prior.wait()

                            with (
                                dt_dfb.reserve() as dt_blk,
                                max_flow_dfb.reserve() as max_flow_blk,
                                neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                clip_max_dfb.reserve() as clip_max_blk,
                                area_scale_dfb.reserve() as area_scale_blk,
                                zero_dfb.reserve() as zero_blk,
                            ):
                                tx_dt = ttl.copy(params[2, 0], dt_blk)
                                tx_max_flow = ttl.copy(params[3, 0], max_flow_blk)
                                tx_neg_max_flow = ttl.copy(params[4, 0], neg_max_flow_blk)
                                tx_sigma_plus_half = ttl.copy(params[5, 0], sigma_plus_half_blk)
                                tx_clip_max = ttl.copy(params[6, 0], clip_max_blk)
                                tx_area_scale = ttl.copy(params[7, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[8, 0], zero_blk)
                                tx_dt.wait()
                                tx_max_flow.wait()
                                tx_neg_max_flow.wait()
                                tx_sigma_plus_half.wait()
                                tx_clip_max.wait()
                                tx_area_scale.wait()
                                tx_zero.wait()

                            for offset_index in range(offset_count):
                                selector_base = offset_index * 2
                                param_base = offset_index * 9

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with (
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
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

    return subtile_reintegration_group


def make_subtile_reintegration_group_initial(offsets: tuple[tuple[int, int], ...]):
    """Grouped split-selector reintegration update with a zero initial accumulator."""

    _require_ttlang()
    offsets, _, _, row_terms0, row_terms1, col_terms0, col_terms1 = _prepare_group_geometry(offsets)
    row_add0, row_back0, row_wrap0 = row_terms0
    row_add1, row_back1, row_wrap1 = row_terms1
    col_add0, col_back0, col_wrap0 = col_terms0
    col_add1, col_back1, col_wrap1 = col_terms1
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_initial(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with total_acc_dfb.reserve() as total_acc_blk:
                                total_acc_blk.store(ttl.math.fill(total_acc_blk, 0.0))
                            with (
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                            ):
                                for _ in range(offset_count):
                                    with mass_acc_dfb.reserve() as mass_acc_blk:
                                        mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                    with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                        flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                    with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                        flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                                    for _ in range(4):
                                        with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                            with mass_src_dfb.wait() as mass_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ mass_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                                with mass_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_y_src_dfb.wait() as flow_y_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_y_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                                with flow_y_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_x_src_dfb.wait() as flow_x_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_x_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                                with flow_x_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                    with (
                                        flow_y_acc_dfb.wait() as flow_y_blk,
                                        flow_x_acc_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                    ):
                                        with weight_dfb.reserve() as weight_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                            wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                            weight_blk.store(wy * wx * area_scale_blk)
                                    with (
                                        mass_acc_dfb.wait() as mass_blk,
                                        weight_dfb.wait() as weight_blk,
                                        total_acc_dfb.wait() as total_blk,
                                    ):
                                        with total_acc_dfb.reserve() as total_acc_blk:
                                            total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

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
                                tx_dt = ttl.copy(params[2, 0], dt_blk)
                                tx_max_flow = ttl.copy(params[3, 0], max_flow_blk)
                                tx_neg_max_flow = ttl.copy(params[4, 0], neg_max_flow_blk)
                                tx_sigma_plus_half = ttl.copy(params[5, 0], sigma_plus_half_blk)
                                tx_clip_max = ttl.copy(params[6, 0], clip_max_blk)
                                tx_area_scale = ttl.copy(params[7, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[8, 0], zero_blk)
                                tx_dt.wait()
                                tx_max_flow.wait()
                                tx_neg_max_flow.wait()
                                tx_sigma_plus_half.wait()
                                tx_clip_max.wait()
                                tx_area_scale.wait()
                                tx_zero.wait()

                            for offset_index in range(offset_count):
                                selector_base = offset_index * 2
                                param_base = offset_index * 9

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with (
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
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

    return subtile_reintegration_group_initial


def make_subtile_reintegration_group_boundary(offsets: tuple[tuple[int, int], ...]):
    """Grouped split-selector reintegration update for torus boundary tiles only."""

    _require_ttlang()
    offsets, row_deltas, col_deltas, row_terms0, row_terms1, col_terms0, col_terms1 = _prepare_group_geometry(offsets)
    row_delta0, row_delta1 = row_deltas
    col_delta0, col_delta1 = col_deltas
    row_add0, row_back0, row_wrap0 = row_terms0
    row_add1, row_back1, row_wrap1 = row_terms1
    col_add0, col_back0, col_wrap0 = col_terms0
    col_add1, col_back1, col_wrap1 = col_terms1
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_boundary(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        out_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    out_spatial_row = row % sx_tiles
                    interior_row = (
                        (row_delta0 >= 0 and out_spatial_row + row_delta1 < sx_tiles)
                        or (row_delta0 < 0 and out_spatial_row > 0)
                    )
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            interior_col = (
                                (col_delta0 >= 0 and col + col_delta1 < sy_tiles)
                                or (col_delta0 < 0 and col > 0)
                            )
                            if (not interior_row) or (not interior_col):
                                with prior_acc_dfb.wait() as prior_acc_blk:
                                    with total_acc_dfb.reserve() as total_acc_blk:
                                        total_acc_blk.store(prior_acc_blk)
                                for _ in range(offset_count):
                                    with mass_acc_dfb.reserve() as mass_acc_blk:
                                        mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                    with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                        flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                    with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                        flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                                    for _ in range(4):
                                        with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                            with mass_src_dfb.wait() as mass_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ mass_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                                with mass_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_y_src_dfb.wait() as flow_y_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_y_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                                with flow_y_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                            with flow_x_src_dfb.wait() as flow_x_src_blk:
                                                with tmp_dfb.reserve() as tmp_blk:
                                                    tmp_blk.store(row_blk @ flow_x_src_blk)
                                            with tmp_dfb.wait() as tmp_blk:
                                                with part_dfb.reserve() as part_blk:
                                                    part_blk.store(tmp_blk @ col_blk)
                                            with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                                with flow_x_acc_dfb.reserve() as acc_blk:
                                                    acc_blk.store(prev_blk + part_blk)

                                    with (
                                        flow_y_acc_dfb.wait() as flow_y_blk,
                                        flow_x_acc_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                        dt_dfb.wait() as dt_blk,
                                        max_flow_dfb.wait() as max_flow_blk,
                                        neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                        sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                        clip_max_dfb.wait() as clip_max_blk,
                                        area_scale_dfb.wait() as area_scale_blk,
                                        zero_dfb.wait() as zero_blk,
                                    ):
                                        with weight_dfb.reserve() as weight_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                            wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                            weight_blk.store(wy * wx * area_scale_blk)
                                    with (
                                        mass_acc_dfb.wait() as mass_blk,
                                        weight_dfb.wait() as weight_blk,
                                        total_acc_dfb.wait() as total_blk,
                                    ):
                                        with total_acc_dfb.reserve() as total_acc_blk:
                                            total_acc_blk.store(total_blk + mass_blk * weight_blk)
                                with total_acc_dfb.wait() as total_blk:
                                    with out_dfb.reserve() as out_blk:
                                        out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    out_spatial_row = row - plane_index * sx_tiles
                    interior_row = (
                        (row_delta0 >= 0 and out_spatial_row + row_delta1 < sx_tiles)
                        or (row_delta0 < 0 and out_spatial_row > 0)
                    )
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            interior_col = (
                                (col_delta0 >= 0 and col + col_delta1 < sy_tiles)
                                or (col_delta0 < 0 and col > 0)
                            )
                            if (not interior_row) or (not interior_col):
                                with prior_acc_dfb.reserve() as prior_acc_blk:
                                    tx_prior = ttl.copy(acc_in[row, col], prior_acc_blk)
                                    tx_prior.wait()
                                for offset_index in range(offset_count):
                                    selector_base = offset_index * 2
                                    param_base = offset_index * 9

                                    source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                    source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                    source_tile_row = plane_index * sx_tiles + source_row
                                    with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                        tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                        tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                        tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                        tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                        tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                        tx_mass.wait()
                                        tx_flow_y.wait()
                                        tx_flow_x.wait()
                                        tx_row.wait()
                                        tx_col.wait()

                                    source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                    source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                    source_tile_row = plane_index * sx_tiles + source_row
                                    with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                        tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                        tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                        tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                        tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                        tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                        tx_mass.wait()
                                        tx_flow_y.wait()
                                        tx_flow_x.wait()
                                        tx_row.wait()
                                        tx_col.wait()

                                    source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                    source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                    source_tile_row = plane_index * sx_tiles + source_row
                                    with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                        tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                        tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                        tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                        tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                        tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                        tx_mass.wait()
                                        tx_flow_y.wait()
                                        tx_flow_x.wait()
                                        tx_row.wait()
                                        tx_col.wait()

                                    source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                    source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                    source_tile_row = plane_index * sx_tiles + source_row
                                    with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                        tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                        tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                        tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                        tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                        tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                        tx_mass.wait()
                                        tx_flow_y.wait()
                                        tx_flow_x.wait()
                                        tx_row.wait()
                                        tx_col.wait()

                                    with (
                                        shift_y_dfb.reserve() as shift_y_blk,
                                        shift_x_dfb.reserve() as shift_x_blk,
                                        dt_dfb.reserve() as dt_blk,
                                        max_flow_dfb.reserve() as max_flow_blk,
                                        neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                        sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                        clip_max_dfb.reserve() as clip_max_blk,
                                        area_scale_dfb.reserve() as area_scale_blk,
                                        zero_dfb.reserve() as zero_blk,
                                    ):
                                        tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                        tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
                                        tx_dt = ttl.copy(params[param_base + 2, 0], dt_blk)
                                        tx_max_flow = ttl.copy(params[param_base + 3, 0], max_flow_blk)
                                        tx_neg_max_flow = ttl.copy(params[param_base + 4, 0], neg_max_flow_blk)
                                        tx_sigma_plus_half = ttl.copy(params[param_base + 5, 0], sigma_plus_half_blk)
                                        tx_clip_max = ttl.copy(params[param_base + 6, 0], clip_max_blk)
                                        tx_area_scale = ttl.copy(params[param_base + 7, 0], area_scale_blk)
                                        tx_zero = ttl.copy(params[param_base + 8, 0], zero_blk)
                                        tx_shift_y.wait()
                                        tx_shift_x.wait()
                                        tx_dt.wait()
                                        tx_max_flow.wait()
                                        tx_neg_max_flow.wait()
                                        tx_sigma_plus_half.wait()
                                        tx_clip_max.wait()
                                        tx_area_scale.wait()
                                        tx_zero.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            out_spatial_row = row % sx_tiles
                            interior_row = (
                                (row_delta0 >= 0 and out_spatial_row + row_delta1 < sx_tiles)
                                or (row_delta0 < 0 and out_spatial_row > 0)
                            )
                            interior_col = (
                                (col_delta0 >= 0 and col + col_delta1 < sy_tiles)
                                or (col_delta0 < 0 and col > 0)
                            )
                            if (not interior_row) or (not interior_col):
                                with out_dfb.wait() as out_blk:
                                    tx = ttl.copy(out_blk, out[row, col])
                                    tx.wait()

    return subtile_reintegration_group_boundary


def make_subtile_reintegration_group_boundary_row(offsets: tuple[tuple[int, int], ...]):
    """Grouped split-selector reintegration update for the torus row boundary."""

    _require_ttlang()
    offsets, row_deltas, col_deltas, row_terms0, row_terms1, col_terms0, col_terms1 = _prepare_group_geometry(offsets)
    row_delta0, row_delta1 = row_deltas
    col_delta0, col_delta1 = col_deltas
    row_add0, row_back0, row_wrap0 = row_terms0
    row_add1, row_back1, row_wrap1 = row_terms1
    col_add0, col_back0, col_wrap0 = col_terms0
    col_add1, col_back1, col_wrap1 = col_terms1
    row_boundary_scale = 1 if row_delta0 >= 0 else 0
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_boundary_row(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            for _ in range(offset_count):
                                with mass_acc_dfb.reserve() as mass_acc_blk:
                                    mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                    flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                    flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                                for _ in range(4):
                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with mass_src_dfb.wait() as mass_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ mass_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                            with mass_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_y_src_dfb.wait() as flow_y_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_y_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                            with flow_y_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_x_src_dfb.wait() as flow_x_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_x_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                            with flow_x_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                with (
                                    flow_y_acc_dfb.wait() as flow_y_blk,
                                    flow_x_acc_dfb.wait() as flow_x_blk,
                                    shift_y_dfb.wait() as shift_y_blk,
                                    shift_x_dfb.wait() as shift_x_blk,
                                    dt_dfb.wait() as dt_blk,
                                    max_flow_dfb.wait() as max_flow_blk,
                                    neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                    sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                    clip_max_dfb.wait() as clip_max_blk,
                                    area_scale_dfb.wait() as area_scale_blk,
                                    zero_dfb.wait() as zero_blk,
                                ):
                                    with weight_dfb.reserve() as weight_blk:
                                        adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                        adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                        adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                        adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                        raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                        raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                        wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                        wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                        weight_blk.store(wy * wx * area_scale_blk)
                                with (
                                    mass_acc_dfb.wait() as mass_blk,
                                    weight_dfb.wait() as weight_blk,
                                    total_acc_dfb.wait() as total_blk,
                                ):
                                    with total_acc_dfb.reserve() as total_acc_blk:
                                        total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row
                    out_spatial_row = (sx_tiles - 1) * row_boundary_scale
                    out_tile_row = plane_index * sx_tiles + out_spatial_row
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[out_tile_row, col], prior_acc_blk)
                                tx_prior.wait()
                            for offset_index in range(offset_count):
                                selector_base = offset_index * 2
                                param_base = offset_index * 9

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with (
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                    dt_dfb.reserve() as dt_blk,
                                    max_flow_dfb.reserve() as max_flow_blk,
                                    neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                    sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                    clip_max_dfb.reserve() as clip_max_blk,
                                    area_scale_dfb.reserve() as area_scale_blk,
                                    zero_dfb.reserve() as zero_blk,
                                ):
                                    tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
                                    tx_dt = ttl.copy(params[param_base + 2, 0], dt_blk)
                                    tx_max_flow = ttl.copy(params[param_base + 3, 0], max_flow_blk)
                                    tx_neg_max_flow = ttl.copy(params[param_base + 4, 0], neg_max_flow_blk)
                                    tx_sigma_plus_half = ttl.copy(params[param_base + 5, 0], sigma_plus_half_blk)
                                    tx_clip_max = ttl.copy(params[param_base + 6, 0], clip_max_blk)
                                    tx_area_scale = ttl.copy(params[param_base + 7, 0], area_scale_blk)
                                    tx_zero = ttl.copy(params[param_base + 8, 0], zero_blk)
                                    tx_shift_y.wait()
                                    tx_shift_x.wait()
                                    tx_dt.wait()
                                    tx_max_flow.wait()
                                    tx_neg_max_flow.wait()
                                    tx_sigma_plus_half.wait()
                                    tx_clip_max.wait()
                                    tx_area_scale.wait()
                                    tx_zero.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row
                    out_tile_row = plane_index * sx_tiles + (sx_tiles - 1) * row_boundary_scale
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with out_dfb.wait() as out_blk:
                                tx = ttl.copy(out_blk, out[out_tile_row, col])
                                tx.wait()

    return subtile_reintegration_group_boundary_row


def make_subtile_reintegration_group_boundary_col(offsets: tuple[tuple[int, int], ...]):
    """Grouped split-selector reintegration update for the torus column boundary."""

    _require_ttlang()
    offsets, row_deltas, col_deltas, row_terms0, row_terms1, col_terms0, col_terms1 = _prepare_group_geometry(offsets)
    row_delta0, row_delta1 = row_deltas
    col_delta0, col_delta1 = col_deltas
    row_add0, row_back0, row_wrap0 = row_terms0
    row_add1, row_back1, row_wrap1 = row_terms1
    col_add0, col_back0, col_wrap0 = col_terms0
    col_add1, col_back1, col_wrap1 = col_terms1
    row_skip_first = 0 if row_delta0 >= 0 else 1
    col_boundary_scale = 1 if col_delta0 >= 0 else 0
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_boundary_col(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * (sx_tiles - 1)
        cols = 1
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        out_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        local_boundary_col = node_col * cols_per_node + local_col
                        if local_boundary_col < cols:
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            for _ in range(offset_count):
                                with mass_acc_dfb.reserve() as mass_acc_blk:
                                    mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                    flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                    flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))
                                for _ in range(4):
                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with mass_src_dfb.wait() as mass_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ mass_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                            with mass_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_y_src_dfb.wait() as flow_y_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_y_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                            with flow_y_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_x_src_dfb.wait() as flow_x_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_x_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                            with flow_x_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                with (
                                    flow_y_acc_dfb.wait() as flow_y_blk,
                                    flow_x_acc_dfb.wait() as flow_x_blk,
                                    shift_y_dfb.wait() as shift_y_blk,
                                    shift_x_dfb.wait() as shift_x_blk,
                                    dt_dfb.wait() as dt_blk,
                                    max_flow_dfb.wait() as max_flow_blk,
                                    neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                    sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                    clip_max_dfb.wait() as clip_max_blk,
                                    area_scale_dfb.wait() as area_scale_blk,
                                    zero_dfb.wait() as zero_blk,
                                ):
                                    with weight_dfb.reserve() as weight_blk:
                                        adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                        adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                        adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                        adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                        raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                        raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                        wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                        wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                        weight_blk.store(wy * wx * area_scale_blk)
                                with (
                                    mass_acc_dfb.wait() as mass_blk,
                                    weight_dfb.wait() as weight_blk,
                                    total_acc_dfb.wait() as total_blk,
                                ):
                                    with total_acc_dfb.reserve() as total_acc_blk:
                                        total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // (sx_tiles - 1)
                    boundary_plane_row = row - plane_index * (sx_tiles - 1)
                    out_spatial_row = boundary_plane_row + row_skip_first
                    out_tile_row = plane_index * sx_tiles + out_spatial_row
                    col = (sy_tiles - 1) * col_boundary_scale
                    for local_col in range(cols_per_node):
                        local_boundary_col = node_col * cols_per_node + local_col
                        if local_boundary_col < cols:
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[out_tile_row, col], prior_acc_blk)
                                tx_prior.wait()
                            for offset_index in range(offset_count):
                                selector_base = offset_index * 2
                                param_base = offset_index * 9

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                                source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with mass_src_dfb.reserve() as mass_blk, flow_y_src_dfb.reserve() as flow_y_blk, flow_x_src_dfb.reserve() as flow_x_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                    tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                    tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_mass.wait()
                                    tx_flow_y.wait()
                                    tx_flow_x.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with (
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                    dt_dfb.reserve() as dt_blk,
                                    max_flow_dfb.reserve() as max_flow_blk,
                                    neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                    sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                    clip_max_dfb.reserve() as clip_max_blk,
                                    area_scale_dfb.reserve() as area_scale_blk,
                                    zero_dfb.reserve() as zero_blk,
                                ):
                                    tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
                                    tx_dt = ttl.copy(params[param_base + 2, 0], dt_blk)
                                    tx_max_flow = ttl.copy(params[param_base + 3, 0], max_flow_blk)
                                    tx_neg_max_flow = ttl.copy(params[param_base + 4, 0], neg_max_flow_blk)
                                    tx_sigma_plus_half = ttl.copy(params[param_base + 5, 0], sigma_plus_half_blk)
                                    tx_clip_max = ttl.copy(params[param_base + 6, 0], clip_max_blk)
                                    tx_area_scale = ttl.copy(params[param_base + 7, 0], area_scale_blk)
                                    tx_zero = ttl.copy(params[param_base + 8, 0], zero_blk)
                                    tx_shift_y.wait()
                                    tx_shift_x.wait()
                                    tx_dt.wait()
                                    tx_max_flow.wait()
                                    tx_neg_max_flow.wait()
                                    tx_sigma_plus_half.wait()
                                    tx_clip_max.wait()
                                    tx_area_scale.wait()
                                    tx_zero.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // (sx_tiles - 1)
                    boundary_plane_row = row - plane_index * (sx_tiles - 1)
                    out_spatial_row = boundary_plane_row + row_skip_first
                    out_tile_row = plane_index * sx_tiles + out_spatial_row
                    col = (sy_tiles - 1) * col_boundary_scale
                    for local_col in range(cols_per_node):
                        local_boundary_col = node_col * cols_per_node + local_col
                        if local_boundary_col < cols:
                            with out_dfb.wait() as out_blk:
                                tx = ttl.copy(out_blk, out[out_tile_row, col])
                                tx.wait()

    return subtile_reintegration_group_boundary_col


def make_subtile_reintegration_group_block_interior(offsets: tuple[tuple[int, int], ...]):
    """Prototype grouped reintegration using 2x2 source blocks for interior tiles.

    Boundary output tiles pass through acc_in unchanged. A runtime integration
    needs a companion boundary kernel, but this isolates the faster interior
    shift formulation for correctness/performance testing.
    """

    _require_ttlang()
    offsets, row_deltas, col_deltas, *_ = _prepare_group_geometry(offsets)
    row_delta0, row_delta1 = row_deltas
    col_delta0, col_delta1 = col_deltas
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_block_interior(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass, shape=(2, 2), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(2, 2), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(2, 2), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 2), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(2, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 2), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        mass_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        out_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    out_spatial_row = row % sx_tiles
                    interior_row = (
                        (row_delta0 >= 0 and out_spatial_row + row_delta1 < sx_tiles)
                        or (row_delta0 < 0 and out_spatial_row > 0)
                    )
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            interior_col = (
                                (col_delta0 >= 0 and col + col_delta1 < sy_tiles)
                                or (col_delta0 < 0 and col > 0)
                            )
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            if interior_row and interior_col:
                                for _ in range(offset_count):
                                    with mass_acc_dfb.reserve() as mass_acc_blk:
                                        mass_acc_blk.store(ttl.math.fill(mass_acc_blk, 0.0))
                                    with flow_y_acc_dfb.reserve() as flow_y_acc_blk:
                                        flow_y_acc_blk.store(ttl.math.fill(flow_y_acc_blk, 0.0))
                                    with flow_x_acc_dfb.reserve() as flow_x_acc_blk:
                                        flow_x_acc_blk.store(ttl.math.fill(flow_x_acc_blk, 0.0))

                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with mass_src_dfb.wait() as mass_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ mass_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, mass_acc_dfb.wait() as prev_blk:
                                            with mass_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_y_src_dfb.wait() as flow_y_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_y_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_y_acc_dfb.wait() as prev_blk:
                                            with flow_y_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with flow_x_src_dfb.wait() as flow_x_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ flow_x_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, flow_x_acc_dfb.wait() as prev_blk:
                                            with flow_x_acc_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                    with (
                                        flow_y_acc_dfb.wait() as flow_y_blk,
                                        flow_x_acc_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                        dt_dfb.wait() as dt_blk,
                                        max_flow_dfb.wait() as max_flow_blk,
                                        neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                        sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                        clip_max_dfb.wait() as clip_max_blk,
                                        area_scale_dfb.wait() as area_scale_blk,
                                        zero_dfb.wait() as zero_blk,
                                    ):
                                        with weight_dfb.reserve() as weight_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                            wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                            weight_blk.store(wy * wx * area_scale_blk)
                                    with (
                                        mass_acc_dfb.wait() as mass_blk,
                                        weight_dfb.wait() as weight_blk,
                                        total_acc_dfb.wait() as total_blk,
                                    ):
                                        with total_acc_dfb.reserve() as total_acc_blk:
                                            total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    out_spatial_row = row - plane_index * sx_tiles
                    source_row = out_spatial_row + row_delta0
                    interior_row = 0 <= source_row and source_row + 1 < sx_tiles
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            source_col = col + col_delta0
                            interior_col = 0 <= source_col and source_col + 1 < sy_tiles
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[row, col], prior_acc_blk)
                                tx_prior.wait()

                            if interior_row and interior_col:
                                source_tile_row = plane_index * sx_tiles + source_row
                                for offset_index in range(offset_count):
                                    param_base = offset_index * 9
                                    with (
                                        mass_src_dfb.reserve() as mass_blk,
                                        flow_y_src_dfb.reserve() as flow_y_blk,
                                        flow_x_src_dfb.reserve() as flow_x_blk,
                                        row_dfb.reserve() as row_blk,
                                        col_dfb.reserve() as col_blk,
                                    ):
                                        tx_mass = ttl.copy(
                                            mass[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                            mass_blk,
                                        )
                                        tx_flow_y = ttl.copy(
                                            flow_y[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                            flow_y_blk,
                                        )
                                        tx_flow_x = ttl.copy(
                                            flow_x[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                            flow_x_blk,
                                        )
                                        tx_row = ttl.copy(row_selectors[offset_index, 0:2], row_blk)
                                        tx_col = ttl.copy(col_selectors[2 * offset_index : 2 * offset_index + 2, 0], col_blk)
                                        tx_mass.wait()
                                        tx_flow_y.wait()
                                        tx_flow_x.wait()
                                        tx_row.wait()
                                        tx_col.wait()

                                    with (
                                        shift_y_dfb.reserve() as shift_y_blk,
                                        shift_x_dfb.reserve() as shift_x_blk,
                                        dt_dfb.reserve() as dt_blk,
                                        max_flow_dfb.reserve() as max_flow_blk,
                                        neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                        sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                        clip_max_dfb.reserve() as clip_max_blk,
                                        area_scale_dfb.reserve() as area_scale_blk,
                                        zero_dfb.reserve() as zero_blk,
                                    ):
                                        tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                        tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
                                        tx_dt = ttl.copy(params[param_base + 2, 0], dt_blk)
                                        tx_max_flow = ttl.copy(params[param_base + 3, 0], max_flow_blk)
                                        tx_neg_max_flow = ttl.copy(params[param_base + 4, 0], neg_max_flow_blk)
                                        tx_sigma_plus_half = ttl.copy(params[param_base + 5, 0], sigma_plus_half_blk)
                                        tx_clip_max = ttl.copy(params[param_base + 6, 0], clip_max_blk)
                                        tx_area_scale = ttl.copy(params[param_base + 7, 0], area_scale_blk)
                                        tx_zero = ttl.copy(params[param_base + 8, 0], zero_blk)
                                        tx_shift_y.wait()
                                        tx_shift_x.wait()
                                        tx_dt.wait()
                                        tx_max_flow.wait()
                                        tx_neg_max_flow.wait()
                                        tx_sigma_plus_half.wait()
                                        tx_clip_max.wait()
                                        tx_area_scale.wait()
                                        tx_zero.wait()

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

    return subtile_reintegration_group_block_interior


def make_torus_halo_pad(offsets: tuple[tuple[int, int], ...]):
    """Copy state planes into a one-tile torus halo for a grouped block kernel."""

    _require_ttlang()
    _, row_deltas, col_deltas, *_ = _prepare_group_geometry(offsets)
    row_pad_offset = 1 if row_deltas[0] < 0 else 0
    col_pad_offset = 1 if col_deltas[0] < 0 else 0

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def torus_halo_pad(
        mass: ttnn.Tensor,
        flow_y: ttnn.Tensor,
        flow_x: ttnn.Tensor,
        mass_padded: ttnn.Tensor,
        flow_y_padded: ttnn.Tensor,
        flow_x_padded: ttnn.Tensor,
    ) -> None:
        sy_tiles = mass.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = mass.shape[0] // mass.shape[1]
        padded_sx_tiles = sx_tiles + 1
        padded_sy_tiles = sy_tiles + 1
        rows = plane_count * padded_sx_tiles
        cols = padded_sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_in_dfb = ttl.make_dataflow_buffer_like(mass, shape=(1, 1), block_count=2)
        flow_y_in_dfb = ttl.make_dataflow_buffer_like(flow_y, shape=(1, 1), block_count=2)
        flow_x_in_dfb = ttl.make_dataflow_buffer_like(flow_x, shape=(1, 1), block_count=2)
        mass_out_dfb = ttl.make_dataflow_buffer_like(mass_padded, shape=(1, 1), block_count=2)
        flow_y_out_dfb = ttl.make_dataflow_buffer_like(flow_y_padded, shape=(1, 1), block_count=2)
        flow_x_out_dfb = ttl.make_dataflow_buffer_like(flow_x_padded, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with (
                                mass_in_dfb.wait() as mass_blk,
                                flow_y_in_dfb.wait() as flow_y_blk,
                                flow_x_in_dfb.wait() as flow_x_blk,
                            ):
                                with (
                                    mass_out_dfb.reserve() as mass_out_blk,
                                    flow_y_out_dfb.reserve() as flow_y_out_blk,
                                    flow_x_out_dfb.reserve() as flow_x_out_blk,
                                ):
                                    mass_out_blk.store(mass_blk)
                                    flow_y_out_blk.store(flow_y_blk)
                                    flow_x_out_blk.store(flow_x_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // padded_sx_tiles
                    padded_row = row - plane_index * padded_sx_tiles
                    source_row = (padded_row + sx_tiles - row_pad_offset) % sx_tiles
                    source_tile_row = plane_index * sx_tiles + source_row
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            source_col = (col + sy_tiles - col_pad_offset) % sy_tiles
                            with (
                                mass_in_dfb.reserve() as mass_blk,
                                flow_y_in_dfb.reserve() as flow_y_blk,
                                flow_x_in_dfb.reserve() as flow_x_blk,
                            ):
                                tx_mass = ttl.copy(mass[source_tile_row, source_col], mass_blk)
                                tx_flow_y = ttl.copy(flow_y[source_tile_row, source_col], flow_y_blk)
                                tx_flow_x = ttl.copy(flow_x[source_tile_row, source_col], flow_x_blk)
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with (
                                mass_out_dfb.wait() as mass_blk,
                                flow_y_out_dfb.wait() as flow_y_blk,
                                flow_x_out_dfb.wait() as flow_x_blk,
                            ):
                                tx_mass = ttl.copy(mass_blk, mass_padded[row, col])
                                tx_flow_y = ttl.copy(flow_y_blk, flow_y_padded[row, col])
                                tx_flow_x = ttl.copy(flow_x_blk, flow_x_padded[row, col])
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()

    return torus_halo_pad


def make_subtile_reintegration_group_block_halo(offsets: tuple[tuple[int, int], ...]):
    """Grouped reintegration using a padded torus halo and 2x2 source blocks."""

    _require_ttlang()
    offsets, row_deltas, col_deltas, *_ = _prepare_group_geometry(offsets)
    row_delta0, _ = row_deltas
    col_delta0, _ = col_deltas
    row_pad_offset = 1 if row_delta0 < 0 else 0
    col_pad_offset = 1 if col_delta0 < 0 else 0
    offset_count = len(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_block_halo(
        mass_padded: ttnn.Tensor,
        flow_y_padded: ttnn.Tensor,
        flow_x_padded: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = out.shape[1] // TILE_SIZE
        plane_count = (mass_padded.shape[0] - out.shape[0]) // TILE_SIZE
        sx_tiles = (out.shape[0] // TILE_SIZE) // plane_count
        padded_sx_tiles = sx_tiles + 1
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass_padded, shape=(2, 2), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y_padded, shape=(2, 2), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x_padded, shape=(2, 2), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 2), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(2, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 2), block_count=2)
        mass_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            with (
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                                mass_src_dfb.wait() as mass_src_blk,
                                flow_y_src_dfb.wait() as flow_y_src_blk,
                                flow_x_src_dfb.wait() as flow_x_src_blk,
                            ):
                                for _ in range(offset_count):
                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ mass_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with mass_part_dfb.reserve() as mass_part_blk:
                                                mass_part_blk.store(tmp_blk @ col_blk)

                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ flow_y_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with flow_y_part_dfb.reserve() as flow_y_part_blk:
                                                flow_y_part_blk.store(tmp_blk @ col_blk)

                                        with tmp_dfb.reserve() as tmp_blk:
                                            tmp_blk.store(row_blk @ flow_x_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with flow_x_part_dfb.reserve() as flow_x_part_blk:
                                                flow_x_part_blk.store(tmp_blk @ col_blk)

                                    with (
                                        flow_y_part_dfb.wait() as flow_y_blk,
                                        flow_x_part_dfb.wait() as flow_x_blk,
                                        shift_y_dfb.wait() as shift_y_blk,
                                        shift_x_dfb.wait() as shift_x_blk,
                                    ):
                                        with weight_dfb.reserve() as weight_blk:
                                            adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                            adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                            adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                            adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                            raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                            raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                            wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                            wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                            weight_blk.store(wy * wx * area_scale_blk)
                                    with (
                                        mass_part_dfb.wait() as mass_blk,
                                        weight_dfb.wait() as weight_blk,
                                        total_acc_dfb.wait() as total_blk,
                                    ):
                                        with total_acc_dfb.reserve() as total_acc_blk:
                                            total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    out_spatial_row = row - plane_index * sx_tiles
                    source_row = out_spatial_row + row_pad_offset + row_delta0
                    source_tile_row = plane_index * padded_sx_tiles + source_row
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            source_col = col + col_pad_offset + col_delta0
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[row, col], prior_acc_blk)
                                tx_prior.wait()

                            with (
                                dt_dfb.reserve() as dt_blk,
                                max_flow_dfb.reserve() as max_flow_blk,
                                neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                clip_max_dfb.reserve() as clip_max_blk,
                                area_scale_dfb.reserve() as area_scale_blk,
                                zero_dfb.reserve() as zero_blk,
                            ):
                                tx_dt = ttl.copy(params[2, 0], dt_blk)
                                tx_max_flow = ttl.copy(params[3, 0], max_flow_blk)
                                tx_neg_max_flow = ttl.copy(params[4, 0], neg_max_flow_blk)
                                tx_sigma_plus_half = ttl.copy(params[5, 0], sigma_plus_half_blk)
                                tx_clip_max = ttl.copy(params[6, 0], clip_max_blk)
                                tx_area_scale = ttl.copy(params[7, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[8, 0], zero_blk)
                                tx_dt.wait()
                                tx_max_flow.wait()
                                tx_neg_max_flow.wait()
                                tx_sigma_plus_half.wait()
                                tx_clip_max.wait()
                                tx_area_scale.wait()
                                tx_zero.wait()

                            with (
                                mass_src_dfb.reserve() as mass_blk,
                                flow_y_src_dfb.reserve() as flow_y_blk,
                                flow_x_src_dfb.reserve() as flow_x_blk,
                            ):
                                tx_mass = ttl.copy(
                                    mass_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    mass_blk,
                                )
                                tx_flow_y = ttl.copy(
                                    flow_y_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    flow_y_blk,
                                )
                                tx_flow_x = ttl.copy(
                                    flow_x_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    flow_x_blk,
                                )
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()

                            for offset_index in range(offset_count):
                                param_base = offset_index * 9
                                with (
                                    row_dfb.reserve() as row_blk,
                                    col_dfb.reserve() as col_blk,
                                    shift_y_dfb.reserve() as shift_y_blk,
                                    shift_x_dfb.reserve() as shift_x_blk,
                                ):
                                    tx_row = ttl.copy(row_selectors[offset_index, 0:2], row_blk)
                                    tx_col = ttl.copy(col_selectors[2 * offset_index : 2 * offset_index + 2, 0], col_blk)
                                    tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                    tx_shift_x = ttl.copy(params[param_base + 1, 0], shift_x_blk)
                                    tx_row.wait()
                                    tx_col.wait()
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

    return subtile_reintegration_group_block_halo


def make_subtile_reintegration_group_block_halo_separable(offsets: tuple[tuple[int, int], ...]):
    """Grouped halo/block reintegration with row-factored selector reuse."""

    _require_ttlang()
    offsets, row_deltas, col_deltas, *_ = _prepare_group_geometry(offsets)
    row_delta0, _ = row_deltas
    col_delta0, _ = col_deltas
    row_pad_offset = 1 if row_delta0 < 0 else 0
    col_pad_offset = 1 if col_delta0 < 0 else 0
    row_offset_count, col_offset_count = _rectangular_offset_grid(offsets)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_reintegration_group_block_halo_separable(
        mass_padded: ttnn.Tensor,
        flow_y_padded: ttnn.Tensor,
        flow_x_padded: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        acc_in: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = out.shape[1] // TILE_SIZE
        plane_count = (mass_padded.shape[0] - out.shape[0]) // TILE_SIZE
        sx_tiles = (out.shape[0] // TILE_SIZE) // plane_count
        padded_sx_tiles = sx_tiles + 1
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_src_dfb = ttl.make_dataflow_buffer_like(mass_padded, shape=(2, 2), block_count=2)
        flow_y_src_dfb = ttl.make_dataflow_buffer_like(flow_y_padded, shape=(2, 2), block_count=2)
        flow_x_src_dfb = ttl.make_dataflow_buffer_like(flow_x_padded, shape=(2, 2), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 2), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(2, 1), block_count=2)
        mass_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_y_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        flow_x_part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        prior_acc_dfb = ttl.make_dataflow_buffer_like(acc_in, shape=(1, 1), block_count=2)
        total_acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        shift_y_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        shift_x_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        dt_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_max_flow_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        sigma_plus_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        clip_max_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        area_scale_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        weight_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            with prior_acc_dfb.wait() as prior_acc_blk:
                                with total_acc_dfb.reserve() as total_acc_blk:
                                    total_acc_blk.store(prior_acc_blk)
                            with (
                                dt_dfb.wait() as dt_blk,
                                max_flow_dfb.wait() as max_flow_blk,
                                neg_max_flow_dfb.wait() as neg_max_flow_blk,
                                sigma_plus_half_dfb.wait() as sigma_plus_half_blk,
                                clip_max_dfb.wait() as clip_max_blk,
                                area_scale_dfb.wait() as area_scale_blk,
                                zero_dfb.wait() as zero_blk,
                                mass_src_dfb.wait() as mass_src_blk,
                                flow_y_src_dfb.wait() as flow_y_src_blk,
                                flow_x_src_dfb.wait() as flow_x_src_blk,
                            ):
                                for _ in range(row_offset_count):
                                    with row_dfb.wait() as row_blk, shift_x_dfb.wait() as shift_x_blk:
                                        mass_row = row_blk @ mass_src_blk
                                        flow_y_row = row_blk @ flow_y_src_blk
                                        flow_x_row = row_blk @ flow_x_src_blk
                                        for _ in range(col_offset_count):
                                            with col_dfb.wait() as col_blk:
                                                with mass_part_dfb.reserve() as mass_part_blk:
                                                    mass_part_blk.store(mass_row @ col_blk)
                                                with flow_y_part_dfb.reserve() as flow_y_part_blk:
                                                    flow_y_part_blk.store(flow_y_row @ col_blk)
                                                with flow_x_part_dfb.reserve() as flow_x_part_blk:
                                                    flow_x_part_blk.store(flow_x_row @ col_blk)

                                            with (
                                                flow_y_part_dfb.wait() as flow_y_blk,
                                                flow_x_part_dfb.wait() as flow_x_blk,
                                                shift_y_dfb.wait() as shift_y_blk,
                                            ):
                                                with weight_dfb.reserve() as weight_blk:
                                                    adv_y_floor = ttl.math.max(flow_y_blk * dt_blk, neg_max_flow_blk)
                                                    adv_y = ttl.math.min(adv_y_floor, max_flow_blk)
                                                    adv_x_floor = ttl.math.max(flow_x_blk * dt_blk, neg_max_flow_blk)
                                                    adv_x = ttl.math.min(adv_x_floor, max_flow_blk)
                                                    raw_y = sigma_plus_half_blk - ttl.math.abs(shift_y_blk + adv_y)
                                                    raw_x = sigma_plus_half_blk - ttl.math.abs(shift_x_blk + adv_x)
                                                    wy = ttl.math.min(ttl.math.max(raw_y, zero_blk), clip_max_blk)
                                                    wx = ttl.math.min(ttl.math.max(raw_x, zero_blk), clip_max_blk)
                                                    weight_blk.store(wy * wx * area_scale_blk)
                                            with (
                                                mass_part_dfb.wait() as mass_blk,
                                                weight_dfb.wait() as weight_blk,
                                                total_acc_dfb.wait() as total_blk,
                                            ):
                                                with total_acc_dfb.reserve() as total_acc_blk:
                                                    total_acc_blk.store(total_blk + mass_blk * weight_blk)
                            with total_acc_dfb.wait() as total_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(total_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    out_spatial_row = row - plane_index * sx_tiles
                    source_row = out_spatial_row + row_pad_offset + row_delta0
                    source_tile_row = plane_index * padded_sx_tiles + source_row
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            source_col = col + col_pad_offset + col_delta0
                            with prior_acc_dfb.reserve() as prior_acc_blk:
                                tx_prior = ttl.copy(acc_in[row, col], prior_acc_blk)
                                tx_prior.wait()

                            with (
                                dt_dfb.reserve() as dt_blk,
                                max_flow_dfb.reserve() as max_flow_blk,
                                neg_max_flow_dfb.reserve() as neg_max_flow_blk,
                                sigma_plus_half_dfb.reserve() as sigma_plus_half_blk,
                                clip_max_dfb.reserve() as clip_max_blk,
                                area_scale_dfb.reserve() as area_scale_blk,
                                zero_dfb.reserve() as zero_blk,
                            ):
                                tx_dt = ttl.copy(params[2, 0], dt_blk)
                                tx_max_flow = ttl.copy(params[3, 0], max_flow_blk)
                                tx_neg_max_flow = ttl.copy(params[4, 0], neg_max_flow_blk)
                                tx_sigma_plus_half = ttl.copy(params[5, 0], sigma_plus_half_blk)
                                tx_clip_max = ttl.copy(params[6, 0], clip_max_blk)
                                tx_area_scale = ttl.copy(params[7, 0], area_scale_blk)
                                tx_zero = ttl.copy(params[8, 0], zero_blk)
                                tx_dt.wait()
                                tx_max_flow.wait()
                                tx_neg_max_flow.wait()
                                tx_sigma_plus_half.wait()
                                tx_clip_max.wait()
                                tx_area_scale.wait()
                                tx_zero.wait()

                            with (
                                mass_src_dfb.reserve() as mass_blk,
                                flow_y_src_dfb.reserve() as flow_y_blk,
                                flow_x_src_dfb.reserve() as flow_x_blk,
                            ):
                                tx_mass = ttl.copy(
                                    mass_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    mass_blk,
                                )
                                tx_flow_y = ttl.copy(
                                    flow_y_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    flow_y_blk,
                                )
                                tx_flow_x = ttl.copy(
                                    flow_x_padded[source_tile_row : source_tile_row + 2, source_col : source_col + 2],
                                    flow_x_blk,
                                )
                                tx_mass.wait()
                                tx_flow_y.wait()
                                tx_flow_x.wait()

                            for row_offset_index in range(row_offset_count):
                                row_offset_base = row_offset_index * col_offset_count
                                row_param_base = row_offset_base * 9
                                with row_dfb.reserve() as row_blk, shift_x_dfb.reserve() as shift_x_blk:
                                    tx_row = ttl.copy(row_selectors[row_offset_base, 0:2], row_blk)
                                    tx_shift_x = ttl.copy(params[row_param_base + 1, 0], shift_x_blk)
                                    tx_row.wait()
                                    tx_shift_x.wait()
                                for col_offset_index in range(col_offset_count):
                                    offset_index = row_offset_base + col_offset_index
                                    param_base = offset_index * 9
                                    with col_dfb.reserve() as col_blk, shift_y_dfb.reserve() as shift_y_blk:
                                        tx_col = ttl.copy(
                                            col_selectors[2 * offset_index : 2 * offset_index + 2, 0],
                                            col_blk,
                                        )
                                        tx_shift_y = ttl.copy(params[param_base, 0], shift_y_blk)
                                        tx_col.wait()
                                        tx_shift_y.wait()

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

    return subtile_reintegration_group_block_halo_separable


def _to_device_matrix(matrix: np.ndarray, *, device, dtype, memory_config=None):
    _require_ttlang()
    import torch

    if memory_config is None:
        memory_config = ttnn.DRAM_MEMORY_CONFIG
    return ttnn.from_torch(
        torch.from_numpy(matrix),
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
        device=device,
        memory_config=memory_config,
    )


def _make_demo_state(*, sx: int, sy: int, channels: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(31)
    rows = np.arange(sx, dtype=np.float32).reshape(1, sx, 1, 1)
    cols = np.arange(sy, dtype=np.float32).reshape(1, 1, sy, 1)
    channel_offsets = np.arange(channels, dtype=np.float32).reshape(1, 1, 1, channels)
    mass = 0.015 * rows + 0.003 * cols + 0.19 * channel_offsets
    mass += rng.uniform(-0.01, 0.01, size=(1, sx, sy, channels)).astype(np.float32)
    flow_y = 0.03 * np.sin(cols / 11.0) + 0.01 * channel_offsets
    flow_x = 0.02 * np.cos(rows / 13.0) - 0.01 * channel_offsets
    return (
        mass.astype(np.float32, copy=False),
        np.broadcast_to(flow_y, mass.shape).astype(np.float32, copy=True),
        np.broadcast_to(flow_x, mass.shape).astype(np.float32, copy=True),
    )


def run_smoke(
    *,
    sx: int,
    sy: int,
    channels: int,
    row_offset: int,
    col_offset: int,
    dt: float,
    dd: int,
    sigma: float,
    device_id: int,
    dtype_name: str,
    warmup: int,
    runs: int,
    debug_stats: bool = False,
) -> None:
    _require_ttlang()
    if sx != sy:
        raise ValueError(f"subtile_reintegration currently expects square grids, got {sx}x{sy}.")
    if sx % TILE_SIZE != 0 or sy % TILE_SIZE != 0:
        raise ValueError(f"Expected dimensions divisible by {TILE_SIZE}, got {sx}x{sy}.")
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True

    max_flow = float(dd) - float(sigma)
    mass, flow_y, flow_x = _make_demo_state(sx=sx, sy=sy, channels=channels)
    expected = subtile_reintegration_reference(
        mass,
        flow_y,
        flow_x,
        row_offset=row_offset,
        col_offset=col_offset,
        dt=dt,
        max_flow=max_flow,
        sigma=sigma,
    )
    mass_matrix, shape = lenia_state_to_plane_matrix(mass)
    flow_y_matrix, _ = lenia_state_to_plane_matrix(flow_y)
    flow_x_matrix, _ = lenia_state_to_plane_matrix(flow_x)
    out_matrix = np.zeros(shape.matrix_shape, dtype=np.float32)
    row_selectors, col_selectors = subtile_shift_selector_matrices(
        row_offset=row_offset,
        col_offset=col_offset,
    )
    params_matrix = subtile_reintegration_param_matrix(
        row_offset=row_offset,
        col_offset=col_offset,
        dt=dt,
        max_flow=max_flow,
        sigma=sigma,
    )

    for matrix in (mass_matrix, flow_y_matrix, flow_x_matrix, out_matrix, row_selectors, col_selectors, params_matrix):
        require_tiled_matrix_shape(matrix, row_block_tiles=1, col_block_tiles=1, tile_size=TILE_SIZE)

    dtype = ttnn.float32 if dtype_name == "float32" else ttnn.bfloat16
    device = ttnn.open_device(device_id=device_id)
    try:
        mass_tt = _to_device_matrix(mass_matrix, device=device, dtype=dtype)
        flow_y_tt = _to_device_matrix(flow_y_matrix, device=device, dtype=dtype)
        flow_x_tt = _to_device_matrix(flow_x_matrix, device=device, dtype=dtype)
        rows_tt = _to_device_matrix(row_selectors, device=device, dtype=dtype)
        cols_tt = _to_device_matrix(col_selectors, device=device, dtype=dtype)
        params_tt = _to_device_matrix(params_matrix, device=device, dtype=dtype)
        out_tt = _to_device_matrix(out_matrix, device=device, dtype=dtype)
        kernel = make_subtile_reintegration(row_offset=row_offset, col_offset=col_offset)
        for _ in range(warmup):
            kernel(mass_tt, flow_y_tt, flow_x_tt, rows_tt, cols_tt, params_tt, out_tt)
            ttnn.synchronize_device(device)
        started_at = time.perf_counter()
        for _ in range(runs):
            kernel(mass_tt, flow_y_tt, flow_x_tt, rows_tt, cols_tt, params_tt, out_tt)
        ttnn.synchronize_device(device)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
        actual_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
        actual = plane_matrix_to_lenia_state(actual_matrix, shape)
        max_abs = float(np.max(np.abs(actual - expected)))
        mean_abs = float(np.mean(np.abs(actual - expected)))
        max_expected = float(np.max(np.abs(expected))) if expected.size else 0.0
        tolerance = smoke_tolerance(dtype_name, expected)
        if debug_stats:
            diff = actual - expected
            source_mass_debug = subtile_shift_reference(mass, row_offset=row_offset, col_offset=col_offset)
            with np.errstate(divide="ignore", invalid="ignore"):
                actual_weight = np.where(source_mass_debug != 0.0, actual / source_mass_debug, 0.0)
                expected_weight = np.where(source_mass_debug != 0.0, expected / source_mass_debug, 0.0)
            print(
                "debug: "
                f"actual_min={float(np.min(actual)):.6g} actual_max={float(np.max(actual)):.6g} "
                f"actual_mean={float(np.mean(actual)):.6g} actual_nonzero={int(np.count_nonzero(actual))} "
                f"expected_min={float(np.min(expected)):.6g} expected_max={float(np.max(expected)):.6g} "
                f"expected_mean={float(np.mean(expected)):.6g} expected_nonzero={int(np.count_nonzero(expected))} "
                f"diff_min={float(np.min(diff)):.6g} diff_max={float(np.max(diff)):.6g}"
            )
            print(
                "debug_weight: "
                f"actual_min={float(np.min(actual_weight)):.6g} actual_max={float(np.max(actual_weight)):.6g} "
                f"actual_mean={float(np.mean(actual_weight)):.6g} "
                f"expected_min={float(np.min(expected_weight)):.6g} expected_max={float(np.max(expected_weight)):.6g} "
                f"expected_mean={float(np.mean(expected_weight)):.6g}"
            )
        print(
            f"tt-lang subtile_reintegration smoke: state={mass.shape} offset=({row_offset},{col_offset}) "
            f"dtype={dtype_name} warmup={warmup} runs={runs} mean_elapsed={mean_elapsed_ms:.3f}ms "
            f"max_abs={max_abs:.6g} mean_abs={mean_abs:.6g} max_expected={max_expected:.6g} "
            f"tolerance={tolerance:.6g}"
        )
        if max_abs > tolerance:
            raise SystemExit(f"subtile_reintegration failed: max_abs={max_abs} > {tolerance}")
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TT-Lang sub-tile reintegration primitive.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--row-offset", type=int, default=1)
    parser.add_argument("--col-offset", type=int, default=-1)
    parser.add_argument("--dt", type=float, default=0.2)
    parser.add_argument("--dd", type=int, default=5)
    parser.add_argument("--sigma", type=float, default=0.65)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--dtype", choices=["float32", "bfloat16"], default="bfloat16")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--debug-stats", action="store_true")
    args = parser.parse_args()
    if args.tt_visible_devices is not None:
        os.environ["TT_VISIBLE_DEVICES"] = args.tt_visible_devices
    run_smoke(
        sx=args.sx,
        sy=args.sy,
        channels=args.channels,
        row_offset=args.row_offset,
        col_offset=args.col_offset,
        dt=args.dt,
        dd=args.dd,
        sigma=args.sigma,
        device_id=args.device_id,
        dtype_name=args.dtype,
        warmup=args.warmup,
        runs=args.runs,
        debug_stats=args.debug_stats,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
