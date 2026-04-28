from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.export_render_bundle import export_render_bundle


def test_export_render_bundle_preserves_body_channels(tmp_path: Path) -> None:
    ndjson = tmp_path / "run.ndjson"
    out_dir = tmp_path / "bundle"
    rows = [
        {
            "record_type": "meta",
            "run_id": "demo",
            "scenario": "imprint",
            "policy": "directed",
            "memory_mode": "on",
            "backend": "cpu",
            "layout": "line",
            "memory_variant": "baseline",
            "steps": 2,
            "dt": 0.1,
            "body_count": 2,
            "memory_params": {
                "min_friction": 0.1,
                "max_friction": 1.2,
                "min_stiffness": 4.0,
                "max_stiffness": 32.0,
                "max_plastic": 5.0,
            },
            "scenario_params": {},
        },
        {
            "record_type": "step",
            "body_positions": [0.0, 0.4, 0.0, 0.6, 0.5, 0.0],
            "body_strain": [0.1, 0.2],
            "body_contact": [1.0, 0.0],
            "body_friction": [0.45, 0.60],
            "body_stiffness": [18.0, 24.0],
            "body_plasticity": [0.0, 1.5],
            "goal_x": 1.2,
            "drive_signal": 0.8,
        },
        {
            "record_type": "step",
            "body_positions": [0.1, 0.45, 0.0, 0.7, 0.55, 0.0],
            "body_strain": [0.3, 0.4],
            "body_contact": [1.0, 1.0],
            "body_friction": [0.52, 0.68],
            "body_stiffness": [20.0, 28.0],
            "body_plasticity": [0.4, 2.0],
            "goal_x": 1.4,
            "drive_signal": 0.0,
        },
        {"record_type": "summary"},
    ]
    ndjson.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    export_render_bundle(ndjson, out_dir, stride=1)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["channels"]["body_plasticity"]["range"] == [0.0, 5.0]
    assert manifest["channels"]["body_stiffness"]["range"] == [4.0, 32.0]

    tracks = np.load(out_dir / "tracks.npz")
    np.testing.assert_allclose(
        tracks["body_translation"],
        np.array(
            [
                [[0.0, 0.4, 0.0], [0.6, 0.5, 0.0]],
                [[0.1, 0.45, 0.0], [0.7, 0.55, 0.0]],
            ],
            dtype=np.float32,
        ),
    )
    np.testing.assert_allclose(
        tracks["body_plasticity"],
        np.array([[0.0, 1.5], [0.4, 2.0]], dtype=np.float32),
    )
    np.testing.assert_allclose(
        tracks["body_contact"],
        np.array([[1.0, 0.0], [1.0, 1.0]], dtype=np.float32),
    )
