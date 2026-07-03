import base64

import numpy as np

from lenia_swarm_analysis.anatomical_compiler.form_topology import (
    feature_counts,
    persistence_image,
    topo_distance,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import state_patch_config
from lenia_swarm_analysis.anatomical_compiler.swift_form_seed import form_is_held


def test_persistence_signature_distinguishes_ring_from_disk() -> None:
    size = 32
    y, x = np.ogrid[:size, :size]
    radius = np.sqrt((x - (size - 1) / 2) ** 2 + (y - (size - 1) / 2) ** 2)
    ring = ((radius >= 7) & (radius <= 10)).astype(np.float64)
    disk = (radius <= 10).astype(np.float64)

    assert feature_counts(ring) == (1, 1)
    assert feature_counts(disk) == (1, 0)
    assert topo_distance(persistence_image(ring), persistence_image(disk)) > 0


def test_persistence_signature_is_density_scale_invariant() -> None:
    field = np.zeros((16, 16), dtype=np.float64)
    field[4:12, 4:12] = 0.25

    assert topo_distance(persistence_image(field), persistence_image(field * 3.0)) == 0


def test_state_patch_config_encodes_c_order_float32_without_mutating_source() -> None:
    base = {
        "init": {
            "seed": 99,
            "patches": [{"center": [1, 1], "size": 2}],
            "a_uniform": {"low": 0.1, "high": 0.2},
        }
    }
    field = np.arange(8, dtype=np.float32).reshape(2, 2, 2)

    configured = state_patch_config(base, field, center=(5, 7), seed=11)

    assert base["init"]["seed"] == 99
    assert configured["init"]["seed"] == 11
    assert configured["init"]["patches"] == []
    assert configured["init"]["a_uniform"] == {"low": 0.0, "high": 0.0}
    patch = configured["init"]["state_patch"]
    assert patch["center"] == [5, 7]
    assert (patch["width"], patch["height"], patch["channels"]) == (2, 2, 2)
    decoded = np.frombuffer(base64.b64decode(patch["data"]), dtype="<f4")
    np.testing.assert_array_equal(decoded, field.ravel(order="C"))


def test_swift_acceptance_requires_matching_form_topology() -> None:
    common = {
        "stable": True,
        "mass_conservation": 1.0,
        "form_drift": 0.1,
        "topology_distance": 0.1,
        "target_features": (1, 1),
    }

    assert form_is_held(**common, terminal_features=(1, 1))
    assert not form_is_held(**common, terminal_features=(1, 0))
