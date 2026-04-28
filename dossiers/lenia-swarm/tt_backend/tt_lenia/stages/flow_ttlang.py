from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ttlang_runtime import run_ttlang_kernel
from .reintegration_generic import _np_to_ttnn_layout


@dataclass
class _FlowSobelContext:
    batch: int
    channels: int
    sx: int
    sy: int
    flow_clip: str
    kernel: object
    out_y_placeholder: object
    out_x_placeholder: object


@dataclass
class _FlowGradientContext:
    batch: int
    channels: int
    sx: int
    sy: int
    kernel: object
    out_y_placeholder: object
    out_x_placeholder: object


@dataclass
class _FlowCombineContext:
    batch: int
    channels: int
    sx: int
    sy: int
    kernel: object
    out_y_placeholder: object
    out_x_placeholder: object


def _flow_kernel_grid(*, batch: int, channels: int, sx: int, sy: int) -> tuple[int, int]:
    """Map packed matrix tiles to quietbox-safe Wormhole cores."""
    del batch
    sx_tiles = int(sx) // 32
    sy_tiles = int(sy) // 32
    plane_rows = max(1, int(channels) * sx_tiles)
    return (min(8, sy_tiles), min(7, plane_rows))


class TTLangPackedSobelGradient:
    """TT-Lang Sobel gradient over packed Lenia plane matrices."""

    def __init__(self, device, *, dtype=None):
        import ttnn
        from ttlang.flow_gradient import flow_gradient_param_matrix, flow_gradient_selector_matrices

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._contexts: dict[tuple[int, int, int, int], _FlowGradientContext] = {}
        row_selectors, col_selectors = flow_gradient_selector_matrices()
        self.row_selectors = _np_to_ttnn_layout(
            row_selectors,
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self.col_selectors = _np_to_ttnn_layout(
            col_selectors,
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self.params = _np_to_ttnn_layout(
            flow_gradient_param_matrix(),
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )

    def close(self) -> None:
        import ttnn

        for tensor in (self.row_selectors, self.col_selectors, self.params):
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass
        for context in self._contexts.values():
            for tensor in (context.out_y_placeholder, context.out_x_placeholder):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._contexts.clear()

    def __call__(self, matrix_tt, *, batch: int, channels: int, sx: int, sy: int):
        if int(batch) != 1:
            raise ValueError("TT-Lang packed Sobel gradient currently supports batch=1 only.")
        if sx != sy:
            raise ValueError(f"TT-Lang packed Sobel gradient expects a square grid, got {sx}x{sy}.")
        if sx % 32 != 0 or sy % 32 != 0:
            raise ValueError(f"TT-Lang packed Sobel gradient expects tile-aligned dimensions, got {sx}x{sy}.")

        import ttnn

        context = self._context(batch=batch, channels=channels, sx=sx, sy=sy)
        out_y = ttnn.allocate_tensor_on_device(context.out_y_placeholder.spec, self.device)
        out_x = ttnn.allocate_tensor_on_device(context.out_x_placeholder.spec, self.device)
        src = ttnn.typecast(ttnn.to_layout(matrix_tt, ttnn.TILE_LAYOUT), self.dtype)
        try:
            run_ttlang_kernel(context.kernel, src, self.row_selectors, self.col_selectors, self.params, out_y, out_x)
        finally:
            try:
                ttnn.deallocate(src)
            except Exception:
                pass
        return out_y, out_x

    def _context(self, *, batch: int, channels: int, sx: int, sy: int) -> _FlowGradientContext:
        from ttlang.flow_gradient import make_flow_gradient

        key = (int(batch), int(channels), int(sx), int(sy))
        cached = self._contexts.get(key)
        if cached is not None:
            return cached

        import ttnn

        zeros = np.zeros((batch * channels * sx, sy), dtype=np.float32)
        out_y_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        out_x_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        context = _FlowGradientContext(
            batch=batch,
            channels=channels,
            sx=sx,
            sy=sy,
            kernel=make_flow_gradient(grid=_flow_kernel_grid(batch=batch, channels=channels, sx=sx, sy=sy)),
            out_y_placeholder=out_y_placeholder,
            out_x_placeholder=out_x_placeholder,
        )
        self._contexts[key] = context
        return context


class TTLangPackedFlowCombine:
    """TT-Lang alpha/combine flow stage over packed gradient matrices."""

    def __init__(self, device, *, dtype=None):
        import ttnn

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._contexts: dict[tuple[int, int, int, int], _FlowCombineContext] = {}
        self._params: dict[float, object] = {}

    def close(self) -> None:
        import ttnn

        for tensor in self._params.values():
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass
        for context in self._contexts.values():
            for tensor in (context.out_y_placeholder, context.out_x_placeholder):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._contexts.clear()
        self._params.clear()

    def __call__(
        self,
        mass_total_matrix_tt,
        gy_u_tt,
        gx_u_tt,
        gy_mass_tt,
        gx_mass_tt,
        *,
        batch: int,
        channels: int,
        sx: int,
        sy: int,
        theta_a: float,
    ):
        if int(batch) != 1:
            raise ValueError("TT-Lang packed flow combine currently supports batch=1 only.")
        if sx != sy:
            raise ValueError(f"TT-Lang packed flow combine expects a square grid, got {sx}x{sy}.")
        if sx % 32 != 0 or sy % 32 != 0:
            raise ValueError(f"TT-Lang packed flow combine expects tile-aligned dimensions, got {sx}x{sy}.")

        import ttnn

        context = self._context(batch=batch, channels=channels, sx=sx, sy=sy)
        out_y = ttnn.allocate_tensor_on_device(context.out_y_placeholder.spec, self.device)
        out_x = ttnn.allocate_tensor_on_device(context.out_x_placeholder.spec, self.device)
        inputs = tuple(ttnn.typecast(ttnn.to_layout(tensor, ttnn.TILE_LAYOUT), self.dtype) for tensor in (
            mass_total_matrix_tt,
            gy_u_tt,
            gx_u_tt,
            gy_mass_tt,
            gx_mass_tt,
        ))
        try:
            run_ttlang_kernel(
                context.kernel,
                *inputs,
                self._param_tensor(theta_a=theta_a),
                out_y,
                out_x,
            )
        finally:
            for tensor in inputs:
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        return out_y, out_x

    def _context(self, *, batch: int, channels: int, sx: int, sy: int) -> _FlowCombineContext:
        from ttlang.flow_combine import make_flow_combine

        key = (int(batch), int(channels), int(sx), int(sy))
        cached = self._contexts.get(key)
        if cached is not None:
            return cached

        import ttnn

        zeros = np.zeros((batch * channels * sx, sy), dtype=np.float32)
        out_y_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        out_x_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        context = _FlowCombineContext(
            batch=batch,
            channels=channels,
            sx=sx,
            sy=sy,
            kernel=make_flow_combine(grid=_flow_kernel_grid(batch=batch, channels=channels, sx=sx, sy=sy)),
            out_y_placeholder=out_y_placeholder,
            out_x_placeholder=out_x_placeholder,
        )
        self._contexts[key] = context
        return context

    def _param_tensor(self, *, theta_a: float):
        from ttlang.flow_combine import flow_combine_param_matrix

        key = float(theta_a)
        cached = self._params.get(key)
        if cached is not None:
            return cached

        import ttnn

        tensor = _np_to_ttnn_layout(
            flow_combine_param_matrix(theta_a=theta_a),
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self._params[key] = tensor
        return tensor


class TTLangSplitSobelFlow:
    """TT-Lang Flow Lenia Sobel flow split into compiler-friendly kernels."""

    def __init__(self, device, *, dtype=None):
        self.gradient = TTLangPackedSobelGradient(device, dtype=dtype)
        self.combine = TTLangPackedFlowCombine(device, dtype=dtype)

    def close(self) -> None:
        self.gradient.close()
        self.combine.close()

    def __call__(
        self,
        mass_total_matrix_tt,
        u_matrix_tt,
        *,
        batch: int,
        channels: int,
        sx: int,
        sy: int,
        theta_a: float,
        n: int,
        alpha_mode: str,
        flow_clip: str,
        chem_channel: int | None,
        chem_include_in_mass: bool,
        dd: int,
        sigma: float,
    ):
        del chem_channel, chem_include_in_mass, dd, sigma
        if alpha_mode != "mass":
            raise ValueError("TT-Lang split Sobel flow currently supports alpha_mode='mass' only.")
        if int(n) != 2:
            raise ValueError("TT-Lang split Sobel flow currently supports flow exponent n=2 only.")
        if flow_clip != "none":
            raise ValueError(f"Unsupported TT-Lang split Sobel flow_clip: {flow_clip}.")

        import ttnn

        gy_u = gx_u = gy_mass = gx_mass = None
        try:
            gy_u, gx_u = self.gradient(u_matrix_tt, batch=batch, channels=channels, sx=sx, sy=sy)
            gy_mass, gx_mass = self.gradient(mass_total_matrix_tt, batch=batch, channels=1, sx=sx, sy=sy)
            return self.combine(
                mass_total_matrix_tt,
                gy_u,
                gx_u,
                gy_mass,
                gx_mass,
                batch=batch,
                channels=channels,
                sx=sx,
                sy=sy,
                theta_a=theta_a,
            )
        finally:
            for tensor in (gy_u, gx_u, gy_mass, gx_mass):
                if tensor is None:
                    continue
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass


class TTLangPackedSobelFlow:
    """TT-Lang Sobel/alpha flow over packed Lenia plane matrices.

    The current kernel is the hardware-validated 1-channel stage. It takes a
    channel-summed mass matrix plus the packed U matrix; multi-channel support
    will split shared mass Sobel from per-channel U Sobel to fit NCRISC code.
    """

    def __init__(self, device, *, dtype=None):
        import ttnn
        from ttlang.flow_sobel import flow_sobel_selector_matrices

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._contexts: dict[tuple[int, int, int, int, str], _FlowSobelContext] = {}
        row_selectors, col_selectors = flow_sobel_selector_matrices()
        self.row_selectors = _np_to_ttnn_layout(
            row_selectors,
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self.col_selectors = _np_to_ttnn_layout(
            col_selectors,
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self._params: dict[tuple[float, int, float], object] = {}

    @staticmethod
    def _kernel_grid(*, batch: int, channels: int, sx: int, sy: int) -> tuple[int, int]:
        return _flow_kernel_grid(batch=batch, channels=channels, sx=sx, sy=sy)

    def close(self) -> None:
        import ttnn

        for tensor in (self.row_selectors, self.col_selectors):
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass
        for tensor in self._params.values():
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass
        for context in self._contexts.values():
            for tensor in (context.out_y_placeholder, context.out_x_placeholder):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._contexts.clear()
        self._params.clear()

    def __call__(
        self,
        mass_total_matrix_tt,
        u_matrix_tt,
        *,
        batch: int,
        channels: int,
        sx: int,
        sy: int,
        theta_a: float,
        n: int,
        alpha_mode: str,
        flow_clip: str,
        chem_channel: int | None,
        chem_include_in_mass: bool,
        dd: int,
        sigma: float,
    ):
        if alpha_mode != "mass":
            raise ValueError("TT-Lang packed Sobel flow currently supports alpha_mode='mass' only.")
        if int(n) != 2:
            raise ValueError("TT-Lang packed Sobel flow currently supports flow exponent n=2 only.")
        if flow_clip != "none":
            raise ValueError(f"Unsupported TT-Lang packed Sobel flow_clip: {flow_clip}.")
        if int(batch) != 1:
            raise ValueError("TT-Lang packed Sobel flow currently supports batch=1 only.")
        if sx != sy:
            raise ValueError(f"TT-Lang packed Sobel flow expects a square grid, got {sx}x{sy}.")
        if sx % 32 != 0 or sy % 32 != 0:
            raise ValueError(f"TT-Lang packed Sobel flow expects tile-aligned dimensions, got {sx}x{sy}.")

        import ttnn

        context = self._context(batch=batch, channels=channels, sx=sx, sy=sy, flow_clip=flow_clip)
        out_y = ttnn.allocate_tensor_on_device(context.out_y_placeholder.spec, self.device)
        out_x = ttnn.allocate_tensor_on_device(context.out_x_placeholder.spec, self.device)
        mass_for_flow = ttnn.typecast(ttnn.to_layout(mass_total_matrix_tt, ttnn.TILE_LAYOUT), self.dtype)
        u_for_flow = ttnn.typecast(ttnn.to_layout(u_matrix_tt, ttnn.TILE_LAYOUT), self.dtype)
        try:
            run_ttlang_kernel(
                context.kernel,
                mass_for_flow,
                u_for_flow,
                self.row_selectors,
                self.col_selectors,
                self._param_tensor(theta_a=theta_a, dd=dd, sigma=sigma),
                out_y,
                out_x,
            )
        finally:
            for tensor in (mass_for_flow, u_for_flow):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        return out_y, out_x

    def _context(self, *, batch: int, channels: int, sx: int, sy: int, flow_clip: str) -> _FlowSobelContext:
        from ttlang.flow_sobel import make_flow_sobel

        key = (int(batch), int(channels), int(sx), int(sy), flow_clip)
        cached = self._contexts.get(key)
        if cached is not None:
            return cached

        import ttnn

        zeros = np.zeros((batch * channels * sx, sy), dtype=np.float32)
        out_y_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        out_x_placeholder = _np_to_ttnn_layout(
            zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        context = _FlowSobelContext(
            batch=batch,
            channels=channels,
            sx=sx,
            sy=sy,
            flow_clip=flow_clip,
            kernel=make_flow_sobel(
                clip=flow_clip == "always",
                grid=self._kernel_grid(batch=batch, channels=channels, sx=sx, sy=sy),
            ),
            out_y_placeholder=out_y_placeholder,
            out_x_placeholder=out_x_placeholder,
        )
        self._contexts[key] = context
        return context

    def _param_tensor(self, *, theta_a: float, dd: int, sigma: float):
        from ttlang.flow_sobel import flow_sobel_param_matrix

        key = (float(theta_a), int(dd), float(sigma))
        cached = self._params.get(key)
        if cached is not None:
            return cached

        import ttnn

        params = flow_sobel_param_matrix(theta_a=theta_a, dd=dd, sigma=sigma)
        tensor = _np_to_ttnn_layout(
            params,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self._params[key] = tensor
        return tensor
