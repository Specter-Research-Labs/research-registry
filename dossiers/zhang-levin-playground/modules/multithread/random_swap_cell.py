import random

from .CellGroup import GroupStatus
from .MultiThreadCell import CellStatus, MultiThreadCell


class RandomSwapCell(MultiThreadCell):
    """Baseline agent: swaps with a random adjacent neighbor unconditionally.

    No sorting logic -- this is the "blind search" control for K-computation.
    """

    def __init__(
        self,
        threadID,
        value,
        lock,
        current_position,
        cells,
        left_boundary,
        right_boundary,
        status_probe,
        disable_visualization=False,
        swapping_count=[0],
        export_steps=[],
        label=0,
        reverse_direction=False,
    ):
        super().__init__(
            threadID,
            value,
            lock,
            current_position,
            cells,
            left_boundary,
            right_boundary,
            status_probe,
            disable_visualization=disable_visualization,
            swapping_count=swapping_count,
            export_steps=export_steps,
            reverse_direction=reverse_direction,
        )
        self.cell_vision = 1
        self.cell_type = "RandomSwap"
        self.label = label

    def within_boundary(self, pos):
        if pos[0] > self.right_boundary[0] or pos[1] > self.right_boundary[1]:
            return False
        if pos[0] < self.left_boundary[0] or pos[1] < self.left_boundary[1]:
            return False
        return True

    def should_move(self):
        return True

    def move(self):
        self.lock.acquire()
        self.with_lock = True

        if self.group.status == GroupStatus.SLEEP and self.status != CellStatus.MOVING:
            self.status = CellStatus.SLEEP

        check_right = random.random() < 0.5
        if check_right:
            target = (self.current_position[0] + self.cell_vision, self.current_position[1])
        else:
            target = (self.current_position[0] - self.cell_vision, self.current_position[1])

        if (
            self.within_boundary(target)
            and self.status == CellStatus.ACTIVE
            and (
                self.cells[int(target[0])].status == CellStatus.ACTIVE
                or self.cells[int(target[0])].status == CellStatus.FREEZE
            )
        ):
            self.swap(target)

        self.lock.release()
        self.with_lock = False
