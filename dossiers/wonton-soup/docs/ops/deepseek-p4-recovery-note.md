# DeepSeek p4 Recovery Note

Current paper blocker: the March DeepSeek p4 basin run is incomplete.

## Original March run root

`$SPECTER_RUNTIME_ROOT/wonton-soup/logs/2026-03-02-followup-2026-03-extvol-r2/p4-basin-deep/provider=deepseek/seeds=50`

This run originally failed with partial results after 4 theorem basins.

## Completed theorem basins already present in the March run root

- `SubtractionMonoid_x2etoSubNegZeroMonoid_x2eeq_x5f1`
- `add_x5fleft_x5fiterate`
- `div_x5fdiv`
- `div_x5fdiv_x5fdiv_x5fcancel_x5fright`

## Remaining theorem basins to recover

- `div_x5feq_x5fof_x5feq_x5fmul_x27`
- `AddSemigroup_x2eto_x5fisAssociative`
- `div_x5feq_x5fdiv_x5fiff_x5fdiv_x5feq_x5fdiv`
- `add_x5feq_x5fzero_x5fiff_x5fneg_x5feq`
- `div_x5feq_x5fiff_x5feq_x5fmul_x27`
- `add_x5fzsmul`

## Recovery strategy

Use the DeepSeek model archive root:

`DEEPSEEK_ARTIFACT_ROOT=/path/to/specter-archive`

Run one theorem at a time under a fresh run id, for example:

```bash
cd dossiers/wonton-soup

DEEPSEEK_ARTIFACT_ROOT=/path/to/specter-archive \
uv run python wonton.py lean basin \
  --seeds 50 \
  --blind \
  -m research \
  -c lean:mathlib4#feasible \
  -p deepseek \
  -b standard \
  --workers 1 \
  --plain \
  --theorem <THEOREM_NAME> \
  --run-id 2026-04-18-deepseek-p4-single-retry/provider=deepseek/theorem=<THEOREM_NAME> \
  --no-sync
```

After a theorem completes, copy its theorem directory into the original March run root:

```bash
cp -R \
  "$SPECTER_RUNTIME_ROOT/wonton-soup/logs/2026-04-18-deepseek-p4-single-retry/provider=deepseek/theorem=<THEOREM_NAME>/<THEOREM_NAME>" \
  "$SPECTER_RUNTIME_ROOT/wonton-soup/logs/2026-03-02-followup-2026-03-extvol-r2/p4-basin-deep/provider=deepseek/seeds=50/"
```

`analysis/lake/extract_basin.py` extracts basin facts by scanning theorem subdirectories for `basin_analysis.json`, so copying the finished theorem directory into the March run root is sufficient for lake reconciliation.

## Current live probe

The first recovered theorem currently in flight is:

- theorem: `div_x5feq_x5fof_x5feq_x5fmul_x27`
- run id: `2026-04-18-deepseek-p4-single-retry/provider=deepseek/theorem=div_x5feq_x5fof_x5feq_x5fmul_x27`

At last check it had reached 5 / 50 seeds completed with 3 solved seeds and 3 unique structures.
