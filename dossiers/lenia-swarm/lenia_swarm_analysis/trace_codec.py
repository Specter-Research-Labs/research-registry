"""Decoders for the binary payloads LeniaCLI writes into traces, descriptors and configs."""

from __future__ import annotations

import base64
import zlib
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
        raise SystemExit(
            f"trace row step {row.get('step')}: invalid fieldResolution {resolution!r}"
        )
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


FIELD_ENCODING = "f32le-shuffle-zlib"
RETIRED_FIELD_ENCODINGS = frozenset({"f32le"})
COMPACT_COMMAND = "uv run lenia-swarm-analysis compact <root>"
_ZLIB_LEVEL = 9


class FieldEncodingError(ValueError):
    """Raised for a field payload that is not a valid `f32le-shuffle-zlib` stream."""


def check_field_encoding(encoding: Any, *, label: str) -> None:
    if encoding == FIELD_ENCODING:
        return
    if encoding in RETIRED_FIELD_ENCODINGS:
        raise FieldEncodingError(
            f"{label}: field encoding {encoding!r} is retired; run `{COMPACT_COMMAND}` "
            f"from dossiers/lenia-swarm to rewrite it as {FIELD_ENCODING!r}"
        )
    raise FieldEncodingError(
        f"{label}: unknown field encoding {encoding!r}; only {FIELD_ENCODING!r} is supported"
    )


def encode_field(values: np.ndarray) -> str:
    """Base64 of zlib(byte planes of little-endian float32 values); see docs/contracts/LocalCLI.md."""
    raw = np.ascontiguousarray(values, dtype="<f4").reshape(-1)
    planes = raw.view(np.uint8).reshape(-1, 4).T.tobytes()
    return base64.b64encode(zlib.compress(planes, _ZLIB_LEVEL)).decode("ascii")


def decode_field(payload: Any, *, count: int, label: str) -> np.ndarray:
    """Flat `<f4` values of an `f32le-shuffle-zlib` payload holding exactly `count` values."""
    if not isinstance(payload, str):
        raise FieldEncodingError(f"{label}: expected a base64 string")
    try:
        planes = zlib.decompress(base64.b64decode(payload, validate=True))
    except (ValueError, zlib.error) as error:
        raise FieldEncodingError(f"{label}: invalid field payload ({error})") from error
    if len(planes) != 4 * count:
        raise FieldEncodingError(
            f"{label}: field inflates to {len(planes)} bytes, expected {4 * count}"
        )
    interleaved = np.frombuffer(planes, dtype=np.uint8).reshape(4, count).T.copy()
    return interleaved.reshape(-1).view("<f4")


def state_patch(
    *, center: list[int], width: int, height: int, channels: int, values: np.ndarray
) -> dict[str, Any]:
    """The JSON object LeniaCLI reads as `init.state_patch`, `init.p_state_patch` or a terminal state."""
    flat = np.ascontiguousarray(values, dtype="<f4").reshape(-1)
    if flat.size != width * height * channels:
        raise FieldEncodingError(
            f"state patch: {flat.size} values, expected {width}x{height}x{channels}"
        )
    return {
        "center": [int(center[0]), int(center[1])],
        "width": int(width),
        "height": int(height),
        "channels": int(channels),
        "encoding": FIELD_ENCODING,
        "data": encode_field(flat),
    }


def state_patch_values(patch: dict[str, Any]) -> np.ndarray:
    """Flat little-endian float32 values of an `init.state_patch` or terminal state patch."""
    check_field_encoding(patch["encoding"], label="state patch")
    expected = patch["width"] * patch["height"] * patch["channels"]
    return decode_field(patch["data"], count=expected, label="state patch data")
