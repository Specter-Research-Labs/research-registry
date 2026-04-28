"""TT-Lang packed-matrix Sobel/alpha flow for Flow Lenia."""

from __future__ import annotations

import numpy as np

from ttlang.subtile_shift import TILE_SIZE, subtile_shift_selector_matrices

try:
    import ttl
    import ttnn
except ImportError:
    ttl = None
    ttnn = None


NEIGHBORS: tuple[tuple[int, int, float, float], ...] = (
    (-1, -1, 1.0, 1.0),
    (-1, 0, 2.0, 0.0),
    (-1, 1, 1.0, -1.0),
    (0, -1, 0.0, 2.0),
    (0, 1, 0.0, -2.0),
    (1, -1, -1.0, 1.0),
    (1, 0, -2.0, 0.0),
    (1, 1, -1.0, -1.0),
)


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit("ttlang/flow_sobel.py requires importable ttl and ttnn.")


def flow_sobel_selector_matrices() -> tuple[np.ndarray, np.ndarray]:
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


def flow_sobel_param_matrix(*, theta_a: float, dd: int, sigma: float) -> np.ndarray:
    _ = (dd, sigma)
    gy_coeffs = [gy for _, _, gy, _ in NEIGHBORS]
    gx_coeffs = [gx for _, _, _, gx in NEIGHBORS]
    values = [
        *gy_coeffs,
        *gx_coeffs,
        1.0 / float(theta_a),
        0.0,
        1.0,
    ]
    matrix = np.empty((len(values) * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = np.float32(value)
    return matrix


def packed_flow_sobel_reference(
    mass_matrix: np.ndarray,
    u_matrix: np.ndarray,
    *,
    batch: int,
    channels: int,
    sx: int,
    sy: int,
    theta_a: float,
    dd: int,
    sigma: float,
    flow_clip: str,
) -> tuple[np.ndarray, np.ndarray]:
    mass = mass_matrix.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1)
    u = u_matrix.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1)
    mass_total = mass.sum(axis=-1, keepdims=True)
    gy_u = np.zeros_like(u, dtype=np.float32)
    gx_u = np.zeros_like(u, dtype=np.float32)
    gy_a = np.zeros_like(mass_total, dtype=np.float32)
    gx_a = np.zeros_like(mass_total, dtype=np.float32)
    for row_offset, col_offset, gy_coeff, gx_coeff in NEIGHBORS:
        shifted_u = np.roll(np.roll(u, -row_offset, axis=1), -col_offset, axis=2)
        shifted_mass = np.roll(np.roll(mass_total, -row_offset, axis=1), -col_offset, axis=2)
        gy_u += np.float32(gy_coeff) * shifted_u
        gx_u += np.float32(gx_coeff) * shifted_u
        gy_a += np.float32(gy_coeff) * shifted_mass
        gx_a += np.float32(gx_coeff) * shifted_mass
    alpha = np.clip((mass_total * np.float32(1.0 / float(theta_a))) ** 2, 0.0, 1.0)
    flow_y = gy_u - alpha * (gy_u + gy_a)
    flow_x = gx_u - alpha * (gx_u + gx_a)
    if flow_clip == "always":
        max_flow = np.float32(float(dd) - float(sigma))
        flow_y = np.clip(flow_y, -max_flow, max_flow)
        flow_x = np.clip(flow_x, -max_flow, max_flow)
    return (
        flow_y.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
        flow_x.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
    )


