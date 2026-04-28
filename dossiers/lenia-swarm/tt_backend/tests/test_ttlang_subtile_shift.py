from __future__ import annotations

import numpy as np
import pytest

from ttlang.subtile_shift import (
    TILE_SIZE,
    subtile_part_tile_deltas,
    subtile_shift_reference,
    subtile_shift_selector_matrices,
)


def _make_unique_state(*, sx: int = 64, sy: int = 64) -> np.ndarray:
    rows = np.arange(sx, dtype=np.float32).reshape(1, sx, 1, 1)
    cols = np.arange(sy, dtype=np.float32).reshape(1, 1, sy, 1)
    return rows * np.float32(1000.0) + cols


def _tile(state: np.ndarray, *, tile_row: int, tile_col: int) -> np.ndarray:
    row0 = tile_row * TILE_SIZE
    col0 = tile_col * TILE_SIZE
    return state[0, row0 : row0 + TILE_SIZE, col0 : col0 + TILE_SIZE, 0]


def _selector_shifted_tile(
    state: np.ndarray,
    *,
    tile_row: int,
    tile_col: int,
    row_offset: int,
    col_offset: int,
) -> np.ndarray:
    row_selectors, col_selectors = subtile_shift_selector_matrices(
        row_offset=row_offset,
        col_offset=col_offset,
    )
    row_selector_tiles = row_selectors.reshape(2, TILE_SIZE, TILE_SIZE)
    col_selector_tiles = col_selectors.reshape(2, TILE_SIZE, TILE_SIZE)
    row_deltas = subtile_part_tile_deltas(row_offset)
    col_deltas = subtile_part_tile_deltas(col_offset)
    sx_tiles = state.shape[1] // TILE_SIZE
    sy_tiles = state.shape[2] // TILE_SIZE

    out = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.float32)
    for row_part, row_delta in enumerate(row_deltas):
        for col_part, col_delta in enumerate(col_deltas):
            source_tile = _tile(
                state,
                tile_row=(tile_row + row_delta) % sx_tiles,
                tile_col=(tile_col + col_delta) % sy_tiles,
            )
            out += row_selector_tiles[row_part] @ source_tile @ col_selector_tiles[col_part]
    return out


@pytest.mark.parametrize(
    ("row_offset", "col_offset"),
    [
        (5, -3),
        (-7, 11),
        (0, 0),
        (31, -31),
    ],
)
def test_subtile_shift_selectors_reconstruct_reference_tiles(row_offset: int, col_offset: int):
    state = _make_unique_state()
    expected = subtile_shift_reference(state, row_offset=row_offset, col_offset=col_offset)

    for tile_row in range(2):
        for tile_col in range(2):
            actual_tile = _selector_shifted_tile(
                state,
                tile_row=tile_row,
                tile_col=tile_col,
                row_offset=row_offset,
                col_offset=col_offset,
            )
            expected_tile = _tile(expected, tile_row=tile_row, tile_col=tile_col)
            np.testing.assert_array_equal(actual_tile, expected_tile)


def test_subtile_shift_selector_matrices_cover_each_output_position_once():
    row_selectors, col_selectors = subtile_shift_selector_matrices(row_offset=9, col_offset=-13)

    assert row_selectors.shape == (2 * TILE_SIZE, TILE_SIZE)
    assert col_selectors.shape == (2 * TILE_SIZE, TILE_SIZE)
    np.testing.assert_array_equal(
        row_selectors.reshape(2, TILE_SIZE, TILE_SIZE).sum(axis=(0, 2)),
        np.ones(TILE_SIZE, dtype=np.float32),
    )
    np.testing.assert_array_equal(
        col_selectors.reshape(2, TILE_SIZE, TILE_SIZE).sum(axis=(0, 1)),
        np.ones(TILE_SIZE, dtype=np.float32),
    )


def test_subtile_shift_reference_rolls_lenia_state():
    state = _make_unique_state(sx=64, sy=64)

    shifted = subtile_shift_reference(state, row_offset=-4, col_offset=6)

    assert shifted[0, 0, 0, 0] == state[0, 60, 6, 0]
    assert shifted[0, 63, 63, 0] == state[0, 59, 5, 0]


@pytest.mark.parametrize("offset", [-32, 32])
def test_subtile_shift_rejects_whole_tile_offsets(offset: int):
    with pytest.raises(ValueError, match="Expected sub-tile offset"):
        subtile_shift_selector_matrices(row_offset=offset, col_offset=0)
