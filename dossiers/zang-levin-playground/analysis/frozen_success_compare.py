import numpy as np
from utils import get_monotonicity, parse_seed, frozen_path, frozen_cell_type_path, original_path
import scipy.stats as stats
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.stats.weightstats import ztest as ztest

SEED = parse_seed()


def get_final_monotonicity(arr):
    return 100 - arr[-1]

def get_final_success_value(arr):
    return 1 if arr[-1] == 0 else 0

def get_steps_to_reach_final_monotonicity(arr):
    return  arr.index(arr[-1])

def get_avg_final_monotonicity(arr):
    return  np.average([get_final_monotonicity(a) for a in arr if len(a) > 0])

def get_avg_steps_to_reach_final_monotonicity(arr):
    return np.average([get_steps_to_reach_final_monotonicity(a) for a in arr])

def get_monotonicity_arr(arr):
    return [get_monotonicity(step) for step in arr if len(step) > 0]

def get_cell_exp_monotonicities(file):
    experiments = np.load(file, allow_pickle=True)
    return [get_monotonicity_arr(exp_record) for exp_record in experiments ]

def get_original_exp_monotonicities(file):
    experiments = np.load(file, allow_pickle=True,)
    return [exp_record for exp_record in experiments]

def get_frozen_cell_distance(cell_types, frozen_number):
    first_index = cell_types.index(1)
    i = first_index + 1
    prev = first_index
    res = 0
    while i < len(cell_types):
        if cell_types[i] == 1:
            res += i-prev
            prev = i
        i+=1
    return res / (frozen_number - 1)

def plot_final_step_sorting_cell(algo, frozen_cells):
    file_name = frozen_cell_type_path(algo, frozen_cells, SEED)
    exps = np.load(file_name, allow_pickle=True),
    res = []
    for exp in exps[0]:
        last_step = exp[-1]
        cell_type_in_last_step =  [c[3] for c in last_step]
        res.append(get_frozen_cell_distance(cell_type_in_last_step, frozen_cells))

    first_res = []
    for exp in exps[0]:
        first_step = exp[0]
        cell_type_in_last_step =  [c[3] for c in first_step]
        first_res.append(get_frozen_cell_distance(cell_type_in_last_step, frozen_cells))

def get_success_rate_for_original_exp(file):
    exps = np.load(file, allow_pickle=True)
    return [get_final_monotonicity(exp) for exp in exps]
    success_count = np.average([get_final_monotonicity(exp) for exp in exps])
    return success_count

def get_success_rate_for_cell_exp(file):
    exps = get_cell_exp_monotonicities(file)
    return [get_final_monotonicity(exp) for exp in exps if len(exp) > 0]
    success_count = np.average(([get_final_monotonicity(exp) for exp in exps if len(exp) > 0]))
    return success_count


