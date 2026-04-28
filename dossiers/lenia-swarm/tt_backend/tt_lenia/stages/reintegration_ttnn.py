"""Stage 6: TTNN reintegration — composed from existing TTNN ops.

Restructures the 5D flow tensor F[batch, sx, sy, 2, channels] into
separate F_y and F_x 4D tensors to fit TTNN's tile layout.
"""
from __future__ import annotations

import numpy as np


def reintegrate_ttnn(
    X, F_y, F_x, *, pos_y, pos_x, dt: float, dd: int, sigma: float,
    use_torus: bool, sx: int, sy: int, device,
):
    """Mass-conserving advection on TTNN device.

    All inputs are TTNN device tensors with shape [1, sx, sy, channels].
    F_y, F_x: flow field y and x components
    pos_y, pos_x: position grid y and x components (center + 0.5)
    """
    import ttnn

    ma = float(dd) - sigma
    clip_max = min(1.0, 2.0 * sigma)
    inv_area = 1.0 / (4.0 * sigma * sigma)
    sigma_plus_half = 0.5 + sigma

    out = ttnn.zeros_like(X)
    sigma_half_tensor = ttnn.full_like(X, sigma_plus_half)

    for dx in range(-dd, dd + 1):
        for dy in range(-dd, dd + 1):
            Xr = _roll_2d(X, dx, dy)
            Fr_y = _roll_2d(F_y, dx, dy)
            Fr_x = _roll_2d(F_x, dx, dy)
            pgr_y = _shifted_pos(pos_y, dx, sy)
            pgr_x = _shifted_pos(pos_x, dy, sx)

            delta_y = ttnn.clip(ttnn.multiply(Fr_y, dt), -ma, ma)
            delta_x = ttnn.clip(ttnn.multiply(Fr_x, dt), -ma, ma)
            mur_y = ttnn.add(pgr_y, delta_y)
            mur_x = ttnn.add(pgr_x, delta_x)
            _deallocate(delta_y, delta_x, pgr_y, pgr_x)

            if not use_torus:
                mur_y_clipped = ttnn.clip(mur_y, sigma, sy - sigma)
                mur_x_clipped = ttnn.clip(mur_x, sigma, sx - sigma)
                _deallocate(mur_y, mur_x)
                mur_y = mur_y_clipped
                mur_x = mur_x_clipped

            dy_min = ttnn.abs(ttnn.subtract(pos_y, mur_y))
            dx_min = ttnn.abs(ttnn.subtract(pos_x, mur_x))

            if use_torus:
                for iy_shift in [-sy, sy]:
                    dy_c = ttnn.abs(ttnn.subtract(pos_y, ttnn.add(mur_y, float(iy_shift))))
                    dy_next = ttnn.minimum(dy_min, dy_c)
                    _deallocate(dy_min, dy_c)
                    dy_min = dy_next
                for ix_shift in [-sx, sx]:
                    dx_c = ttnn.abs(ttnn.subtract(pos_x, ttnn.add(mur_x, float(ix_shift))))
                    dx_next = ttnn.minimum(dx_min, dx_c)
                    _deallocate(dx_min, dx_c)
                    dx_min = dx_next

            sz_y = ttnn.clip(ttnn.subtract(sigma_half_tensor, dy_min), 0.0, clip_max)
            sz_x = ttnn.clip(ttnn.subtract(sigma_half_tensor, dx_min), 0.0, clip_max)

            area = ttnn.multiply(sz_y, sz_x)
            weighted = ttnn.multiply(Xr, area)
            next_out = ttnn.add(out, weighted)
            _deallocate(out, Xr, Fr_y, Fr_x, mur_y, mur_x, dy_min, dx_min, sz_y, sz_x, area, weighted)
            out = next_out

    result = ttnn.multiply(out, inv_area)
    _deallocate(out, sigma_half_tensor)
    return result


def _roll_2d(t, dx: int, dy: int):
    import ttnn
    if dx != 0:
        t = ttnn.roll(t, shifts=dx, dim=1)
    if dy != 0:
        t = ttnn.roll(t, shifts=dy, dim=2)
    return t


def _shifted_pos(base, shift: int, period: int):
    import ttnn

    shifted = ttnn.add(base, float(period - shift - 0.5))
    wrapped = ttnn.remainder(shifted, float(period))
    result = ttnn.add(wrapped, 0.5)
    _deallocate(shifted, wrapped)
    return result


def _deallocate(*tensors) -> None:
    import ttnn

    for tensor in tensors:
        if tensor is None:
            continue
        try:
            ttnn.deallocate(tensor)
        except Exception:
            pass


def prepare_reintegration_inputs(
    mass: np.ndarray, F: np.ndarray, pos_grid: np.ndarray, device,
):
    """Convert NumPy inputs to TTNN device tensors with split y/x layout.

    mass: [batch, sx, sy, channels]
    F: [batch, sx, sy, 2, channels]
    pos_grid: [1, sx, sy, 2, 1]
    Returns dict of TTNN tensors ready for reintegrate_ttnn.
    """
    from .fft import _np_to_ttnn

    F_y = F[:, :, :, 0, :]
    F_x = F[:, :, :, 1, :]
    pos_y = np.broadcast_to(pos_grid[:, :, :, 0, :], mass.shape).copy()
    pos_x = np.broadcast_to(pos_grid[:, :, :, 1, :], mass.shape).copy()

    return {
        "X": _np_to_ttnn(mass, device),
        "F_y": _np_to_ttnn(F_y.astype(np.float32), device),
        "F_x": _np_to_ttnn(F_x.astype(np.float32), device),
        "pos_y": _np_to_ttnn(pos_y.astype(np.float32), device),
        "pos_x": _np_to_ttnn(pos_x.astype(np.float32), device),
    }
