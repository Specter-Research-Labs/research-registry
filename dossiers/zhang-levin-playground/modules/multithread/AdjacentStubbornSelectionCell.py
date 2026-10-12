from .CellGroup import GroupStatus
from .MultiThreadCell import CellStatus
from .StubbornSelectionCell import StubbornSelectionCell


class AdjacentStubbornSelectionCell(StubbornSelectionCell):
    """Adjacent-only variant of StubbornSelectionCell."""

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
        self.cell_type = "AdjacentStubbornSelection"

    def _step_target_position(self):
        if self.current_position[0] < self.ideal_position[0]:
            return (self.current_position[0] + 1, self.current_position[1])
        if self.current_position[0] > self.ideal_position[0]:
            return (self.current_position[0] - 1, self.current_position[1])
        return self.current_position

    def _count_frozen_target_attempt(self):
        if not self.tried_to_swap_with_frozen:
            self.status_probe.count_frozen_cell_attempt()
            self.tried_to_swap_with_frozen = True

    def should_move_to(self, target_position):
        target_cell = self.cells[int(target_position[0])]
        if self.within_boundary(target_position) and target_cell.status == CellStatus.FREEZE:
            if self.value < target_cell.value:
                self._count_frozen_target_attempt()
            return False

        return super().should_move_to(target_position)

    def move(self):
        self.lock.acquire()
        self.with_lock = True
        if self.group.status == GroupStatus.SLEEP and self.status != CellStatus.MOVING:
            self.status = CellStatus.SLEEP
        if self.should_move():
            self.status_probe.record_compare_and_swap()
        if self.should_move_to(self.ideal_position):
            step_target = self._step_target_position()
            if step_target != self.current_position:
                step_cell = self.cells[int(step_target[0])]
                if step_cell.status == CellStatus.ACTIVE:
                    self.swap(step_target)
        self.lock.release()
        self.with_lock = False
