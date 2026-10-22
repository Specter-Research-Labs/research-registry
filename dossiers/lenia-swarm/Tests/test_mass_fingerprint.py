import base64
import json
import zlib
from pathlib import Path

import numpy as np

from lenia_swarm_analysis.morphospace.fingerprint import _sequential_sum, box_resample, mass_fingerprint, quantized_fingerprint
from lenia_swarm_analysis.trace_codec import trace_field

FRAMES = Path(__file__).parent / "fixtures" / "metal_mass_fingerprint_frames.json"
TRACE_FRAMES = Path(__file__).parent / "fixtures" / "metal_trace_field_fingerprint_frames.json"


def test_mass_fingerprint_matches_metal_frames_bitwise() -> None:
    """Two raw float32 states from a 2-channel 128x128 torus Metal replay on 6537cb2f (`publish replay
    --development-state`; 060e90 has no raw-state output) at steps 350 and 650, with the `fingerprintU8`
    the replay traced for each. Both frames sit off-centre, so the roll and the wrap are exercised."""
    for frame in json.loads(FRAMES.read_text())["frames"]:
        raw = zlib.decompress(base64.b64decode(frame["stateF32ZlibBase64"]))
        state = np.frombuffer(raw, dtype="<f4").reshape(frame["shape"]).astype(np.float32)
        expected = np.frombuffer(base64.b64decode(frame["fingerprintU8"]), np.uint8).reshape(32, 32)
        got = mass_fingerprint(state)
        assert got.dtype == np.uint8
        diff = int((got != expected).sum())
        assert diff == 0, f"step {frame['step']}: {diff} cells differ"


def test_quantized_fingerprint_of_metal_trace_fields() -> None:
    """Centred float16 trace fields from 128x128 torus Metal replays, with the `fingerprintU8` traced at the
    same step. The trace field is the float32 sample rounded to float16, so a cell whose scaled value lies within
    float16 rounding of a half-integer can land one unit off; elsewhere the port is bitwise."""
    for frame in json.loads(TRACE_FRAMES.read_text())["frames"]:
        field = trace_field(frame).astype(np.float32)
        expected = np.frombuffer(base64.b64decode(frame["fingerprintU8"]), np.uint8).reshape(32, 32)
        got = quantized_fingerprint(field)
        differing = np.argwhere(got != expected)
        if frame["expect"] == "bitwise":
            assert len(differing) == 0, f"{frame['campaign']} step {frame['step']}: {len(differing)} cells differ"
            continue
        assert frame["expect"] == "one_cell_at_rounding_boundary"
        assert len(differing) == 1
        cell = tuple(differing[0])
        assert abs(int(got[cell]) - int(expected[cell])) == 1
        reduced = box_resample(field)
        scaled = float(reduced[cell] / _sequential_sum(reduced) * np.float32(255))
        assert abs(scaled - np.floor(scaled) - 0.5) <= scaled * 2.0**-11


def test_mass_fingerprint_of_empty_state_is_zero() -> None:
    assert not mass_fingerprint(np.zeros((64, 64, 2), np.float32)).any()
