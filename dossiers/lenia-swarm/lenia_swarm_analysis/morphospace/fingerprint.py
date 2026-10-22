"""Port of the LeniaCore terminal mass fingerprint (`fingerprintU8`) on a torus, bit for bit.

`mass_fingerprint` follows `morphospaceFinalSampleSummary` in MorphospaceDescriptors.swift: sum the
channels, roll the mass so its rounded centre of mass sits at the grid centre, box-resample to 32x32,
divide by the resampled total and quantize to uint8. Every sum runs sequentially in float32 in Swift's
order, because numpy's pairwise reductions round differently. Only the torus border is ported.
"""

from __future__ import annotations

import numpy as np

F32 = np.float32
RESOLUTION = 32


def _sequential_sum(values: np.ndarray) -> np.float32:
    return np.add.accumulate(values.ravel(), dtype=F32)[-1]


def _swift_round(value: np.float32) -> int:
    v = float(value)
    return int(np.copysign(np.floor(abs(v) + 0.5), v))


def mass_field(state: np.ndarray) -> np.ndarray:
    """Channel sum of a [rows, cols, channels] float32 state."""
    if state.dtype != F32 or state.ndim != 3:
        raise ValueError(
            f"expected a float32 [rows, cols, channels] state, got {state.dtype} {state.shape}"
        )
    mass = state[..., 0].copy()
    for c in range(1, state.shape[2]):
        mass = mass + state[..., c]
    return mass


def centered_mass(mass: np.ndarray) -> np.ndarray | None:
    """Mass rolled so its centre of mass sits at the grid centre, or None for an empty field."""
    rows, cols = mass.shape
    flat = mass.ravel()
    total = _sequential_sum(flat)
    if not total > F32(1e-8):
        return None
    xs = np.tile(np.arange(cols, dtype=F32) + F32(0.5), rows)
    ys = np.repeat(np.arange(rows, dtype=F32) + F32(0.5), cols)
    center_x = _sequential_sum(flat * xs) / total
    center_y = _sequential_sum(flat * ys) / total
    shift_x = _swift_round(F32(cols) * F32(0.5) - center_x)
    shift_y = _swift_round(F32(rows) * F32(0.5) - center_y)
    return np.roll(mass, (shift_y, shift_x), axis=(0, 1))


def box_resample(sample: np.ndarray, size: int = RESOLUTION) -> np.ndarray:
    """`morphospaceBoxResample`: block means over integer-divided edges, summed row by row."""
    rows, cols = sample.shape
    out = np.zeros((size, size), F32)
    for oy in range(size):
        y0 = oy * rows // size
        y1 = max(y0 + 1, (oy + 1) * rows // size)
        for ox in range(size):
            x0 = ox * cols // size
            x1 = max(x0 + 1, (ox + 1) * cols // size)
            block = sample[y0:y1, x0:x1]
            out[oy, ox] = _sequential_sum(block) / F32(block.size)
    return out


def quantized_fingerprint(sample: np.ndarray, size: int = RESOLUTION) -> np.ndarray:
    """`morphospaceQuantizedFingerprint` of an already centred float32 field."""
    reduced = box_resample(sample.astype(F32, copy=False), size)
    total = _sequential_sum(reduced)
    if not total > F32(1e-8):
        return np.zeros((size, size), np.uint8)
    scaled = np.clip(reduced / total, F32(0), F32(1)) * F32(255)
    return np.floor(scaled.astype(np.float64) + 0.5).astype(np.uint8)


def mass_fingerprint(state: np.ndarray) -> np.ndarray:
    """The 32x32 uint8 `fingerprintU8` LeniaCore writes for a [rows, cols, channels] torus state."""
    centered = centered_mass(mass_field(state))
    if centered is None:
        return np.zeros((RESOLUTION, RESOLUTION), np.uint8)
    return quantized_fingerprint(centered)
