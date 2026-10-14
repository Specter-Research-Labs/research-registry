import threading
import time
from .MultiThreadCell import MultiThreadCell, CellStatus
from .CellGroup import GroupStatus


class ShakerSortCell(MultiThreadCell):
    def __init__(self, threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=False, swapping_count=[0], export_steps=[], label=0, reverse_direction=False):
        super().__init__(threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=disable_visualization, swapping_count=swapping_count, export_steps=export_steps, reverse_direction=reverse_direction)
        self.cell_vision = 1
        self.cell_type = 'Shaker'
        self.label = label
        self.check_right_next = True

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

        bigger_than_right = False
        if self.current_position[0] < self.right_boundary[0]:
            right_cell = self.cells[int(self.current_position[0] + 1)]
            bigger_than_right = self.value > right_cell.value and right_cell.status == CellStatus.ACTIVE

        return smaller_than_left or bigger_than_right

    def move(self):
        self.lock.acquire()
        self.with_lock = True

        if self.group.status == GroupStatus.SLEEP and self.status != CellStatus.MOVING:
            self.status = CellStatus.SLEEP

        if self.should_move():
            self.status_probe.record_compare_and_swap()

        if self.check_right_next:
            target_pos = (self.current_position[0] + self.cell_vision, self.current_position[1])
            if self.within_boundary(target_pos):
                target_cell = self.cells[int(target_pos[0])]
                if target_cell.status == CellStatus.ACTIVE and self.value > target_cell.value:
                    self.swap(target_pos)
        else:
            target_pos = (self.current_position[0] - self.cell_vision, self.current_position[1])
            if self.within_boundary(target_pos):
                target_cell = self.cells[int(target_pos[0])]
                if target_cell.status == CellStatus.ACTIVE and self.value < target_cell.value:
                    self.swap(target_pos)

        self.check_right_next = not self.check_right_next

        self.lock.release()
        self.with_lock = False
