from __future__ import annotations

import numpy as np
import pytest

from ttlang.shape_bridge import (
    PlaneMatrixShape,
    lenia_state_to_plane_matrix,
    plane_matrix_to_lenia_state,
    require_tiled_matrix_shape,
)


def test_lenia_state_to_plane_matrix_groups_batch_channel_planes():
    state = np.arange(2 * 3 * 4 * 2, dtype=np.float32).reshape(2, 3, 4, 2)

    matrix, shape = lenia_state_to_plane_matrix(state)

    assert shape == PlaneMatrixShape(batch=2, sx=3, sy=4, channels=2)
    assert matrix.shape == (12, 4)
    np.testing.assert_array_equal(matrix[0], state[0, 0, :, 0])
    np.testing.assert_array_equal(matrix[3], state[0, 0, :, 1])
    np.testing.assert_array_equal(matrix[6], state[1, 0, :, 0])


def test_plane_matrix_roundtrips_lenia_state():
    rng = np.random.default_rng(0)
    state = rng.uniform(size=(2, 5, 7, 3)).astype(np.float32)

    matrix, shape = lenia_state_to_plane_matrix(state)
    roundtrip = plane_matrix_to_lenia_state(matrix, shape)

    np.testing.assert_array_equal(roundtrip, state)


def test_plane_matrix_rejects_wrong_shape():
    shape = PlaneMatrixShape(batch=1, sx=2, sy=3, channels=4)

    with pytest.raises(ValueError, match="Expected plane matrix"):
        plane_matrix_to_lenia_state(np.zeros((7, 3), dtype=np.float32), shape)


def test_require_tiled_matrix_shape_rejects_non_block_multiple():
    require_tiled_matrix_shape(
        np.zeros((128, 256), dtype=np.float32),
        row_block_tiles=4,
        col_block_tiles=4,
    )

    with pytest.raises(ValueError, match="must be divisible"):
        require_tiled_matrix_shape(
            np.zeros((96, 256), dtype=np.float32),
            row_block_tiles=4,
            col_block_tiles=4,
        )
