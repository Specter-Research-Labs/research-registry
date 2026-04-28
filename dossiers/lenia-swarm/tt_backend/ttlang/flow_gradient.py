"""TT-Lang packed-matrix Sobel gradient primitive for Flow Lenia."""

from __future__ import annotations

import numpy as np

from ttlang.flow_sobel import NEIGHBORS
from ttlang.subtile_shift import TILE_SIZE, subtile_shift_selector_matrices

try:
    import ttl
    import ttnn
except ImportError:
    ttl = None
    ttnn = None


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit("ttlang/flow_gradient.py requires importable ttl and ttnn.")


def flow_gradient_selector_matrices() -> tuple[np.ndarray, np.ndarray]:
    row_selectors = []
    col_selectors = []
    for row_offset, col_offset, _, _ in NEIGHBORS:
        row_matrix, col_matrix = subtile_shift_selector_matrices(
            row_offset=row_offset,
            col_offset=col_offset,
        )
        row_selectors.append(row_matrix)
        col_selectors.append(col_matrix)
    return (
        np.concatenate(row_selectors, axis=0).astype(np.float32, copy=False),
        np.concatenate(col_selectors, axis=0).astype(np.float32, copy=False),
    )


def flow_gradient_param_matrix() -> np.ndarray:
    values = [*[gy for _, _, gy, _ in NEIGHBORS], *[gx for _, _, _, gx in NEIGHBORS]]
    matrix = np.empty((len(values) * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = np.float32(value)
    return matrix


def packed_flow_gradient_reference(
    matrix: np.ndarray,
    *,
    batch: int,
    channels: int,
    sx: int,
    sy: int,
) -> tuple[np.ndarray, np.ndarray]:
    field = matrix.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1)
    gy = np.zeros_like(field, dtype=np.float32)
    gx = np.zeros_like(field, dtype=np.float32)
    for row_offset, col_offset, gy_coeff, gx_coeff in NEIGHBORS:
        shifted = np.roll(np.roll(field, -row_offset, axis=1), -col_offset, axis=2)
        gy += np.float32(gy_coeff) * shifted
        gx += np.float32(gx_coeff) * shifted
    return (
        gy.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
        gx.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
    )


def make_flow_gradient(*, grid: tuple[int, int] | str = "auto"):
    _require_ttlang()

    @ttl.operation(grid=grid, fp32_dest_acc_en=True, dst_full_sync_en=False)
    def flow_gradient(
        src: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        out_y: ttnn.Tensor,
        out_x: ttnn.Tensor,
    ) -> None:
        sy_tiles = src.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = src.shape[0] // src.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        src_dfb = ttl.make_dataflow_buffer_like(src, shape=(1, 1), block_count=4)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=4)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=4)
        coeff_gy_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        coeff_gx_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        shift_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        gy_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        gx_dfb = ttl.make_dataflow_buffer_like(out_x, shape=(1, 1), block_count=2)
        out_y_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        out_x_dfb = ttl.make_dataflow_buffer_like(out_x, shape=(1, 1), block_count=2)

        @ttl.compute()
        def compute():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with gy_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))
                            with gx_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))

                            for _ in range(8):
                                with shift_dfb.reserve() as blk:
                                    blk.store(ttl.math.fill(blk, 0.0))
                                for _ in range(4):
                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with src_dfb.wait() as src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, shift_dfb.wait() as prev_blk:
                                            with shift_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                with (
                                    shift_dfb.wait() as shift_blk,
                                    coeff_gy_dfb.wait() as coeff_gy_blk,
                                    coeff_gx_dfb.wait() as coeff_gx_blk,
                                    gy_dfb.wait() as prev_gy_blk,
                                    gx_dfb.wait() as prev_gx_blk,
                                ):
                                    with gy_dfb.reserve() as blk:
                                        blk.store(prev_gy_blk + shift_blk * coeff_gy_blk)
                                    with gx_dfb.reserve() as blk:
                                        blk.store(prev_gx_blk + shift_blk * coeff_gx_blk)

                            with gy_dfb.wait() as gy_blk, gx_dfb.wait() as gx_blk:
                                with out_y_dfb.reserve() as y_blk, out_x_dfb.reserve() as x_blk:
                                    y_blk.store(gy_blk)
                                    x_blk.store(gx_blk)

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
                            source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                            source_col = (col + sy_tiles - 1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                            source_col = col
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = out_spatial_row
                            source_col = (col + sy_tiles - 1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = out_spatial_row
                            source_col = col
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[1, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                tx_gy = ttl.copy(params[0, 0], gy_blk)
                                tx_gx = ttl.copy(params[8, 0], gx_blk)
                                tx_gy.wait()
                                tx_gx.wait()

                            for neighbor_index in range(2):
                                selector_base = 2 + neighbor_index * 2
                                source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                                source_col = (col + 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = out_spatial_row
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = out_spatial_row
                                source_col = (col + 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[1 + neighbor_index, 0], gy_blk)
                                    tx_gx = ttl.copy(params[9 + neighbor_index, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()

                            for neighbor_index in range(2):
                                selector_base = 6 + neighbor_index * 4
                                source_row = out_spatial_row
                                source_col = (col + sy_tiles - 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = out_spatial_row
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = (col + sy_tiles - 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[3 + neighbor_index * 2, 0], gy_blk)
                                    tx_gx = ttl.copy(params[11 + neighbor_index * 2, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()

                            source_row = out_spatial_row
                            source_col = col
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[8, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = out_spatial_row
                            source_col = (col + 1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[8, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[9, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + 1) % sx_tiles
                            source_col = col
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[9, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            source_row = (out_spatial_row + 1) % sx_tiles
                            source_col = (col + 1) % sy_tiles
                            source_tile_row = plane_index * sx_tiles + source_row
                            with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                tx_row = ttl.copy(row_selectors[9, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[9, 0], col_blk)
                                tx_src.wait()
                                tx_row.wait()
                                tx_col.wait()

                            with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                tx_gy = ttl.copy(params[4, 0], gy_blk)
                                tx_gx = ttl.copy(params[12, 0], gx_blk)
                                tx_gy.wait()
                                tx_gx.wait()

                            for neighbor_index in range(2):
                                selector_base = 12 + neighbor_index * 2
                                source_row = out_spatial_row
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = out_spatial_row
                                source_col = (col + 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = col
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = (col + 1) % sy_tiles
                                source_tile_row = plane_index * sx_tiles + source_row
                                with src_dfb.reserve() as src_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_src = ttl.copy(src[source_tile_row, source_col], src_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_src.wait()
                                    tx_row.wait()
                                    tx_col.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[6 + neighbor_index, 0], gy_blk)
                                    tx_gx = ttl.copy(params[14 + neighbor_index, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()

        @ttl.datamovement()
        def write():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with out_y_dfb.wait() as y_blk, out_x_dfb.wait() as x_blk:
                                tx_y = ttl.copy(y_blk, out_y[row, col])
                                tx_x = ttl.copy(x_blk, out_x[row, col])
                                tx_y.wait()
                                tx_x.wait()

    return flow_gradient
