"""TT Flow Lenia engine — TTNN dense stages with on-device reintegration."""
from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable

import numpy as np

from .config import BatchedConfig, CompiledKernels
from .outputs import StepOutputs
from .stages.fft import TTNNDFTMatmul, TTNNMeshDFTMatmul, _is_mesh_device, _mesh_size, _np_to_ttnn, _ttnn_to_np
from .stages.flow import ttnn_compute_flow, ttnn_mass_field
from .stages.flow_ttlang import TTLangSplitSobelFlow
from .stages.gather_spectra import gather_kernel_spectra_ttnn
from .stages.gather_spectra_ttlang import TTLangGatherKernelSpectra
from .stages.growth import compile_channel_routes, ttnn_growth_bell, ttnn_route_channels
from .stages.growth_ttlang import TTLangGrowthRoute
from .stages.reintegration import build_pos_grid
from .stages.reintegration_generic import _flatten_planes_matrix, _np_to_ttnn_layout, _plane_result_to_host, _restore_planes
from .stages.reintegration_ttlang import TTLangSubtileReintegration
from .stages.reintegration_ttnn import reintegrate_ttnn


def _is_multi_device_mesh(device) -> bool:
    return _is_mesh_device(device) and _mesh_size(device) > 1


class TTFlowLeniaEngine:
    """Flow Lenia engine targeting Tenstorrent hardware."""

    def __init__(
        self,
        config: BatchedConfig,
        kernels: CompiledKernels,
        device=None,
        *,
        front_half_mode: str = "dft_ttlang",
        reintegration_mode: str = "ttlang",
    ):
        if front_half_mode != "dft_ttlang":
            raise ValueError("The TT backend supports only front_half_mode='dft_ttlang'.")
        if reintegration_mode != "ttlang":
            raise ValueError("The TT backend supports only reintegration_mode='ttlang'.")
        if device is None:
            raise ValueError("TTFlowLeniaEngine requires a TT device. Use the reference backend for host execution.")
        self.config = config
        self.kernels = kernels
        self.device = device
        self.front_half_mode = front_half_mode
        self.reintegration_mode = reintegration_mode
        self.pos_grid = build_pos_grid(config.sx, config.sy)
        self._dft = None
        self._kernel_groups = ()
        self._ttlang_spectra = None
        self._spatial_convolution = None
        self._pos_y = None
        self._pos_x = None
        self._reintegration = None
        self._growth_flow = None
        self._growth_reintegration = None
        self._ttlang_reintegration = None
        self._ttlang_growth_route = None
        self._mesh_dft_enabled = _is_multi_device_mesh(device) and os.environ.get("LENIA_TT_MESH_DFT") == "1"
        self._ttlang_flow = TTLangSplitSobelFlow(device) if reintegration_mode == "ttlang" else None
        self._growth_m = _np_to_ttnn(kernels.m.reshape(1, 1, 1, -1), device)
        self._growth_s = _np_to_ttnn(kernels.s.reshape(1, 1, 1, -1), device)
        self._growth_h = _np_to_ttnn(kernels.h.reshape(1, 1, 1, -1), device)
        self._channel_routes = compile_channel_routes(kernels.c1_mask)
        import ttnn

        dft_cls = TTNNMeshDFTMatmul if self._mesh_dft_enabled else TTNNDFTMatmul
        self._dft = dft_cls(config.sx, device, dtype=ttnn.bfloat16)
        self._ttlang_spectra = TTLangGatherKernelSpectra(
            device,
            fK=kernels.fK,
            c0_idxs=kernels.c0_idxs,
        )
        self._ttlang_growth_route = TTLangGrowthRoute(
            device,
            m=kernels.m,
            s=kernels.s,
            h=kernels.h,
            c1_mask=kernels.c1_mask,
        )
        self._ttlang_reintegration = TTLangSubtileReintegration(device)
        self._profile_stage_timings = False
        self._stage_timings: dict[str, list[float]] = {}
        self._trace_stage_profile = os.environ.get("LENIA_TT_STAGE_TRACE") == "1"

    def close(self) -> None:
        if self.device is None:
            return
        try:
            import ttnn

            dft_close = getattr(self._dft, 'close', None)
            if callable(dft_close):
                dft_close()
            spatial_close = getattr(self._spatial_convolution, 'close', None)
            if callable(spatial_close):
                spatial_close()
            spectra_close = getattr(self._ttlang_spectra, 'close', None)
            if callable(spectra_close):
                spectra_close()
            for tensor in (
                getattr(self, '_growth_m', None),
                getattr(self, '_growth_s', None),
                getattr(self, '_growth_h', None),
                getattr(self, '_pos_y', None),
                getattr(self, '_pos_x', None),
                *(group.fK_re for group in getattr(self, '_kernel_groups', ())),
                *(group.fK_im for group in getattr(self, '_kernel_groups', ())),
            ):
                if tensor is None:
                    continue
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
            try:
                reintegration_close = getattr(self, '_reintegration', None)
                if reintegration_close is not None:
                    reintegration_close.close()
            except Exception:
                pass
            try:
                growth_flow_close = getattr(self, '_growth_flow', None)
                if growth_flow_close is not None:
                    growth_flow_close.close()
            except Exception:
                pass
            try:
                growth_reintegration_close = getattr(self, '_growth_reintegration', None)
                if growth_reintegration_close is not None:
                    growth_reintegration_close.close()
            except Exception:
                pass
            try:
                ttlang_reintegration_close = getattr(self, '_ttlang_reintegration', None)
                if ttlang_reintegration_close is not None:
                    ttlang_reintegration_close.close()
            except Exception:
                pass
            try:
                ttlang_growth_close = getattr(self, '_ttlang_growth_route', None)
                if ttlang_growth_close is not None:
                    ttlang_growth_close.close()
                ttlang_flow_close = getattr(self, '_ttlang_flow', None)
                if ttlang_flow_close is not None:
                    ttlang_flow_close.close()
            except Exception:
                pass
            try:
                ttnn.synchronize_device(self.device)
            except Exception:
                pass
        finally:
            self._growth_m = None
            self._growth_s = None
            self._growth_h = None
            self._channel_routes = ()
            self._kernel_groups = ()
            self._ttlang_spectra = None
            self._spatial_convolution = None
            self._reintegration = None
            self._growth_flow = None
            self._growth_reintegration = None
            self._ttlang_reintegration = None
            self._ttlang_growth_route = None
            self._ttlang_flow = None

    def step(self, mass: np.ndarray, capture_stages: bool = False) -> StepOutputs:
        return self._step_ttnn(mass, capture_stages)

    def reset_stage_timings(self) -> None:
        self._profile_stage_timings = True
        self._stage_timings = {}

    def stage_timing_summary(self) -> dict[str, object]:
        mean_ms = {name: 1000.0 * sum(values) / len(values) for name, values in self._stage_timings.items() if values}
        total_ms = {name: 1000.0 * sum(values) for name, values in self._stage_timings.items() if values}
        counts = {name: len(values) for name, values in self._stage_timings.items() if values}
        return {"mean_ms": mean_ms, "total_ms": total_ms, "counts": counts}

    def _record_stage_time(self, name: str, elapsed_s: float) -> None:
        if not self._profile_stage_timings:
            return
        self._stage_timings.setdefault(name, []).append(elapsed_s)

    def _sync_for_profiling(self) -> None:
        if not self._profile_stage_timings:
            return
        import ttnn

        ttnn.synchronize_device(self.device)

    def _begin_profile_stage(self, name: str) -> float | None:
        if not self._profile_stage_timings:
            return None
        if self._trace_stage_profile:
            print(f"[tt-stage-start] {name}", flush=True)
        self._sync_for_profiling()
        return time.perf_counter()

    def _end_profile_stage(self, name: str, started_at: float | None) -> None:
        if started_at is None:
            return
        self._sync_for_profiling()
        elapsed_s = time.perf_counter() - started_at
        self._record_stage_time(name, elapsed_s)
        if self._trace_stage_profile:
            print(f"[tt-stage-end] {name} {elapsed_s * 1000.0:.3f}ms", flush=True)

    @staticmethod
    def _reshape_fft_output(tensor, *, batch: int, size: int, last_dim: int):
        import ttnn

        tensor = ttnn.reshape(tensor, (batch, last_dim, size, size))
        return ttnn.permute(tensor, (0, 2, 3, 1))

    @staticmethod
    def _flatten_last_dim(tensor, *, batch: int, sx: int, sy: int):
        import ttnn

        last_dim = int(tensor.shape[3])
        tensor = ttnn.permute(tensor, (0, 3, 1, 2))
        return ttnn.reshape(tensor, (batch * last_dim, sx, sy))

    def _dft_forward_2d(self, x_re, x_im):
        if not self._mesh_dft_enabled:
            return self._dft.forward_2d(x_re, x_im)
        x_re_sharded = x_im_sharded = None
        try:
            x_re_sharded = self._dft.row_shard_replicated(x_re)
            x_im_sharded = self._dft.row_shard_replicated(x_im)
            return self._dft.forward_2d(x_re_sharded, x_im_sharded)
        finally:
            self._release_tensors((x_re_sharded, x_im_sharded))

    def _dft_inverse_2d(self, x_re, x_im):
        if not self._mesh_dft_enabled:
            return self._dft.inverse_2d(x_re, x_im)
        x_re_sharded = x_im_sharded = None
        try:
            x_re_sharded = self._dft.row_shard_replicated(x_re)
            x_im_sharded = self._dft.row_shard_replicated(x_im)
            return self._dft.inverse_2d(x_re_sharded, x_im_sharded)
        finally:
            self._release_tensors((x_re_sharded, x_im_sharded))

    def _mass_to_device(self, mass: np.ndarray):
        import ttnn

        batch_shard_dim = 0 if _is_multi_device_mesh(self.device) and mass.shape[0] >= _mesh_size(self.device) else None
        dtype = ttnn.bfloat16 if self.front_half_mode in {"dft", "dft_ttlang"} else ttnn.float32
        return _np_to_ttnn(mass, self.device, dtype=dtype, shard_dim=batch_shard_dim)

    def _mass_to_device_packed(self, mass: np.ndarray):
        import ttnn

        batch, sx, sy, channels = mass.shape
        packed = (
            mass.astype(np.float32, copy=False)
            .transpose(0, 3, 1, 2)
            .reshape(batch * channels * sx, sy)
            .astype(np.float32, copy=False)
        )
        shard_dim = 0 if _is_multi_device_mesh(self.device) and batch >= _mesh_size(self.device) else None
        layout = ttnn.TILE_LAYOUT if self.front_half_mode == "dft_ttlang" else ttnn.ROW_MAJOR_LAYOUT
        dtype = ttnn.bfloat16 if self.front_half_mode == "dft_ttlang" else ttnn.float32
        return _np_to_ttnn_layout(
            packed,
            self.device,
            dtype=dtype,
            layout=layout,
            shard_dim=shard_dim,
        )

    def _mass_packed_to_host(self, mass_planes_tt, *, batch: int, channels: int) -> np.ndarray:
        return _plane_result_to_host(
            mass_planes_tt,
            self.device,
            batch=batch,
            sx=self.config.sx,
            sy=self.config.sy,
            channels=channels,
            mesh_sharded=_is_multi_device_mesh(self.device) and batch >= _mesh_size(self.device),
        )

    def _mesh_state_is_sharded(self, *, batch: int) -> bool:
        return _is_multi_device_mesh(self.device) and batch >= _mesh_size(self.device)

    def _plane_matrix_to_host(self, plane_tt, *, batch: int, channels: int) -> np.ndarray:
        return _plane_result_to_host(
            plane_tt,
            self.device,
            batch=batch,
            sx=self.config.sx,
            sy=self.config.sy,
            channels=channels,
            mesh_sharded=self._mesh_state_is_sharded(batch=batch),
        )

    def _use_packed_tt_state(self) -> bool:
        return (
            self.front_half_mode == "dft_ttlang"
            and self.reintegration_mode == "ttlang"
            and not _is_multi_device_mesh(self.device)
        )

    def _packed_mass_field_matrix(self, mass_planes_tt, *, batch: int, channels: int):
        """Return the channel-summed mass matrix from packed `[B*C*sx, sy]` state."""
        import ttnn

        cfg = self.config
        if channels == 1 and (cfg.chem_channel is None or cfg.chem_include_in_mass):
            return mass_planes_tt, ()
        reshaped = ttnn.reshape(mass_planes_tt, (batch, channels, cfg.sx, cfg.sy))
        total = ttnn.sum(reshaped, dim=1, keepdim=True)
        cleanup = [reshaped, total]
        if cfg.chem_channel is not None and not cfg.chem_include_in_mass:
            chem = ttnn.slice(
                reshaped,
                (0, cfg.chem_channel, 0, 0),
                (batch, cfg.chem_channel + 1, cfg.sx, cfg.sy),
            )
            total_without_chem = ttnn.subtract(total, chem)
            cleanup.extend((chem, total_without_chem))
            total = total_without_chem
        matrix = ttnn.reshape(total, (batch * cfg.sx, cfg.sy))
        cleanup.append(matrix)
        return matrix, tuple(cleanup)

    def _reintegrate_ttnn_device(self, mass_tt, flow_y_tt, flow_x_tt, *, batch: int, channels: int):
        import ttnn

        cfg = self.config
        if batch == 1:
            return reintegrate_ttnn(
                mass_tt,
                flow_y_tt,
                flow_x_tt,
                pos_y=self._pos_y,
                pos_x=self._pos_x,
                dt=cfg.dt,
                dd=cfg.dd,
                sigma=cfg.sigma,
                use_torus=cfg.border == "torus",
                sx=cfg.sx,
                sy=cfg.sy,
                device=self.device,
            )

        batch_tensors = []
        for batch_index in range(batch):
            mass_slice = ttnn.slice(mass_tt, (batch_index, 0, 0, 0), (batch_index + 1, cfg.sx, cfg.sy, channels))
            flow_y_slice = ttnn.slice(flow_y_tt, (batch_index, 0, 0, 0), (batch_index + 1, cfg.sx, cfg.sy, channels))
            flow_x_slice = ttnn.slice(flow_x_tt, (batch_index, 0, 0, 0), (batch_index + 1, cfg.sx, cfg.sy, channels))
            result = reintegrate_ttnn(
                mass_slice,
                flow_y_slice,
                flow_x_slice,
                pos_y=self._pos_y,
                pos_x=self._pos_x,
                dt=cfg.dt,
                dd=cfg.dd,
                sigma=cfg.sigma,
                use_torus=cfg.border == "torus",
                sx=cfg.sx,
                sy=cfg.sy,
                device=self.device,
            )
            batch_tensors.append(result)
            for tensor in (mass_slice, flow_y_slice, flow_x_slice):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        if len(batch_tensors) == 1:
            return batch_tensors[0]
        result = ttnn.concat(batch_tensors, dim=0)
        for tensor in batch_tensors:
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass
        return result

    def _reintegrate_device(
        self,
        mass_tt,
        flow_tt,
        flow_y_tt,
        flow_x_tt,
        u_tt,
        *,
        batch: int,
        channels: int,
        mass_is_flat: bool = False,
        flow_is_flat: bool = False,
        return_flat: bool = False,
    ):
        cfg = self.config
        if self.reintegration_mode == "ttnn":
            return self._reintegrate_ttnn_device(mass_tt, flow_y_tt, flow_x_tt, batch=batch, channels=channels)
        if self.reintegration_mode == "ttlang":
            return self._ttlang_reintegration(
                mass_tt,
                flow_y_tt,
                flow_x_tt,
                batch=batch,
                channels=channels,
                sx=cfg.sx,
                sy=cfg.sy,
                dd=cfg.dd,
                dt=cfg.dt,
                sigma=cfg.sigma,
                use_torus=cfg.border == "torus",
                mass_is_flat=mass_is_flat,
                flow_is_flat=flow_is_flat,
                return_flat=return_flat,
            )
        if self.reintegration_mode == "generic_u":
            return self._growth_reintegration(
                mass_tt,
                u_tt,
                batch=batch,
                channels=channels,
                sx=cfg.sx,
                sy=cfg.sy,
                dd=cfg.dd,
                dt=cfg.dt,
                sigma=cfg.sigma,
                theta_a=cfg.theta_a,
                flow_n=cfg.n,
                alpha_mode=cfg.implementation.alpha_mode,
                flow_clip=cfg.implementation.flow_clip,
                chem_channel=cfg.chem_channel,
                chem_include_in_mass=cfg.chem_include_in_mass,
                use_torus=cfg.border == "torus",
                return_device=True,
            )
        return self._reintegration(
            mass_tt,
            flow_tt,
            batch=batch,
            channels=channels,
            sx=cfg.sx,
            sy=cfg.sy,
            dd=cfg.dd,
            dt=cfg.dt,
            sigma=cfg.sigma,
            use_torus=cfg.border == 'torus',
            return_device=True,
        )

    def _ttnn_dense_front_half(self, mass_tt, *, batch: int, channels: int, capture_stages: bool):
        import ttnn

        if self._mesh_dft_enabled and batch != 1:
            raise ValueError("LENIA_TT_MESH_DFT currently supports batch=1 mesh runs only.")

        cfg = self.config
        nb_k = self.kernels.fK.shape[3]

        mass_tile = ttnn.to_layout(mass_tt, ttnn.TILE_LAYOUT)
        uk_matrix_tt = None
        u_matrix_tt = None
        mass_perm = None
        mass_flat = None
        mass_im = None
        fA_re_flat = None
        fA_im_flat = None
        fA_re_matrix = None
        fA_im_matrix = None
        fA_re_tt = None
        fA_im_tt = None
        spec_re_tt = None
        spec_im_tt = None
        spec_re_matrix = None
        spec_im_matrix = None
        spec_re_flat = None
        spec_im_flat = None
        uk_flat = None
        uk_tt = None
        if self.front_half_mode in {"local", "local_ttlang"}:
            stage_started_at = self._begin_profile_stage("front_half")
            if self.front_half_mode == "local_ttlang":
                uk_matrix_tt = self._spatial_convolution(
                    mass_tile,
                    batch=batch,
                    channels=channels,
                    sx=cfg.sx,
                    sy=cfg.sy,
                    return_matrix=True,
                )
                uk_tt = None
            else:
                uk_tt = self._spatial_convolution(mass_tile, batch=batch, channels=channels, sx=cfg.sx, sy=cfg.sy)
            self._end_profile_stage("front_half", stage_started_at)
        else:
            stage_started_at = self._begin_profile_stage("fft")
            mass_perm = ttnn.permute(mass_tile, (0, 3, 1, 2))
            mass_flat = ttnn.reshape(mass_perm, (batch * channels, cfg.sx, cfg.sy))
            mass_im = ttnn.zeros_like(mass_flat)

            fA_re_flat, fA_im_flat = self._dft_forward_2d(mass_flat, mass_im)
            if self.front_half_mode == "dft_ttlang":
                fA_re_matrix = ttnn.reshape(fA_re_flat, (batch * channels * cfg.sx, cfg.sy))
                fA_im_matrix = ttnn.reshape(fA_im_flat, (batch * channels * cfg.sx, cfg.sy))
                if capture_stages:
                    fA_re_tt = self._reshape_fft_output(fA_re_flat, batch=batch, size=cfg.sx, last_dim=channels)
                    fA_im_tt = self._reshape_fft_output(fA_im_flat, batch=batch, size=cfg.sx, last_dim=channels)
            else:
                fA_re_tt = self._reshape_fft_output(fA_re_flat, batch=batch, size=cfg.sx, last_dim=channels)
                fA_im_tt = self._reshape_fft_output(fA_im_flat, batch=batch, size=cfg.sx, last_dim=channels)
            self._end_profile_stage("fft", stage_started_at)

            stage_started_at = self._begin_profile_stage("spectra")
            if self.front_half_mode == "dft_ttlang":
                spec_re_matrix, spec_im_matrix = self._ttlang_spectra(
                    fA_re_matrix,
                    fA_im_matrix,
                    batch=batch,
                    channels=channels,
                    nb_k=nb_k,
                    sx=cfg.sx,
                    sy=cfg.sy,
                )
            else:
                spec_re_tt, spec_im_tt = gather_kernel_spectra_ttnn(fA_re_tt, fA_im_tt, self._kernel_groups)
            self._end_profile_stage("spectra", stage_started_at)

            stage_started_at = self._begin_profile_stage("ifft")
            if self.front_half_mode == "dft_ttlang":
                spec_re_flat = ttnn.reshape(spec_re_matrix, (batch * nb_k, cfg.sx, cfg.sy))
                spec_im_flat = ttnn.reshape(spec_im_matrix, (batch * nb_k, cfg.sx, cfg.sy))
                if capture_stages:
                    spec_re_tt = self._reshape_fft_output(spec_re_flat, batch=batch, size=cfg.sx, last_dim=nb_k)
                    spec_im_tt = self._reshape_fft_output(spec_im_flat, batch=batch, size=cfg.sx, last_dim=nb_k)
            else:
                spec_re_flat = self._flatten_last_dim(spec_re_tt, batch=batch, sx=cfg.sx, sy=cfg.sy)
                spec_im_flat = self._flatten_last_dim(spec_im_tt, batch=batch, sx=cfg.sx, sy=cfg.sy)
            uk_flat, _ = self._dft_inverse_2d(spec_re_flat, spec_im_flat)
            if self.front_half_mode == "dft_ttlang":
                uk_matrix_tt = ttnn.reshape(uk_flat, (batch * nb_k * cfg.sx, cfg.sy))
            else:
                uk_tt = self._reshape_fft_output(uk_flat, batch=batch, size=cfg.sx, last_dim=nb_k)
            self._end_profile_stage("ifft", stage_started_at)

        stage_started_at = self._begin_profile_stage("growth")
        if self.front_half_mode in {"dft_ttlang", "local_ttlang"}:
            growth_tt = None
            if uk_matrix_tt is None:
                uk_matrix_tt = ttnn.reshape(ttnn.permute(uk_tt, (0, 3, 1, 2)), (batch * nb_k * cfg.sx, cfg.sy))
            u_tt = self._ttlang_growth_route(uk_matrix_tt, batch=batch, channels=channels, sx=cfg.sx, sy=cfg.sy)
            u_matrix_tt = u_tt
        else:
            growth_tt = ttnn_growth_bell(uk_tt, self._growth_m, self._growth_s, self._growth_h)
            u_tt = ttnn_route_channels(growth_tt, self._channel_routes)
        self._end_profile_stage("growth", stage_started_at)
        flow_tt = None
        flow_is_flat = False
        flow_cleanup = ()
        if self.reintegration_mode == "generic":
            stage_started_at = self._begin_profile_stage("flow")
            flow_tt, flow_cleanup = self._compute_flow_packed_with_ttnn(
                mass_tt,
                u_matrix_tt if u_matrix_tt is not None else u_tt,
                batch=batch,
                channels=channels,
                mass_is_flat=False,
                u_is_flat=u_matrix_tt is not None,
            )
            self._end_profile_stage("flow", stage_started_at)
            flow_y_tt = None
            flow_x_tt = None
        else:
            stage_started_at = self._begin_profile_stage("flow")
            if self._ttlang_flow is not None:
                mass_field_tt = ttnn_mass_field(
                    mass_tt,
                    cfg.chem_channel,
                    cfg.chem_include_in_mass,
                )
                mass_matrix_tt = _flatten_planes_matrix(mass_field_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=1)
                if u_matrix_tt is None:
                    u_matrix_for_flow = _flatten_planes_matrix(u_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels)
                    flow_cleanup = (mass_field_tt, mass_matrix_tt, u_matrix_for_flow)
                else:
                    u_matrix_for_flow = u_matrix_tt
                    flow_cleanup = (mass_field_tt, mass_matrix_tt)
                flow_y_tt, flow_x_tt = self._ttlang_flow(
                    mass_matrix_tt,
                    u_matrix_for_flow,
                    batch=batch,
                    channels=channels,
                    sx=cfg.sx,
                    sy=cfg.sy,
                    theta_a=cfg.theta_a,
                    n=cfg.n,
                    alpha_mode=cfg.implementation.alpha_mode,
                    flow_clip=cfg.implementation.flow_clip,
                    chem_channel=cfg.chem_channel,
                    chem_include_in_mass=cfg.chem_include_in_mass,
                    dd=cfg.dd,
                    sigma=cfg.sigma,
                )
                flow_is_flat = True
            else:
                u_for_flow = u_tt
                if u_matrix_tt is not None:
                    u_for_flow_rm = _restore_planes(u_matrix_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels)
                    u_for_flow = ttnn.to_layout(u_for_flow_rm, ttnn.TILE_LAYOUT)
                    flow_cleanup = (u_for_flow_rm, u_for_flow)
                flow_y_tt, flow_x_tt = ttnn_compute_flow(
                    u_for_flow,
                    mass_tt,
                    theta_a=cfg.theta_a,
                    n=cfg.n,
                    alpha_mode=cfg.implementation.alpha_mode,
                    flow_clip=cfg.implementation.flow_clip,
                    chem_channel=cfg.chem_channel,
                    chem_include_in_mass=cfg.chem_include_in_mass,
                    dd=cfg.dd,
                    sigma=cfg.sigma,
                    wall_potential=None,
                )
            self._end_profile_stage("flow", stage_started_at)

        captured = None
        if capture_stages:
            if self.reintegration_mode == "generic":
                flow_y_rm, flow_x_rm = flow_tt
                flow_host = np.stack(
                    [
                        self._plane_matrix_to_host(flow_y_rm, batch=batch, channels=channels),
                        self._plane_matrix_to_host(flow_x_rm, batch=batch, channels=channels),
                    ],
                    axis=3,
                )
            else:
                if flow_is_flat:
                    flow_host = np.stack(
                        [
                            self._plane_matrix_to_host(flow_y_tt, batch=batch, channels=channels),
                            self._plane_matrix_to_host(flow_x_tt, batch=batch, channels=channels),
                        ],
                        axis=3,
                    )
                else:
                    flow_host = np.stack([_ttnn_to_np(flow_y_tt), _ttnn_to_np(flow_x_tt)], axis=3)
            captured = {
                'fft_out': None if fA_re_tt is None else _ttnn_to_np(fA_re_tt) + 1j * _ttnn_to_np(fA_im_tt),
                'spectra': None if spec_re_tt is None else _ttnn_to_np(spec_re_tt) + 1j * _ttnn_to_np(spec_im_tt),
                'uk': (
                    self._plane_matrix_to_host(uk_matrix_tt, batch=batch, channels=nb_k)
                    if uk_matrix_tt is not None
                    else (_ttnn_to_np(uk_tt) if uk_tt is not None else None)
                ),
                'growth_out': None if growth_tt is None else _ttnn_to_np(growth_tt),
                'u': (
                    self._plane_matrix_to_host(u_matrix_tt, batch=batch, channels=channels)
                    if u_matrix_tt is not None
                    else _ttnn_to_np(u_tt)
                ),
                'flow': flow_host,
            }

        cleanup = (
            mass_perm,
            mass_flat,
            mass_im,
            fA_re_flat,
            fA_im_flat,
            fA_re_matrix,
            fA_im_matrix,
            fA_re_tt,
            fA_im_tt,
            spec_re_tt,
            spec_im_tt,
            spec_re_matrix,
            spec_im_matrix,
            spec_re_flat,
            spec_im_flat,
            uk_flat,
            uk_tt,
            uk_matrix_tt,
            growth_tt,
            u_tt,
            u_matrix_tt,
            flow_y_tt,
            flow_x_tt,
            *flow_cleanup,
        )
        return {
            "mass_tile": mass_tile,
            "flow_tt": flow_tt,
            "u_tt": u_tt,
            "flow_y_tt": flow_y_tt,
            "flow_x_tt": flow_x_tt,
            "flow_is_flat": flow_is_flat,
            "captured": captured,
            "cleanup": cleanup,
        }

    def _release_tensors(self, tensors, *, keep: tuple[object, ...] = ()) -> None:
        import ttnn

        for tensor in tensors:
            if tensor is None or any(tensor is kept for kept in keep):
                continue
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass

    def _mass_to_host(self, mass_tt, *, batch: int, channels: int) -> np.ndarray:
        import ttnn

        if self.reintegration_mode in {"generic", "generic_u"}:
            plane_tt = ttnn.reshape(
                ttnn.permute(mass_tt, (0, 3, 1, 2)),
                (batch * channels, self.config.sx, self.config.sy, 1),
            )
            try:
                if _is_mesh_device(self.device):
                    if _is_multi_device_mesh(self.device) and batch * channels >= _mesh_size(self.device):
                        host_planes = _ttnn_to_np(plane_tt, compose_dim=0).astype(np.float32, copy=False)
                    else:
                        host_planes = ttnn.to_torch(ttnn.get_device_tensors(plane_tt)[0]).float().numpy().astype(np.float32, copy=False)
                else:
                    host_planes = _ttnn_to_np(plane_tt).astype(np.float32, copy=False)
            finally:
                try:
                    ttnn.deallocate(plane_tt)
                except Exception:
                    pass
            return (
                host_planes.reshape(batch, channels, self.config.sx, self.config.sy, 1)
                .transpose(0, 2, 3, 1, 4)[..., 0]
                .astype(np.float32, copy=False)
            )

        compose_dim = 0 if _is_multi_device_mesh(self.device) and batch >= _mesh_size(self.device) else None
        return _ttnn_to_np(mass_tt, compose_dim=compose_dim).astype(np.float32, copy=False)

    def _compute_flow_packed_with_ttnn(
        self,
        mass_tt,
        u_tt,
        *,
        batch: int,
        channels: int,
        mass_is_flat: bool,
        u_is_flat: bool,
    ):
        import ttnn

        cfg = self.config
        cleanup = []
        if mass_is_flat:
            mass_rm = _restore_planes(mass_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels)
            mass_for_flow = ttnn.to_layout(mass_rm, ttnn.TILE_LAYOUT)
            cleanup.extend((mass_rm, mass_for_flow))
        else:
            mass_for_flow = mass_tt

        if u_is_flat:
            u_rm = _restore_planes(u_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels)
            u_for_flow = ttnn.to_layout(u_rm, ttnn.TILE_LAYOUT)
            cleanup.extend((u_rm, u_for_flow))
        else:
            u_for_flow = u_tt

        flow_y_tt, flow_x_tt = ttnn_compute_flow(
            u_for_flow,
            mass_for_flow,
            theta_a=cfg.theta_a,
            n=cfg.n,
            alpha_mode=cfg.implementation.alpha_mode,
            flow_clip=cfg.implementation.flow_clip,
            chem_channel=cfg.chem_channel,
            chem_include_in_mass=cfg.chem_include_in_mass,
            dd=cfg.dd,
            sigma=cfg.sigma,
            wall_potential=None,
        )
        flow_y_rm = ttnn.to_layout(_flatten_planes_matrix(flow_y_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels), ttnn.ROW_MAJOR_LAYOUT)
        flow_x_rm = ttnn.to_layout(_flatten_planes_matrix(flow_x_tt, batch=batch, sx=cfg.sx, sy=cfg.sy, channels=channels), ttnn.ROW_MAJOR_LAYOUT)
        cleanup.extend((flow_y_tt, flow_x_tt, flow_y_rm, flow_x_rm))
        return (flow_y_rm, flow_x_rm), tuple(cleanup)

    def _ttnn_dense_front_half_packed(self, mass_planes_tt, *, batch: int, channels: int, capture_stages: bool = False):
        import ttnn

        if self._mesh_dft_enabled and batch != 1:
            raise ValueError("LENIA_TT_MESH_DFT currently supports batch=1 mesh runs only.")

        cfg = self.config
        nb_k = self.kernels.fK.shape[3]
        mass_flat = None
        mass_im = None
        fA_re_flat = None
        fA_im_flat = None
        fA_re_matrix = None
        fA_im_matrix = None
        fA_re_tt = None
        fA_im_tt = None
        spec_re_matrix = None
        spec_im_matrix = None
        spec_re_tt = None
        spec_im_tt = None
        spec_re_flat = None
        spec_im_flat = None
        uk_flat = None
        uk_tt = None

        stage_started_at = self._begin_profile_stage("fft")
        mass_flat = ttnn.reshape(mass_planes_tt, (batch * channels, cfg.sx, cfg.sy))
        mass_im = ttnn.zeros_like(mass_flat)
        fA_re_flat, fA_im_flat = self._dft_forward_2d(mass_flat, mass_im)
        fA_re_matrix = ttnn.reshape(fA_re_flat, (batch * channels * cfg.sx, cfg.sy))
        fA_im_matrix = ttnn.reshape(fA_im_flat, (batch * channels * cfg.sx, cfg.sy))
        if capture_stages:
            fA_re_tt = self._reshape_fft_output(fA_re_flat, batch=batch, size=cfg.sx, last_dim=channels)
            fA_im_tt = self._reshape_fft_output(fA_im_flat, batch=batch, size=cfg.sx, last_dim=channels)
        self._end_profile_stage("fft", stage_started_at)

        stage_started_at = self._begin_profile_stage("spectra")
        spec_re_matrix, spec_im_matrix = self._ttlang_spectra(
            fA_re_matrix,
            fA_im_matrix,
            batch=batch,
            channels=channels,
            nb_k=nb_k,
            sx=cfg.sx,
            sy=cfg.sy,
        )
        self._end_profile_stage("spectra", stage_started_at)

        stage_started_at = self._begin_profile_stage("ifft")
        spec_re_flat = ttnn.reshape(spec_re_matrix, (batch * nb_k, cfg.sx, cfg.sy))
        spec_im_flat = ttnn.reshape(spec_im_matrix, (batch * nb_k, cfg.sx, cfg.sy))
        if capture_stages:
            spec_re_tt = self._reshape_fft_output(spec_re_flat, batch=batch, size=cfg.sx, last_dim=nb_k)
            spec_im_tt = self._reshape_fft_output(spec_im_flat, batch=batch, size=cfg.sx, last_dim=nb_k)
        uk_flat, _ = self._dft_inverse_2d(spec_re_flat, spec_im_flat)
        uk_tt = ttnn.reshape(uk_flat, (batch * nb_k * cfg.sx, cfg.sy))
        self._end_profile_stage("ifft", stage_started_at)

        stage_started_at = self._begin_profile_stage("growth")
        u_tt = self._ttlang_growth_route(uk_tt, batch=batch, channels=channels, sx=cfg.sx, sy=cfg.sy)
        u_matrix_tt = u_tt
        self._end_profile_stage("growth", stage_started_at)

        stage_started_at = self._begin_profile_stage("flow")
        mass_total_matrix_tt, mass_field_cleanup = self._packed_mass_field_matrix(
            mass_planes_tt,
            batch=batch,
            channels=channels,
        )
        flow_y_tt, flow_x_tt = self._ttlang_flow(
            mass_total_matrix_tt,
            u_matrix_tt,
            batch=batch,
            channels=channels,
            sx=cfg.sx,
            sy=cfg.sy,
            theta_a=cfg.theta_a,
            n=cfg.n,
            alpha_mode=cfg.implementation.alpha_mode,
            flow_clip=cfg.implementation.flow_clip,
            chem_channel=cfg.chem_channel,
            chem_include_in_mass=cfg.chem_include_in_mass,
            dd=cfg.dd,
            sigma=cfg.sigma,
        )
        flow_cleanup = mass_field_cleanup
        self._end_profile_stage("flow", stage_started_at)

        captured = None
        if capture_stages:
            flow_host = np.stack(
                [
                    self._plane_matrix_to_host(flow_y_tt, batch=batch, channels=channels),
                    self._plane_matrix_to_host(flow_x_tt, batch=batch, channels=channels),
                ],
                axis=3,
            )
            captured = {
                "fft_out": None if fA_re_tt is None else _ttnn_to_np(fA_re_tt) + 1j * _ttnn_to_np(fA_im_tt),
                "spectra": None if spec_re_tt is None else _ttnn_to_np(spec_re_tt) + 1j * _ttnn_to_np(spec_im_tt),
                "uk": self._plane_matrix_to_host(uk_tt, batch=batch, channels=nb_k),
                "growth_out": None,
                "u": self._plane_matrix_to_host(u_tt, batch=batch, channels=channels),
                "flow": flow_host,
            }
        return {
            "flow_y_tt": flow_y_tt,
            "flow_x_tt": flow_x_tt,
            "u_tt": u_tt,
            "captured": captured,
            "cleanup": (
                mass_flat,
                mass_im,
                fA_re_flat,
                fA_im_flat,
                fA_re_matrix,
                fA_im_matrix,
                fA_re_tt,
                fA_im_tt,
                spec_re_matrix,
                spec_im_matrix,
                spec_re_tt,
                spec_im_tt,
                spec_re_flat,
                spec_im_flat,
                uk_flat,
                uk_tt,
                u_tt,
                u_matrix_tt,
                flow_y_tt,
                flow_x_tt,
                *flow_cleanup,
            ),
        }

    def _step_ttnn_device_packed(self, mass_planes_tt, *, batch: int, channels: int, capture_stages: bool = False):
        front = self._ttnn_dense_front_half_packed(
            mass_planes_tt,
            batch=batch,
            channels=channels,
            capture_stages=capture_stages,
        )
        stage_started_at = self._begin_profile_stage("reintegration")
        next_mass_planes_tt = self._reintegrate_device(
            mass_planes_tt,
            None,
            front["flow_y_tt"],
            front["flow_x_tt"],
            front["u_tt"],
            batch=batch,
            channels=channels,
            mass_is_flat=True,
            flow_is_flat=True,
            return_flat=True,
        )
        self._end_profile_stage("reintegration", stage_started_at)
        self._release_tensors(front["cleanup"], keep=(next_mass_planes_tt,))
        return next_mass_planes_tt, front["captured"]

    def _step_ttnn_device(self, mass_tt, *, batch: int, channels: int, capture_stages: bool):
        front = self._ttnn_dense_front_half(
            mass_tt,
            batch=batch,
            channels=channels,
            capture_stages=capture_stages,
        )
        mass_tile = front["mass_tile"]
        stage_started_at = self._begin_profile_stage("reintegration")
        next_mass_tt = self._reintegrate_device(
            mass_tile,
            front["flow_tt"],
            front["flow_y_tt"],
            front["flow_x_tt"],
            front["u_tt"],
            batch=batch,
            channels=channels,
            flow_is_flat=front["flow_is_flat"],
        )
        self._end_profile_stage("reintegration", stage_started_at)

        self._release_tensors(front["cleanup"], keep=(mass_tt, mass_tile, next_mass_tt))
        if mass_tile is not mass_tt:
            self._release_tensors((mass_tile,), keep=(mass_tt, next_mass_tt))
        return next_mass_tt, front["captured"]

    def _step_ttnn(self, mass: np.ndarray, capture_stages: bool) -> StepOutputs:
        batch = mass.shape[0]
        channels = mass.shape[3]

        import ttnn

        if (self._use_packed_tt_state() and not capture_stages) or (
            self.front_half_mode in {"local", "local_ttlang"} and self.reintegration_mode == "generic"
        ):
            stage_started_at = self._begin_profile_stage("prepare")
            mass_tt = self._mass_to_device_packed(mass)
            self._end_profile_stage("prepare", stage_started_at)
            next_mass_tt, captured = self._step_ttnn_device_packed(
                mass_tt,
                batch=batch,
                channels=channels,
                capture_stages=capture_stages,
            )
            stage_started_at = self._begin_profile_stage("finalize")
            next_mass = self._mass_packed_to_host(next_mass_tt, batch=batch, channels=channels)
            self._end_profile_stage("finalize", stage_started_at)

            for tensor in (mass_tt, next_mass_tt):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass

            if capture_stages:
                return StepOutputs(
                    mass=next_mass,
                    fft_out=captured["fft_out"],
                    spectra=captured["spectra"],
                    uk=captured["uk"],
                    growth_out=captured["growth_out"],
                    u=captured["u"],
                    flow=captured["flow"],
                )
            return StepOutputs(mass=next_mass)

        stage_started_at = self._begin_profile_stage("prepare")
        mass_tt = self._mass_to_device(mass)
        self._end_profile_stage("prepare", stage_started_at)
        next_mass_tt, captured = self._step_ttnn_device(mass_tt, batch=batch, channels=channels, capture_stages=capture_stages)
        stage_started_at = self._begin_profile_stage("finalize")
        next_mass = self._mass_to_host(next_mass_tt, batch=batch, channels=channels)
        self._end_profile_stage("finalize", stage_started_at)

        for tensor in (mass_tt, next_mass_tt):
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass

        if capture_stages:
            return StepOutputs(
                mass=next_mass,
                fft_out=captured['fft_out'],
                spectra=captured['spectra'],
                uk=captured['uk'],
                growth_out=captured['growth_out'],
                u=captured['u'],
                flow=captured['flow'],
            )
        return StepOutputs(mass=next_mass)

    def run(self, mass: np.ndarray, steps: int) -> np.ndarray:
        if steps <= 0:
            return mass.copy()

        import ttnn

        batch = mass.shape[0]
        channels = mass.shape[3]
        if self._use_packed_tt_state() or (
            self.front_half_mode in {"local", "local_ttlang"} and self.reintegration_mode == "generic"
        ):
            stage_started_at = self._begin_profile_stage("prepare")
            state_tt = self._mass_to_device_packed(mass)
            self._end_profile_stage("prepare", stage_started_at)
            for _ in range(steps):
                next_state_tt, _ = self._step_ttnn_device_packed(state_tt, batch=batch, channels=channels)
                try:
                    ttnn.deallocate(state_tt)
                except Exception:
                    pass
                state_tt = next_state_tt
            stage_started_at = self._begin_profile_stage("finalize")
            state = self._mass_packed_to_host(state_tt, batch=batch, channels=channels)
            self._end_profile_stage("finalize", stage_started_at)
            try:
                ttnn.deallocate(state_tt)
            except Exception:
                pass
            return state

        stage_started_at = self._begin_profile_stage("prepare")
        state_tt = self._mass_to_device(mass)
        self._end_profile_stage("prepare", stage_started_at)
        for step_index in range(steps):
            next_state_tt, _ = self._step_ttnn_device(
                state_tt,
                batch=batch,
                channels=channels,
                capture_stages=False,
            )
            try:
                ttnn.deallocate(state_tt)
            except Exception:
                pass
            state_tt = next_state_tt
        stage_started_at = self._begin_profile_stage("finalize")
        state = self._mass_to_host(state_tt, batch=batch, channels=channels)
        self._end_profile_stage("finalize", stage_started_at)
        try:
            ttnn.deallocate(state_tt)
        except Exception:
            pass
        return state

    def run_sampled(
        self,
        mass: np.ndarray,
        steps: int,
        sample_steps: Iterable[int],
        on_sample: Callable[[int, np.ndarray], None],
    ) -> np.ndarray:
        """Run with device-resident state and host readback only at requested steps."""
        if steps <= 0:
            state = mass.copy()
            if 0 in set(sample_steps):
                on_sample(0, state)
            return state

        samples = {int(step) for step in sample_steps if 0 <= int(step) <= steps}
        if not samples:
            return self.run(mass, steps)
        if 0 in samples:
            on_sample(0, mass.copy())

        import ttnn

        batch = mass.shape[0]
        channels = mass.shape[3]
        last_sample: np.ndarray | None = mass.copy() if 0 in samples else None

        if self._use_packed_tt_state() or (
            self.front_half_mode in {"local", "local_ttlang"} and self.reintegration_mode == "generic"
        ):
            stage_started_at = self._begin_profile_stage("prepare")
            state_tt = self._mass_to_device_packed(mass)
            self._end_profile_stage("prepare", stage_started_at)
            for step in range(1, steps + 1):
                next_state_tt, _ = self._step_ttnn_device_packed(
                    state_tt,
                    batch=batch,
                    channels=channels,
                )
                try:
                    ttnn.deallocate(state_tt)
                except Exception:
                    pass
                state_tt = next_state_tt
                if step in samples:
                    stage_started_at = self._begin_profile_stage("sample")
                    last_sample = self._mass_packed_to_host(
                        state_tt,
                        batch=batch,
                        channels=channels,
                    )
                    self._end_profile_stage("sample", stage_started_at)
                    on_sample(step, last_sample)

            if steps in samples and last_sample is not None:
                state = last_sample
            else:
                stage_started_at = self._begin_profile_stage("finalize")
                state = self._mass_packed_to_host(state_tt, batch=batch, channels=channels)
                self._end_profile_stage("finalize", stage_started_at)
            try:
                ttnn.deallocate(state_tt)
            except Exception:
                pass
            return state

        stage_started_at = self._begin_profile_stage("prepare")
        state_tt = self._mass_to_device(mass)
        self._end_profile_stage("prepare", stage_started_at)
        for step_index in range(steps):
            step = step_index + 1
            next_state_tt, _ = self._step_ttnn_device(
                state_tt,
                batch=batch,
                channels=channels,
                capture_stages=False,
            )
            try:
                ttnn.deallocate(state_tt)
            except Exception:
                pass
            state_tt = next_state_tt
            if step in samples:
                stage_started_at = self._begin_profile_stage("sample")
                last_sample = self._mass_to_host(state_tt, batch=batch, channels=channels)
                self._end_profile_stage("sample", stage_started_at)
                on_sample(step, last_sample)

        if steps in samples and last_sample is not None:
            state = last_sample
        else:
            stage_started_at = self._begin_profile_stage("finalize")
            state = self._mass_to_host(state_tt, batch=batch, channels=channels)
            self._end_profile_stage("finalize", stage_started_at)
        try:
            ttnn.deallocate(state_tt)
        except Exception:
            pass
        return state
