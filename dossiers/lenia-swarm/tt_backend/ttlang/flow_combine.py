"""TT-Lang packed-matrix alpha/combine primitive for Flow Lenia."""

from __future__ import annotations

import numpy as np

from ttlang.subtile_shift import TILE_SIZE

try:
    import ttl
    import ttnn
except ImportError:
    ttl = None
    ttnn = None


def _require_ttlang() -> None:
    if ttl is None or ttnn is None:
        raise SystemExit("ttlang/flow_combine.py requires importable ttl and ttnn.")


def flow_combine_param_matrix(*, theta_a: float) -> np.ndarray:
    values = [1.0 / float(theta_a), 0.0, 1.0]
    matrix = np.empty((len(values) * TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row, value in enumerate(values):
        matrix[row * TILE_SIZE : (row + 1) * TILE_SIZE, :] = np.float32(value)
    return matrix


def packed_flow_combine_reference(
    mass_total_matrix: np.ndarray,
    gy_u_matrix: np.ndarray,
    gx_u_matrix: np.ndarray,
    gy_mass_matrix: np.ndarray,
    gx_mass_matrix: np.ndarray,
    *,
    batch: int,
    channels: int,
    sx: int,
    sy: int,
    theta_a: float,
) -> tuple[np.ndarray, np.ndarray]:
    mass = mass_total_matrix.reshape(batch, 1, sx, sy).transpose(0, 2, 3, 1)
    gy_u = gy_u_matrix.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1)
    gx_u = gx_u_matrix.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1)
    gy_mass = gy_mass_matrix.reshape(batch, 1, sx, sy).transpose(0, 2, 3, 1)
    gx_mass = gx_mass_matrix.reshape(batch, 1, sx, sy).transpose(0, 2, 3, 1)
    alpha = np.clip((mass * np.float32(1.0 / float(theta_a))) ** 2, 0.0, 1.0)
    flow_y = gy_u - alpha * (gy_u + gy_mass)
    flow_x = gx_u - alpha * (gx_u + gx_mass)
    return (
        flow_y.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
        flow_x.transpose(0, 3, 1, 2).reshape(batch * channels * sx, sy).astype(np.float32, copy=False),
    )


def make_flow_combine(*, grid: tuple[int, int] | str = "auto"):
    _require_ttlang()

    @ttl.operation(grid=grid, fp32_dest_acc_en=True, dst_full_sync_en=False)
    def flow_combine(
        mass_total: ttnn.Tensor,
        gy_u: ttnn.Tensor,
        gx_u: ttnn.Tensor,
        gy_mass: ttnn.Tensor,
        gx_mass: ttnn.Tensor,
        params: ttnn.Tensor,
        out_y: ttnn.Tensor,
        out_x: ttnn.Tensor,
    ) -> None:
        sy_tiles = gy_u.shape[1] // TILE_SIZE
        sx_tiles = sy_tiles
        plane_count = gy_u.shape[0] // gy_u.shape[1]
        rows = plane_count * sx_tiles
        cols = sy_tiles
        grid_cols, grid_rows = ttl.grid_size(dims=2)
        rows_per_node = -(-rows // grid_rows)
        cols_per_node = -(-cols // grid_cols)

        mass_dfb = ttl.make_dataflow_buffer_like(mass_total, shape=(1, 1), block_count=2)
        gy_u_dfb = ttl.make_dataflow_buffer_like(gy_u, shape=(1, 1), block_count=2)
        gx_u_dfb = ttl.make_dataflow_buffer_like(gx_u, shape=(1, 1), block_count=2)
        gy_mass_dfb = ttl.make_dataflow_buffer_like(gy_mass, shape=(1, 1), block_count=2)
        gx_mass_dfb = ttl.make_dataflow_buffer_like(gx_mass, shape=(1, 1), block_count=2)
        inv_theta_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        zero_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
        one_dfb = ttl.make_dataflow_buffer_like(params, shape=(1, 1), block_count=2)
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
                            with (
                                mass_dfb.wait() as mass_blk,
                                gy_u_dfb.wait() as gy_u_blk,
                                gx_u_dfb.wait() as gx_u_blk,
                                gy_mass_dfb.wait() as gy_mass_blk,
                                gx_mass_dfb.wait() as gx_mass_blk,
                                inv_theta_dfb.wait() as inv_theta_blk,
                                zero_dfb.wait() as zero_blk,
                                one_dfb.wait() as one_blk,
                            ):
                                with out_y_dfb.reserve() as y_blk, out_x_dfb.reserve() as x_blk:
                                    scaled = mass_blk * inv_theta_blk
                                    alpha = ttl.math.min(ttl.math.max(scaled * scaled, zero_blk), one_blk)
                                    y_blk.store(gy_u_blk - alpha * (gy_u_blk + gy_mass_blk))
                                    x_blk.store(gx_u_blk - alpha * (gx_u_blk + gx_mass_blk))

        @ttl.datamovement()
        def read():
            node_col, node_row = ttl.node(dims=2)
            for local_row in range(rows_per_node):
                row = node_row * rows_per_node + local_row
                if row < rows:
                    plane_index = row // sx_tiles
                    spatial_row = row - plane_index * sx_tiles
                    for local_col in range(cols_per_node):
                        col = node_col * cols_per_node + local_col
                        if col < cols:
                            with (
                                mass_dfb.reserve() as mass_blk,
                                gy_u_dfb.reserve() as gy_u_blk,
                                gx_u_dfb.reserve() as gx_u_blk,
                                gy_mass_dfb.reserve() as gy_mass_blk,
                                gx_mass_dfb.reserve() as gx_mass_blk,
                                inv_theta_dfb.reserve() as inv_theta_blk,
                                zero_dfb.reserve() as zero_blk,
                                one_dfb.reserve() as one_blk,
                            ):
                                tx_mass = ttl.copy(mass_total[spatial_row, col], mass_blk)
                                tx_gy_u = ttl.copy(gy_u[row, col], gy_u_blk)
                                tx_gx_u = ttl.copy(gx_u[row, col], gx_u_blk)
                                tx_gy_mass = ttl.copy(gy_mass[spatial_row, col], gy_mass_blk)
                                tx_gx_mass = ttl.copy(gx_mass[spatial_row, col], gx_mass_blk)
                                tx_inv_theta = ttl.copy(params[0, 0], inv_theta_blk)
                                tx_zero = ttl.copy(params[1, 0], zero_blk)
                                tx_one = ttl.copy(params[2, 0], one_blk)
                                tx_mass.wait()
                                tx_gy_u.wait()
                                tx_gx_u.wait()
                                tx_gy_mass.wait()
                                tx_gx_mass.wait()
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

    return flow_combine
