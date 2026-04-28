"""Probe row-sharded mesh boundary exchange for future resident reintegration."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.device import (
    apply_tt_runtime_env,
    close_ttnn_device,
    open_ttnn_device,
    parse_mesh_shape,
    restore_tt_runtime_env,
)
from tt_lenia.stages.fft import _safe_deallocate
from tt_lenia.stages.mesh_halo import assemble_one_sided_mesh_row_halo, slice_along_dim


def _mesh_shape_tuple(mesh_shape) -> tuple[int, int]:
    return int(mesh_shape[0]), int(mesh_shape[1])


def _to_row_sharded(matrix: np.ndarray, *, mesh, dtype, shard_dim: int):
    import torch
    import ttnn

    return ttnn.from_torch(
        torch.from_numpy(matrix.astype(np.float32, copy=False)),
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
        device=mesh,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
        mesh_mapper=ttnn.ShardTensorToMesh(mesh, dim=shard_dim),
    )


def _first_device_tensor_to_numpy(tensor) -> np.ndarray:
    import ttnn

    device_tensors = ttnn.get_device_tensors(tensor)
    if not device_tensors:
        raise RuntimeError("Expected a mesh tensor with at least one device-local tensor.")
    return ttnn.to_torch(device_tensors[0]).float().numpy().astype(np.float32, copy=False)


def _device_tensor_to_numpy(tensor) -> np.ndarray:
    import ttnn

    return ttnn.to_torch(tensor).float().numpy().astype(np.float32, copy=False)


def _sync(device) -> None:
    import ttnn

    ttnn.synchronize_device(device)


def _np_slice_along_dim(array: np.ndarray, *, dim: int, start: int, end: int) -> np.ndarray:
    index = [slice(None)] * array.ndim
    index[dim] = slice(start, end)
    return array[tuple(index)]


def _expected_padded_shard(
    matrix: np.ndarray,
    *,
    rank: int,
    mesh_size: int,
    local_rows: int,
    boundary_rows: int,
    shard_dim: int,
    pad_before: bool,
) -> np.ndarray:
    local_start = rank * local_rows
    local = _np_slice_along_dim(matrix, dim=shard_dim, start=local_start, end=local_start + local_rows)
    if pad_before:
        neighbor = (rank - 1) % mesh_size
        halo_start = (neighbor + 1) * local_rows - boundary_rows
        halo = _np_slice_along_dim(matrix, dim=shard_dim, start=halo_start, end=halo_start + boundary_rows)
        return np.concatenate([halo, local], axis=shard_dim)

    neighbor = (rank + 1) % mesh_size
    halo_start = neighbor * local_rows
    halo = _np_slice_along_dim(matrix, dim=shard_dim, start=halo_start, end=halo_start + boundary_rows)
    return np.concatenate([local, halo], axis=shard_dim)


def _probe_halo_assembly(
    *,
    sharded,
    top_gathered,
    bottom_gathered,
    matrix: np.ndarray,
    mesh,
    mesh_size: int,
    local_rows: int,
    boundary_rows: int,
    shard_dim: int,
    pad_before: bool,
) -> None:
    import ttnn

    assembly = None
    try:
        assembly = assemble_one_sided_mesh_row_halo(
            sharded,
            top_gathered,
            bottom_gathered,
            mesh_size=mesh_size,
            boundary_rows=boundary_rows,
            shard_dim=shard_dim,
            pad_before=pad_before,
        )
        _sync(mesh)
        padded_shards = ttnn.get_device_tensors(assembly.tensor)

        max_diff = 0.0
        for rank, padded_shard in enumerate(padded_shards):
            actual = _device_tensor_to_numpy(padded_shard)
            expected = _expected_padded_shard(
                matrix,
                rank=rank,
                mesh_size=mesh_size,
                local_rows=local_rows,
                boundary_rows=boundary_rows,
                shard_dim=shard_dim,
                pad_before=pad_before,
            )
            max_diff = max(max_diff, float(np.abs(actual - expected).max()))

        print(
            "mesh_halo_assembly "
            f"pad={'before' if pad_before else 'after'} "
            "mesh_tensor=True "
            "mode=rotate-partition "
            f"local_padded_shape={tuple(padded_shards[0].shape) if padded_shards else None} "
            f"max_diff={max_diff:.6g}"
        )
    finally:
        if assembly is not None:
            assembly.close()


def probe_halo_exchange(
    *,
    mesh,
    size: int,
    planes: int,
    boundary_rows: int,
    warmup: int,
    runs: int,
    assemble: bool,
) -> None:
    import ttnn

    mesh_shape = _mesh_shape_tuple(mesh.shape)
    mesh_size = mesh_shape[0] * mesh_shape[1]
    if size % mesh_size != 0:
        raise ValueError(f"--size must be divisible by mesh size {mesh_size}.")
    if boundary_rows % 32 != 0:
        raise ValueError("--boundary-rows must be tile-aligned.")
    local_rows = size // mesh_size
    if boundary_rows > local_rows:
        raise ValueError(f"--boundary-rows={boundary_rows} exceeds local shard rows {local_rows}.")

    row_ids = np.arange(size, dtype=np.float32).reshape(size, 1)
    col_ids = np.arange(size, dtype=np.float32).reshape(1, size)
    if planes == 1:
        matrix = row_ids + 0.001 * col_ids
        shard_dim = 0
        top_expected = np.concatenate(
            [matrix[rank * local_rows : rank * local_rows + boundary_rows, :] for rank in range(mesh_size)],
            axis=0,
        )
        bottom_expected = np.concatenate(
            [matrix[(rank + 1) * local_rows - boundary_rows : (rank + 1) * local_rows, :] for rank in range(mesh_size)],
            axis=0,
        )
    else:
        plane_ids = np.arange(planes, dtype=np.float32).reshape(planes, 1, 1)
        matrix = plane_ids + 0.01 * row_ids.reshape(1, size, 1) + 0.00001 * col_ids.reshape(1, 1, size)
        shard_dim = 1
        top_expected = np.concatenate(
            [
                matrix[:, rank * local_rows : rank * local_rows + boundary_rows, :]
                for rank in range(mesh_size)
            ],
            axis=shard_dim,
        )
        bottom_expected = np.concatenate(
            [
                matrix[:, (rank + 1) * local_rows - boundary_rows : (rank + 1) * local_rows, :]
                for rank in range(mesh_size)
            ],
            axis=shard_dim,
        )

    sharded = top = bottom = top_gathered = bottom_gathered = None
    try:
        sharded = _to_row_sharded(matrix, mesh=mesh, dtype=ttnn.bfloat16, shard_dim=shard_dim)
        local_shape = tuple(sharded.shape)

        for _ in range(warmup):
            warm_top = slice_along_dim(sharded, dim=shard_dim, start=0, end=boundary_rows)
            warm_bottom = slice_along_dim(
                sharded,
                dim=shard_dim,
                start=local_rows - boundary_rows,
                end=local_rows,
            )
            warm_top_gathered = ttnn.all_gather(warm_top, dim=shard_dim)
            warm_bottom_gathered = ttnn.all_gather(warm_bottom, dim=shard_dim)
            _sync(mesh)
            _safe_deallocate(warm_top, warm_bottom, warm_top_gathered, warm_bottom_gathered)

        started_at = time.perf_counter()
        for _ in range(runs):
            _safe_deallocate(top, bottom, top_gathered, bottom_gathered)
            top = slice_along_dim(sharded, dim=shard_dim, start=0, end=boundary_rows)
            bottom = slice_along_dim(
                sharded,
                dim=shard_dim,
                start=local_rows - boundary_rows,
                end=local_rows,
            )
            top_gathered = ttnn.all_gather(top, dim=shard_dim)
            bottom_gathered = ttnn.all_gather(bottom, dim=shard_dim)
            _sync(mesh)
        mean_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)

        top_actual = _first_device_tensor_to_numpy(top_gathered)
        bottom_actual = _first_device_tensor_to_numpy(bottom_gathered)
        top_diff = np.abs(top_actual - top_expected)
        bottom_diff = np.abs(bottom_actual - bottom_expected)
        print(
            "mesh_halo_probe "
            f"size={size} planes={planes} mesh={mesh_shape[0]}x{mesh_shape[1]} "
            f"local_shape={local_shape} boundary_rows={boundary_rows} "
            f"mean_ms={mean_ms:.3f} "
            f"top_max={float(top_diff.max()):.6g} bottom_max={float(bottom_diff.max()):.6g} "
            f"top_shape={tuple(top_actual.shape)} bottom_shape={tuple(bottom_actual.shape)}"
        )
        if assemble:
            for pad_before in (True, False):
                _probe_halo_assembly(
                    sharded=sharded,
                    top_gathered=top_gathered,
                    bottom_gathered=bottom_gathered,
                    matrix=matrix,
                    mesh=mesh,
                    mesh_size=mesh_size,
                    local_rows=local_rows,
                    boundary_rows=boundary_rows,
                    shard_dim=shard_dim,
                    pad_before=pad_before,
                )
    finally:
        _safe_deallocate(sharded, top, bottom, top_gathered, bottom_gathered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--mesh-shape", required=True, help="TTNN mesh shape as rows,cols.")
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--planes", type=int, default=1)
    parser.add_argument("--boundary-rows", type=int, default=32)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="Also assemble rank-specific one-sided row halos from gathered boundaries.",
    )
    args = parser.parse_args()

    mesh_shape = parse_mesh_shape(args.mesh_shape)
    if mesh_shape is None:
        parser.error("--mesh-shape is required.")

    previous_env = apply_tt_runtime_env(visible_device=args.tt_visible_devices)
    device = None
    try:
        device = open_ttnn_device(device_id=args.device_id, mesh_shape=mesh_shape)
        probe_halo_exchange(
            mesh=device,
            size=args.size,
            planes=args.planes,
            boundary_rows=args.boundary_rows,
            warmup=args.warmup,
            runs=args.runs,
            assemble=args.assemble,
        )
    finally:
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)


if __name__ == "__main__":
    main()
