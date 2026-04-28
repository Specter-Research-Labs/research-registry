from .CellGroup import GroupStatus
from .GnomeSortCell import GnomeSortCell
from .MultiThreadCell import CellStatus


class DelayedGnomeCell(GnomeSortCell):
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
            label=label,
            reverse_direction=reverse_direction,
        )
        self.cell_type = "DelayedGnome"

    def is_enable_to_move(self):
        prev = 100000 if self.reverse_direction else -1
        for index in range(int(self.left_boundary[0]), int(self.current_position[0])):
            if self.cells[index].status == CellStatus.FREEZE:
                prev = -1
                continue
            if self.reverse_direction and self.cells[index].value > prev:
                return False
            if not self.reverse_direction and self.cells[index].value < prev:
                return False
            prev = self.cells[index].value
        return True

    def should_move(self):
        return self.is_enable_to_move() and super().should_move()

    def move(self):
        self.lock.acquire()
        self.with_lock = True
        if not self.is_enable_to_move():
            self.lock.release()
            self.with_lock = False
            return
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
