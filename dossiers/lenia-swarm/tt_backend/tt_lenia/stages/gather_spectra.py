"""Stage 2: Gather kernel spectra — element-wise complex multiply in frequency domain."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class KernelSourceGroup:
    source_channel: int
    start: int
    stop: int


def compile_kernel_source_groups(c0_idxs: np.ndarray) -> tuple[KernelSourceGroup, ...]:
    if c0_idxs.ndim != 1:
        raise ValueError(f"Expected 1D c0_idxs, got shape {c0_idxs.shape}")
    if c0_idxs.size == 0:
        return ()
    groups: list[KernelSourceGroup] = []
    start = 0
    current = int(c0_idxs[0])
    for idx in range(1, int(c0_idxs.size)):
        source = int(c0_idxs[idx])
        if source == current:
            continue
        groups.append(KernelSourceGroup(source_channel=current, start=start, stop=idx))
        start = idx
        current = source
    groups.append(KernelSourceGroup(source_channel=current, start=start, stop=int(c0_idxs.size)))
    return tuple(groups)


def gather_kernel_spectra_numpy(
    fA_re: np.ndarray,
    fA_im: np.ndarray,
    fK_re: np.ndarray,
    fK_im: np.ndarray,
    c0_idxs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Complex multiply of selected channel spectra by kernel spectra.

    fA: [batch, sx, sy, channels] (re + im)
    fK: [1, sx, sy, nb_k] (re + im)
    c0_idxs: [nb_k] source channel indices
    Returns: [batch, sx, sy, nb_k] (re + im)

    Note: TTNN lacks general gather-by-index, so this stays on host.
    The channel select (c0_idxs) is a non-contiguous index operation
    that doesn't map cleanly to TTNN's tile-based memory layout.
    """
    fAK_re = fA_re[:, :, :, c0_idxs]
    fAK_im = fA_im[:, :, :, c0_idxs]
    out_re = fAK_re * fK_re - fAK_im * fK_im
    out_im = fAK_re * fK_im + fAK_im * fK_re
    return out_re, out_im


@dataclass(frozen=True)
class TTNNKernelSourceGroup:
    source_channel: int
    fK_re: object
    fK_im: object


def build_ttnn_kernel_groups(fK: np.ndarray, c0_idxs: np.ndarray, device) -> tuple[TTNNKernelSourceGroup, ...]:
    from .fft import _np_to_ttnn

    groups = compile_kernel_source_groups(c0_idxs)
    fK_re = fK.real.astype(np.float32, copy=False)
    fK_im = fK.imag.astype(np.float32, copy=False)
    result: list[TTNNKernelSourceGroup] = []
    for group in groups:
        result.append(
            TTNNKernelSourceGroup(
                source_channel=group.source_channel,
                fK_re=_np_to_ttnn(fK_re[:, :, :, group.start : group.stop], device),
                fK_im=_np_to_ttnn(fK_im[:, :, :, group.start : group.stop], device),
            )
        )
    return tuple(result)


def gather_kernel_spectra_ttnn(fA_re, fA_im, kernel_groups: tuple[TTNNKernelSourceGroup, ...]):
    import ttnn

    batch, sx, sy, _ = (int(dim) for dim in fA_re.shape)
    out_re = []
    out_im = []
    for group in kernel_groups:
        src_re = ttnn.slice(fA_re, (0, 0, 0, group.source_channel), (batch, sx, sy, group.source_channel + 1))
        src_im = ttnn.slice(fA_im, (0, 0, 0, group.source_channel), (batch, sx, sy, group.source_channel + 1))
        re_re = ttnn.multiply(src_re, group.fK_re)
        im_im = ttnn.multiply(src_im, group.fK_im)
        re_im = ttnn.multiply(src_re, group.fK_im)
        im_re = ttnn.multiply(src_im, group.fK_re)
        out_re.append(ttnn.subtract(re_re, im_im))
        out_im.append(ttnn.add(re_im, im_re))
        for tensor in (src_re, src_im, re_re, im_im, re_im, im_re):
            ttnn.deallocate(tensor)
    if len(out_re) == 1:
        return out_re[0], out_im[0]
    return ttnn.concat(out_re, dim=3), ttnn.concat(out_im, dim=3)
