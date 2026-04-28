from __future__ import annotations

import json

import numpy as np
import pytest

from devtools.run import (
    default_initial_seeds,
    make_initial_state,
    parse_seed_list,
    resolved_parameter_seed,
    validate_execution_batch,
    write_run_manifest,
)
from tt_lenia.config import resolve_params


def _raw_config() -> dict:
    return {
        "init": {
            "seed": 0,
            "patches": [{"center": [2, 2], "size": 2}],
            "a_uniform": {"low": 0.0, "high": 1.0},
            "state_patch": None,
        },
        "params": {
            "mode": "random",
            "seed": 0,
            "ranges": {
                "r": [0.2, 1.0],
                "b": [0.0, 1.0],
                "w": [0.01, 0.5],
                "a": [0.0, 1.0],
                "m": [0.05, 0.5],
                "s": [0.001, 0.2],
                "h": [0.0, 1.0],
                "R": [2.0, 25.0],
            },
        },
    }


def test_resolve_params_seed_argument_overrides_config_seed():
    raw = _raw_config()

    default_params = resolve_params(raw, nb_k=1)
    override_params = resolve_params(raw, nb_k=1, seed=17)

    assert override_params.h != default_params.h


def test_resolved_parameter_seed_uses_config_when_override_is_absent():
    raw = _raw_config()
    raw["params"]["seed"] = 23

    assert resolved_parameter_seed(raw, None) == 23
    assert resolved_parameter_seed(raw, 17) == 17


def test_default_initial_seeds_use_init_seed_not_parameter_seed():
    raw = _raw_config()
    raw["init"]["seed"] = 41
    raw["params"]["seed"] = 3

    assert default_initial_seeds(raw, 3) == [41, 42, 43]


def test_parse_seed_list_rejects_empty_values():
    assert parse_seed_list("3, 5,8") == [3, 5, 8]
    with pytest.raises(ValueError, match="seed"):
        parse_seed_list(" , ")


def test_make_initial_state_uses_independent_seed_per_batch_sample():
    raw = _raw_config()

    batch = make_initial_state(raw, 4, 4, 1, 2, seed_list=[3, 7])
    seed_7 = make_initial_state(raw, 4, 4, 1, 1, seed_list=[7])
    offset_3 = make_initial_state(raw, 4, 4, 1, 1, seed_list=[3], init_seed_offset=4)

    np.testing.assert_array_equal(batch[1:2], seed_7)
    np.testing.assert_array_equal(seed_7, offset_3)


def test_make_initial_state_reuses_rng_across_multiple_patches_per_sample():
    raw = _raw_config()
    raw["init"]["patches"] = [
        {"center": [1, 1], "size": 2},
        {"center": [3, 3], "size": 2},
    ]

    batch = make_initial_state(raw, 4, 4, 1, 1, seed_list=[3])
    rng = np.random.default_rng(3)
    expected_first = rng.uniform(0.0, 1.0, (2, 2, 1)).astype(np.float32)
    expected_second = rng.uniform(0.0, 1.0, (2, 2, 1)).astype(np.float32)

    np.testing.assert_array_equal(batch[0, 0:2, 0:2, :], expected_first)
    np.testing.assert_array_equal(batch[0, 2:4, 2:4, :], expected_second)


def test_write_run_manifest_records_candidate_provenance(tmp_path):
    final_mass = np.array(
        [
            [[[0.0], [0.5]], [[1.0], [0.25]]],
            [[[0.2], [0.3]], [[0.4], [0.5]]],
        ],
        dtype=np.float32,
    )

    path = write_run_manifest(
        out_dir=tmp_path,
        config_path="configs/base/paper_base_1c_128.json",
        reference_path=None,
        backend="tt",
        execution_mode="single",
        execution_strategy="single-device",
        mesh_shape=None,
        visible_devices=None,
        mesh_dft=False,
        steps=2,
        seed=3,
        seed_list=[3, 7],
        init_seed_offset=11,
        final_mass=final_mass,
        elapsed_s=0.5,
    )

    manifest = json.loads(path.read_text())
    assert manifest["kind"] == "lenia_tt_run"
    assert manifest["execution_strategy"] == "single-device"
    assert manifest["mesh_shape"] is None
    assert manifest["mesh_dft"] is False
    assert manifest["parameter_seed"] == 3
    assert manifest["seed_list"] == [3, 7]
    assert manifest["steps_per_second"] == 4.0
    assert manifest["samples"][1]["seed"] == 7
    assert manifest["samples"][1]["init_seed"] == 18


def test_validate_execution_batch_requires_fleet_for_batch_parallel_runs():
    validate_execution_batch("fleet", 2)
    validate_execution_batch("single", 1)
    with pytest.raises(ValueError, match="fleet"):
        validate_execution_batch("single", 2)
