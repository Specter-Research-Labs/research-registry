import threading
import time
from .MultiThreadCell import MultiThreadCell, CellStatus
from .CellGroup import GroupStatus
import random


class StubbornSelectionCell(MultiThreadCell):
    """
    Selection sort cell WITHOUT goal adjustment when blocked by frozen cells.

    Unlike regular SelectionSortCell, this version does NOT adjust ideal_position
    when encountering a frozen cell. It simply fails and retries the same target
    on the next iteration.

    This is used for ablation testing to determine whether goal adjustment
    actually provides benefit, or if random retry would work just as well.
    """
    def __init__(self, threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=False, swapping_count=[0], export_steps=[], label=0, reverse_direction=False):
        super().__init__(threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=disable_visualization, swapping_count=swapping_count, export_steps=export_steps, reverse_direction=reverse_direction)
        if self.reverse_direction:
            self.ideal_position = right_boundary
        else:
            self.ideal_position = left_boundary
        self.cell_type = 'StubbornSelection'
        self.label = label

    def within_boundary(self, pos):
        if pos[0] > self.right_boundary[0] or pos[1] > self.right_boundary[1]:
            return False
        if pos[0] < self.left_boundary[0] or pos[1] < self.left_boundary[1]:
            return False
        return True

    def should_move(self):
        return self.current_position != self.ideal_position and self.within_boundary(self.ideal_position)

    def should_move_to(self, target_position):
        if self.within_boundary(target_position) and self.cells[int(target_position[0])].status == CellStatus.FREEZE:
            if self.value < self.cells[int(target_position[0])].value:
                self.swap(target_position)
            return False

        if (
            (self.status == CellStatus.ACTIVE)
            and self.within_boundary(target_position)
            and self.current_position != self.ideal_position
            and (self.cells[int(target_position[0])].status == CellStatus.ACTIVE)
        ):
            if self.value >= self.cells[int(target_position[0])].value:
                if self.reverse_direction:
                    self.ideal_position = (self.ideal_position[0] - 1, self.ideal_position[1])
                else:
                    self.ideal_position = (self.ideal_position[0] + 1, self.ideal_position[1])
                return False
            return True

    def update(self):
        if self.reverse_direction:
            self.ideal_position = self.right_boundary
        else:
            self.ideal_position = self.left_boundary

    def move(self):
        self.lock.acquire()
        self.with_lock = True
        if self.group.status == GroupStatus.SLEEP and self.status != CellStatus.MOVING:
            self.status = CellStatus.SLEEP
        if self.should_move():
            self.status_probe.record_compare_and_swap()
        if self.should_move_to(self.ideal_position):
            cell_at_idea_position = self.cells[int(self.ideal_position[0])]
            if cell_at_idea_position.status == CellStatus.ACTIVE:
                self.swap(self.ideal_position)
        self.lock.release()
        self.with_lock = False
