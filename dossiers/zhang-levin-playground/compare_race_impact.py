"""
Race Condition Impact Analysis: Original vs Synchronized Generators

This script runs both original (racy) and synchronized (fixed) versions of the
data generators with identical random seeds, then compares results to quantify
the impact of race conditions on the statistical conclusions.

Usage:
    python compare_race_impact.py [seed] [--skip-generate] [--baseline-only]

Options:
    seed            Random seed (default: 42)
    --skip-generate Skip running generators, just analyze existing data
    --baseline-only Only run/analyze baseline data (skip frozen experiments)

The script will:
1. Run baseline generators (original + synchronized) with the given seed
2. Compare swap counts, step counts, and early termination detection
3. Output a formatted comparison table with statistical tests

Note: Uses np.load with allow_pickle=True because the existing data format uses
dtype=object arrays. This is safe as we're loading our own generated data.
"""

import subprocess
import sys
import time
import numpy as np
from pathlib import Path
from scipy import stats
from paths import resolve_artifact_dir

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data")
SYNC_DATA_DIR = DATA_DIR / "synchronized"


def run_generator(script_name, seed, timeout=3600):
    script_path = Path(__file__).parent / script_name
    print(f"  Running {script_name} with seed {seed}...")
    start = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path), str(seed)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=Path(__file__).parent,
    )
    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr[:500]}")
        return False
    print(f"    Completed in {elapsed:.1f}s")
    return True


def count_swaps_from_steps(steps_array):
    return [len(exp) for exp in steps_array]


def load_baseline_data(seed):
    original = {}
    synchronized = {}

    for alg in ['bubble', 'selection', 'insertion']:
        orig_path = DATA_DIR / f'{alg}_sort_sorting_steps_100exps_seed{seed}.npy'
        sync_path = SYNC_DATA_DIR / f'{alg}_sort_sorting_steps_100exps_seed{seed}.npy'

        if orig_path.exists():
            original[alg] = np.load(orig_path, allow_pickle=True)
        if sync_path.exists():
            synchronized[alg] = np.load(sync_path, allow_pickle=True)

    return original, synchronized


def load_frozen_data(seed, frozen_count=0):
    original = {}
    synchronized = {}

    for alg in ['bubble', 'selection', 'insertion']:
        orig_path = DATA_DIR / f'{alg}_sort_sorting_with_{frozen_count}frozen_steps_100exps_seed{seed}.npy'
        sync_path = SYNC_DATA_DIR / f'{alg}_sort_sorting_with_{frozen_count}frozen_steps_100exps_seed{seed}.npy'

        if orig_path.exists():
            original[alg] = np.load(orig_path, allow_pickle=True)
        if sync_path.exists():
            synchronized[alg] = np.load(sync_path, allow_pickle=True)

    return original, synchronized


def compare_swap_counts(original_data, synchronized_data, label):
    print(f"\n{label}")
    print("-" * 70)
    print(f"{'Algorithm':<15} {'Original Swaps':>18} {'Synced Swaps':>18} {'Delta':>10} {'% Diff':>10}")
    print("-" * 70)

    results = {}
    early_terminations = 0
    total_experiments = 0

    for alg in ['bubble', 'selection', 'insertion']:
        if alg not in original_data or alg not in synchronized_data:
            continue

        orig_swaps = count_swaps_from_steps(original_data[alg])
        sync_swaps = count_swaps_from_steps(synchronized_data[alg])

        orig_mean = np.mean(orig_swaps)
        orig_std = np.std(orig_swaps)
        sync_mean = np.mean(sync_swaps)
        sync_std = np.std(sync_swaps)

        delta = sync_mean - orig_mean
        pct_diff = (delta / orig_mean * 100) if orig_mean > 0 else 0

        for o, s in zip(orig_swaps, sync_swaps):
            total_experiments += 1
            if o < s:
                early_terminations += 1

        t_stat, p_value = stats.ttest_rel(orig_swaps, sync_swaps)

        results[alg] = {
            'orig_mean': orig_mean,
            'orig_std': orig_std,
            'sync_mean': sync_mean,
            'sync_std': sync_std,
            'delta': delta,
            'pct_diff': pct_diff,
            't_stat': t_stat,
            'p_value': p_value,
        }

        print(f"{alg.capitalize():<15} {orig_mean:>10.1f} +/- {orig_std:>4.1f} {sync_mean:>10.1f} +/- {sync_std:>4.1f} {delta:>+10.1f} {pct_diff:>+9.2f}%")

    print("-" * 70)
    if total_experiments > 0:
        print(f"Early terminations detected: {early_terminations}/{total_experiments} "
              f"(original terminated before synced)")

    return results, early_terminations, total_experiments


