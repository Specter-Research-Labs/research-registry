# tinygrad-benchmarks

History-mined benchmark tasks for tinygrad.

The benchmark asks one question: given a small real tinygrad change request,
can a model write a patch that passes the pinned check in a sealed evaluation
tree?

The public benchmark keeps the task, target paths, and acceptance command. The
private ledger keeps gold commits, gold patches, and leakage notes.

Read `docs/benchmark-card.md` for the row contract and
`docs/task-selection.md` for phase-0 task rules.

## Check

```bash
cd addenda/tinygrad-benchmarks
nix develop
uv run ruff check .
uv run ty check .
uv run python -m pytest
uv run python -m tinygrad_benchmarks --help
```

`direnv allow` enters the same shell.

## Workflow

`mine-history`
: Find candidate tasks from tinygrad commits, issues, and PRs. The miner scores
  accepted candidates before truncation, so `--max-candidates 50` means the 50
  strongest reviewed-looking tasks in the scanned range.

`curate`
: Write a public index and a maintainer-only gold ledger.

`export-prompts`
: Render model-facing packets from the public index. Prompt packets omit repo
  URLs, commit ids, source refs, and mining metadata.

`freeze-split`
: Freeze public-dev and heldout splits from the public index.

`run`
: Apply candidate patches inside a working tree rooted at the pinned commit.
  The evaluation tree strips `.git`, does not fetch live upstream state, and
  assumes the model process has no network.

`score`
: Reduce attempt records into run metrics.

`compare-gold`
: Compare model patches against the private historical solution ledger.

## Example

Mine candidate rows from a local tinygrad checkout:

```bash
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

Create the public index and private ledger:

```bash
uv run tinygrad-benchmarks curate \
  --input ../../tmp/tinygrad-benchmarks/mined-seeds.jsonl \
  --out ../../tmp/tinygrad-benchmarks/index.jsonl \
  --private-out ../../tmp/tinygrad-benchmarks/private-tasks.json
```

Export prompts and freeze the split:

```bash
uv run tinygrad-benchmarks export-prompts \
  --index ../../tmp/tinygrad-benchmarks/index.jsonl \
  --out ../../tmp/tinygrad-benchmarks/prompts.jsonl

uv run tinygrad-benchmarks freeze-split \
  --index ../../tmp/tinygrad-benchmarks/index.jsonl \
  --out-dir ../../tmp/tinygrad-benchmarks/frozen-split-v1 \
  --seed 7 \
  --heldout-fraction 0.2
```

Run submissions against a local repo source:

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

Score and compare to the private ledger:

```bash
uv run tinygrad-benchmarks score \
  --attempts ../../tmp/tinygrad-benchmarks/run-smoke/attempts.jsonl

uv run tinygrad-benchmarks compare-gold \
  --attempts ../../tmp/tinygrad-benchmarks/run-smoke/attempts.jsonl \
  --private ../../tmp/tinygrad-benchmarks/private-tasks.json \
  --out-dir ../../tmp/tinygrad-benchmarks/run-smoke/gold-compare
```

## Artifacts

Public:

- `index.jsonl`
- `prompts.jsonl`
- frozen split manifests
- attempt records and run summaries
- candidate quality metadata

Private:

- `private-tasks.json`
- gold commits and patches
- stripped commit metadata
- source refs and leakage notes

Phase 0 is CPU-only. External, model-heavy, speed, web, GPU, and
hardware-specific tests do not enter the benchmark.
