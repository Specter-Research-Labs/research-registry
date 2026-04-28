from __future__ import annotations

import json

import numpy as np

from tt_lenia.reference import (
    load_initial_mass_from_reference,
    load_kernels_from_reference,
    load_reference_arrays,
    load_reference_manifest,
    load_resolved_params,
)


def test_load_reference_bundle(tmp_path):
    mass = np.ones((1, 4, 4, 1), dtype=np.float32)
    np.save(tmp_path / "mass_in.npy", mass)
    np.save(tmp_path / "kernel_fK_re.npy", np.ones((1, 4, 4, 3), dtype=np.float32))
    np.save(tmp_path / "kernel_fK_im.npy", np.zeros((1, 4, 4, 3), dtype=np.float32))
    np.save(tmp_path / "kernel_m.npy", np.array([0.1, 0.2, 0.3], dtype=np.float32))
    np.save(tmp_path / "kernel_s.npy", np.array([0.4, 0.5, 0.6], dtype=np.float32))
    np.save(tmp_path / "kernel_h.npy", np.array([0.7, 0.8, 0.9], dtype=np.float32))
    np.save(tmp_path / "kernel_c0.npy", np.array([0, 0, 0], dtype=np.int32))
    np.save(tmp_path / "kernel_c1_mask.npy", np.array([[1.0, 1.0, 1.0]], dtype=np.float32))

    ref = load_reference_arrays(tmp_path)
    loaded_mass = load_initial_mass_from_reference(ref)
    kernels = load_kernels_from_reference(ref)

    assert np.array_equal(loaded_mass, mass)
    assert kernels.fK.shape == (1, 4, 4, 3)
    assert kernels.c0_idxs.dtype == np.int32
    assert kernels.c1_mask.dtype == np.float32


def test_load_resolved_params_artifact(tmp_path):
    artifact = {
        "seed": 17,
        "params": {
            "r": [0.1, 0.2],
            "b": [[0.3, 0.4, 0.5], [0.6, 0.7, 0.8]],
            "w": [[0.9, 1.0, 1.1], [1.2, 1.3, 1.4]],
            "a": [[0.15, 0.25, 0.35], [0.45, 0.55, 0.65]],
            "m": [0.12, 0.34],
            "s": [0.56, 0.78],
            "h": [0.9, 1.1],
            "R": 12.0,
        },
    }
    path = tmp_path / "resolved_params.json"
    path.write_text(json.dumps(artifact))

    seed, params = load_resolved_params(path)

    assert seed == 17
    assert params.b[0] == [0.3, 0.4, 0.5]
    assert params.R == 12.0


def test_load_reference_manifest_when_present(tmp_path):
    manifest = {
        "manifest_version": 1,
        "kind": "lenia_swift_reference_bundle",
        "parameter_seed": 3,
        "initial_seeds": [3, 7],
        "init_seed_offset": 11,
    }
    (tmp_path / "reference_manifest.json").write_text(json.dumps(manifest))

    assert load_reference_manifest(tmp_path) == manifest
    assert load_reference_manifest(tmp_path / "missing") is None
