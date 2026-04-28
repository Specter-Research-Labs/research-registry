from pathlib import Path
import argparse
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from paths import resolve_artifact_dir

DATA_DIR = resolve_artifact_dir("data", ROOT_DIR / "data")
FIGURES_DIR = resolve_artifact_dir("figures", ROOT_DIR / "figures")


def parse_seed(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--seed", type=int, default=None)
    args, _ = parser.parse_known_args(argv)
    return args.seed


def _path(stem, seed):
    if seed is not None:
        return DATA_DIR / f"{stem}_seed{seed}.npy"
    return DATA_DIR / f"{stem}.npy"


def baseline_path(algo, seed):
    return _path(f"{algo}_sort_sorting_steps_100exps", seed)


def frozen_path(algo, frozen_count, seed, movable=True):
    if movable:
        return _path(f"{algo}_sort_sorting_with_{frozen_count}frozen_steps_100exps", seed)
    return _path(f"{algo}_sort_sorting_with_{frozen_count}frozen_cannot_move_steps_100exps", seed)


def frozen_swap_count_path(algo, frozen_count, seed):
    return _path(f"{algo}_sort_sorting_with_{frozen_count}frozen_frozen_swap_count_100exps", seed)


def frozen_cell_type_path(algo, frozen_count, seed):
    return _path(f"{algo}_sort_sorting_with_{frozen_count}frozen_steps_cell_type_100exps", seed)


def original_path(algo, frozen_count, seed, movable=True):
    if movable:
        return _path(f"original_{algo}_sort_with_{frozen_count}frozen_steps_100exps", seed)
    return _path(f"original_{algo}_sort_with_{frozen_count}frozen_cannot_move_sorting_steps_100exps", seed)


def original_records_path(algo, frozen_count, seed):
    return _path(f"original_{algo}_sort_with_{frozen_count}frozen_cannot_move_sorting_records_100exps", seed)


def twenty_points_path(algo, seed):
    return _path(f"{algo}_sort_20_points_sorting_steps", seed)


def get_monotonicity(arr):
    monotonicity_value = 1
    prev = arr[0]
    for i in range(1, len(arr)):
        if arr[i] >= prev:
            monotonicity_value += 1
        prev = arr[i]
    return (monotonicity_value / len(arr)) * 100

def get_spearman_distance(arr):
    res = 0
    for i in range(len(arr)):
        res += abs(arr[i] - i)
    return res
