"""TT-Lang probe for pixel-shifted tiled Lenia windows.

Lenia reintegration needs source windows shifted by -dd..dd pixels, not whole
tiles. TT-Lang hardware interop currently wants tiled tensors, so this probe
constructs a sub-tile shifted 32x32 window from neighboring 32x32 tiles using
sparse row/column selector tiles and TT matmul.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
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


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit("ttlang/subtile_shift.py requires importable ttl and ttnn.")


def _validate_offset(offset: int) -> None:
    if offset <= -TILE_SIZE or offset >= TILE_SIZE:
        raise ValueError(f"Expected sub-tile offset in (-{TILE_SIZE}, {TILE_SIZE}), got {offset}.")


def subtile_part_tile_deltas(offset: int) -> tuple[int, int]:
    _validate_offset(offset)
    if offset >= 0:
        return (0, 1)
    return (-1, 0)


def _delta_terms(delta: int) -> tuple[int, int, int]:
    return (
        delta if delta > 0 else 0,
        -delta if delta < 0 else 0,
        1 if delta < 0 else 0,
    )


def subtile_shift_selector_matrices(*, row_offset: int, col_offset: int) -> tuple[np.ndarray, np.ndarray]:
    """Return stacked row/column selector tiles for a pixel offset.

    Row selectors use [out_row, source_row] layout for left matmul. Column
    selectors use [source_col, out_col] layout for right matmul.
    """
    _validate_offset(row_offset)
    _validate_offset(col_offset)
    row_deltas = subtile_part_tile_deltas(row_offset)
    col_deltas = subtile_part_tile_deltas(col_offset)
    row_selectors = np.zeros((2, TILE_SIZE, TILE_SIZE), dtype=np.float32)
    col_selectors = np.zeros((2, TILE_SIZE, TILE_SIZE), dtype=np.float32)

    for part, tile_delta in enumerate(row_deltas):
        for out_row in range(TILE_SIZE):
            source_row = out_row + row_offset - tile_delta * TILE_SIZE
            if 0 <= source_row < TILE_SIZE:
                row_selectors[part, out_row, source_row] = 1.0

    for part, tile_delta in enumerate(col_deltas):
        for out_col in range(TILE_SIZE):
            source_col = out_col + col_offset - tile_delta * TILE_SIZE
            if 0 <= source_col < TILE_SIZE:
                col_selectors[part, source_col, out_col] = 1.0

    return (
        row_selectors.reshape(2 * TILE_SIZE, TILE_SIZE),
        col_selectors.reshape(2 * TILE_SIZE, TILE_SIZE),
    )


def subtile_shift_reference(state: np.ndarray, *, row_offset: int, col_offset: int) -> np.ndarray:
    if state.ndim != 4:
        raise ValueError(f"Expected Lenia state [batch, sx, sy, channels], got {state.shape}.")
    _validate_offset(row_offset)
    _validate_offset(col_offset)
    return np.roll(np.roll(state, -row_offset, axis=1), -col_offset, axis=2).astype(
        np.float32,
        copy=False,
    )


def make_subtile_shift(*, row_offset: int, col_offset: int):
    _require_ttlang()
    _validate_offset(row_offset)
    _validate_offset(col_offset)
    row_delta0, row_delta1 = subtile_part_tile_deltas(row_offset)
    col_delta0, col_delta1 = subtile_part_tile_deltas(col_offset)
    row_add0, row_back0, row_wrap0 = _delta_terms(row_delta0)
    row_add1, row_back1, row_wrap1 = _delta_terms(row_delta1)
    col_add0, col_back0, col_wrap0 = _delta_terms(col_delta0)
    col_add1, col_back1, col_wrap1 = _delta_terms(col_delta1)

    @ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
    def subtile_shift(
        src: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        out: ttnn.Tensor,
    ) -> None:
        sy_tiles = src.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = src.shape[0] // src.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        src_dfb = ttl.make_dataflow_buffer_like(src, shape=(1, 1), block_count=2)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=2)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out, shape=(1, 1), block_count=2)
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
                            for _ in range(4):
                                with row_dfb.wait() as row_blk, src_dfb.wait() as src_blk:
                                    with tmp_dfb.reserve() as tmp_blk:
                                        tmp_blk.store(row_blk @ src_blk)
                                with tmp_dfb.wait() as tmp_blk, col_dfb.wait() as col_blk:
                                    with part_dfb.reserve() as part_blk:
                                        part_blk.store(tmp_blk @ col_blk)
                                with part_dfb.wait() as part_blk, acc_dfb.wait() as prev_blk:
                                    with acc_dfb.reserve() as acc_blk:
                                        acc_blk.store(prev_blk + part_blk)
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
                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add0 + row_wrap0 * sx_tiles - row_back0) % sx_tiles
                            source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                            source_col = (col + col_add0 + col_wrap0 * sy_tiles - col_back0) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + row_add1 + row_wrap1 * sx_tiles - row_back1) % sx_tiles
                            source_col = (col + col_add1 + col_wrap1 * sy_tiles - col_back1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

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

    return subtile_shift


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


def _make_demo_state(*, sx: int, sy: int, channels: int) -> np.ndarray:
    rng = np.random.default_rng(29)
    rows = np.arange(sx, dtype=np.float32).reshape(1, sx, 1, 1)
    cols = np.arange(sy, dtype=np.float32).reshape(1, 1, sy, 1)
    channel_offsets = np.arange(channels, dtype=np.float32).reshape(1, 1, 1, channels)
    state = 0.013 * rows + 0.002 * cols + 0.25 * channel_offsets
    state += rng.uniform(-0.01, 0.01, size=(1, sx, sy, channels)).astype(np.float32)
    return state.astype(np.float32, copy=False)


def smoke_tolerance(dtype_name: str, expected: np.ndarray) -> float:
    max_expected = float(np.max(np.abs(expected))) if expected.size else 0.0
    if dtype_name == "float32":
        return max(1.0e-3, 1.0e-4 * max_expected)
    if dtype_name == "bfloat16":
        return max(5.0e-2, 1.5e-2 * max_expected)
    raise ValueError(f"Unsupported dtype {dtype_name!r}.")


def run_smoke(
    *,
    sx: int,
    sy: int,
    channels: int,
    row_offset: int,
    col_offset: int,
    device_id: int,
    dtype_name: str,
    warmup: int,
    runs: int,
) -> None:
    _require_ttlang()
    if sx != sy:
        raise ValueError(f"subtile_shift currently expects square grids, got {sx}x{sy}.")
    if sx % TILE_SIZE != 0 or sy % TILE_SIZE != 0:
        raise ValueError(f"Expected dimensions divisible by {TILE_SIZE}, got {sx}x{sy}.")
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True

    state = _make_demo_state(sx=sx, sy=sy, channels=channels)
    expected = subtile_shift_reference(state, row_offset=row_offset, col_offset=col_offset)
    src_matrix, shape = lenia_state_to_plane_matrix(state)
    expected_matrix, _ = lenia_state_to_plane_matrix(expected)
    out_matrix = np.zeros(shape.matrix_shape, dtype=np.float32)
    row_selectors, col_selectors = subtile_shift_selector_matrices(
        row_offset=row_offset,
        col_offset=col_offset,
    )

    for matrix in (src_matrix, out_matrix, row_selectors, col_selectors):
        require_tiled_matrix_shape(matrix, row_block_tiles=1, col_block_tiles=1, tile_size=TILE_SIZE)

    dtype = ttnn.float32 if dtype_name == "float32" else ttnn.bfloat16
    device = ttnn.open_device(device_id=device_id)
    try:
        src_tt = _to_device_matrix(src_matrix, device=device, dtype=dtype)
        rows_tt = _to_device_matrix(row_selectors, device=device, dtype=dtype)
        cols_tt = _to_device_matrix(col_selectors, device=device, dtype=dtype)
        out_tt = _to_device_matrix(out_matrix, device=device, dtype=dtype)
        kernel = make_subtile_shift(row_offset=row_offset, col_offset=col_offset)
        for _ in range(warmup):
            kernel(src_tt, rows_tt, cols_tt, out_tt)
            ttnn.synchronize_device(device)
        started_at = time.perf_counter()
        for _ in range(runs):
            kernel(src_tt, rows_tt, cols_tt, out_tt)
        ttnn.synchronize_device(device)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
        actual_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
        actual = plane_matrix_to_lenia_state(actual_matrix, shape)
        max_abs = float(np.max(np.abs(actual - expected)))
        mean_abs = float(np.mean(np.abs(actual - expected)))
        max_expected = float(np.max(np.abs(expected_matrix))) if expected_matrix.size else 0.0
        tolerance = smoke_tolerance(dtype_name, expected)
        print(
            f"tt-lang subtile_shift smoke: state={state.shape} offset=({row_offset},{col_offset}) "
            f"dtype={dtype_name} warmup={warmup} runs={runs} mean_elapsed={mean_elapsed_ms:.3f}ms "
            f"max_abs={max_abs:.6g} mean_abs={mean_abs:.6g} max_expected={max_expected:.6g} "
            f"tolerance={tolerance:.6g}"
        )
        if max_abs > tolerance:
            raise SystemExit(f"subtile_shift failed: max_abs={max_abs} > {tolerance}")
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TT-Lang sub-tile shift primitive.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--row-offset", type=int, default=5)
    parser.add_argument("--col-offset", type=int, default=-3)
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
        row_offset=args.row_offset,
        col_offset=args.col_offset,
        device_id=args.device_id,
        dtype_name=args.dtype,
        warmup=args.warmup,
        runs=args.runs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
