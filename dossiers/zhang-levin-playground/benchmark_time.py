import time
import threading
import random
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.SelectionSortCell import SelectionSortCell
from exp14_cellview_vs_traditional import _run_traditional_trial, _run_cellview_trial

class TraditionalBubble:
    def solve(self, arr, frozen):
        n = len(arr)
        for i in range(n):
            for j in range(0, n - i - 1):
                if j in frozen or (j+1) in frozen:
                    continue
                if arr[j] > arr[j+1]:
                    arr[j], arr[j+1] = arr[j+1], arr[j]

def benchmark():
    n_cells = 30
    trials = 10
    
    cell_times = []
    central_times = []
    
    for _ in range(trials):
        values = list(range(n_cells))
        random.shuffle(values)
        
        t0 = time.time()
        # run cell view
        _run_cellview_trial(
            cell_class=SelectionSortCell, 
            values=list(values), 
            frozen_indices=set(), 
            timeout=10.0
        )
        t1 = time.time()
        cell_times.append(t1 - t0)
        
        t0 = time.time()
        # run traditional
        # Just use Selection for comparison
        from exp14_cellview_vs_traditional import _traditional_selection_sort
        _traditional_selection_sort(list(values), set())
        t1 = time.time()
        central_times.append(t1 - t0)
        
    print(f"Cell-view Selection mean time: {np.mean(cell_times):.3f}s")
    print(f"Traditional Selection mean time: {np.mean(central_times):.3f}s")

if __name__ == '__main__':
    benchmark()
