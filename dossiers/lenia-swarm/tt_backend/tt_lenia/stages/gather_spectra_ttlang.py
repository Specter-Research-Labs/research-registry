from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ttlang_runtime import run_ttlang_kernel
from .gather_spectra import compile_kernel_source_groups
from .reintegration_generic import _np_to_ttnn_layout


@dataclass
class _SpectraGroupContext:
    source_channel: int
    start: int
    stop: int
    kernel: object
    fK_re: object
    fK_im: object


class TTLangGatherKernelSpectra:
    """Fused TT-Lang complex gather/multiply over packed FFT plane matrices."""

    def __init__(self, device, *, fK: np.ndarray, c0_idxs: np.ndarray, dtype=None):
        import ttnn
        from ttlang.gather_spectra import (
            kernel_spectra_plane_matrices,
            make_gather_kernel_spectra_group_into_full,
        )

        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        self._placeholders: dict[tuple[int, int, int, int], tuple[object, object]] = {}
        self._groups: list[_SpectraGroupContext] = []
        total_kernels = int(fK.shape[3])
        for group in compile_kernel_source_groups(c0_idxs):
            fK_re, fK_im = kernel_spectra_plane_matrices(fK, start=group.start, stop=group.stop)
            self._groups.append(
                _SpectraGroupContext(
                    source_channel=group.source_channel,
                    start=group.start,
                    stop=group.stop,
                    kernel=make_gather_kernel_spectra_group_into_full(
                        group.source_channel,
                        kernel_start=group.start,
                        total_kernels=total_kernels,
                    ),
                    fK_re=_np_to_ttnn_layout(
                        fK_re,
                        device,
                        dtype=self.dtype,
                        layout=ttnn.TILE_LAYOUT,
                    ),
                    fK_im=_np_to_ttnn_layout(
                        fK_im,
                        device,
                        dtype=self.dtype,
                        layout=ttnn.TILE_LAYOUT,
                    ),
                )
            )

    def close(self) -> None:
        import ttnn

        for group in self._groups:
            for tensor in (group.fK_re, group.fK_im):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._groups.clear()
        for out_re, out_im in self._placeholders.values():
            for tensor in (out_re, out_im):
                try:
                    ttnn.deallocate(tensor)
                except Exception:
                    pass
        self._placeholders.clear()

    def __call__(self, fA_re_matrix, fA_im_matrix, *, batch: int, channels: int, nb_k: int, sx: int, sy: int):
        import ttnn

        if not self._groups:
            raise RuntimeError("TTLangGatherKernelSpectra has no kernel groups.")
        total_kernels = sum(group.stop - group.start for group in self._groups)
        if total_kernels != nb_k:
            raise ValueError(f"Expected {total_kernels} kernels from groups, got nb_k={nb_k}.")

        out_re_placeholder, out_im_placeholder = self._context(batch=batch, nb_k=nb_k, sx=sx, sy=sy)
        out_re = ttnn.allocate_tensor_on_device(out_re_placeholder.spec, self.device)
        out_im = ttnn.allocate_tensor_on_device(out_im_placeholder.spec, self.device)
        for group in self._groups:
            run_ttlang_kernel(group.kernel, fA_re_matrix, fA_im_matrix, group.fK_re, group.fK_im, out_re, out_im)
        return out_re, out_im

    def _context(
        self,
        *,
        batch: int,
        nb_k: int,
        sx: int,
        sy: int,
    ) -> tuple[object, object]:
        key = (batch, nb_k, sx, sy)
        cached = self._placeholders.get(key)
        if cached is not None:
            return cached

        import ttnn

        out_zeros = np.zeros((batch * nb_k * sx, sy), dtype=np.float32)
        out_re = _np_to_ttnn_layout(
            out_zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        out_im = _np_to_ttnn_layout(
            out_zeros,
            self.device,
            dtype=self.dtype,
            layout=ttnn.TILE_LAYOUT,
        )
        self._placeholders[key] = (out_re, out_im)
        return out_re, out_im
