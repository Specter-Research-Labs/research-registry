from __future__ import annotations

import numpy as np
import pytest

from ttlang.reintegration_tile_shift import (
    TILE_SIZE,
    TileReintegrationShift,
    smoke_tolerance,
    tile_reintegration_param_matrix,
    tile_shift_reintegration_reference,
)


def test_tile_reintegration_param_matrix_packs_shift_and_constants_as_tiles():
    shifts = (
        TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.25, x_distance=-0.5),
        TileReintegrationShift(row_shift_tiles=1, col_shift_tiles=-1, y_distance=-0.125, x_distance=0.75),
    )

    matrix = tile_reintegration_param_matrix(shifts, dt=0.1, max_flow=0.5, sigma=0.65)

    assert matrix.shape == ((2 * len(shifts) + 7) * TILE_SIZE, TILE_SIZE)
    np.testing.assert_array_equal(matrix[0:TILE_SIZE, :], np.float32(0.25))
    np.testing.assert_array_equal(matrix[TILE_SIZE : 2 * TILE_SIZE, :], np.float32(-0.125))
    np.testing.assert_array_equal(matrix[2 * TILE_SIZE : 3 * TILE_SIZE, :], np.float32(-0.5))
    np.testing.assert_array_equal(matrix[3 * TILE_SIZE : 4 * TILE_SIZE, :], np.float32(0.75))
    np.testing.assert_allclose(matrix[4 * TILE_SIZE, 0], np.float32(0.1))
    np.testing.assert_allclose(matrix[5 * TILE_SIZE, 0], np.float32(0.5))
    np.testing.assert_allclose(matrix[6 * TILE_SIZE, 0], np.float32(-0.5))
    np.testing.assert_allclose(matrix[7 * TILE_SIZE, 0], np.float32(1.15))
    np.testing.assert_allclose(matrix[8 * TILE_SIZE, 0], np.float32(1.0))
    np.testing.assert_allclose(matrix[9 * TILE_SIZE, 0], np.float32(1.0 / (4.0 * 0.65 * 0.65)))
    np.testing.assert_allclose(matrix[10 * TILE_SIZE, 0], np.float32(0.0))


def test_tile_shift_reintegration_reference_accumulates_shifted_sources():
    sx = sy = 64
    mass = np.zeros((1, sx, sy, 1), dtype=np.float32)
    mass[:, 0:32, 0:32, 0] = 1.0
    flow = np.zeros((1, sx, sy, 2, 1), dtype=np.float32)
    shifts = (
        TileReintegrationShift(row_shift_tiles=0, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),
        TileReintegrationShift(row_shift_tiles=1, col_shift_tiles=0, y_distance=0.0, x_distance=0.0),
    )

    result = tile_shift_reintegration_reference(mass, flow, shifts, dt=0.0, max_flow=0.0, sigma=0.5)

    expected = mass + np.roll(mass, -32, axis=1)
    np.testing.assert_array_equal(result, expected)


def test_tile_shift_reintegration_reference_rejects_incompatible_flow_shape():
    mass = np.zeros((1, 32, 32, 2), dtype=np.float32)
    flow = np.zeros((1, 32, 32, 2, 1), dtype=np.float32)
    shifts = (TileReintegrationShift(0, 0, 0.0, 0.0),)

    with pytest.raises(ValueError, match="Expected flow shape"):
        tile_shift_reintegration_reference(mass, flow, shifts, dt=0.1, max_flow=0.5, sigma=0.65)


def test_smoke_tolerance_scales_bfloat16_for_larger_outputs():
    expected = np.array([0.0, 6.5], dtype=np.float32)

    assert smoke_tolerance("float32", expected) == pytest.approx(3.25e-2)
    assert smoke_tolerance("bfloat16", expected) == pytest.approx(9.75e-2)