def plot_bar_chart_for_frozen_affect(fozen_cell_number, movable=False):
    success_results_bubble_arr = get_success_rate_for_original_exp(original_path('bubble', fozen_cell_number, SEED, movable=movable))
    success_results_cell_bubble_arr = get_success_rate_for_cell_exp(frozen_path('bubble', fozen_cell_number, SEED, movable=movable))
    success_results_insertion_arr = get_success_rate_for_original_exp(original_path('insertion', fozen_cell_number, SEED, movable=movable))
    success_results_cell_insertion_arr = get_success_rate_for_cell_exp(frozen_path('insertion', fozen_cell_number, SEED, movable=movable))
    success_results_selection_arr = get_success_rate_for_original_exp(original_path('selection', fozen_cell_number, SEED, movable=movable))
    success_results_cell_selection_arr = get_success_rate_for_cell_exp(frozen_path('selection', fozen_cell_number, SEED, movable=movable))
    success_results_bubble = np.average(success_results_bubble_arr)
    success_results_cell_bubble = np.average(success_results_cell_bubble_arr)
    success_results_insertion = np.average(success_results_insertion_arr)
    success_results_cell_insertion = np.average(success_results_cell_insertion_arr)
    success_results_selection = np.average(success_results_selection_arr)
    success_results_cell_selection = np.average(success_results_cell_selection_arr)
    print(f">>>>>>>>>>>>>>>>>>>>fozen cell {fozen_cell_number}>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(f"average bubble: {success_results_bubble} std bubble: {np.std(success_results_bubble_arr)}")
    print(f"average cell bubble: {success_results_cell_bubble} std cell bubble: {np.std(success_results_cell_bubble_arr)}")
    print(f"average insertion: {success_results_insertion} std insertion: {np.std(success_results_insertion_arr)}")
    print(f"average cell insertion: {success_results_cell_insertion} std cell insertion: {np.std(success_results_cell_insertion_arr)}")
    print(f"average selection: {success_results_selection} std selection: {np.std(success_results_selection_arr)}")
    print(f"average cell selection: {success_results_cell_selection} std cell_selection: {np.std(success_results_cell_selection_arr)}")

    barWidth = 0.25

    traditional = [success_results_bubble, success_results_insertion, success_results_selection]
    cell_view = [success_results_cell_bubble, success_results_cell_insertion, success_results_cell_selection]

    br1 = np.arange(len(traditional))
    br2 = [x + barWidth for x in br1]

    no_frozen_bars = plt.bar(br1, traditional, color ='r', width = barWidth,
            edgecolor ='grey', label ='Tradition')
    one_frozen_bars = plt.bar(br2, cell_view, color ='g', width = barWidth,
            edgecolor ='grey', label ='Cell View')

    for bar in no_frozen_bars:
        yval = round(bar.get_height(), 2)
        plt.text(bar.get_x() + barWidth / 2 , yval + .005, yval)

    for bar in one_frozen_bars:
        yval = round(bar.get_height(), 2)
        plt.text(bar.get_x() + barWidth / 2, yval + .005, yval)

    plt.ylabel(f'frozen cell = {fozen_cell_number}')
    plt.xticks([r + barWidth / 2 for r in range(len(traditional))],
            ['bubble', 'insertion', 'selection'], fontsize = 15)

    plt.legend()


def compare_algorithms(algo, frozen_cells):
    original_file = original_path(algo, frozen_cells, SEED, movable=False)
    cell_file = frozen_path(algo, frozen_cells, SEED, movable=False)
    original_exp_monotonicities = get_original_exp_monotonicities(original_file)
    cell_exp_monotonicities = get_cell_exp_monotonicities(cell_file)
    print(f"avg final monotonicity: {get_avg_final_monotonicity(original_exp_monotonicities)}, {get_avg_final_monotonicity(cell_exp_monotonicities)}, {stats.ttest_ind([get_final_monotonicity(a) for a in original_exp_monotonicities], [get_final_monotonicity(a) for a in cell_exp_monotonicities], equal_var=True)}")
    print(f"avg steps to final monotonicity: {get_avg_steps_to_reach_final_monotonicity(original_exp_monotonicities)}, {get_avg_steps_to_reach_final_monotonicity(cell_exp_monotonicities)}, {stats.ttest_ind([get_steps_to_reach_final_monotonicity(a) for a in original_exp_monotonicities], [get_steps_to_reach_final_monotonicity(a) for a in cell_exp_monotonicities], equal_var=True)}")

def get_observe_matrix(algo):
    return [[get_final_monotonicity(a) for a in get_cell_exp_monotonicities(frozen_path(algo, f, SEED, movable=False))] for f in range(1, 4)]

def plot_all_unmovable_graph():
    figure = plt.figure(figsize =(8, 12))
    figure.supylabel('Monotonicity Error', fontweight ='bold', fontsize = 15)
    figure.suptitle("Frozen Cell Unmovable by Others")
    plt.subplot(3, 1, 1)
    plot_bar_chart_for_frozen_affect(1)
    plt.title('Traditional vs Cell View Algorithms', fontweight ='bold', fontsize = 15)

    plt.subplot(3, 1, 2)
    plot_bar_chart_for_frozen_affect(2)

    plt.subplot(3, 1, 3)
    plot_bar_chart_for_frozen_affect(3)

plot_all_unmovable_graph()

def plot_all_movable_graph():
    figure = plt.figure(figsize =(8, 12))
    figure.supylabel('Monotonicity Error', fontweight ='bold', fontsize = 15)
    figure.suptitle("Frozen Cell Movable by Others")
    plt.subplot(3, 1, 1)
    plot_bar_chart_for_frozen_affect(1, True)
    plt.title('Traditional vs Cell View Algorithms', fontweight ='bold', fontsize = 15)

    plt.subplot(3, 1, 2)
    plot_bar_chart_for_frozen_affect(2, True)

    plt.subplot(3, 1, 3)
    plot_bar_chart_for_frozen_affect(3, True)

plot_all_movable_graph()