def make_flow_sobel(*, clip: bool, grid: tuple[int, int] | str = "auto"):
    _require_ttlang()
    if clip:
        raise ValueError("TT-Lang packed Sobel flow currently supports flow_clip='none' only.")

    @ttl.operation(grid=grid, fp32_dest_acc_en=True, dst_full_sync_en=False)
    def flow_sobel(
        mass_total: ttnn.Tensor,
        u: ttnn.Tensor,
        row_selectors: ttnn.Tensor,
        col_selectors: ttnn.Tensor,
        params: ttnn.Tensor,
        out_y: ttnn.Tensor,
        out_x: ttnn.Tensor,
    ) -> None:
        sy_tiles = u.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = u.shape[0] // u.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        u_src_dfb = ttl.make_dataflow_buffer_like(u, shape=(1, 1), block_count=4)
        mass_src_dfb = ttl.make_dataflow_buffer_like(mass_total, shape=(1, 1), block_count=4)
        current_mass_dfb = ttl.make_dataflow_buffer_like(mass_total, shape=(1, 1), block_count=4)
        row_dfb = ttl.make_dataflow_buffer_like(row_selectors, shape=(1, 1), block_count=4)
        col_dfb = ttl.make_dataflow_buffer_like(col_selectors, shape=(1, 1), block_count=4)
        coeff_gy_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        coeff_gx_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        inv_theta_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        one_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        tmp_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        part_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        u_shift_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        mass_shift_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        gy_u_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        gx_u_dfb = ttl.make_dataflow_buffer_like(out_x, shape=(1, 1), block_count=2)
        gy_a_dfb = ttl.make_dataflow_buffer_like(out_y, shape=(1, 1), block_count=2)
        gx_a_dfb = ttl.make_dataflow_buffer_like(out_x, shape=(1, 1), block_count=2)
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
                            with gy_u_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))
                            with gx_u_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))
                            with gy_a_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))
                            with gx_a_dfb.reserve() as blk:
                                blk.store(ttl.math.fill(blk, 0.0))

                            for _ in range(8):
                                with u_shift_dfb.reserve() as blk:
                                    blk.store(ttl.math.fill(blk, 0.0))
                                with mass_shift_dfb.reserve() as blk:
                                    blk.store(ttl.math.fill(blk, 0.0))
                                for _ in range(4):
                                    with row_dfb.wait() as row_blk, col_dfb.wait() as col_blk:
                                        with u_src_dfb.wait() as u_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ u_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, u_shift_dfb.wait() as prev_blk:
                                            with u_shift_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                        with mass_src_dfb.wait() as mass_src_blk:
                                            with tmp_dfb.reserve() as tmp_blk:
                                                tmp_blk.store(row_blk @ mass_src_blk)
                                        with tmp_dfb.wait() as tmp_blk:
                                            with part_dfb.reserve() as part_blk:
                                                part_blk.store(tmp_blk @ col_blk)
                                        with part_dfb.wait() as part_blk, mass_shift_dfb.wait() as prev_blk:
                                            with mass_shift_dfb.reserve() as acc_blk:
                                                acc_blk.store(prev_blk + part_blk)

                                with (
                                    u_shift_dfb.wait() as u_shift_blk,
                                    mass_shift_dfb.wait() as mass_shift_blk,
                                    coeff_gy_dfb.wait() as coeff_gy_blk,
                                    coeff_gx_dfb.wait() as coeff_gx_blk,
                                    gy_u_dfb.wait() as prev_gy_u_blk,
                                    gx_u_dfb.wait() as prev_gx_u_blk,
                                    gy_a_dfb.wait() as prev_gy_a_blk,
                                    gx_a_dfb.wait() as prev_gx_a_blk,
                                ):
                                    with gy_u_dfb.reserve() as blk:
                                        blk.store(prev_gy_u_blk + u_shift_blk * coeff_gy_blk)
                                    with gx_u_dfb.reserve() as blk:
                                        blk.store(prev_gx_u_blk + u_shift_blk * coeff_gx_blk)
                                    with gy_a_dfb.reserve() as blk:
                                        blk.store(prev_gy_a_blk + mass_shift_blk * coeff_gy_blk)
                                    with gx_a_dfb.reserve() as blk:
                                        blk.store(prev_gx_a_blk + mass_shift_blk * coeff_gx_blk)

                            with (
                                current_mass_dfb.wait() as alpha_src_blk,
                                gy_u_dfb.wait() as gy_u_blk,
                                gx_u_dfb.wait() as gx_u_blk,
                                gy_a_dfb.wait() as gy_a_blk,
                                gx_a_dfb.wait() as gx_a_blk,
                                inv_theta_dfb.wait() as inv_theta_blk,
                                zero_dfb.wait() as zero_blk,
                                one_dfb.wait() as one_blk,
                            ):
                                with out_y_dfb.reserve() as y_blk, out_x_dfb.reserve() as x_blk:
                                    scaled = alpha_src_blk * inv_theta_blk
                                    alpha = ttl.math.min(ttl.math.max(scaled * scaled, zero_blk), one_blk)
                                    y = gy_u_blk - alpha * (gy_u_blk + gy_a_blk)
                                    x = gx_u_blk - alpha * (gx_u_blk + gx_a_blk)
                                    y_blk.store(y)
                                    x_blk.store(x)

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
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                            source_col = col
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[0, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0 + 1, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = out_spatial_row
                            source_col = (col + sy_tiles - 1) % sy_tiles
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[0 + 1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = out_spatial_row
                            source_col = col
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[0 + 1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[0 + 1, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                tx_gy = ttl.copy(params[0, 0], gy_blk)
                                tx_gx = ttl.copy(params[8, 0], gx_blk)
                                tx_gy.wait()
                                tx_gx.wait()
                            for neighbor_index in range(2):
                                selector_base = 2 + neighbor_index * 2
                                source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = (out_spatial_row + sx_tiles - 1) % sx_tiles
                                source_col = (col + 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = out_spatial_row
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = out_spatial_row
                                source_col = (col + 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[1 + neighbor_index, 0], gy_blk)
                                    tx_gx = ttl.copy(params[9 + neighbor_index, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()
                            for neighbor_index in range(2):
                                selector_base = 6 + neighbor_index * 4
                                source_row = out_spatial_row
                                source_col = (col + sy_tiles - 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = out_spatial_row
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = (col + sy_tiles - 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[3 + neighbor_index * 2, 0], gy_blk)
                                    tx_gx = ttl.copy(params[11 + neighbor_index * 2, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()
                            source_row = out_spatial_row
                            source_col = col
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[8, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = out_spatial_row
                            source_col = (col + 1) % sy_tiles
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[8, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8 + 1, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = (out_spatial_row + 1) % sx_tiles
                            source_col = col
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[8 + 1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            source_row = (out_spatial_row + 1) % sx_tiles
                            source_col = (col + 1) % sy_tiles
                            u_source_tile_row = plane_index * sx_tiles + source_row
                            with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                tx_row = ttl.copy(row_selectors[8 + 1, 0], row_blk)
                                tx_col = ttl.copy(col_selectors[8 + 1, 0], col_blk)
                                tx_u.wait()
                                tx_row.wait()
                                tx_col.wait()
                            with mass_src_dfb.reserve() as mass_blk:
                                tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                tx_mass.wait()

                            with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                tx_gy = ttl.copy(params[4, 0], gy_blk)
                                tx_gx = ttl.copy(params[12, 0], gx_blk)
                                tx_gy.wait()
                                tx_gx.wait()
                            for neighbor_index in range(2):
                                selector_base = 12 + neighbor_index * 2
                                source_row = out_spatial_row
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = out_spatial_row
                                source_col = (col + 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = col
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                source_row = (out_spatial_row + 1) % sx_tiles
                                source_col = (col + 1) % sy_tiles
                                u_source_tile_row = plane_index * sx_tiles + source_row
                                with u_src_dfb.reserve() as u_blk, row_dfb.reserve() as row_blk, col_dfb.reserve() as col_blk:
                                    tx_u = ttl.copy(u[u_source_tile_row, source_col], u_blk)
                                    tx_row = ttl.copy(row_selectors[selector_base + 1, 0], row_blk)
                                    tx_col = ttl.copy(col_selectors[selector_base + 1, 0], col_blk)
                                    tx_u.wait()
                                    tx_row.wait()
                                    tx_col.wait()
                                with mass_src_dfb.reserve() as mass_blk:
                                    tx_mass = ttl.copy(mass_total[source_row, source_col], mass_blk)
                                    tx_mass.wait()

                                with coeff_gy_dfb.reserve() as gy_blk, coeff_gx_dfb.reserve() as gx_blk:
                                    tx_gy = ttl.copy(params[6 + neighbor_index, 0], gy_blk)
                                    tx_gx = ttl.copy(params[14 + neighbor_index, 0], gx_blk)
                                    tx_gy.wait()
                                    tx_gx.wait()

                            current_tile_row = out_spatial_row
                            with current_mass_dfb.reserve() as current_blk:
                                tx_current = ttl.copy(mass_total[current_tile_row, col], current_blk)
                                tx_current.wait()

                            with (
                                inv_theta_dfb.reserve() as inv_theta_blk,
                                zero_dfb.reserve() as zero_blk,
                                one_dfb.reserve() as one_blk,
                            ):
                                tx_inv_theta = ttl.copy(params[16, 0], inv_theta_blk)
                                tx_zero = ttl.copy(params[17, 0], zero_blk)
                                tx_one = ttl.copy(params[18, 0], one_blk)
                                tx_inv_theta.wait()
                                tx_zero.wait()
                                tx_one.wait()

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

    return flow_sobel
