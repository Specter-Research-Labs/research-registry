from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.morphospace.common_morphology import (
    AXIS_IDS,
    point_cloud_shape_features,
)
from lenia_swarm_analysis.morphospace.track1_common_morphology import (
    load_frame,
    results_observations,
)


def _record(seed: int, fingerprint: np.ndarray) -> bytes:
    terminal = {
        "fingerprintResolution": fingerprint.shape[0],
        "fingerprintU8": base64.b64encode(fingerprint.astype(np.uint8).tobytes()).decode(),
    }
    row = {
        "seed": seed,
        "filters_passed": True,
        "descriptor_bundle": {"terminal": terminal},
        "metrics": {"displacement": 7.0, "heading_rad": 0.5,
                    "largest_component_fraction": 0.5, "component_count": 7.0},
    }
    return (json.dumps(row) + "\n").encode()


def test_results_observations_use_the_terminal_fingerprint() -> None:
    blob = np.zeros((32, 32))
    blob[10:14, 8:20] = 200
    blob[12, 20] = 50
    observed = list(results_observations([_record(1, blob), _record(2, np.zeros((32, 32)))]))

    ys, xs = np.nonzero(blob)
    expected = point_cloud_shape_features(
        np.column_stack([xs, ys]).astype(float), weights=blob[ys, xs].astype(float)
    )
    assert observed[0]["has_observation"] is True
    assert [observed[0][axis] for axis in AXIS_IDS] == [expected[axis] for axis in AXIS_IDS]
    assert observed[1]["has_observation"] is False
    assert observed[1]["elongation"] is None
    assert observed[1]["displacement"] == 7.0
    assert observed[0]["component_count"] == expected["component_count"] != 7.0
    assert observed[0]["harvest_component_count"] == 7.0
    assert observed[0]["harvest_largest_component_fraction"] == 0.5


def test_load_frame_requires_the_common_axes_in_order(tmp_path: Path) -> None:
    axes = [{"axisId": axis, "metadata": {"robustCenter": 1.0, "robustScale": 2.0}}
            for axis in AXIS_IDS]
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"axes": axes}), encoding="utf-8")
    assert load_frame(good)["coverage"] == (1.0, 2.0)

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"axes": axes[::-1]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_frame(bad)
