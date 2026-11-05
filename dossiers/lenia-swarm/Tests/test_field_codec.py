import base64
import hashlib
import json
import zlib
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.trace_codec import (
    FIELD_ENCODING,
    FieldEncodingError,
    decode_field,
    encode_field,
    state_patch,
    state_patch_values,
)

FIXTURE = Path(__file__).parent / "LeniaCoreTests" / "Fixtures" / "field-codec.json"


def test_round_trip_preserves_every_bit() -> None:
    bits = np.array([0, 0x80000000, 1, 0x7F800000, 0xFF800000, 0x7FC00123, 0x3F800000], "<u4")
    values = np.concatenate([bits.view("<f4"), np.linspace(-3, 3, 1001, dtype="<f4")])
    decoded = decode_field(encode_field(values), count=values.size, label="t")
    assert decoded.tobytes() == values.tobytes()


def test_stream_is_plain_zlib_over_byte_planes() -> None:
    values = np.array([1.0, 2.0, -0.5], "<f4")
    planes = zlib.decompress(base64.b64decode(encode_field(values)))
    raw = values.tobytes()
    assert planes == bytes(raw[i] for plane in range(4) for i in range(plane, len(raw), 4))


def test_fixture_is_bit_identical_with_swift() -> None:
    fixture = json.loads(FIXTURE.read_text())
    raw = base64.b64decode(fixture["raw_f32le_base64"])
    assert hashlib.sha256(raw).hexdigest() == fixture["raw_sha256"]
    values = state_patch_values({**fixture, "center": [0, 0]})
    assert values.tobytes() == raw
    assert encode_field(np.frombuffer(raw, "<f4")) == fixture["data"]


def test_state_patch_writes_the_single_encoding() -> None:
    patch = state_patch(center=[4, 4], width=2, height=1, channels=2, values=np.arange(4))
    assert patch["encoding"] == FIELD_ENCODING
    assert state_patch_values(patch).tolist() == [0.0, 1.0, 2.0, 3.0]


def test_retired_encoding_names_the_compaction_command() -> None:
    patch = {"width": 1, "height": 1, "channels": 1, "encoding": "f32le", "data": "AACAPw=="}
    with pytest.raises(FieldEncodingError, match="lenia-swarm-analysis compact"):
        state_patch_values(patch)


def test_unknown_encoding_and_wrong_length_fail() -> None:
    with pytest.raises(FieldEncodingError, match="unknown field encoding"):
        state_patch_values({"width": 1, "height": 1, "channels": 1, "encoding": "f16", "data": ""})
    with pytest.raises(FieldEncodingError, match="expected 12"):
        decode_field(encode_field(np.zeros(2, "<f4")), count=3, label="t")