def print_statistical_significance(results, label):
    print(f"\nSTATISTICAL SIGNIFICANCE - {label}")
    print("-" * 70)

    for alg, r in results.items():
        sig = "SIGNIFICANT" if r['p_value'] < 0.05 else "not significant"
        print(f"Paired t-test ({alg}): t={r['t_stat']:.3f}, p={r['p_value']:.4f} ({sig})")


def main(argv):
    skip_generate = "--skip-generate" in argv
    baseline_only = "--baseline-only" in argv

    numeric_args = [a for a in argv if not a.startswith("--")]
    seed = int(numeric_args[0]) if numeric_args else 42

    print("=" * 70)
    print("RACE CONDITION IMPACT ANALYSIS")
    print(f"Seed: {seed} | Experiments: 100 per condition")
    if skip_generate:
        print("Mode: Analysis only (--skip-generate)")
    if baseline_only:
        print("Mode: Baseline only (--baseline-only)")
    print("=" * 70)

    if not skip_generate:
        print("\n[1/2] Running original baseline generator...")
        if not run_generator("generate_baseline_data.py", seed):
            print("Failed to run original baseline generator")
            return 1

        print("\n[2/2] Running synchronized baseline generator...")
        if not run_generator("generate_baseline_data_synchronized.py", seed):
            print("Failed to run synchronized baseline generator")
            return 1

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    baseline_results = None
    baseline_early = 0
    baseline_total = 0

    orig_baseline, sync_baseline = load_baseline_data(seed)
    if orig_baseline and sync_baseline:
        baseline_results, baseline_early, baseline_total = compare_swap_counts(
            orig_baseline, sync_baseline, "BASELINE DATA (generate_baseline_data)"
        )
        print_statistical_significance(baseline_results, "BASELINE")
    else:
        print("\nNo baseline data found. Run without --skip-generate first.")

    frozen_results = None
    frozen_early = 0
    frozen_total = 0

    if not baseline_only:
        orig_frozen, sync_frozen = load_frozen_data(seed, frozen_count=0)
        if orig_frozen and sync_frozen:
            frozen_results, frozen_early, frozen_total = compare_swap_counts(
                orig_frozen, sync_frozen, "FROZEN DATA (generate_frozen_data, 0 frozen)"
            )
            print_statistical_significance(frozen_results, "FROZEN (0 frozen)")

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)

    total_early = baseline_early + frozen_early
    total_exp = baseline_total + frozen_total

    if total_exp > 0:
        early_pct = total_early / total_exp * 100
        print(f"Early terminations: {total_early}/{total_exp} experiments ({early_pct:.1f}%)")

        any_significant = False
        if baseline_results:
            for alg, r in baseline_results.items():
                if r['p_value'] < 0.05:
                    any_significant = True
                    break

        if any_significant:
            print("The race conditions cause STATISTICALLY SIGNIFICANT differences in swap counts.")
            print("Statistical conclusions MAY change when using synchronized version.")
        else:
            print("The race conditions do NOT cause statistically significant differences.")
            print("Statistical conclusions are robust to these race conditions.")
    else:
        print("No data to compare. Check that generators ran successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
