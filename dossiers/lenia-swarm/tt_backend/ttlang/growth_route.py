from __future__ import annotations

import argparse
import linecache
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

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
except ImportError as exc:
    raise SystemExit(
        "ttlang/growth_route.py requires a TT-Lang environment with importable ttl and ttnn."
    ) from exc


TILE_SIZE = 32
ROW_BLOCK_TILES = 2
COL_BLOCK_TILES = 2


@ttl.operation(grid="auto")
def growth_route(
    uk: ttnn.Tensor,
    params: ttnn.Tensor,
    out: ttnn.Tensor,
) -> None:
    row_tiles_per_block = ROW_BLOCK_TILES
    col_tiles_per_block = COL_BLOCK_TILES
    sx_tiles = uk.shape[1] // TILE_SIZE
    nb_k = uk.shape[0] // uk.shape[1]
    channels = out.shape[0] // out.shape[1]
    rows = out.shape[0] // TILE_SIZE // row_tiles_per_block
    cols = out.shape[1] // TILE_SIZE // col_tiles_per_block
    grid_cols, grid_rows = ttl.grid_size(dims=2)
    rows_per_node = -(-rows // grid_rows)
    cols_per_node = -(-cols // grid_cols)

    uk_dfb = ttl.make_dataflow_buffer_like(uk, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
    m_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    inv_s_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    h_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    route_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    neg_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    two_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    minus_one_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    # Keep routed kernel accumulation in a compute-local CB. This follows TT-Lang's matmul_acc
    # example and avoids relying on pack-to-output-CB accumulation across kernel routes.
    acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
    out_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)

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
                        for kernel_index in range(nb_k):
                            with (
                                uk_dfb.wait() as uk_blk,
                                m_dfb.wait() as m_tile,
                                inv_s_dfb.wait() as inv_s_tile,
                                h_dfb.wait() as h_tile,
                                route_dfb.wait() as route_tile,
                                neg_half_dfb.wait() as neg_half_tile,
                                two_dfb.wait() as two_tile,
                                minus_one_dfb.wait() as minus_one_tile,
                                acc_dfb.wait() as prev,
                            ):
                                with acc_dfb.reserve() as acc_blk:
                                    m_blk = ttl.math.broadcast(m_tile, acc_blk, dims=[0, 1])
                                    inv_s_blk = ttl.math.broadcast(inv_s_tile, acc_blk, dims=[0, 1])
                                    h_blk = ttl.math.broadcast(h_tile, acc_blk, dims=[0, 1])
                                    route_blk = ttl.math.broadcast(route_tile, acc_blk, dims=[0, 1])
                                    neg_half_blk = ttl.math.broadcast(neg_half_tile, acc_blk, dims=[0, 1])
                                    two_blk = ttl.math.broadcast(two_tile, acc_blk, dims=[0, 1])
                                    minus_one_blk = ttl.math.broadcast(minus_one_tile, acc_blk, dims=[0, 1])
                                    diff = (uk_blk - m_blk) * inv_s_blk
                                    grown = (ttl.math.exp(diff * diff * neg_half_blk) * two_blk + minus_one_blk) * h_blk
                                    acc_blk.store(prev + grown * route_blk)
                        with acc_dfb.wait() as acc_blk:
                            with out_dfb.reserve() as out_blk:
                                out_blk.store(acc_blk)

    @ttl.datamovement()
    def read():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                row_start = row * row_tiles_per_block
                out_plane = row_start // sx_tiles
                batch_index = out_plane // channels
                out_channel = out_plane % channels
                source_row_offset = row_start % sx_tiles
                source_row_end = source_row_offset + row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = col_start + col_tiles_per_block
                        for kernel_index in range(nb_k):
                            with (
                                uk_dfb.reserve() as uk_blk,
                                m_dfb.reserve() as m_tile,
                                inv_s_dfb.reserve() as inv_s_tile,
                                h_dfb.reserve() as h_tile,
                                route_dfb.reserve() as route_tile,
                                neg_half_dfb.reserve() as neg_half_tile,
                                two_dfb.reserve() as two_tile,
                                minus_one_dfb.reserve() as minus_one_tile,
                            ):
                                source_plane = batch_index * nb_k + kernel_index
                                source_row_start = source_plane * sx_tiles + source_row_offset
                                source_row_stop = source_plane * sx_tiles + source_row_end
                                route_row = 3 * nb_k + out_channel * nb_k + kernel_index
                                constants_base = 3 * nb_k + channels * nb_k
                                tx_uk = ttl.copy(uk[source_row_start:source_row_stop, col_start:col_end], uk_blk)
                                tx_m = ttl.copy(params[kernel_index, 0], m_tile)
                                tx_inv_s = ttl.copy(params[nb_k + kernel_index, 0], inv_s_tile)
                                tx_h = ttl.copy(params[2 * nb_k + kernel_index, 0], h_tile)
                                tx_route = ttl.copy(params[route_row, 0], route_tile)
                                tx_neg_half = ttl.copy(params[constants_base, 0], neg_half_tile)
                                tx_two = ttl.copy(params[constants_base + 1, 0], two_tile)
                                tx_minus_one = ttl.copy(params[constants_base + 2, 0], minus_one_tile)
                                tx_uk.wait()
                                tx_m.wait()
                                tx_inv_s.wait()
                                tx_h.wait()
                                tx_route.wait()
                                tx_neg_half.wait()
                                tx_two.wait()
                                tx_minus_one.wait()

    @ttl.datamovement()
    def write():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                row_start = row * row_tiles_per_block
                row_end = row_start + row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = col_start + col_tiles_per_block
                        with out_dfb.wait() as out_blk:
                            tx = ttl.copy(out_blk, out[row_start:row_end, col_start:col_end])
                            tx.wait()


def make_growth_route(*, batch: int, channels: int, nb_k: int):
    batch = int(batch)
    channels = int(channels)
    nb_k = int(nb_k)
    if batch <= 0 or channels <= 0 or nb_k <= 0:
        raise ValueError(f"Expected positive batch/channels/nb_k, got {batch}/{channels}/{nb_k}.")

    @ttl.operation(grid="auto")
    def growth_route_contextual(
        uk: ttnn.Tensor,
        params: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        row_tiles_per_block = ROW_BLOCK_TILES
        col_tiles_per_block = COL_BLOCK_TILES
        sx_tiles = uk.shape[1] // TILE_SIZE
        rows = out.shape[0] // TILE_SIZE // row_tiles_per_block
        cols = out.shape[1] // TILE_SIZE // col_tiles_per_block
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        uk_dfb = ttl.make_dataflow_buffer_like(uk, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
        m_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        inv_s_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        h_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        route_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        neg_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        two_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        minus_one_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
        out_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)

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
                            for kernel_index in range(nb_k):
                                with (
                                    uk_dfb.wait() as uk_blk,
                                    m_dfb.wait() as m_tile,
                                    inv_s_dfb.wait() as inv_s_tile,
                                    h_dfb.wait() as h_tile,
                                    route_dfb.wait() as route_tile,
                                    neg_half_dfb.wait() as neg_half_tile,
                                    two_dfb.wait() as two_tile,
                                    minus_one_dfb.wait() as minus_one_tile,
                                    acc_dfb.wait() as prev,
                                ):
                                    with acc_dfb.reserve() as acc_blk:
                                        m_blk = ttl.math.broadcast(m_tile, acc_blk, dims=[0, 1])
                                        inv_s_blk = ttl.math.broadcast(inv_s_tile, acc_blk, dims=[0, 1])
                                        h_blk = ttl.math.broadcast(h_tile, acc_blk, dims=[0, 1])
                                        route_blk = ttl.math.broadcast(route_tile, acc_blk, dims=[0, 1])
                                        neg_half_blk = ttl.math.broadcast(neg_half_tile, acc_blk, dims=[0, 1])
                                        two_blk = ttl.math.broadcast(two_tile, acc_blk, dims=[0, 1])
                                        minus_one_blk = ttl.math.broadcast(minus_one_tile, acc_blk, dims=[0, 1])
                                        diff = (uk_blk - m_blk) * inv_s_blk
                                        grown = (ttl.math.exp(diff * diff * neg_half_blk) * two_blk + minus_one_blk) * h_blk
                                        acc_blk.store(prev + grown * route_blk)
                            with acc_dfb.wait() as acc_blk:
                                with out_dfb.reserve() as out_blk:
                                    out_blk.store(acc_blk)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    row_start = row * row_tiles_per_block
                    out_plane = row_start // sx_tiles
                    batch_index = out_plane // channels
                    out_channel = out_plane % channels
                    source_row_offset = row_start % sx_tiles
                    source_row_end = source_row_offset + row_tiles_per_block
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            col_start = col * col_tiles_per_block
                            col_end = col_start + col_tiles_per_block
                            for kernel_index in range(nb_k):
                                with (
                                    uk_dfb.reserve() as uk_blk,
                                    m_dfb.reserve() as m_tile,
                                    inv_s_dfb.reserve() as inv_s_tile,
                                    h_dfb.reserve() as h_tile,
                                    route_dfb.reserve() as route_tile,
                                    neg_half_dfb.reserve() as neg_half_tile,
                                    two_dfb.reserve() as two_tile,
                                    minus_one_dfb.reserve() as minus_one_tile,
                                ):
                                    source_plane = batch_index * nb_k + kernel_index
                                    source_row_start = source_plane * sx_tiles + source_row_offset
                                    source_row_stop = source_plane * sx_tiles + source_row_end
                                    route_row = 3 * nb_k + out_channel * nb_k + kernel_index
                                    constants_base = 3 * nb_k + channels * nb_k
                                    tx_uk = ttl.copy(uk[source_row_start:source_row_stop, col_start:col_end], uk_blk)
                                    tx_m = ttl.copy(params[kernel_index, 0], m_tile)
                                    tx_inv_s = ttl.copy(params[nb_k + kernel_index, 0], inv_s_tile)
                                    tx_h = ttl.copy(params[2 * nb_k + kernel_index, 0], h_tile)
                                    tx_route = ttl.copy(params[route_row, 0], route_tile)
                                    tx_neg_half = ttl.copy(params[constants_base, 0], neg_half_tile)
                                    tx_two = ttl.copy(params[constants_base + 1, 0], two_tile)
                                    tx_minus_one = ttl.copy(params[constants_base + 2, 0], minus_one_tile)
                                    tx_uk.wait()
                                    tx_m.wait()
                                    tx_inv_s.wait()
                                    tx_h.wait()
                                    tx_route.wait()
                                    tx_neg_half.wait()
                                    tx_two.wait()
                                    tx_minus_one.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    row_start = row * row_tiles_per_block
                    row_end = row_start + row_tiles_per_block
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            col_start = col * col_tiles_per_block
                            col_end = col_start + col_tiles_per_block
                            with out_dfb.wait() as out_blk:
                                tx = ttl.copy(out_blk, out[row_start:row_end, col_start:col_end])
                                tx.wait()

    return growth_route_contextual


def _kernel_name_for_route(
    *,
    batch: int,
    channels: int,
    nb_k: int,
    sx: int,
    sy: int,
    channel_index: int,
    route: tuple[int, ...],
    accumulate: bool,
) -> str:
    route_suffix = "_".join(str(kernel_index) for kernel_index in route) or "empty"
    mode_suffix = "acc" if accumulate else "init"
    return f"growth_route_{mode_suffix}_ch{channel_index}_b{batch}_c{channels}_k{nb_k}_s{sx}x{sy}_r{route_suffix}"


def _emit_route_statements(
    *,
    route: tuple[int, ...],
    nb_k: int,
    channels: int,
    indent: str,
) -> tuple[str, str]:
    compute_parts: list[str] = []
    read_parts: list[str] = []
    constants_base = 3 * nb_k + channels * nb_k
    for kernel_index in route:
        compute_parts.append(
            f"""{indent}with (
{indent}    uk_dfb.wait() as uk_blk,
{indent}    m_dfb.wait() as m_tile,
{indent}    inv_s_dfb.wait() as inv_s_tile,
{indent}    h_dfb.wait() as h_tile,
{indent}    neg_half_dfb.wait() as neg_half_tile,
{indent}    two_dfb.wait() as two_tile,
{indent}    minus_one_dfb.wait() as minus_one_tile,
{indent}    acc_dfb.wait() as prev,
{indent}):
{indent}    with acc_dfb.reserve() as acc_blk:
{indent}        m_blk = ttl.math.broadcast(m_tile, acc_blk, dims=[0, 1])
{indent}        inv_s_blk = ttl.math.broadcast(inv_s_tile, acc_blk, dims=[0, 1])
{indent}        h_blk = ttl.math.broadcast(h_tile, acc_blk, dims=[0, 1])
{indent}        neg_half_blk = ttl.math.broadcast(neg_half_tile, acc_blk, dims=[0, 1])
{indent}        two_blk = ttl.math.broadcast(two_tile, acc_blk, dims=[0, 1])
{indent}        minus_one_blk = ttl.math.broadcast(minus_one_tile, acc_blk, dims=[0, 1])
{indent}        diff = (uk_blk - m_blk) * inv_s_blk
{indent}        grown = (ttl.math.exp(diff * diff * neg_half_blk) * two_blk + minus_one_blk) * h_blk
{indent}        acc_blk.store(prev + grown)"""
        )
        read_parts.append(
            f"""{indent}with (
{indent}    uk_dfb.reserve() as uk_blk,
{indent}    m_dfb.reserve() as m_tile,
{indent}    inv_s_dfb.reserve() as inv_s_tile,
{indent}    h_dfb.reserve() as h_tile,
{indent}    neg_half_dfb.reserve() as neg_half_tile,
{indent}    two_dfb.reserve() as two_tile,
{indent}    minus_one_dfb.reserve() as minus_one_tile,
{indent}):
{indent}    source_plane = batch_index * {nb_k} + {kernel_index}
{indent}    source_row_start = source_plane * sx_tiles + source_row_offset
{indent}    source_row_stop = source_plane * sx_tiles + source_row_end
{indent}    tx_uk = ttl.copy(uk[source_row_start:source_row_stop, col_start:col_end], uk_blk)
{indent}    tx_m = ttl.copy(params[{kernel_index}, 0], m_tile)
{indent}    tx_inv_s = ttl.copy(params[{nb_k + kernel_index}, 0], inv_s_tile)
{indent}    tx_h = ttl.copy(params[{2 * nb_k + kernel_index}, 0], h_tile)
{indent}    tx_neg_half = ttl.copy(params[{constants_base}, 0], neg_half_tile)
{indent}    tx_two = ttl.copy(params[{constants_base + 1}, 0], two_tile)
{indent}    tx_minus_one = ttl.copy(params[{constants_base + 2}, 0], minus_one_tile)
{indent}    tx_uk.wait()
{indent}    tx_m.wait()
{indent}    tx_inv_s.wait()
{indent}    tx_h.wait()
{indent}    tx_neg_half.wait()
{indent}    tx_two.wait()
{indent}    tx_minus_one.wait()"""
        )
    return "\n".join(compute_parts), "\n".join(read_parts)


def make_growth_route_channel_unrolled(
    *,
    batch: int,
    channels: int,
    nb_k: int,
    sx: int,
    sy: int,
    channel_index: int,
    route: tuple[int, ...],
    accumulate: bool = False,
):
    batch = int(batch)
    channels = int(channels)
    nb_k = int(nb_k)
    sx = int(sx)
    sy = int(sy)
    channel_index = int(channel_index)
    route = tuple(int(kernel_index) for kernel_index in route)
    if batch <= 0 or channels <= 0 or nb_k <= 0:
        raise ValueError(f"Expected positive batch/channels/nb_k, got {batch}/{channels}/{nb_k}.")
    if sx <= 0 or sy <= 0 or sx % (TILE_SIZE * ROW_BLOCK_TILES) != 0 or sy % (TILE_SIZE * COL_BLOCK_TILES) != 0:
        raise ValueError(f"Expected sx/sy divisible by 64, got {sx}x{sy}.")
    if channel_index < 0 or channel_index >= channels:
        raise ValueError(f"Invalid channel_index={channel_index} for {channels} channels.")
    for kernel_index in route:
        if kernel_index < 0 or kernel_index >= nb_k:
            raise ValueError(f"Invalid kernel index {kernel_index} in route for channel {channel_index}.")

    name = _kernel_name_for_route(
        batch=batch,
        channels=channels,
        nb_k=nb_k,
        sx=sx,
        sy=sy,
        channel_index=channel_index,
        route=route,
        accumulate=accumulate,
    )
    compute_route, read_route = _emit_route_statements(
        route=route,
        nb_k=nb_k,
        channels=channels,
        indent="                        ",
    )
    compute_route = compute_route or "                        pass"
    read_route = read_route or "                        pass"
    sx_tiles = sx // TILE_SIZE
    rows = batch * sx_tiles // ROW_BLOCK_TILES
    channel_rows = sx_tiles // ROW_BLOCK_TILES
    cols = sy // TILE_SIZE // COL_BLOCK_TILES
    source_plane_base = channel_index * sx_tiles
    init_dfb_decl = (
        "    init_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)\n"
        if accumulate
        else ""
    )
    init_compute = (
        """                        with init_dfb.wait() as init_blk:
                            with acc_dfb.reserve() as acc_blk:
                                acc_blk.store(init_blk)"""
        if accumulate
        else """                        with acc_dfb.reserve() as acc_blk:
                            acc_blk.store(ttl.math.fill(acc_blk, 0.0))"""
    )
    init_read = (
        f"""                        out_row_start = batch_index * {channels * sx_tiles} + {source_plane_base} + source_row_offset
                        out_row_end = out_row_start + row_tiles_per_block
                        with init_dfb.reserve() as init_blk:
                            tx_init = ttl.copy(out[out_row_start:out_row_end, col_start:col_end], init_blk)
                            tx_init.wait()"""
        if accumulate
        else ""
    )

    source = f'''
@ttl.operation(grid="auto")
def {name}(uk: ttnn.Tensor, params: ttnn.Tensor, out: ttnn.Tensor) -> None:
    row_tiles_per_block = {ROW_BLOCK_TILES}
    col_tiles_per_block = {COL_BLOCK_TILES}
    sx_tiles = {sx_tiles}
    rows = {rows}
    channel_rows = {channel_rows}
    cols = {cols}
    grid_cols, grid_rows = ttl.grid_size(dims=2)
    rows_per_node = -(-rows // grid_rows)
    cols_per_node = -(-cols // grid_cols)

    uk_dfb = ttl.make_dataflow_buffer_like(uk, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
    m_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    inv_s_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    h_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    neg_half_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    two_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
    minus_one_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
{init_dfb_decl.rstrip()}
    acc_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)
    out_dfb = ttl.make_dataflow_buffer_like(out, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2)

    @ttl.compute()
    def compute():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
{init_compute}
{compute_route}
                        with acc_dfb.wait() as acc_blk:
                            with out_dfb.reserve() as out_blk:
                                out_blk.store(acc_blk)

    @ttl.datamovement()
    def read():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                batch_index = row // channel_rows
                source_row_offset = (row - batch_index * channel_rows) * row_tiles_per_block
                source_row_end = source_row_offset + row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = col_start + col_tiles_per_block
{init_read}
{read_route}

    @ttl.datamovement()
    def write():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                batch_index = row // channel_rows
                source_row_offset = (row - batch_index * channel_rows) * row_tiles_per_block
                out_row_start = batch_index * {channels * sx_tiles} + {source_plane_base} + source_row_offset
                out_row_end = out_row_start + row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = col_start + col_tiles_per_block
                        with out_dfb.wait() as out_blk:
                            tx = ttl.copy(out_blk, out[out_row_start:out_row_end, col_start:col_end])
                            tx.wait()
'''.lstrip()
    filename = f"<ttlang_{name}>"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    namespace: dict[str, object] = {"ttl": ttl, "ttnn": ttnn}
    exec(compile(source, filename, "exec"), namespace)
    return namespace[name]


def growth_route_param_matrix(
    *,
    m: np.ndarray,
    s: np.ndarray,
    h: np.ndarray,
    c1_mask: np.ndarray,
) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    s = np.asarray(s, dtype=np.float32)
    h = np.asarray(h, dtype=np.float32)
    c1_mask = np.asarray(c1_mask, dtype=np.float32)
    if m.ndim != 1 or s.shape != m.shape or h.shape != m.shape:
        raise ValueError(f"Expected m/s/h vectors with matching shape, got {m.shape}, {s.shape}, {h.shape}.")
    if c1_mask.shape[1] != m.shape[0]:
        raise ValueError(f"Expected c1_mask second dimension {m.shape[0]}, got {c1_mask.shape}.")
    values = np.concatenate([m, 1.0 / s, h, c1_mask.reshape(-1), [-0.5, 2.0, -1.0]]).astype(
        np.float32,
        copy=False,
    )
    matrix = np.empty((values.shape[0] * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = value
    return matrix


def _growth_route_reference(
    uk: np.ndarray,
    *,
    m: np.ndarray,
    s: np.ndarray,
    h: np.ndarray,
    c1_mask: np.ndarray,
) -> np.ndarray:
    diff = (uk - m.reshape(1, 1, 1, -1)) / s.reshape(1, 1, 1, -1)
    grown = (2.0 * np.exp(-0.5 * diff * diff) - 1.0) * h.reshape(1, 1, 1, -1)
    return np.einsum("bxyk,ck->bxyc", grown, c1_mask).astype(np.float32)


def _to_device_matrix(matrix: np.ndarray, *, device):
    return ttnn.from_torch(
        torch.from_numpy(matrix),
        dtype=ttnn.bfloat16,
        layout=ttnn.TILE_LAYOUT,
        device=device,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
    )


def run_smoke(
    *,
    sx: int,
    sy: int,
    batch: int,
    nb_k: int,
    channels: int,
    device_id: int,
    warmup: int,
    runs: int,
    mode: str,
    specialized_chunk_size: int,
) -> None:
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if mode not in {"generic", "specialized", "both"}:
        raise ValueError(f"Unknown growth_route smoke mode: {mode}.")
    if specialized_chunk_size <= 0:
        raise ValueError(f"Expected specialized_chunk_size > 0, got {specialized_chunk_size}.")
    if batch != 1:
        raise ValueError("growth_route currently derives nb_k/channels from square batch=1 matrices.")
    if sx != sy:
        raise ValueError(f"growth_route currently supports square grids, got {sx}x{sy}.")
    if sx % (TILE_SIZE * ROW_BLOCK_TILES) != 0 or sy % (TILE_SIZE * COL_BLOCK_TILES) != 0:
        raise ValueError(f"Expected sx/sy divisible by 64, got {sx}x{sy}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True

    rng = np.random.default_rng(3)
    uk = rng.uniform(0.0, 1.0, size=(batch, sx, sy, nb_k)).astype(np.float32)
    m = rng.uniform(0.15, 0.35, size=nb_k).astype(np.float32)
    s = rng.uniform(0.08, 0.25, size=nb_k).astype(np.float32)
    h = rng.uniform(0.4, 0.95, size=nb_k).astype(np.float32)
    c1_mask = (rng.uniform(0.0, 1.0, size=(channels, nb_k)) > 0.5).astype(np.float32)
    for channel in range(channels):
        if not np.any(c1_mask[channel]):
            c1_mask[channel, channel % nb_k] = 1.0
    expected = _growth_route_reference(uk, m=m, s=s, h=h, c1_mask=c1_mask)

    uk_matrix, uk_shape = lenia_state_to_plane_matrix(uk)
    out_matrix = np.zeros((batch * channels * sx, sy), dtype=np.float32)
    params_matrix = growth_route_param_matrix(m=m, s=s, h=h, c1_mask=c1_mask)
    require_tiled_matrix_shape(
        uk_matrix,
        row_block_tiles=ROW_BLOCK_TILES,
        col_block_tiles=COL_BLOCK_TILES,
        tile_size=TILE_SIZE,
    )
    require_tiled_matrix_shape(
        out_matrix,
        row_block_tiles=ROW_BLOCK_TILES,
        col_block_tiles=COL_BLOCK_TILES,
        tile_size=TILE_SIZE,
    )

    device = ttnn.open_device(device_id=device_id)
    try:
        uk_tt = _to_device_matrix(uk_matrix, device=device)
        params_tt = _to_device_matrix(params_matrix, device=device)

        def run_kernel_set(label: str, kernels: tuple[object, ...]) -> None:
            out_tt = _to_device_matrix(out_matrix, device=device)
            try:
                for _ in range(warmup):
                    for kernel in kernels:
                        kernel(uk_tt, params_tt, out_tt)
                    ttnn.synchronize_device(device)
                started_at = time.perf_counter()
                for _ in range(runs):
                    for kernel in kernels:
                        kernel(uk_tt, params_tt, out_tt)
                ttnn.synchronize_device(device)
                mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
                result_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
                result = plane_matrix_to_lenia_state(
                    result_matrix,
                    type(uk_shape)(batch=uk_shape.batch, sx=uk_shape.sx, sy=uk_shape.sy, channels=channels),
                )
                max_abs = float(np.max(np.abs(result - expected)))
                mean_abs = float(np.mean(np.abs(result - expected)))
                print(
                    f"tt-lang growth_route {label}: shape={uk.shape}->{result.shape} warmup={warmup} runs={runs} "
                    f"mean_elapsed={mean_elapsed_ms:.3f}ms max_abs={max_abs:.6g} mean_abs={mean_abs:.6g}"
                )
                max_abs_tol = max(0.08, 0.01 * nb_k)
                mean_abs_tol = max(0.02, 0.002 * nb_k)
                if max_abs > max_abs_tol or mean_abs > mean_abs_tol:
                    raise SystemExit(
                        f"tt-lang growth_route {label} failed: max_abs={max_abs}, mean_abs={mean_abs} "
                        f"tol=({max_abs_tol}, {mean_abs_tol})"
                    )
            finally:
                try:
                    ttnn.deallocate(out_tt)
                except Exception:
                    pass

        if mode in {"generic", "both"}:
            run_kernel_set("generic", (growth_route,))
        if mode in {"specialized", "both"}:
            kernels = []
            for channel in range(channels):
                route = tuple(int(index) for index in np.flatnonzero(c1_mask[channel]))
                chunks = tuple(
                    route[start : start + specialized_chunk_size]
                    for start in range(0, len(route), specialized_chunk_size)
                ) or ((),)
                for chunk_index, chunk in enumerate(chunks):
                    kernels.append(
                        make_growth_route_channel_unrolled(
                            batch=batch,
                            channels=channels,
                            nb_k=nb_k,
                            sx=sx,
                            sy=sy,
                            channel_index=channel,
                            route=chunk,
                            accumulate=chunk_index > 0,
                        )
                    )
            run_kernel_set("specialized", kernels)
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test generic TT-Lang Lenia growth+route.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--nb-k", type=int, default=4)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--mode", choices=["generic", "specialized", "both"], default="generic")
    parser.add_argument("--specialized-chunk-size", type=int, default=4)
    args = parser.parse_args()
    if args.tt_visible_devices is not None:
        os.environ["TT_VISIBLE_DEVICES"] = args.tt_visible_devices
    run_smoke(
        sx=args.sx,
        sy=args.sy,
        batch=args.batch,
        nb_k=args.nb_k,
        channels=args.channels,
        device_id=args.device_id,
        warmup=args.warmup,
        runs=args.runs,
        mode=args.mode,
        specialized_chunk_size=args.specialized_chunk_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
