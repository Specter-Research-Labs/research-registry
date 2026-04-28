from __future__ import annotations

import json

import numpy as np
import pytest

from devtools.run import _sampling_steps
from tt_lenia.frame_export import FrameSequenceWriter, project_mass_to_u8


def test_project_mass_to_u8_sums_channels_for_matter_projection():
    mass = np.array([[[[0.2, 0.3], [0.1, 0.0]], [[0.9, 0.4], [-1.0, 2.0]]]], dtype=np.float32)

    projected = project_mass_to_u8(mass, projection="matter")

    assert projected.tolist() == [[127, 25], [255, 255]]


def test_project_mass_to_u8_can_select_channel():
    mass = np.array([[[[0.2, 0.8], [0.1, 0.0]]]], dtype=np.float32)

    projected = project_mass_to_u8(mass, projection="channel:1")

    assert projected.tolist() == [[204, 0]]


def test_project_mass_to_u8_rejects_bad_projection():
    mass = np.zeros((1, 2, 2, 1), dtype=np.float32)

    with pytest.raises(ValueError, match="projection"):
        project_mass_to_u8(mass, projection="rgb")


def test_frame_sequence_writer_writes_manifest_and_raw_frames(tmp_path):
    writer = FrameSequenceWriter(
        output_dir=tmp_path,
        backend="tt",
        config_path="configs/base/paper_base_2c_128.json",
        steps=4,
        frame_every=2,
        metadata={"dt": 0.1, "kernel_count": 3},
    )
    mass0 = np.zeros((1, 2, 2, 2), dtype=np.float32)
    mass2 = np.full((1, 2, 2, 2), 0.25, dtype=np.float32)

    writer.write_frame(0, mass0)
    writer.write_frame(2, mass2)
    manifest_path = writer.write_manifest(final_mass_path="mass_final.npy")

    manifest = json.loads(manifest_path.read_text())
    assert manifest["kind"] == "lenia_tt_frame_sequence"
    assert manifest["backend"] == "tt"
    assert manifest["width"] == 2
    assert manifest["height"] == 2
    assert manifest["channels"] == 2
    assert manifest["projection"] == "matter"
    assert manifest["frames"] == [
        {"step": 0, "path": "frames/frame_000000.r8"},
        {"step": 2, "path": "frames/frame_000002.r8"},
    ]
    assert (tmp_path / "frames" / "frame_000000.r8").read_bytes() == bytes([0, 0, 0, 0])
    assert (tmp_path / "frames" / "frame_000002.r8").read_bytes() == bytes([127, 127, 127, 127])


def test_frame_sampling_includes_terminal_step():
    assert _sampling_steps(steps=25, save_every=0, frame_every=10) == {0, 10, 20, 25}
