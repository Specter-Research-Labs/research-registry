"""TT-Lang fused complex gather/multiply for Lenia kernel spectra."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import ttl
    import ttnn
except ImportError as exc:
    raise SystemExit(
        "ttlang/gather_spectra.py requires a TT-Lang environment with importable ttl and ttnn."
    ) from exc


TILE_SIZE = 32
ROW_BLOCK_TILES = 2
COL_BLOCK_TILES = 2


def kernel_spectra_plane_matrices(
    fK: np.ndarray,
    *,
    start: int = 0,
    stop: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Pack [1, sx, sy, kernels] complex kernels into [kernels * sx, sy] matrices."""
    if fK.ndim != 4 or fK.shape[0] != 1:
        raise ValueError(f"Expected fK shape [1, sx, sy, nb_k], got {fK.shape}.")
    stop = fK.shape[3] if stop is None else int(stop)
    start = int(start)
    if start < 0 or stop > fK.shape[3] or start >= stop:
        raise ValueError(f"Invalid kernel range [{start}, {stop}) for fK with {fK.shape[3]} kernels.")
    group = fK[:, :, :, start:stop]
    matrix = group[0].transpose(2, 0, 1).reshape((stop - start) * fK.shape[1], fK.shape[2])
    return (
        np.ascontiguousarray(matrix.real.astype(np.float32, copy=False)),
        np.ascontiguousarray(matrix.imag.astype(np.float32, copy=False)),
    )


