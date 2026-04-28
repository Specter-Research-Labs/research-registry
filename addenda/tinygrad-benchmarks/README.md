# tinygrad-benchmarks

Phase-0 benchmark program for history-mined tinygrad tasks.

This addendum exists to answer one narrow question: given a concrete tinygrad change request mined
from git history or issue threads, can a model produce a patch that passes the pinned acceptance
check in a sealed, reproducible evaluation tree?

The benchmark is intentionally split into three surfaces:

- the public benchmark index, which contains only what the evaluator needs
- the maintainer-only private ledger, which can retain gold commits, gold patches, and other
  leakage-sensitive provenance for comparison against real historical solutions
- the model-visible prompt packets, which omit repo provenance and mining metadata before the task
  is shown to a model

## Workflows

`mine-history`
curate candidate tasks from tinygrad history, issue threads, and PR discussions. The output should
separate public task rows from maintainer-only provenance so the benchmark remains usable without
exposing the solution trail.

The miner now scores accepted candidates and ranks them by quality before truncation. That matters:
`--max-candidates 50` should mean “best 50 reviewed-looking fixes in the scanned range,” not
“first 50 commits that happened to pass a weak filter.”

For tinygrad phase-0, the miner should usually be scoped to `tinygrad/` plus benchmark-suitable
`test/` suites with explicit excluded prefixes for external, model-heavy, speed, web, and
hardware-specific coverage.

`curate`
normalize the mined rows into a frozen index with deterministic identifiers, stable task metadata,
explicit acceptance commands, and a strict public/private provenance split.

`export-prompts`
render model-facing task packets from the curated index. This surface omits `repo_remote`,
`repo_commit`, source refs, and mining metadata so prompt packets stay smaller and less leaky than
the evaluator index.

`freeze-split`
freeze public-dev and heldout splits from the curated index so repeated runs select the same task
set from the same manifest and seed.

`run`
execute candidate patches in a sealed working tree rooted at the pinned commit. The evaluation
workspace should not expose `.git` history, should not fetch live upstream state, and should assume
the model process has no network access.

`score`
reduce attempt-level outputs into run-level metrics and summary artifacts.

`compare-gold`
compare run outputs against the maintainer-only gold ledger to measure how closely the benchmarked
patch matches the historical resolution, not just whether it passes.

## Validate

```bash
cd addenda/tinygrad-benchmarks
nix develop
uv run ruff check .
uv run ty check
uv run pytest
uv run python -m tinygrad_benchmarks --help
```

If you use direnv, `direnv allow` from `addenda/tinygrad-benchmarks/` is equivalent.

## Example Flow

Mine candidate rows from a local tinygrad checkout:

```bash
cd addenda/tinygrad-benchmarks
uv run tinygrad-benchmarks mine-history \
  --repo /path/to/tinygrad \
  --repo-remote https://github.com/tinygrad/tinygrad \
  --out ../../tmp/tinygrad-benchmarks/mined-seeds.jsonl \
  --rev-range HEAD~500..HEAD \
  --max-source-files 2 \
  --max-test-files 2 \
  --max-files 6 \
  --max-patch-lines 120 \
  --include-source-prefix tinygrad \
  --include-test-prefix test \
  --exclude-path-prefix extra \
  --exclude-path-prefix examples \
  --exclude-path-prefix docs \
  --exclude-path-prefix test/external \
  --exclude-path-prefix test/models \
  --exclude-path-prefix test/speed \
  --exclude-path-prefix test/web \
  --exclude-path-prefix test/amd \
  --exclude-path-prefix test/device \
  --exclude-path-prefix test/mockgpu \
  --progress-every 25
```

Split the mined seeds into a public index plus a private gold ledger:

```bash
uv run tinygrad-benchmarks curate \
  --input ../../tmp/tinygrad-benchmarks/mined-seeds.jsonl \
  --out ../../tmp/tinygrad-benchmarks/index.jsonl \
  --private-out ../../tmp/tinygrad-benchmarks/private-tasks.json
```

Export model-facing prompt packets from the public index:

```bash
uv run tinygrad-benchmarks export-prompts \
  --index ../../tmp/tinygrad-benchmarks/index.jsonl \
  --out ../../tmp/tinygrad-benchmarks/prompts.jsonl
```

Freeze the split:

```bash
uv run tinygrad-benchmarks freeze-split \
  --index ../../tmp/tinygrad-benchmarks/index.jsonl \
  --out-dir ../../tmp/tinygrad-benchmarks/frozen-split-v1 \
  --seed 7 \
  --heldout-fraction 0.2
```

Run submissions against a local repo source without exposing `.git`:

```bash
cat > ../../tmp/tinygrad-benchmarks/repo-map.json <<'JSON'
{
  "https://github.com/tinygrad/tinygrad": "/path/to/tinygrad"
}
JSON

uv run tinygrad-benchmarks run \
  --index ../../tmp/tinygrad-benchmarks/frozen-split-v1/public_dev.jsonl \
  --submissions ../../tmp/tinygrad-benchmarks/submissions.jsonl \
  --repo-map ../../tmp/tinygrad-benchmarks/repo-map.json \
  --out-dir ../../tmp/tinygrad-benchmarks/run-smoke
```

Score the run and compare it to the private ledger:

```bash
uv run tinygrad-benchmarks score \
  --attempts ../../tmp/tinygrad-benchmarks/run-smoke/attempts.jsonl

uv run tinygrad-benchmarks compare-gold \
  --attempts ../../tmp/tinygrad-benchmarks/run-smoke/attempts.jsonl \
  --private ../../tmp/tinygrad-benchmarks/private-tasks.json \
  --out-dir ../../tmp/tinygrad-benchmarks/run-smoke/gold-compare
```

## Artifact Split

Public artifacts:

- mined-and-curated `index.jsonl`
- `prompts.jsonl` model-visible packets with stripped provenance
- frozen split artifacts
- submission attempts and run summaries
- candidate quality metadata and review priority in curated rows

Maintainer-only artifacts:

- `private-tasks.json`
- gold commits
- gold patches
- stripped commit metadata, private source refs, and leakage notes

## Phase-0 Shape

- tasks are mined from real tinygrad history, not invented prompts
- every row pins a starting commit, target paths, acceptance command, and environment assumptions
- phase-0 mining only accepts benchmark-suitable tests; external, model, web, speed, and
  hardware-specific suites are filtered out
- selection is deterministic from a frozen manifest
- the public index stays free of gold solution material
- mined task statements are synthesized from file and test paths instead of raw commit subjects
- model-visible prompt packets omit repo provenance and mining metadata
- the evaluator runs in a sealed tree without `.git`
- the clean-run expectation is explicit: no network, no hidden fetches, no live upstream drift

## Start Here

The workflow should be read in this order:

1. mine history for candidate tasks and gold provenance
2. curate a public index plus private ledger
3. export model-visible prompt packets
4. freeze the split
5. run candidate patches
6. score the attempts
7. compare against the gold ledger

## Non-Goals For Phase-0

- no open-ended benchmark marketplace
- no live task discovery during evaluation
- no reliance on mutable upstream branches
- no GPU or throughput ranking yet
- no second harness for other repos until tinygrad is stable
