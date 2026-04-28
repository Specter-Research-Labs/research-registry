"""Stage 6: TT-Lang sub-tile reintegration orchestration."""
from __future__ import annotations

from dataclasses import dataclass
import os
import time

import numpy as np

from ..ttlang_runtime import run_ttlang_kernel
from .fft import _is_mesh_device, _mesh_size
from .mesh_halo import (
    assemble_one_sided_mesh_row_halo,
    assemble_one_sided_torus_col_halo,
    gather_mesh_row_boundaries,
)
from .reintegration_generic import _np_to_ttnn_layout, _same_device_buffer
from ttlang.reintegration_subtile import (
    make_torus_halo_pad,
    make_subtile_reintegration_group_block_halo_separable,
    subtile_reintegration_group_param_matrix,
    subtile_reintegration_group_block_selector_matrices,
    subtile_reintegration_offset_groups,
)
from ttlang.subtile_shift import (
    TILE_SIZE,
    subtile_part_tile_deltas,
)


@dataclass
class _GroupResources:
    offsets: tuple[tuple[int, int], ...]
    pad_kernel: object
    kernel: object
    row_selectors: object
    col_selectors: object
    params: object


@dataclass
class _PaddedBuffers:
    mass: object
    flow_y: object
    flow_x: object


@dataclass
class _MeshInputShards:
    matrix: object
    local: object
    top_gathered: object
    bottom_gathered: object
    cleanup: tuple[object, ...]

    def close(self) -> None:
        _deallocate_many((self.top_gathered, self.bottom_gathered, *self.cleanup))


@dataclass
class _MeshPaddedBuffers:
    mass: object
    flow_y: object
    flow_x: object
    cleanup: tuple[object, ...]

    def close(self) -> None:
        for item in self.cleanup:
            close = getattr(item, "close", None)
            if callable(close):
                close()
            else:
                _deallocate_many((item,))