def make_gather_kernel_spectra_group(source_channel: int):
    source_channel = int(source_channel)
    if source_channel < 0:
        raise ValueError(f"Expected non-negative source channel, got {source_channel}.")

    @ttl.operation(grid="auto")
    def gather_kernel_spectra(
        fA_re: ttnn.Tensor,
        fA_im: ttnn.Tensor,
        fK_re: ttnn.Tensor,
        fK_im: ttnn.Tensor,
        out_re: ttnn.Tensor,
        out_im: ttnn.Tensor,
    ) -> None:
        row_tiles_per_block = ROW_BLOCK_TILES
        col_tiles_per_block = COL_BLOCK_TILES
        sx_tiles = out_re.shape[1] // TILE_SIZE
        out_planes = out_re.shape[0] // out_re.shape[1]
        group_kernels = fK_re.shape[0] // fK_re.shape[1]
        batch = out_planes // group_kernels
        channel_count = (fA_re.shape[0] // fA_re.shape[1]) // batch
        rows = out_re.shape[0] // TILE_SIZE // row_tiles_per_block
        cols = out_re.shape[1] // TILE_SIZE // col_tiles_per_block
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        fA_re_dfb = ttl.make_dataflow_buffer_like(
            fA_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fA_im_dfb = ttl.make_dataflow_buffer_like(
            fA_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fK_re_dfb = ttl.make_dataflow_buffer_like(
            fK_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fK_im_dfb = ttl.make_dataflow_buffer_like(
            fK_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        out_re_dfb = ttl.make_dataflow_buffer_like(
            out_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        out_im_dfb = ttl.make_dataflow_buffer_like(
            out_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
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
                            with (
                                fA_re_dfb.wait() as a_re,
                                fA_im_dfb.wait() as a_im,
                                fK_re_dfb.wait() as k_re,
                                fK_im_dfb.wait() as k_im,
                            ):
                                with out_re_dfb.reserve() as re_blk, out_im_dfb.reserve() as im_blk:
                                    re_blk.store(a_re * k_re - a_im * k_im)
                                    im_blk.store(a_re * k_im + a_im * k_re)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    row_start = row * row_tiles_per_block
                    out_plane = row_start // sx_tiles
                    batch_index = out_plane // group_kernels
                    kernel_index = out_plane % group_kernels
                    source_row_offset = row_start % sx_tiles
                    source_row_end = source_row_offset + row_tiles_per_block
                    source_plane = batch_index * channel_count + source_channel
                    source_row_start = source_plane * sx_tiles + source_row_offset
                    source_row_stop = source_plane * sx_tiles + source_row_end
                    kernel_row_start = kernel_index * sx_tiles + source_row_offset
                    kernel_row_stop = kernel_index * sx_tiles + source_row_end
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            col_start = col * col_tiles_per_block
                            col_end = col_start + col_tiles_per_block
                            with (
                                fA_re_dfb.reserve() as a_re,
                                fA_im_dfb.reserve() as a_im,
                                fK_re_dfb.reserve() as k_re,
                                fK_im_dfb.reserve() as k_im,
                            ):
                                tx_a_re = ttl.copy(fA_re[source_row_start:source_row_stop, col_start:col_end], a_re)
                                tx_a_im = ttl.copy(fA_im[source_row_start:source_row_stop, col_start:col_end], a_im)
                                tx_k_re = ttl.copy(fK_re[kernel_row_start:kernel_row_stop, col_start:col_end], k_re)
                                tx_k_im = ttl.copy(fK_im[kernel_row_start:kernel_row_stop, col_start:col_end], k_im)
                                tx_a_re.wait()
                                tx_a_im.wait()
                                tx_k_re.wait()
                                tx_k_im.wait()

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
                            with out_re_dfb.wait() as re_blk, out_im_dfb.wait() as im_blk:
                                tx_re = ttl.copy(re_blk, out_re[row_start:row_end, col_start:col_end])
                                tx_im = ttl.copy(im_blk, out_im[row_start:row_end, col_start:col_end])
                                tx_re.wait()
                                tx_im.wait()

    return gather_kernel_spectra


def make_gather_kernel_spectra_group_into_full(
    source_channel: int,
    *,
    kernel_start: int,
    total_kernels: int,
):
    source_channel = int(source_channel)
    kernel_start = int(kernel_start)
    total_kernels = int(total_kernels)
    if source_channel < 0:
        raise ValueError(f"Expected non-negative source channel, got {source_channel}.")
    if kernel_start < 0 or total_kernels <= kernel_start:
        raise ValueError(f"Invalid kernel_start/total_kernels: {kernel_start}/{total_kernels}.")

    @ttl.operation(grid="auto")
    def gather_kernel_spectra_full(
        fA_re: ttnn.Tensor,
        fA_im: ttnn.Tensor,
        fK_re: ttnn.Tensor,
        fK_im: ttnn.Tensor,
        out_re: ttnn.Tensor,
        out_im: ttnn.Tensor,
    ) -> None:
        row_tiles_per_block = ROW_BLOCK_TILES
        col_tiles_per_block = COL_BLOCK_TILES
        sx_tiles = out_re.shape[1] // TILE_SIZE
        out_planes = out_re.shape[0] // out_re.shape[1]
        group_kernels = fK_re.shape[0] // fK_re.shape[1]
        batch = out_planes // total_kernels
        channel_count = (fA_re.shape[0] // fA_re.shape[1]) // batch
        rows = batch * group_kernels * sx_tiles // row_tiles_per_block
        cols = out_re.shape[1] // TILE_SIZE // col_tiles_per_block
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        fA_re_dfb = ttl.make_dataflow_buffer_like(
            fA_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fA_im_dfb = ttl.make_dataflow_buffer_like(
            fA_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fK_re_dfb = ttl.make_dataflow_buffer_like(
            fK_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        fK_im_dfb = ttl.make_dataflow_buffer_like(
            fK_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        out_re_dfb = ttl.make_dataflow_buffer_like(
            out_re,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
        )
        out_im_dfb = ttl.make_dataflow_buffer_like(
            out_im,
            shape=(row_tiles_per_block, col_tiles_per_block),
            block_count=2,
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
                            with (
                                fA_re_dfb.wait() as a_re,
                                fA_im_dfb.wait() as a_im,
                                fK_re_dfb.wait() as k_re,
                                fK_im_dfb.wait() as k_im,
                            ):
                                with out_re_dfb.reserve() as re_blk, out_im_dfb.reserve() as im_blk:
                                    re_blk.store(a_re * k_re - a_im * k_im)
                                    im_blk.store(a_re * k_im + a_im * k_re)

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    row_start = row * row_tiles_per_block
                    group_plane = row_start // sx_tiles
                    batch_index = group_plane // group_kernels
                    kernel_index = group_plane % group_kernels
                    source_row_offset = row_start % sx_tiles
                    source_row_end = source_row_offset + row_tiles_per_block
                    source_plane = batch_index * channel_count + source_channel
                    source_row_start = source_plane * sx_tiles + source_row_offset
                    source_row_stop = source_plane * sx_tiles + source_row_end
                    kernel_row_start = kernel_index * sx_tiles + source_row_offset
                    kernel_row_stop = kernel_index * sx_tiles + source_row_end
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            col_start = col * col_tiles_per_block
                            col_end = col_start + col_tiles_per_block
                            with (
                                fA_re_dfb.reserve() as a_re,
                                fA_im_dfb.reserve() as a_im,
                                fK_re_dfb.reserve() as k_re,
                                fK_im_dfb.reserve() as k_im,
                            ):
                                tx_a_re = ttl.copy(fA_re[source_row_start:source_row_stop, col_start:col_end], a_re)
                                tx_a_im = ttl.copy(fA_im[source_row_start:source_row_stop, col_start:col_end], a_im)
                                tx_k_re = ttl.copy(fK_re[kernel_row_start:kernel_row_stop, col_start:col_end], k_re)
                                tx_k_im = ttl.copy(fK_im[kernel_row_start:kernel_row_stop, col_start:col_end], k_im)
                                tx_a_re.wait()
                                tx_a_im.wait()
                                tx_k_re.wait()
                                tx_k_im.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    row_start = row * row_tiles_per_block
                    group_plane = row_start // sx_tiles
                    batch_index = group_plane // group_kernels
                    kernel_index = group_plane % group_kernels
                    source_row_offset = row_start % sx_tiles
                    output_plane = batch_index * total_kernels + kernel_start + kernel_index
                    output_row_start = output_plane * sx_tiles + source_row_offset
                    output_row_end = output_row_start + row_tiles_per_block
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            col_start = col * col_tiles_per_block
                            col_end = col_start + col_tiles_per_block
                            with out_re_dfb.wait() as re_blk, out_im_dfb.wait() as im_blk:
                                tx_re = ttl.copy(re_blk, out_re[output_row_start:output_row_end, col_start:col_end])
                                tx_im = ttl.copy(im_blk, out_im[output_row_start:output_row_end, col_start:col_end])
                                tx_re.wait()
                                tx_im.wait()

    return gather_kernel_spectra_full
