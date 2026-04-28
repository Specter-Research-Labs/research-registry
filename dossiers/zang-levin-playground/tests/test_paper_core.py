import unittest

from paper.exp2d_core import (
    Bubble2DCell,
    Grid2D,
    OrderMode,
    frozen_counts_for_size,
    order_positions_for_mode,
)


class PaperCoreTests(unittest.TestCase):
    def test_order_modes_are_stable(self):
        self.assertEqual(
            order_positions_for_mode(3, OrderMode.ROW_MAJOR),
            [
                (0, 0),
                (1, 0),
                (2, 0),
                (0, 1),
                (1, 1),
                (2, 1),
                (0, 2),
                (1, 2),
                (2, 2),
            ],
        )
        self.assertEqual(
            order_positions_for_mode(3, OrderMode.SERPENTINE),
            [
                (0, 0),
                (1, 0),
                (2, 0),
                (2, 1),
                (1, 1),
                (0, 1),
                (0, 2),
                (1, 2),
                (2, 2),
            ],
        )
        self.assertEqual(
            order_positions_for_mode(2, OrderMode.SHELL),
            [(0, 0), (0, 1), (1, 0), (1, 1)],
        )

    def test_frozen_counts_match_paper_grid_ratios(self):
        self.assertEqual(frozen_counts_for_size(6), [0, 3, 6, 9])
        self.assertEqual(frozen_counts_for_size(8), [0, 5, 11, 16])

    def test_grid_swap_updates_positions_and_lookup(self):
        grid = Grid2D(2, 2, 4, order_positions_for_mode(2, OrderMode.ROW_MAJOR))
        left = Bubble2DCell(2, (0, 0))
        right = Bubble2DCell(1, (1, 0))
        grid.add_cell(left)
        grid.add_cell(right)

        grid.swap_cells(left, right)

        self.assertEqual(left.position, (1, 0))
        self.assertEqual(right.position, (0, 0))
        self.assertIs(grid.get_cell_at(1, 0), left)
        self.assertIs(grid.get_cell_at(0, 0), right)


if __name__ == "__main__":
    unittest.main()
