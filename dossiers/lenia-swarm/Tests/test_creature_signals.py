from __future__ import annotations

import numpy as np

from lenia_swarm_analysis.morphospace.creature_signals import (
    _largest_component_share,
    _persistence_pairs,
    _registered_overlap_score,
    creature_bucket,
    temporal_individuality_class,
    temporal_individuality_score,
)


def test_largest_component_share_is_mass_weighted_and_eight_connected() -> None:
    values = np.zeros((4, 4), dtype=np.float32)
    values[0, 0] = 4.0
    values[1, 1] = 4.0
    values[3, 3] = 2.0

    share, dominant = _largest_component_share(values > 0, weights=values)

    assert share == 0.8
    assert int(np.count_nonzero(dominant)) == 2


def test_registered_overlap_removes_translation_and_rotation() -> None:
    original = np.zeros((21, 21), dtype=bool)
    original[7:14, 8:11] = True
    original[11:14, 8:16] = True
    transformed = np.roll(np.rot90(original), shift=(2, -3), axis=(0, 1))

    assert _registered_overlap_score(original, transformed) == 1.0


def test_persistence_pairs_include_adjacent_and_long_lags() -> None:
    pairs = _persistence_pairs(8)

    assert (0, 1) in pairs
    assert (0, 2) in pairs
    assert (0, 4) in pairs
    assert (0, 7) in pairs


def test_temporal_individuality_is_required_before_creature_bucketing() -> None:
    raw_axes = {
        "fragmentation": 1.0,
        "axial_polarity": 0.4,
        "locomotion": 0.02,
    }
    transient_axes = {
        "coherence_min": 0.95,
        "coherence_mean": 0.95,
        "whole_body_motion_score": 0.02,
        "temporal_individuality_score": 0.69,
    }
    persistent_axes = {**transient_axes, "temporal_individuality_score": 0.7}

    assert temporal_individuality_class(creature_axes=transient_axes) == "transient_or_incoherent"
    assert creature_bucket(raw_axes=raw_axes, creature_axes=transient_axes) == "diffuse_or_fragmented"
    assert temporal_individuality_class(creature_axes=persistent_axes) == "persistent_individual"
    assert creature_bucket(raw_axes=raw_axes, creature_axes=persistent_axes) == "coherent_polarized"


def test_temporal_individuality_score_uses_the_weakest_persistence_measurement() -> None:
    score = temporal_individuality_score(
        creature_axes={
            "coherence_min": 0.94,
            "shape_persistence_score": 0.88,
            "part_persistence_score": 0.72,
            "localization_score": 0.93,
            "extent_stability_score": 0.91,
        }
    )

    assert score == 0.72


def test_delocalized_field_cannot_score_as_an_individual() -> None:
    axes = {
        "coherence_min": 0.99,
        "shape_persistence_score": 0.99,
        "part_persistence_score": 0.99,
        "localization_score": 0.20,
        "extent_stability_score": 0.99,
    }
    score = temporal_individuality_score(creature_axes=axes)

    assert score == 0.20
    assert (
        temporal_individuality_class(
            creature_axes={**axes, "temporal_individuality_score": score}
        )
        == "transient_or_incoherent"
    )
