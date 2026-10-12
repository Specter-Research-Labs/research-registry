import threading
import time
from .MultiThreadCell import MultiThreadCell, CellStatus
from .CellGroup import GroupStatus
import random


class InsertionNoWaitCell(MultiThreadCell):
    """
    Insertion sort WITHOUT the enable_to_move constraint.

    Normal Insertion: waits for left portion to be sorted before moving.
    This version: moves immediately if out of order with left neighbor.

    If temporal separation causes clustering, removing this constraint
    should make InsertionNoWait behave like Bubble/Gnome (move early)
    and clustering should DISAPPEAR.
    """

    def __init__(self, threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=False, swapping_count=[0], export_steps=[], label=0, reverse_direction=False):
        super().__init__(threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=disable_visualization, swapping_count=swapping_count, export_steps=export_steps, reverse_direction=reverse_direction)
        self.cell_vision = 1
        self.cell_type = 'InsertionNoWait'
        self.label = label

    def within_boundary(self, pos):
        if pos[0] > self.right_boundary[0] or pos[1] > self.right_boundary[1]:
            return False
        if pos[0] < self.left_boundary[0] or pos[1] < self.left_boundary[1]:
            return False
        return True

    def should_move(self):
        smaller_than_left = False
        if self.current_position[0] > self.left_boundary[0]:
            left_cell = self.cells[int(self.current_position[0] - 1)]
            smaller_than_left = self.value < left_cell.value and left_cell.status == CellStatus.ACTIVE
        return smaller_than_left

    def should_move_to(self, target_position):
        if (
            self.status == CellStatus.ACTIVE
            and self.within_boundary(target_position)
            and self.cells[int(target_position[0])].status == CellStatus.ACTIVE
        ):
            return self.value < self.cells[int(target_position[0])].value

    def move(self):
        self.lock.acquire()

        if self.should_move():
            self.status_probe.record_compare_and_swap()

        if self.group.status == GroupStatus.SLEEP and self.status != CellStatus.MOVING:
            self.status = CellStatus.SLEEP

        target_position = (self.current_position[0] - self.cell_vision, self.current_position[1])

        if self.should_move_to(target_position):
            self.swap(target_position)

        self.lock.release()
