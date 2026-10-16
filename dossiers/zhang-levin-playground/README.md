---
summary: "Audits and extends the Zhang and Levin sorting-cell model, with the copied original sources, the paper-facing scripts and the current findings."
---

# Zhang-Levin Playground

Audits and extends the Zhang & Levin sorting-cell model from [arXiv:2401.05375](https://arxiv.org/abs/2401.05375). The current paper-facing path is organized around explicit semantics, operator classes, and reproducible archives under `paper/results/`.

## Original Surfaces

The following files are literal or near-literal copies from the original repository:

### Core cell implementations
```text
modules/multithread/BubbleSortCell.py
modules/multithread/SelectionSortCell.py
modules/multithread/InsertionSortCell.py
modules/multithread/MergeSortCell.py
modules/multithread/CellGroup.py
modules/multithread/__init__.py
```

### Core infrastructure with added instrumentation
```text
modules/multithread/MultiThreadCell.py
modules/multithread/StatusProbe.py
```

### Original-generation scripts preserved for reproduction
```text
generate_baseline_data.py
generate_frozen_data.py
generate_chimeric_data.py
generate_group_id_data.py
```

These preserved-original scripts keep the original mechanics, including race-condition-prone completion detection. They are useful for reproducing the published model, but they are not the only paper-facing path for this dossier.

## Current Paper Path

The paper now leans on a smaller set of reproducible, audited surfaces:

- `paper/compute_fig1_temporal_clustering.py`
  Writes `paper/results/fig1_temporal_vs_clustering.json` with seeded per-trial rows.
- `paper/run_clustering_ablation.py`
  Writes `paper/results/fig2_clustering_ablation.json` with seeded per-trial rows.
- `exp25_selection_factorization.py`
  Factorizes 1D Selection into action range and blocked-target behavior.
- `exp26_substrate_matched_baselines.py`
  Separates substrate effects from policy/operator effects.
- `exp27_timing_interventions.py`
  Tests whether synthetic waiting gates transfer clustering beyond native Insertion.
- `exp28_2d_canonical.py`
  Writes the canonical raw-trial archive for the paper's 2D section.
- `paper/aggregate_fig3_2d.py`
  Regenerates `fig3_2d_success_heatmaps.json` and `fig3b_alt_orderings.json` from that raw 2D archive.
- `paper/clustering_null.py`
  Scores a per-swap clustering trajectory against a label-permutation null; every clustering figure reports the excess over it.
- `paper/make_figures.py`
  Regenerates all paper figures from the compact result files in `paper/results/`. The Exp10 and Exp14 tables in `main.tex` come from an earlier archive that was not retained.

Legacy 2D scripts such as `exp19_2d_sorting.py`, `exp22_2d_deeper.py`, and `exp23_2d_alt_ordering.py` remain in the repo as exploratory or historical surfaces. They are no longer the intended provenance path for Figure 3.

## Current Findings

Clustering is reported as the excess of the trajectory maximum of C(t) over a 200-shuffle label-permutation null on the same per-swap trajectory, because the raw maximum sits about 0.11 to 0.14 above the random-mixing baseline even for identical rules.

1. Semantics and operator classes matter. Published 1D Selection is not an adjacent-only local rule; it performs direct transpositions toward an ideal target.
2. Mixtures with a waiting gate cluster above the null and ungated adjacent mixtures sit at it. In Figure 1 (n=30, 50 trials per pair) the four Insertion pairs have excess `+0.051` to `+0.090`, the three Selection pairs without Insertion `+0.026` to `+0.031` at separations of only `0.04` to `0.05`, and Bubble/Gnome/Shaker pairs about zero. Pearson r between separation and excess is `0.94` across all ten pairs and `0.43` without Insertion pairs, so the correlation is carried by the Insertion family.
3. Removing Insertion's waiting gate returns clustering to the null. Figure 2 (n=50, 20 trials, C(t) recorded after every swap) gives excess `+0.079` for Bubble+Insertion, `-0.007` for Bubble+InsertionNoWait and `+0.011` for Bubble+Gnome. The earlier version sampled C(t) on wall-clock time, which inflated the gated condition.
4. Transplanting the gate reproduces the clustering of native Insertion. In the Exp27 aggregate (30 trials per pair) Bubble+DelayedBubble reaches excess `+0.064` at separation `0.114` against `+0.017` and `0.024` for Bubble+BubbleClone, and Gnome+DelayedGnome reaches `+0.052` at `0.107` against `+0.006` and `0.025` for Gnome+GnomeClone, beside Bubble+Insertion at `+0.061`. This is a causal test of the efficiency hypothesis in Zhang et al.
5. Under immovable frozen indices only long-range Selection with frozen-target rerouting can reach the sorted state (Exp25). Adjacent moves cannot carry values across a frozen index and a stubborn cell waits forever on a frozen target, so this, the Exp10 rerouting ablation and the Exp14 cell-view/traditional agreement follow from the rule definitions and serve as consistency checks.
6. With frozen cells left without threads, as in the original code, threaded and sequential cell-view schedules agree in outcome and do the same work (Exp26 compare-count ratios `0.97` to `1.02`). The earlier `35.9x`/`97.8x` Selection work ratios came from frozen Selection threads spinning without acting. All cell threads share one lock, so the threaded substrate is a serialized random scheduler.
7. K_state sits 1.7 to 2.6 units below log10(n_active!) for every algorithm that finishes (long-range rerouting `30.45`, `26.14`, `22.00`, `18.01` at frozen 0/3/6/9 against `32.42`, `28.04`, `23.79`, `19.71`), so it is set mostly by reachable state-space size.
8. The 2D section is still narrower than the 1D story, but the intended paper path is now a canonical raw-trial archive plus aggregation step rather than mixed summary files with unclear provenance.

Not yet followed up from the original paper: duplicate values (`exp17_duplicate_values.py`, final-state aggregation), opposite-direction chimeras, the three-type mix, the efficiency comparisons, and the rise of delayed gratification with frozen count. Exp10, Exp14, `paper/compute_dip_stats.py`, `exp1_frozen_cells.py` and `exp16_movable_frozen.py` still start threads for frozen cells.

## Semantics Notes

Several claims depend qualitatively on semantics that are easy to blur together:

- `movable` vs `immovable` frozen cells
- adjacent swaps vs arbitrary transpositions
- local comparison order vs explicit ideal-position targeting
- threaded cell-view execution vs sequential execution of the same local policy
- shell, row-major, and serpentine 2D target orders

If a result does not state these semantics explicitly, treat it as underspecified.

## Key Commands

From `dossiers/zhang-levin-playground/`:

### Figure 1
```bash
uv run python paper/compute_fig1_temporal_clustering.py
```

### Figure 2
```bash
uv run python paper/run_clustering_ablation.py
```

### Exp25: Selection factorization
```bash
for s in 40 41 42; do
  uv run python exp25_selection_factorization.py \
    --seed "$s" \
    --n-trials 10 \
    --timeout 5 \
    --semantics immovable \
    --out "paper/results/exp25_seed${s}_n30_t5_immovable.json"
done

uv run python paper/aggregate_exp25_selection_factorization.py --inputs \
  paper/results/exp25_seed40_n30_t5_immovable.json \
  paper/results/exp25_seed41_n30_t5_immovable.json \
  paper/results/exp25_seed42_n30_t5_immovable.json \
  --out paper/results/exp25_selection_factorization_aggregate_n30_t5_immovable.json

for s in 40 41 42; do
  uv run python exp25_selection_factorization.py \
    --seed "$s" \
    --n-trials 5 \
    --timeout 5 \
    --semantics movable \
    --out "paper/results/exp25_seed${s}_n30_t5_movable.json"
done

uv run python paper/aggregate_exp25_selection_factorization.py --inputs \
  paper/results/exp25_seed40_n30_t5_movable.json \
  paper/results/exp25_seed41_n30_t5_movable.json \
  paper/results/exp25_seed42_n30_t5_movable.json \
  --out paper/results/exp25_selection_factorization_aggregate_n30_t5_movable.json

uv run python paper/compute_k.py
```

### Exp26: matched substrate baselines
```bash
for s in 40 41 42; do
  uv run python exp26_substrate_matched_baselines.py \
    --seed "$s" \
    --n-trials 3 \
    --timeout 5 \
    --max-compare-and-swap 200000 \
    --frozen-counts 1,3 \
    --algorithms Bubble,Insertion,Selection \
    --out "paper/results/exp26_original_trio_seed${s}_n30_t3_frozen1_3_budget200k.json"
done

uv run python paper/aggregate_exp26_substrate_matched_baselines.py --inputs \
  paper/results/exp26_original_trio_seed40_n30_t3_frozen1_3_budget200k.json \
  paper/results/exp26_original_trio_seed41_n30_t3_frozen1_3_budget200k.json \
  paper/results/exp26_original_trio_seed42_n30_t3_frozen1_3_budget200k.json \
  --out paper/results/exp26_original_trio_aggregate_n30_t3_frozen1_3_budget200k.json
```

### Exp27: timing-gate transfer
```bash
for s in 40 41 42; do
  uv run python exp27_timing_interventions.py \
    --base-seed "$s" \
    --n-trials 10 \
    --out "paper/results/exp27_seed${s}_n50_t10.json"
done

uv run python paper/aggregate_exp27_timing_interventions.py --inputs \
  paper/results/exp27_seed40_n50_t10.json \
  paper/results/exp27_seed41_n50_t10.json \
  paper/results/exp27_seed42_n50_t10.json \
  --out paper/results/exp27_timing_interventions_aggregate.json
```

### Exp28: canonical 2D archive
```bash
uv run python exp28_2d_canonical.py \
  --out paper/results/exp28_2d_canonical_trials.json

uv run python paper/aggregate_fig3_2d.py \
  --input paper/results/exp28_2d_canonical_trials.json \
  --heatmap-out paper/results/fig3_2d_success_heatmaps.json \
  --alt-out paper/results/fig3b_alt_orderings.json
```

### Regenerate paper figures
```bash
uv run python paper/make_figures.py
```

## Experiment Map

### Core original and follow-up 1D experiments
```text
exp1_frozen_cells.py
exp10_ablation_goal_adjustment.py
exp11_robustness_curve.py
exp14_cellview_vs_traditional.py
exp15_delay_gratification.py
exp16_movable_frozen.py
exp17_duplicate_values.py
exp18_nudge_unfreezing.py
exp25_selection_factorization.py
exp26_substrate_matched_baselines.py
exp27_timing_interventions.py
```

### 2D experiments
```text
exp19_2d_sorting.py              # legacy exploratory surface
exp22_2d_deeper.py               # legacy exploratory surface
exp23_2d_alt_ordering.py         # legacy exploratory surface
exp24_pattern_guided_2d.py       # exploratory extension
exp28_2d_canonical.py            # canonical paper-facing 2D archive
paper/exp2d_core.py              # canonical 2D engine
paper/aggregate_fig3_2d.py       # canonical Figure 3 aggregation
```

### Diagnostics and secondary metrics
```text
paper/compute_dip_stats.py
paper/compute_fig5_h1.py
paper/compute_directed_flow.py
paper/compute_k.py               # matched state-space K on the Exp25 immovable factorization
analysis/persistent_homology.py
```

## Data

The original experimental data from Zhang & Levin is not tracked in this repository. It can be regenerated from their published codebase at [github.com/Zhangtaining/cell_research](https://github.com/Zhangtaining/cell_research) (companion to [arXiv:2401.05375](https://arxiv.org/abs/2401.05375)). To populate a local `data/` directory:

```bash
# Clone the original repo and run their generation scripts,
# or symlink an existing copy:
ln -s /path/to/your/zhang-levin-data data
```

The generation scripts in this dossier (`generate_baseline_data.py`, `generate_frozen_data.py`, etc.) can also reproduce the data given sufficient compute.

## Outputs

Paper-facing outputs live in `paper/results/` and `paper/figures/`. For the central claims, prefer committed JSON archives over stdout logs.

- Figure and table inputs: `paper/results/*.json`
- Rendered figures: `paper/figures/*.pdf` (tracked) and `paper/figures/*.png` (ignored)
- Rendered manuscript: build locally from `paper/main.tex`; `paper/main.pdf` is ignored

Result files keep per-trial measurements and summaries only, without full state trajectories. Some exploratory scripts still print summaries to stdout, but if a result matters for the paper it should have a JSON artifact under `paper/results/`.
