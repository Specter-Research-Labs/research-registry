from __future__ import annotations

import numpy as np
import pytest

from ttlang.shape_bridge import lenia_state_to_plane_matrix
from ttlang.reintegration_subtile import (
    TILE_SIZE,
    subtile_reintegration_group_block_selector_matrices,
    subtile_reintegration_group_param_matrix,
    subtile_reintegration_group_reference,
    subtile_reintegration_group_selector_matrices,
    subtile_reintegration_offset_groups,
    subtile_reintegration_param_matrix,
    subtile_reintegration_reference,
    torus_halo_pad_plane_matrix,
)
from ttlang.subtile_shift import subtile_shift_reference


def test_subtile_reintegration_param_matrix_packs_distances_and_constants():
    matrix = subtile_reintegration_param_matrix(
        row_offset=3,
        col_offset=-2,
        dt=0.2,
        max_flow=4.35,
        sigma=0.65,
    )

    assert matrix.shape == (9 * TILE_SIZE, TILE_SIZE)
    np.testing.assert_array_equal(matrix[0:TILE_SIZE, :], np.float32(-2.0))
    np.testing.assert_array_equal(matrix[TILE_SIZE : 2 * TILE_SIZE, :], np.float32(3.0))
    np.testing.assert_allclose(matrix[2 * TILE_SIZE, 0], np.float32(0.2))
    np.testing.assert_allclose(matrix[3 * TILE_SIZE, 0], np.float32(4.35))
    np.testing.assert_allclose(matrix[4 * TILE_SIZE, 0], np.float32(-4.35))
    np.testing.assert_allclose(matrix[5 * TILE_SIZE, 0], np.float32(1.15))
    np.testing.assert_allclose(matrix[6 * TILE_SIZE, 0], np.float32(1.0))
    np.testing.assert_allclose(matrix[7 * TILE_SIZE, 0], np.float32(1.0 / (4.0 * 0.65 * 0.65)))
    np.testing.assert_allclose(matrix[8 * TILE_SIZE, 0], np.float32(0.0))


def test_subtile_reintegration_offset_groups_share_tile_deltas():
    groups = subtile_reintegration_offset_groups(1)

    assert sorted(len(group) for group in groups) == [1, 2, 2, 4]
    assert sum(len(group) for group in groups) == 9


def test_subtile_reintegration_group_matrices_stack_offsets():
    offsets = ((0, 0), (1, 0), (0, 1), (1, 1))

    row_selectors, col_selectors = subtile_reintegration_group_selector_matrices(offsets)
    params = subtile_reintegration_group_param_matrix(
        offsets,
        dt=0.2,
        max_flow=4.35,
        sigma=0.65,
    )

    assert row_selectors.shape == (2 * len(offsets) * TILE_SIZE, TILE_SIZE)
    assert col_selectors.shape == (2 * len(offsets) * TILE_SIZE, TILE_SIZE)
    assert params.shape == (9 * len(offsets) * TILE_SIZE, TILE_SIZE)
    np.testing.assert_array_equal(params[9 * TILE_SIZE : 10 * TILE_SIZE, :], np.float32(0.0))
    np.testing.assert_array_equal(params[10 * TILE_SIZE : 11 * TILE_SIZE, :], np.float32(1.0))


def test_subtile_reintegration_block_selectors_match_split_selectors():
    offsets = ((-1, 2), (0, 3), (1, 4))

    row_split, col_split = subtile_reintegration_group_selector_matrices(offsets)
    row_block, col_block = subtile_reintegration_group_block_selector_matrices(offsets)

    assert row_block.shape == (len(offsets) * TILE_SIZE, 2 * TILE_SIZE)
    assert col_block.shape == (2 * len(offsets) * TILE_SIZE, TILE_SIZE)
    for offset_index in range(len(offsets)):
        split_base = offset_index * 2 * TILE_SIZE
        row_parts = row_split[split_base : split_base + 2 * TILE_SIZE, :].reshape(2, TILE_SIZE, TILE_SIZE)
        col_parts = col_split[split_base : split_base + 2 * TILE_SIZE, :].reshape(2, TILE_SIZE, TILE_SIZE)
        np.testing.assert_array_equal(
            row_block[offset_index * TILE_SIZE : (offset_index + 1) * TILE_SIZE, :],
            np.concatenate([row_parts[0], row_parts[1]], axis=1),
        )
        np.testing.assert_array_equal(
            col_block[split_base : split_base + 2 * TILE_SIZE, :],
            np.concatenate([col_parts[0], col_parts[1]], axis=0),
        )


