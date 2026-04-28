from .GnomeSortCell import GnomeSortCell


class GnomeCloneCell(GnomeSortCell):
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
        self.cell_type = "GnomeClone"
