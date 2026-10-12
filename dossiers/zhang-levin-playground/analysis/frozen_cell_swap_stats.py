import numpy as np
from utils import parse_seed, frozen_path, frozen_swap_count_path

SEED = parse_seed()


def get_avg_total_steps(file):
    exps = np.load(file, allow_pickle=True)
    return np.average([len(exp) for exp in exps])

def get_avg_frozen_cell_attempt(file):
    exps = np.load(file, allow_pickle=True)
    return np.average([attempt for attempt in exps])

def get_frozen_cell_attempt_stats():
    for algo in ['bubble', 'insertion', 'selection']:
        for frozen_cells in range(4):
            print(f"{algo} with {frozen_cells} frozen cells: {get_avg_frozen_cell_attempt(frozen_swap_count_path(algo, frozen_cells, SEED))}, {get_avg_total_steps(frozen_path(algo, frozen_cells, SEED, movable=False))}")


get_frozen_cell_attempt_stats()
