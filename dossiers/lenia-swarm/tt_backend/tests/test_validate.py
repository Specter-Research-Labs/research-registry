from __future__ import annotations

import pytest

from devtools.validate import TOLERANCES, multi_step_drift_tolerance


def test_multi_step_drift_tolerance_keeps_reference_strict():
    assert multi_step_drift_tolerance("reference", 3) == pytest.approx(
        TOLERANCES["reference_multi_step"]
    )


def test_multi_step_drift_tolerance_scales_runtime_backends():
    assert multi_step_drift_tolerance("tt", 1) == pytest.approx(
        TOLERANCES["runtime_vs_reference"]
    )
    assert multi_step_drift_tolerance("tt", 3) == pytest.approx(
        TOLERANCES["runtime_vs_reference"] * (3.0**0.5)
    )


def test_multi_step_drift_tolerance_rejects_non_positive_steps():
    with pytest.raises(ValueError, match="steps > 0"):
        multi_step_drift_tolerance("tt", 0)
