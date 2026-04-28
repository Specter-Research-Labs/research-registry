from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ttlang_runtime import run_ttlang_kernel
from .reintegration_generic import _np_to_ttnn_layout


@dataclass
class _GrowthRouteContext:
    batch: int
    channels: int
    sx: int
    sy: int
    kernels: tuple[object, ...]
    out_placeholder: object


_SPECIALIZED_ROUTE_CHUNK_SIZE = 5


class TTLangGrowthRoute:
    """TT-Lang fused Lenia growth+channel route over packed plane matrices."""

    def __init__(self, device, *, m: np.ndarray, s: np.ndarray, h: np.ndarray, c1_mask: np.ndarray, dtype=None):
        import ttnn
        from ttlang.growth_route import growth_route_param_matrix

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._contexts: dict[tuple[int, int, int, int], _GrowthRouteContext] = {}
        self._nb_k = int(np.asarray(m).shape[0])
        c1_mask = np.asarray(c1_mask, dtype=np.float32)
        route_weights_are_binary = bool(np.all(np.isclose(c1_mask, 0.0) | np.isclose(c1_mask, 1.0)))
        self._channel_routes = tuple(
            tuple(int(kernel_index) for kernel_index in np.flatnonzero(c1_mask[channel]))
            for channel in range(int(c1_mask.shape[0]))
        )
        self._use_route_specialization = route_weights_are_binary and any(
            len(route) != self._nb_k for route in self._channel_routes
        )
        params = growth_route_param_matrix(m=m, s=s, h=h, c1_mask=c1_mask)
        self.params = _np_to_ttnn_layout(
            params,
            device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )

    def close(self) -> None:
        import ttnn

        try:
            ttnn.deallocate(self.params)
        except Exception:
            pass
        for context in self._contexts.values():
            try:
                ttnn.deallocate(context.out_placeholder)
            except Exception:
                pass
        self._contexts.clear()

    def __call__(self, uk_matrix_tt, *, batch: int, channels: int, sx: int, sy: int):
        import ttnn

        context = self._context(batch=batch, channels=channels, sx=sx, sy=sy)
        out_matrix_tt = ttnn.allocate_tensor_on_device(context.out_placeholder.spec, self.device)
        for kernel in context.kernels:
            run_ttlang_kernel(kernel, uk_matrix_tt, self.params, out_matrix_tt)
        return out_matrix_tt

    def _context(self, *, batch: int, channels: int, sx: int, sy: int) -> _GrowthRouteContext:
        from ttlang.growth_route import make_growth_route, make_growth_route_channel_unrolled

        if sx != sy:
            raise ValueError(f"TT-Lang growth route currently supports square grids, got {sx}x{sy}.")
        if channels != len(self._channel_routes):
            raise ValueError(f"Expected {len(self._channel_routes)} routed channels, got {channels}.")
        key = (batch, channels, sx, sy)
        cached = self._contexts.get(key)
        if cached is not None:
            return cached

        import ttnn

        out_zeros = np.zeros((batch * channels * sx, sy), dtype=np.float32)
        out_placeholder = _np_to_ttnn_layout(
            out_zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        if self._use_route_specialization:
            kernels = []
            for channel in range(channels):
                route = self._channel_routes[channel]
                chunks = tuple(
                    route[start : start + _SPECIALIZED_ROUTE_CHUNK_SIZE]
                    for start in range(0, len(route), _SPECIALIZED_ROUTE_CHUNK_SIZE)
                ) or ((),)
                for chunk_index, chunk in enumerate(chunks):
                    kernels.append(
                        make_growth_route_channel_unrolled(
                            batch=batch,
                            channels=channels,
                            nb_k=self._nb_k,
                            sx=sx,
                            sy=sy,
                            channel_index=channel,
                            route=chunk,
                            accumulate=chunk_index > 0,
                        )
                    )
            context_kernels = tuple(kernels)
        else:
            context_kernels = (make_growth_route(batch=batch, channels=channels, nb_k=self._nb_k),)

        context = _GrowthRouteContext(
            batch=batch,
            channels=channels,
            sx=sx,
            sy=sy,
            kernels=context_kernels,
            out_placeholder=out_placeholder,
        )
        self._contexts[key] = context
        return context