class TTLangSubtileReintegration:
    """Run Lenia reintegration as TT-Lang sub-tile contribution kernels.

    Offsets are grouped by source-tile sign pattern. Each group first stages a
    one-tile torus halo, then runs a 2x2 block-selector kernel over every tile.
    """

    def __init__(self, device, *, dtype=None):
        import ttnn

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._resources: dict[tuple[tuple[tuple[int, int], ...], float, float, float], _GroupResources] = {}
        self._padded_buffers: dict[tuple[tuple[tuple[int, int], ...], int, int, int, int], _PaddedBuffers] = {}
        self._trace_timings = os.environ.get("LENIA_TT_REINTEGRATION_TRACE") == "1"

    def close(self) -> None:
        import ttnn

        for resources in self._resources.values():
            for tensor in (resources.row_selectors, resources.col_selectors, resources.params):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._resources.clear()
        for buffers in self._padded_buffers.values():
            for tensor in (buffers.mass, buffers.flow_y, buffers.flow_x):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._padded_buffers.clear()

    def __call__(
        self,
        mass_tt,
        flow_y_tt,
        flow_x_tt,
        *,
        batch: int,
        channels: int,
        sx: int,
        sy: int,
        dd: int,
        dt: float,
        sigma: float,
        use_torus: bool,
        mass_is_flat: bool = False,
        flow_is_flat: bool = False,
        return_flat: bool = False,
    ):
        if not use_torus:
            raise ValueError("TT-Lang sub-tile reintegration currently supports torus borders only.")
        if sx != sy:
            raise ValueError(f"TT-Lang sub-tile reintegration expects a square grid, got {sx}x{sy}.")
        if sx % TILE_SIZE != 0 or sy % TILE_SIZE != 0:
            raise ValueError(f"Expected dimensions divisible by {TILE_SIZE}, got {sx}x{sy}.")

        import ttnn

        if _is_mesh_device(self.device) and _mesh_size(self.device) > 1:
            return self._call_mesh_sharded(
                mass_tt,
                flow_y_tt,
                flow_x_tt,
                batch=batch,
                channels=channels,
                sx=sx,
                sy=sy,
                dd=dd,
                dt=dt,
                sigma=sigma,
                mass_is_flat=mass_is_flat,
                flow_is_flat=flow_is_flat,
                return_flat=return_flat,
            )

        trace = _TraceTimings(self.device, enabled=self._trace_timings)
        started_at = trace.start()
        if mass_is_flat:
            mass_matrix = mass_tt
            owned_mass_matrices = ()
        else:
            mass_matrix = _flatten_state_matrix(mass_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            owned_mass_matrices = (mass_matrix,)
        if flow_is_flat:
            flow_y_matrix = flow_y_tt
            flow_x_matrix = flow_x_tt
            owned_flow_matrices = ()
        else:
            flow_y_matrix = _flatten_state_matrix(flow_y_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            flow_x_matrix = _flatten_state_matrix(flow_x_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            owned_flow_matrices = (flow_y_matrix, flow_x_matrix)
        started_at = trace.record("flatten", started_at)
        mass_tile = _to_tile_dtype(mass_matrix, self.dtype)
        flow_y_tile = _to_tile_dtype(flow_y_matrix, self.dtype)
        flow_x_tile = _to_tile_dtype(flow_x_matrix, self.dtype)
        started_at = trace.record("to_tile_dtype", started_at)
        acc = ttnn.zeros_like(mass_tile)
        scratch = ttnn.zeros_like(mass_tile)
        started_at = trace.record("allocate_accumulators", started_at)

        try:
            max_flow = float(dd) - float(sigma)
            for group_index, offsets in enumerate(subtile_reintegration_offset_groups(dd)):
                resources = self._group_resources(
                    offsets=offsets,
                    dt=dt,
                    max_flow=max_flow,
                    sigma=sigma,
                )
                started_at = trace.record(f"group_{group_index}_resources[{len(offsets)}]", started_at)
                buffers = self._padded_buffer(
                    offsets=offsets,
                    batch=batch,
                    channels=channels,
                    sx=sx,
                    sy=sy,
                )
                run_ttlang_kernel(
                    resources.pad_kernel,
                    mass_tile,
                    flow_y_tile,
                    flow_x_tile,
                    buffers.mass,
                    buffers.flow_y,
                    buffers.flow_x,
                )
                run_ttlang_kernel(
                    resources.kernel,
                    buffers.mass,
                    buffers.flow_y,
                    buffers.flow_x,
                    resources.row_selectors,
                    resources.col_selectors,
                    resources.params,
                    acc,
                    scratch,
                )
                acc, scratch = scratch, acc
                started_at = trace.record(f"group_{group_index}_kernel_accumulate[{len(offsets)}]", started_at)

            if return_flat:
                trace.record("return_flat", started_at)
                return acc

            result = ttnn.reshape(acc, (batch, channels, sx, sy))
            result = ttnn.permute(result, (0, 2, 3, 1))
            trace.record("restore_shape", started_at)
            return result
        finally:
            borrowed = (mass_tt, flow_y_tt, flow_x_tt, acc)
            for tensor in (*owned_mass_matrices, *owned_flow_matrices, mass_tile, flow_y_tile, flow_x_tile, scratch):
                if tensor is None or tensor is acc or _is_borrowed_tensor(tensor, borrowed):
                    continue
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass

    def _group_resources(
        self,
        *,
        offsets: tuple[tuple[int, int], ...],
        dt: float,
        max_flow: float,
        sigma: float,
    ) -> _GroupResources:
        key = (offsets, float(dt), float(max_flow), float(sigma))
        cached = self._resources.get(key)
        if cached is not None:
            return cached

        row_selectors, col_selectors = subtile_reintegration_group_block_selector_matrices(offsets)
        params = subtile_reintegration_group_param_matrix(
            offsets,
            dt=dt,
            max_flow=max_flow,
            sigma=sigma,
        )
        resources = _GroupResources(
            offsets=offsets,
            pad_kernel=make_torus_halo_pad(offsets),
            kernel=make_subtile_reintegration_group_block_halo_separable(offsets),
            row_selectors=_matrix_to_device(row_selectors, self.device, self.dtype),
            col_selectors=_matrix_to_device(col_selectors, self.device, self.dtype),
            params=_matrix_to_device(params, self.device, self.dtype),
        )
        self._resources[key] = resources
        return resources

    def _padded_buffer(
        self,
        *,
        offsets: tuple[tuple[int, int], ...],
        batch: int,
        channels: int,
        sx: int,
        sy: int,
    ) -> _PaddedBuffers:
        key = (offsets, int(batch), int(channels), int(sx), int(sy))
        cached = self._padded_buffers.get(key)
        if cached is not None:
            return cached

        padded = np.zeros((batch * channels * (sx + TILE_SIZE), sy + TILE_SIZE), dtype=np.float32)
        buffers = _PaddedBuffers(
            mass=_matrix_to_device(padded, self.device, self.dtype),
            flow_y=_matrix_to_device(padded, self.device, self.dtype),
            flow_x=_matrix_to_device(padded, self.device, self.dtype),
        )
        self._padded_buffers[key] = buffers
        return buffers

    def _call_mesh_sharded(
        self,
        mass_tt,
        flow_y_tt,
        flow_x_tt,
        *,
        batch: int,
        channels: int,
        sx: int,
        sy: int,
        dd: int,
        dt: float,
        sigma: float,
        mass_is_flat: bool,
        flow_is_flat: bool,
        return_flat: bool,
    ):
        import ttnn

        mesh_size = _mesh_size(self.device)
        if sx % mesh_size != 0:
            raise ValueError(f"Mesh reintegration requires sx={sx} divisible by mesh size {mesh_size}.")
        local_sx = sx // mesh_size
        if local_sx % TILE_SIZE != 0:
            raise ValueError(f"Mesh reintegration local rows must be tile-aligned, got {local_sx}.")

        trace = _TraceTimings(self.device, enabled=self._trace_timings)
        started_at = trace.start()
        plane_count = batch * channels
        owned_mass_matrices = ()
        owned_flow_matrices = ()
        if mass_is_flat:
            mass_matrix = mass_tt
        else:
            mass_matrix = _flatten_state_matrix(mass_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            owned_mass_matrices = (mass_matrix,)
        if flow_is_flat:
            flow_y_matrix = flow_y_tt
            flow_x_matrix = flow_x_tt
        else:
            flow_y_matrix = _flatten_state_matrix(flow_y_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            flow_x_matrix = _flatten_state_matrix(flow_x_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            owned_flow_matrices = (flow_y_matrix, flow_x_matrix)
        started_at = trace.record("mesh_flatten", started_at)

        mass_tile = _to_tile_dtype(mass_matrix, self.dtype)
        flow_y_tile = _to_tile_dtype(flow_y_matrix, self.dtype)
        flow_x_tile = _to_tile_dtype(flow_x_matrix, self.dtype)
        started_at = trace.record("mesh_to_tile_dtype", started_at)

        mass_shards = flow_y_shards = flow_x_shards = None
        acc = scratch = acc3 = full3 = result = None
        try:
            mass_shards = _mesh_row_shard_matrix(
                mass_tile,
                plane_count=plane_count,
                sx=sx,
                sy=sy,
                local_sx=local_sx,
            )
            flow_y_shards = _mesh_row_shard_matrix(
                flow_y_tile,
                plane_count=plane_count,
                sx=sx,
                sy=sy,
                local_sx=local_sx,
            )
            flow_x_shards = _mesh_row_shard_matrix(
                flow_x_tile,
                plane_count=plane_count,
                sx=sx,
                sy=sy,
                local_sx=local_sx,
            )
            started_at = trace.record("mesh_partition_and_gather_halos", started_at)

            acc = ttnn.zeros_like(mass_shards.local)
            scratch = ttnn.zeros_like(mass_shards.local)
            started_at = trace.record("mesh_allocate_accumulators", started_at)

            max_flow = float(dd) - float(sigma)
            for group_index, offsets in enumerate(subtile_reintegration_offset_groups(dd)):
                resources = self._group_resources(
                    offsets=offsets,
                    dt=dt,
                    max_flow=max_flow,
                    sigma=sigma,
                )
                buffers = self._mesh_padded_buffers(
                    mass=mass_shards,
                    flow_y=flow_y_shards,
                    flow_x=flow_x_shards,
                    offsets=offsets,
                    mesh_size=mesh_size,
                    plane_count=plane_count,
                    local_sx=local_sx,
                    sy=sy,
                )
                try:
                    run_ttlang_kernel(
                        resources.kernel,
                        buffers.mass,
                        buffers.flow_y,
                        buffers.flow_x,
                        resources.row_selectors,
                        resources.col_selectors,
                        resources.params,
                        acc,
                        scratch,
                    )
                finally:
                    buffers.close()
                acc, scratch = scratch, acc
                started_at = trace.record(f"mesh_group_{group_index}_kernel_accumulate[{len(offsets)}]", started_at)

            acc3 = ttnn.reshape(acc, (plane_count, local_sx, sy))
            full3 = ttnn.all_gather(acc3, dim=1)
            started_at = trace.record("mesh_all_gather_result", started_at)
            if return_flat:
                result = ttnn.reshape(full3, (plane_count * sx, sy))
            else:
                full4 = ttnn.reshape(full3, (batch, channels, sx, sy))
                result = ttnn.permute(full4, (0, 2, 3, 1))
            trace.record("mesh_restore_shape", started_at)
            return result
        finally:
            borrowed = (mass_tt, flow_y_tt, flow_x_tt, acc, result)
            for shards in (mass_shards, flow_y_shards, flow_x_shards):
                if shards is not None:
                    shards.close()
            for tensor in (
                *owned_mass_matrices,
                *owned_flow_matrices,
                mass_tile,
                flow_y_tile,
                flow_x_tile,
                scratch,
            ):
                if tensor is None or _is_borrowed_tensor(tensor, borrowed):
                    continue
                _deallocate_many((tensor,))

    def _mesh_padded_buffers(
        self,
        *,
        mass: _MeshInputShards,
        flow_y: _MeshInputShards,
        flow_x: _MeshInputShards,
        offsets: tuple[tuple[int, int], ...],
        mesh_size: int,
        plane_count: int,
        local_sx: int,
        sy: int,
    ) -> _MeshPaddedBuffers:
        row_delta0, _ = subtile_part_tile_deltas(offsets[0][0])
        col_delta0, _ = subtile_part_tile_deltas(offsets[0][1])
        pad_row_before = row_delta0 < 0
        pad_col_before = col_delta0 < 0
        mass_padded, mass_cleanup = _mesh_one_sided_halo_matrix(
            mass,
            mesh_size=mesh_size,
            pad_row_before=pad_row_before,
            pad_col_before=pad_col_before,
            plane_count=plane_count,
            local_sx=local_sx,
            sy=sy,
        )
        flow_y_padded, flow_y_cleanup = _mesh_one_sided_halo_matrix(
            flow_y,
            mesh_size=mesh_size,
            pad_row_before=pad_row_before,
            pad_col_before=pad_col_before,
            plane_count=plane_count,
            local_sx=local_sx,
            sy=sy,
        )
        flow_x_padded, flow_x_cleanup = _mesh_one_sided_halo_matrix(
            flow_x,
            mesh_size=mesh_size,
            pad_row_before=pad_row_before,
            pad_col_before=pad_col_before,
            plane_count=plane_count,
            local_sx=local_sx,
            sy=sy,
        )
        return _MeshPaddedBuffers(
            mass=mass_padded,
            flow_y=flow_y_padded,
            flow_x=flow_x_padded,
            cleanup=(*mass_cleanup, *flow_y_cleanup, *flow_x_cleanup),
        )


class _TraceTimings:
    def __init__(self, device, *, enabled: bool):
        self.device = device
        self.enabled = enabled

    def start(self) -> float | None:
        if not self.enabled:
            return None
        self._sync()
        return time.perf_counter()

    def record(self, label: str, started_at: float | None) -> float | None:
        if not self.enabled or started_at is None:
            return None
        self._sync()
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        print(f"[tt-reintegration] {label} {elapsed_ms:.3f}ms", flush=True)
        return time.perf_counter()

    def _sync(self) -> None:
        import ttnn

        ttnn.synchronize_device(self.device)


def _flatten_state_matrix(tensor, *, batch: int, channels: int, sx: int, sy: int):
    import ttnn

    return ttnn.reshape(ttnn.permute(tensor, (0, 3, 1, 2)), (batch * channels * sx, sy))


def _to_tile_dtype(tensor, dtype):
    import ttnn

    tiled = ttnn.to_layout(tensor, ttnn.TILE_LAYOUT)
    return ttnn.typecast(tiled, dtype)


def _is_borrowed_tensor(tensor, borrowed: tuple[object, ...]) -> bool:
    return any(candidate is not None and _same_device_buffer(tensor, candidate) for candidate in borrowed)


def _matrix_to_device(matrix: np.ndarray, device, dtype):
    import ttnn

    return _np_to_ttnn_layout(
        matrix,
        device,
        dtype=dtype,
        layout=ttnn.TILE_LAYOUT,
    )


def _mesh_row_shard_matrix(matrix, *, plane_count: int, sx: int, sy: int, local_sx: int) -> _MeshInputShards:
    import ttnn

    matrix3 = ttnn.reshape(matrix, (plane_count, sx, sy))
    sharded3 = ttnn.mesh_partition(matrix3, dim=1)
    local = ttnn.reshape(sharded3, (plane_count * local_sx, sy))
    top_gathered, bottom_gathered, boundary_cleanup = gather_mesh_row_boundaries(
        sharded3,
        local_rows=local_sx,
        boundary_rows=TILE_SIZE,
        shard_dim=1,
    )
    return _MeshInputShards(
        matrix=matrix3,
        local=local,
        top_gathered=top_gathered,
        bottom_gathered=bottom_gathered,
        cleanup=(sharded3, *boundary_cleanup),
    )


def _mesh_one_sided_halo_matrix(
    shards: _MeshInputShards,
    *,
    mesh_size: int,
    pad_row_before: bool,
    pad_col_before: bool,
    plane_count: int,
    local_sx: int,
    sy: int,
) -> tuple[object, tuple[object, ...]]:
    import ttnn

    local3 = ttnn.reshape(shards.local, (plane_count, local_sx, sy))
    row = assemble_one_sided_mesh_row_halo(
        local3,
        shards.top_gathered,
        shards.bottom_gathered,
        mesh_size=mesh_size,
        boundary_rows=TILE_SIZE,
        shard_dim=1,
        pad_before=pad_row_before,
    )
    col = assemble_one_sided_torus_col_halo(
        row.tensor,
        boundary_cols=TILE_SIZE,
        pad_before=pad_col_before,
    )
    padded = ttnn.reshape(col.tensor, (plane_count * (local_sx + TILE_SIZE), sy + TILE_SIZE))
    return padded, (col, row)


def _deallocate_many(tensors: tuple[object, ...]) -> None:
    import ttnn

    for tensor in tensors:
        if tensor is None:
            continue
        try:
            ttnn.deallocate(tensor)
        except Exception:
            pass
