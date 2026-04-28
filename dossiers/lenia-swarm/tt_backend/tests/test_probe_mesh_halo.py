from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_probe_module():
    probe_path = Path(__file__).resolve().parents[1] / "devtools" / "probe_mesh_halo.py"
    spec = importlib.util.spec_from_file_location("tt_backend_probe_mesh_halo", probe_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mesh_halo_probe_imports_without_ttnn():
    probe = _load_probe_module()

    assert probe._mesh_shape_tuple((1, 2)) == (1, 2)


def test_mesh_halo_runtime_helpers_import_without_ttnn():
    from tt_lenia.stages import mesh_halo

    assert mesh_halo.MeshRowHalo(tensor=None, cleanup=()).cleanup == ()