def test_subtile_reintegration_group_reference_sums_offsets():
    rng = np.random.default_rng(9)
    mass = rng.uniform(0.0, 1.0, size=(1, 64, 64, 1)).astype(np.float32)
    flow_y = rng.uniform(-0.2, 0.2, size=mass.shape).astype(np.float32)
    flow_x = rng.uniform(-0.2, 0.2, size=mass.shape).astype(np.float32)
    offsets = ((0, 0), (1, 0), (0, 1), (1, 1))

    actual = subtile_reintegration_group_reference(
        mass,
        flow_y,
        flow_x,
        offsets,
        dt=0.2,
        max_flow=4.35,
        sigma=0.65,
    )
    expected = sum(
        subtile_reintegration_reference(
            mass,
            flow_y,
            flow_x,
            row_offset=row_offset,
            col_offset=col_offset,
            dt=0.2,
            max_flow=4.35,
            sigma=0.65,
        )
        for row_offset, col_offset in offsets
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


def test_torus_halo_pad_plane_matrix_supports_rectangular_positive_offsets():
    state = np.arange(1 * 64 * 96 * 2, dtype=np.float32).reshape(1, 64, 96, 2)
    matrix, shape = lenia_state_to_plane_matrix(state)

    padded = torus_halo_pad_plane_matrix(matrix, shape, ((0, 0), (0, 1), (1, 0), (1, 1)))

    assert padded.shape == (2 * (64 + TILE_SIZE), 96 + TILE_SIZE)
    np.testing.assert_array_equal(padded[64:96, 96:128], matrix[0:32, 0:32])
    np.testing.assert_array_equal(padded[160:192, 96:128], matrix[64:96, 0:32])


def test_torus_halo_pad_plane_matrix_supports_rectangular_negative_offsets():
    state = np.arange(1 * 64 * 96 * 2, dtype=np.float32).reshape(1, 64, 96, 2)
    matrix, shape = lenia_state_to_plane_matrix(state)

    padded = torus_halo_pad_plane_matrix(matrix, shape, ((-1, -1),))

    assert padded.shape == (2 * (64 + TILE_SIZE), 96 + TILE_SIZE)
    np.testing.assert_array_equal(padded[0:32, 0:32], matrix[32:64, 64:96])
    np.testing.assert_array_equal(padded[96:128, 0:32], matrix[96:128, 64:96])


def test_subtile_reintegration_reference_matches_zero_flow_weighted_shift():
    rng = np.random.default_rng(7)
    mass = rng.uniform(0.0, 1.0, size=(1, 64, 64, 2)).astype(np.float32)
    flow_y = np.zeros_like(mass)
    flow_x = np.zeros_like(mass)

    actual = subtile_reintegration_reference(
        mass,
        flow_y,
        flow_x,
        row_offset=1,
        col_offset=-1,
        dt=0.2,
        max_flow=4.35,
        sigma=0.65,
    )

    shifted = subtile_shift_reference(mass, row_offset=1, col_offset=-1)
    weight = (1.15 - 1.0) * (1.15 - 1.0) / (4.0 * 0.65 * 0.65)
    np.testing.assert_allclose(actual, shifted * np.float32(weight), rtol=1e-6, atol=1e-6)


def test_subtile_reintegration_reference_rejects_mismatched_shapes():
    mass = np.zeros((1, 64, 64, 2), dtype=np.float32)
    flow_y = np.zeros((1, 64, 64, 1), dtype=np.float32)
    flow_x = np.zeros_like(mass)

    with pytest.raises(ValueError, match="Expected mass/flow shapes"):
        subtile_reintegration_reference(
            mass,
            flow_y,
            flow_x,
            row_offset=0,
            col_offset=0,
            dt=0.2,
            max_flow=4.35,
            sigma=0.65,
        )
