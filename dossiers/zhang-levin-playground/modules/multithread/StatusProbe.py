import time
from collections import defaultdict


class StatusProbe:
    def __init__(self):
        self.sorting_steps = []
        self.swap_count = 0
        self.cell_types = []
        self.frozen_swap_attempts = 0
        self.compare_and_swap_count = 0

    def record_swap(self):
        self.swap_count += 1

    def record_compare_and_swap(self):
        self.compare_and_swap_count += 1

    def record_sorting_step(self, snapshot):
        self.sorting_steps.append(snapshot)

    def record_cell_type(self, snapshot):
        self.cell_types.append(snapshot)

    def count_frozen_cell_attempt(self):
        self.frozen_swap_attempts += 1

    def record_swap_extended(self, cell_a, cell_b, pos_a, pos_b):
        pass


class ExtendedStatusProbe(StatusProbe):
    def __init__(self):
        super().__init__()
        self.position_history = defaultdict(list)
        self.interaction_graph = defaultdict(int)
        self.swap_events = []
        self.movement_by_type = defaultdict(list)
        self.start_time = time.time()
        self.cell_types_map = {}

    def record_swap_extended(self, cell_a, cell_b, pos_a, pos_b):
        timestamp = time.time() - self.start_time

        key = tuple(sorted([cell_a.threadID, cell_b.threadID]))
        self.interaction_graph[key] += 1

        self.position_history[cell_a.threadID].append((pos_b[0], timestamp))
        self.position_history[cell_b.threadID].append((pos_a[0], timestamp))

        self.swap_events.append((
            timestamp,
            cell_a.threadID,
            cell_b.threadID,
            cell_a.cell_type,
            cell_b.cell_type
        ))

        dist = abs(pos_b[0] - pos_a[0])
        self.movement_by_type[cell_a.cell_type].append(dist)
        self.movement_by_type[cell_b.cell_type].append(dist)

        self.cell_types_map[cell_a.threadID] = cell_a.cell_type
        self.cell_types_map[cell_b.threadID] = cell_b.cell_type
