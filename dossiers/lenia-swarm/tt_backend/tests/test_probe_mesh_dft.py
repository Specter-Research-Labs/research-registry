from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


def _load_probe_module():
    probe_path = Path(__file__).resolve().parents[1] / "devtools" / "probe_mesh_dft.py"
    spec = importlib.util.spec_from_file_location("tt_backend_probe_mesh_dft", probe_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_metrics_report_identical_arrays_as_perfect_match():
    probe = _load_probe_module()
    values = np.arange(16, dtype=np.float32).reshape(4, 4)

    pcc, max_abs_diff = probe._metrics(values, values.copy())

    assert pcc == 1.0
    assert max_abs_diff == 0.0


def test_probe_metrics_reject_shape_mismatch():
    probe = _load_probe_module()

    try:
        probe._metrics(np.zeros((2, 2), dtype=np.float32), np.zeros((4, 4), dtype=np.float32))
    except ValueError as exc:
        assert "Shape mismatch" in str(exc)
    else:
        raise AssertionError("Expected shape mismatch to raise.")
