"""Shared TT tensor helpers for Lenia plane/matrix kernels."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fft import _is_mesh_device, _mesh_size, _ttnn_to_np

TH = 32
TW = 32


def _np_to_ttnn_layout(arr: np.ndarray, device, *, dtype, layout, shard_dim: int | None = None):
    import torch
    import ttnn

    tensor = torch.from_numpy(arr.astype(np.float32, copy=False))
    mesh_mapper = None
    if _is_mesh_device(device):
        if shard_dim is not None and arr.shape[shard_dim] >= _mesh_size(device):
            mesh_mapper = ttnn.shard_tensor_to_mesh_mapper(device, shard_dim)
        else:
            mesh_mapper = ttnn.replicate_tensor_to_mesh_mapper(device)
    return ttnn.from_torch(
        tensor,
        device=device,
        layout=layout,
        dtype=dtype,
        mesh_mapper=mesh_mapper,
    )


def _same_device_buffer(lhs, rhs) -> bool:
    if lhs is None or rhs is None:
        return False
    if lhs is rhs:
        return True
    try:
        return lhs.buffer_address() == rhs.buffer_address()
    except Exception:
        return False


@dataclass(frozen=True)
class _CoreSpan:
    x: int
    y: int
    start_tile: int
    tile_count: int


def _build_core_spans(num_tiles: int, grid_x: int, grid_y: int) -> tuple[object, tuple[_CoreSpan, ...]]:
    import ttnn

    max_cores = grid_x * grid_y
    if num_tiles <= 0 or max_cores <= 0:
        raise ValueError("Cannot build TT core spans for empty work or grid")
    spans: list[_CoreSpan] = []
    ranges = []
    num_cores = min(num_tiles, max_cores)
    base_tiles = num_tiles // num_cores
    extra_tiles = num_tiles % num_cores
    start_tile = 0
    for index in range(num_cores):
        x = index % grid_x
        y = index // grid_x
        tile_count = base_tiles + (1 if index < extra_tiles else 0)
        coord = ttnn.CoreCoord(x, y)
        spans.append(_CoreSpan(x=x, y=y, start_tile=start_tile, tile_count=tile_count))
        ranges.append(ttnn.CoreRange(coord, coord))
        start_tile += tile_count
    return ttnn.CoreRangeSet(ranges), tuple(spans)


def _mesh_coords(device) -> list[object]:
    import ttnn

    if not _is_mesh_device(device):
        return []
    rows, cols = device.shape
    return [ttnn.MeshCoordinate(r, c) for r in range(rows) for c in range(cols)]


def _flatten_planes_matrix(tensor, *, batch: int, sx: int, sy: int, channels: int):
    import ttnn

    permuted = ttnn.permute(tensor, (0, 3, 1, 2))
    return ttnn.reshape(permuted, (batch * channels * sx, sy))


def _restore_planes(tensor, *, batch: int, sx: int, sy: int, channels: int):
    import ttnn

    reshaped = ttnn.reshape(tensor, (batch, channels, sx, sy))
    return ttnn.permute(reshaped, (0, 2, 3, 1))


def _plane_result_to_host(
    plane_result,
    device,
    *,
    batch: int,
    sx: int,
    sy: int,
    channels: int,
    mesh_sharded: bool | None = None,
) -> np.ndarray:
    import ttnn

    if not _is_mesh_device(device):
        host_planes = _ttnn_to_np(plane_result).astype(np.float32, copy=False)
    else:
        compose_shards = batch * channels >= _mesh_size(device) if mesh_sharded is None else mesh_sharded
        if compose_shards:
            host_planes = _ttnn_to_np(plane_result, compose_dim=0).astype(np.float32, copy=False)
        else:
            host_planes = ttnn.to_torch(ttnn.get_device_tensors(plane_result)[0]).float().numpy().astype(np.float32, copy=False)
    if host_planes.ndim == 2:
        return host_planes.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1).astype(np.float32, copy=False)
    return host_planes.reshape(batch, channels, sx, sy, 1).transpose(0, 2, 3, 1, 4)[..., 0].astype(np.float32, copy=False)


def _tiles_to_mass(pages: np.ndarray, *, sx: int, sy: int, total_tiles: int) -> np.ndarray:
    if pages.ndim != 3 or pages.shape[1:] != (TH, TW):
        raise ValueError(f"Expected pages [tiles, {TH}, {TW}], got {pages.shape}.")
    if total_tiles < 0 or total_tiles > pages.shape[0]:
        raise ValueError(f"Invalid total_tiles={total_tiles} for pages shape {pages.shape}.")
    tiles_x = (sy + TW - 1) // TW
    tiles_y = (sx + TH - 1) // TH
    if total_tiles > tiles_x * tiles_y:
        raise ValueError(f"total_tiles={total_tiles} exceeds padded grid {tiles_y}x{tiles_x}.")
    padded = np.zeros((tiles_y * TH, tiles_x * TW), dtype=np.float32)
    for tile_index in range(total_tiles):
        tile_y = tile_index // tiles_x
        tile_x = tile_index % tiles_x
        row = tile_y * TH
        col = tile_x * TW
        padded[row : row + TH, col : col + TW] = pages[tile_index]
    return padded[:sx, :sy].astype(np.float32, copy=False)
