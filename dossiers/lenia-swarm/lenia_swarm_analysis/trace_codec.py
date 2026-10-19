"""Decoders for the binary payloads LeniaCLI writes into traces, descriptors and configs."""

from __future__ import annotations

import base64
from typing import Any

import numpy as np


def _b64(payload: Any, *, label: str) -> bytes:
    if not isinstance(payload, str):
        raise SystemExit(f"{label}: expected a base64 string")
    return base64.b64decode(payload, validate=True)


def trace_field(row: dict[str, Any]) -> np.ndarray:
    """Centred little-endian float16 field of one development-trace row, shape (n, n).

    The array keeps the stored `<f2` bytes so callers can hash `.tobytes()` exactly.
    """
    resolution = row["fieldResolution"]
    if not isinstance(resolution, int) or resolution <= 0:
        raise SystemExit(f"trace row step {row.get('step')}: invalid fieldResolution {resolution!r}")
    values = np.frombuffer(_b64(row["fieldF16Base64"], label="fieldF16Base64"), dtype="<f2")
    if values.size != resolution * resolution:
        raise SystemExit(
            f"trace row step {row.get('step')}: field has {values.size} values, "
            f"expected {resolution}x{resolution}"
        )
    return values.reshape(resolution, resolution)


def fingerprint_u8(terminal: dict[str, Any], *, specimen_id: str) -> np.ndarray:
    """Terminal uint8 mass fingerprint, shape (n, n), from a base64 string or a list of ints."""
    resolution = terminal.get("fingerprintResolution")
    if not isinstance(resolution, (int, float)) or resolution <= 0 or int(resolution) != resolution:
        raise SystemExit(f"{specimen_id}: invalid fingerprintResolution {resolution!r}")
    resolution = int(resolution)
    payload = terminal.get("fingerprintU8")
    if isinstance(payload, str):
        values = np.frombuffer(_b64(payload, label=f"{specimen_id}.fingerprintU8"), dtype=np.uint8)
    elif isinstance(payload, list) and all(
        isinstance(value, int) and 0 <= value <= 255 for value in payload
    ):
        values = np.asarray(payload, dtype=np.uint8)
    else:
        raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
    if values.size != resolution * resolution:
        raise SystemExit(
            f"{specimen_id}: fingerprint has {values.size} values, "
            f"expected {resolution}x{resolution}"
        )
    return values.reshape(resolution, resolution)


def state_patch_values(patch: dict[str, Any]) -> np.ndarray:
    """Flat little-endian float32 values of an `init.state_patch` or terminal state patch."""
    if patch["encoding"] != "f32le":
        raise SystemExit(f"state patch: unsupported encoding {patch['encoding']!r}")
    values = np.frombuffer(_b64(patch["data"], label="state patch data"), dtype="<f4")
    expected = patch["width"] * patch["height"] * patch["channels"]
    if values.size != expected:
        raise SystemExit(f"state patch: {values.size} values, expected {expected}")
    return values


def encode_state_patch_values(values: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(values, dtype="<f4").tobytes()).decode("ascii")
