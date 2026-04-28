Audits and extends the Zang & Levin sorting-cell model from [arXiv:2401.05375](https://arxiv.org/abs/2401.05375). The current paper-facing path is organized around explicit semantics, operator classes, and reproducible archives under `paper/results/`.

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
- `paper/make_figures.py`
  Regenerates all paper figures from committed result JSON files.

Legacy 2D scripts such as `exp19_2d_sorting.py`, `exp22_2d_deeper.py`, and `exp23_2d_alt_ordering.py` remain in the repo as exploratory or historical surfaces. They are no longer the intended provenance path for Figure 3.

## Current Findings

The current paper is narrower and more defensible than the earlier draft.

1. Semantics and operator classes matter. Published 1D Selection is not an adjacent-only local rule; it performs direct transpositions toward an ideal target.
2. Temporal separation is positively associated with clustering, but the signal is concentrated in Insertion-containing mixtures. In the archived Figure 1 rerun, `r = 0.781722` across all ten pairs, about `0.054` after removing Insertion pairs, and about `0.975` within Insertion pairs.
3. Removing Insertion's waiting gate sharply reduces clustering without eliminating it. The current seeded Figure 2 archive gives mean clustering increases of `0.166` for Bubble+Insertion, `0.091` for Bubble+InsertionNoWait, and `0.073` for Bubble+Gnome.
4. The timing mechanism now transfers beyond native Insertion. In the Exp27 aggregate, Bubble+DelayedBubble reaches `ΔC = 0.175510` with separation `0.111468`, versus Bubble+BubbleClone at `ΔC = 0.155102` and `0.027056`; Gnome+DelayedGnome reaches `ΔC = 0.166667` with separation `0.105616`, versus Gnome+GnomeClone at `ΔC = 0.125850` and `0.042849`.
5. Under immovable frozen-index semantics, Selection robustness depends on both long-range action and frozen-target rerouting. Exp25 makes that decomposition explicit.
6. Under matched frozen semantics, cell-view execution does not add robustness relative to centralized baselines. Exp14 gives the negative result against traditional baselines, and Exp26 shows that matched threaded vs sequential cell-view runs agree on success while differing mainly in work cost.
7. The 2D section is still narrower than the 1D story, but the intended paper path is now a canonical raw-trial archive plus aggregation step rather than mixed summary files with unclear provenance.

## Semantics Notes

Several claims depend qualitatively on semantics that are easy to blur together:

- `movable` vs `immovable` frozen cells
- adjacent swaps vs arbitrary transpositions
- local comparison order vs explicit ideal-position targeting
- threaded cell-view execution vs sequential execution of the same local policy
- shell, row-major, and serpentine 2D target orders

If a result does not state these semantics explicitly, treat it as underspecified.

## Key Commands

From `dossiers/zang-levin-playground/`:

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

The original experimental data from Zang & Levin is not tracked in this repository. It can be regenerated from their published codebase at [github.com/gzangs/sorting-network](https://github.com/gzangs/sorting-network) (companion to [arXiv:2401.05375](https://arxiv.org/abs/2401.05375)). To populate a local `data/` directory:

```bash
# Clone the original repo and run their generation scripts,
# or symlink an existing copy:
ln -s /path/to/your/zang-levin-data data
```

The generation scripts in this dossier (`generate_baseline_data.py`, `generate_frozen_data.py`, etc.) can also reproduce the data given sufficient compute.

## Outputs

Paper-facing outputs live in `paper/results/` and `paper/figures/`. For the central claims, prefer committed JSON archives over stdout logs.

- Figure and table inputs: `paper/results/*.json`
- Rendered figures: `paper/figures/*.pdf` and `paper/figures/*.png`
- Rendered manuscript: `paper/main.pdf`

Some exploratory scripts still print summaries to stdout, but if a result matters for the paper it should have a committed JSON artifact under `paper/results/`.
