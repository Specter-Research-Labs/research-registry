import threading
import time
from .MultiThreadCell import MultiThreadCell, CellStatus
from .CellGroup import GroupStatus


class GnomeSortCell(MultiThreadCell):
    def __init__(self, threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=False, swapping_count=[0], export_steps=[], label=0, reverse_direction=False):
        super().__init__(threadID, value, lock, current_position, cells, left_boundary, right_boundary, status_probe, disable_visualization=disable_visualization, swapping_count=swapping_count, export_steps=export_steps, reverse_direction=reverse_direction)
        self.cell_vision = 1
        self.cell_type = 'Gnome'
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

        left_pos = (self.current_position[0] - self.cell_vision, self.current_position[1])
        right_pos = (self.current_position[0] + self.cell_vision, self.current_position[1])

        if self.within_boundary(left_pos):
            left_cell = self.cells[int(left_pos[0])]
            if left_cell.status == CellStatus.ACTIVE and self.value < left_cell.value:
                self.swap(left_pos)
                self.lock.release()
                self.with_lock = False
                return

        if self.within_boundary(right_pos):
            right_cell = self.cells[int(right_pos[0])]
            if right_cell.status == CellStatus.ACTIVE and self.value > right_cell.value:
                self.swap(right_pos)

        self.lock.release()
        self.with_lock = False
