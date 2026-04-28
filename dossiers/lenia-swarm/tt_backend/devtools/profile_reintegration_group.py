"""Profile active and prototype TT-Lang reintegration group kernels."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttlang.shape_bridge import lenia_state_to_plane_matrix, plane_matrix_to_lenia_state
from ttlang.reintegration_subtile import (
    _make_demo_state,
    _to_device_matrix,
    make_torus_halo_pad,
    make_subtile_reintegration_group,
    make_subtile_reintegration_group_block_halo,
    make_subtile_reintegration_group_initial,
    make_subtile_reintegration_group_block_interior,
    make_subtile_reintegration_group_boundary,
    make_subtile_reintegration_group_boundary_col,
    make_subtile_reintegration_group_boundary_row,
    subtile_reintegration_group_block_selector_matrices,
    make_subtile_reintegration_group_block_halo_separable,
    subtile_reintegration_group_param_matrix,
    subtile_reintegration_group_reference,
    subtile_reintegration_group_selector_matrices,
    subtile_reintegration_offset_groups,
    torus_halo_pad_plane_matrix,
)
from ttlang.subtile_shift import subtile_part_tile_deltas


def _interior_mask(
    shape: tuple[int, ...],
    *,
    sx: int,
    sy: int,
    offsets: tuple[tuple[int, int], ...],
) -> np.ndarray:
    """Return true for tiles the block-interior kernel can compute."""
    row_delta0, row_delta1 = subtile_part_tile_deltas(offsets[0][0])
    col_delta0, col_delta1 = subtile_part_tile_deltas(offsets[0][1])
    mask = np.ones(shape, dtype=bool)
    sx_tiles = sx // 32
    sy_tiles = sy // 32
    if row_delta0 >= 0:
        mask[:, (sx_tiles - row_delta1) * 32 : sx, :, :] = False
    else:
        mask[:, :32, :, :] = False
    if col_delta0 >= 0:
        mask[:, :, (sy_tiles - col_delta1) * 32 : sy, :] = False
    else:
        mask[:, :, :32, :] = False
    return mask


def _boundary_row_mask(
    shape: tuple[int, ...],
    *,
    sx: int,
    offsets: tuple[tuple[int, int], ...],
) -> np.ndarray:
    row_delta0, _ = subtile_part_tile_deltas(offsets[0][0])
    mask = np.zeros(shape, dtype=bool)
    if row_delta0 >= 0:
        mask[:, sx - 32 : sx, :, :] = True
    else:
        mask[:, :32, :, :] = True
    return mask


def _boundary_col_mask(
    shape: tuple[int, ...],
    *,
    sy: int,
    offsets: tuple[tuple[int, int], ...],
) -> np.ndarray:
    col_delta0, _ = subtile_part_tile_deltas(offsets[0][1])
    mask = np.zeros(shape, dtype=bool)
    if col_delta0 >= 0:
        mask[:, :, sy - 32 : sy, :] = True
    else:
        mask[:, :, :32, :] = True
    return mask


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sx", type=int, default=128)
    parser.add_argument("--sy", type=int, default=128)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument(
        "--impl",
        choices=(
            "split",
            "split-boundary",
            "split-boundary-row",
            "split-boundary-col",
            "block-interior",
            "block-halo",
            "block-halo-separable",
            "block-composite",
            "block-composite-compact",
        ),
        default="split",
    )
    parser.add_argument("--dd", type=int, default=None)
    parser.add_argument("--group-index", type=int, default=0)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--init-from-zero", action="store_true")
    parser.add_argument(
        "--host-prepadded",
        action="store_true",
        help="Precompute the one-tile torus halo on host; useful for rectangular mesh-local shard probes.",
    )
    parser.add_argument(
        "--constant-memory",
        choices=("dram", "l1"),
        default="dram",
        help="Memory space for selector/parameter tensors; state tensors stay in DRAM.",
    )
    args = parser.parse_args()

    import ttnn

    halo_impl = args.impl in {"block-halo", "block-halo-separable"}
    if args.host_prepadded and not halo_impl:
        raise ValueError("--host-prepadded is only supported by --impl block-halo or block-halo-separable.")
    if args.sx != args.sy and not (halo_impl and args.host_prepadded):
        raise ValueError("Non-square reintegration probes currently require --host-prepadded block-halo kernels.")

    groups = (((0, 0), (0, 1), (1, 0), (1, 1)),) if args.dd is None else subtile_reintegration_offset_groups(args.dd)
    offsets = groups[args.group_index]
    dt = 0.2
    max_flow = 4.35
    sigma = 0.65

    mass, flow_y, flow_x = _make_demo_state(sx=args.sx, sy=args.sy, channels=args.channels)
    expected = subtile_reintegration_group_reference(
        mass,
        flow_y,
        flow_x,
        offsets,
        dt=dt,
        max_flow=max_flow,
        sigma=sigma,
    )
    if args.impl in {"block-interior", "split-boundary", "split-boundary-row", "split-boundary-col"}:
        interior = _interior_mask(expected.shape, sx=args.sx, sy=args.sy, offsets=offsets)
        # The split-boundary and block-interior probes each cover one half of
        # the eventual composite, so compare only the tiles each half owns.
        if args.impl == "block-interior":
            expected = np.where(interior, expected, 0.0).astype(np.float32, copy=False)
        elif args.impl == "split-boundary-row":
            row_boundary = _boundary_row_mask(expected.shape, sx=args.sx, offsets=offsets)
            expected = np.where(row_boundary, expected, 0.0).astype(np.float32, copy=False)
        elif args.impl == "split-boundary-col":
            row_boundary = _boundary_row_mask(expected.shape, sx=args.sx, offsets=offsets)
            col_boundary = _boundary_col_mask(expected.shape, sy=args.sy, offsets=offsets)
            expected = np.where(col_boundary & ~row_boundary, expected, 0.0).astype(np.float32, copy=False)
        else:
            expected = np.where(interior, 0.0, expected).astype(np.float32, copy=False)

    mass_matrix, shape = lenia_state_to_plane_matrix(mass)
    flow_y_matrix, _ = lenia_state_to_plane_matrix(flow_y)
    flow_x_matrix, _ = lenia_state_to_plane_matrix(flow_x)
    if args.impl in {
        "block-interior",
        "block-halo",
        "block-halo-separable",
        "block-composite",
        "block-composite-compact",
    }:
        row_selectors, col_selectors = subtile_reintegration_group_block_selector_matrices(offsets)
        kernel_factory = (
            make_subtile_reintegration_group_block_halo
            if args.impl == "block-halo"
            else (
                make_subtile_reintegration_group_block_halo_separable
                if args.impl == "block-halo-separable"
                else make_subtile_reintegration_group_block_interior
            )
        )
        boundary_row_selectors, boundary_col_selectors = subtile_reintegration_group_selector_matrices(offsets)
    elif args.impl in {"split-boundary", "split-boundary-row", "split-boundary-col"}:
        row_selectors, col_selectors = subtile_reintegration_group_selector_matrices(offsets)
        if args.impl == "split-boundary-row":
            kernel_factory = make_subtile_reintegration_group_boundary_row
        elif args.impl == "split-boundary-col":
            kernel_factory = make_subtile_reintegration_group_boundary_col
        else:
            kernel_factory = make_subtile_reintegration_group_boundary
        boundary_row_selectors = boundary_col_selectors = None
    else:
        row_selectors, col_selectors = subtile_reintegration_group_selector_matrices(offsets)
        kernel_factory = make_subtile_reintegration_group
        boundary_row_selectors = boundary_col_selectors = None
    params = subtile_reintegration_group_param_matrix(offsets, dt=dt, max_flow=max_flow, sigma=sigma)
    acc = np.zeros(shape.matrix_shape, dtype=np.float32)
    out = np.zeros_like(acc)
    if args.init_from_zero and args.impl != "split":
        raise ValueError("--init-from-zero is only supported by --impl split.")

    device = ttnn.open_device(device_id=args.device_id)
    try:
        dtype = ttnn.bfloat16
        constant_memory_config = ttnn.L1_MEMORY_CONFIG if args.constant_memory == "l1" else ttnn.DRAM_MEMORY_CONFIG
        mass_tt = _to_device_matrix(mass_matrix, device=device, dtype=dtype)
        flow_y_tt = _to_device_matrix(flow_y_matrix, device=device, dtype=dtype)
        flow_x_tt = _to_device_matrix(flow_x_matrix, device=device, dtype=dtype)
        row_tt = _to_device_matrix(row_selectors, device=device, dtype=dtype, memory_config=constant_memory_config)
        col_tt = _to_device_matrix(col_selectors, device=device, dtype=dtype, memory_config=constant_memory_config)
        params_tt = _to_device_matrix(params, device=device, dtype=dtype, memory_config=constant_memory_config)
        acc_tt = _to_device_matrix(acc, device=device, dtype=dtype)
        out_tt = _to_device_matrix(out, device=device, dtype=dtype)
        if args.impl in {"block-halo", "block-halo-separable"}:
            if args.host_prepadded:
                mass_padded = torus_halo_pad_plane_matrix(mass_matrix, shape, offsets)
                flow_y_padded = torus_halo_pad_plane_matrix(flow_y_matrix, shape, offsets)
                flow_x_padded = torus_halo_pad_plane_matrix(flow_x_matrix, shape, offsets)
                pad_kernel = None
            else:
                plane_count = mass_matrix.shape[0] // mass_matrix.shape[1]
                padded_shape = (mass_matrix.shape[0] + plane_count * 32, mass_matrix.shape[1] + 32)
                mass_padded = np.zeros(padded_shape, dtype=np.float32)
                flow_y_padded = np.zeros(padded_shape, dtype=np.float32)
                flow_x_padded = np.zeros(padded_shape, dtype=np.float32)
                pad_kernel = make_torus_halo_pad(offsets)
            mass_padded_tt = _to_device_matrix(mass_padded, device=device, dtype=dtype)
            flow_y_padded_tt = _to_device_matrix(flow_y_padded, device=device, dtype=dtype)
            flow_x_padded_tt = _to_device_matrix(flow_x_padded, device=device, dtype=dtype)
        else:
            mass_padded_tt = flow_y_padded_tt = flow_x_padded_tt = pad_kernel = None
        if args.impl == "split":
            kernel = make_subtile_reintegration_group_initial(offsets) if args.init_from_zero else kernel_factory(offsets)
        else:
            kernel = kernel_factory(offsets)
        if args.impl in {"block-composite", "block-composite-compact"}:
            boundary_row_tt = _to_device_matrix(
                boundary_row_selectors,
                device=device,
                dtype=dtype,
                memory_config=constant_memory_config,
            )
            boundary_col_tt = _to_device_matrix(
                boundary_col_selectors,
                device=device,
                dtype=dtype,
                memory_config=constant_memory_config,
            )
            if args.impl == "block-composite-compact":
                boundary_kernel = make_subtile_reintegration_group_boundary_row(offsets)
                boundary_col_kernel = make_subtile_reintegration_group_boundary_col(offsets)
            else:
                boundary_kernel = make_subtile_reintegration_group_boundary(offsets)
                boundary_col_kernel = None
        else:
            boundary_row_tt = boundary_col_tt = boundary_kernel = boundary_col_kernel = None

        for _ in range(args.warmup):
            if args.impl in {"block-halo", "block-halo-separable"}:
                if pad_kernel is not None:
                    pad_kernel(mass_tt, flow_y_tt, flow_x_tt, mass_padded_tt, flow_y_padded_tt, flow_x_padded_tt)
                kernel(mass_padded_tt, flow_y_padded_tt, flow_x_padded_tt, row_tt, col_tt, params_tt, acc_tt, out_tt)
            else:
                kernel(mass_tt, flow_y_tt, flow_x_tt, row_tt, col_tt, params_tt, acc_tt, out_tt)
            if args.impl in {"block-composite", "block-composite-compact"}:
                boundary_kernel(
                    mass_tt,
                    flow_y_tt,
                    flow_x_tt,
                    boundary_row_tt,
                    boundary_col_tt,
                    params_tt,
                    out_tt,
                    out_tt,
                )
                if boundary_col_kernel is not None:
                    boundary_col_kernel(
                        mass_tt,
                        flow_y_tt,
                        flow_x_tt,
                        boundary_row_tt,
                        boundary_col_tt,
                        params_tt,
                        out_tt,
                        out_tt,
                    )
            ttnn.synchronize_device(device)

        started_at = time.perf_counter()
        for _ in range(args.runs):
            if args.impl in {"block-halo", "block-halo-separable"}:
                if pad_kernel is not None:
                    pad_kernel(mass_tt, flow_y_tt, flow_x_tt, mass_padded_tt, flow_y_padded_tt, flow_x_padded_tt)
                kernel(mass_padded_tt, flow_y_padded_tt, flow_x_padded_tt, row_tt, col_tt, params_tt, acc_tt, out_tt)
            else:
                kernel(mass_tt, flow_y_tt, flow_x_tt, row_tt, col_tt, params_tt, acc_tt, out_tt)
            if args.impl in {"block-composite", "block-composite-compact"}:
                boundary_kernel(
                    mass_tt,
                    flow_y_tt,
                    flow_x_tt,
                    boundary_row_tt,
                    boundary_col_tt,
                    params_tt,
                    out_tt,
                    out_tt,
                )
                if boundary_col_kernel is not None:
                    boundary_col_kernel(
                        mass_tt,
                        flow_y_tt,
                        flow_x_tt,
                        boundary_row_tt,
                        boundary_col_tt,
                        params_tt,
                        out_tt,
                        out_tt,
                    )
        ttnn.synchronize_device(device)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(args.runs)

        actual_matrix = ttnn.to_torch(out_tt).float().numpy().astype(np.float32, copy=False)
        actual = plane_matrix_to_lenia_state(actual_matrix, shape)
        diff = np.abs(actual - expected)
        print(
            f"reintegration_group_profile impl={args.impl} mean_ms={elapsed_ms:.3f} "
            f"constant_memory={args.constant_memory} "
            f"host_prepadded={args.host_prepadded} "
            f"offsets={len(offsets)} "
            f"max={float(np.max(diff)):.6g} mean={float(np.mean(diff)):.6g} "
            f"actual_sum={float(np.sum(actual)):.6g} expected_sum={float(np.sum(expected)):.6g}"
        )
    finally:
        ttnn.close_device(device)


if __name__ == "__main__":
    main()
