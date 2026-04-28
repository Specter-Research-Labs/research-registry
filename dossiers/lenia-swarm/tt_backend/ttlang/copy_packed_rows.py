from __future__ import annotations

import argparse
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
        "ttlang/copy_packed_rows.py requires a TT-Lang environment with importable ttl and ttnn."
    ) from exc


TILE_SIZE = 32
ROW_BLOCK_TILES = 4
COL_BLOCK_TILES = 4


@ttl.operation(grid="auto", fp32_dest_acc_en=True, dst_full_sync_en=False)
def copy_plane_matrix(src: ttnn.Tensor, dst: ttnn.Tensor) -> None:
    row_tiles_per_block = ROW_BLOCK_TILES
    col_tiles_per_block = COL_BLOCK_TILES
    rows = src.shape[0] // TILE_SIZE // row_tiles_per_block
    cols = src.shape[1] // TILE_SIZE // col_tiles_per_block
    grid_cols, grid_rows = ttl.grid_size(dims=2)
    rows_per_node = -(-rows // grid_rows)
    cols_per_node = -(-cols // grid_cols)

    src_dfb = ttl.make_dataflow_buffer_like(
        src, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2
    )
    dst_dfb = ttl.make_dataflow_buffer_like(
        dst, shape=(row_tiles_per_block, col_tiles_per_block), block_count=2
    )

    @ttl.compute()
    def compute():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        with src_dfb.wait() as src_blk, dst_dfb.reserve() as dst_blk:
                            dst_blk.store(src_blk)

    @ttl.datamovement()
    def read():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                row_start = row * row_tiles_per_block
                row_end = (row + 1) * row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = (col + 1) * col_tiles_per_block
                        with src_dfb.reserve() as src_blk:
                            tx = ttl.copy(src[row_start:row_end, col_start:col_end], src_blk)
                            tx.wait()

    @ttl.datamovement()
    def write():
        node_col, node_row = ttl.node(dims=2)
        for local_row in range(rows_per_node):
            row = node_row * rows_per_node + local_row
            if row < rows:
                row_start = row * row_tiles_per_block
                row_end = (row + 1) * row_tiles_per_block
                for local_col in range(cols_per_node):
                    col = node_col * cols_per_node + local_col
                    if col < cols:
                        col_start = col * col_tiles_per_block
                        col_end = (col + 1) * col_tiles_per_block
                        with dst_dfb.wait() as dst_blk:
                            tx = ttl.copy(dst_blk, dst[row_start:row_end, col_start:col_end])
                            tx.wait()


def _to_device_matrix(matrix: np.ndarray, *, device, dtype):
    return ttnn.from_torch(
        torch.from_numpy(matrix),
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
        device=device,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
    )


def run_smoke(
    *,
    sx: int,
    sy: int,
    channels: int,
    batch: int,
    device_id: int,
    dtype_name: str,
    warmup: int,
    runs: int,
) -> None:
    if warmup < 0 or runs <= 0:
        raise ValueError(f"Expected warmup >= 0 and runs > 0, got warmup={warmup}, runs={runs}.")
    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True
    rng = np.random.default_rng(0)
    state = rng.uniform(0.0, 1.0, size=(batch, sx, sy, channels)).astype(np.float32)
    matrix, shape = lenia_state_to_plane_matrix(state)
    require_tiled_matrix_shape(
        matrix,
        row_block_tiles=ROW_BLOCK_TILES,
        col_block_tiles=COL_BLOCK_TILES,
        tile_size=TILE_SIZE,
    )
    dtype = ttnn.float32 if dtype_name == "float32" else ttnn.bfloat16

    device = ttnn.open_device(device_id=device_id)
    try:
        src = _to_device_matrix(matrix, device=device, dtype=dtype)
        dst = ttnn.empty(
            matrix.shape,
            dtype=dtype,
            layout=ttnn.TILE_LAYOUT,
            device=device,
            memory_config=ttnn.DRAM_MEMORY_CONFIG,
        )
        for _ in range(warmup):
            copy_plane_matrix(src, dst)
            ttnn.synchronize_device(device)
        started_at = time.perf_counter()
        for _ in range(runs):
            copy_plane_matrix(src, dst)
        ttnn.synchronize_device(device)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / runs
        source_on_device = ttnn.to_torch(src).float().numpy().astype(np.float32, copy=False)
        copied = ttnn.to_torch(dst).float().numpy().astype(np.float32, copy=False)
        roundtrip = plane_matrix_to_lenia_state(copied, shape)
        copy_max_abs = float(np.max(np.abs(copied - source_on_device)))
        copy_mean_abs = float(np.mean(np.abs(copied - source_on_device)))
        host_max_abs = float(np.max(np.abs(roundtrip - state)))
        host_mean_abs = float(np.mean(np.abs(roundtrip - state)))
        tolerance = 1.0e-6 if dtype_name == "float32" else 8.0e-3
        print(
            f"tt-lang copy smoke: shape={state.shape} matrix={matrix.shape} "
            f"dtype={dtype_name} warmup={warmup} runs={runs} mean_elapsed={elapsed_ms:.3f}ms "
            f"copy_max_abs={copy_max_abs:.6g} "
            f"copy_mean_abs={copy_mean_abs:.6g} host_max_abs={host_max_abs:.6g} "
            f"host_mean_abs={host_mean_abs:.6g}"
        )
        if copy_max_abs > tolerance:
            raise SystemExit(f"tt-lang copy smoke failed: copy_max_abs {copy_max_abs} > {tolerance}")
    finally:
        ttnn.close_device(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TT-Lang over the packed Lenia plane layout.")
    parser.add_argument("--sx", type=int, default=256)
    parser.add_argument("--sy", type=int, default=256)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--batch", type=int, default=1)
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
        batch=args.batch,
        device_id=args.device_id,
        dtype_name=args.dtype,
        warmup=args.warmup,
        runs=args.runs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
