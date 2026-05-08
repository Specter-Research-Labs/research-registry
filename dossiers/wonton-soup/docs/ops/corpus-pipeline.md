# Corpus Pipeline

Uses artifact-backed corpora so runs remain reproducible months later while keeping
large datasets out of git.

Core guarantees:

- deterministic corpus builds (pinned provenance + stable `build_id`)
- deterministic selection (`--offset` / `--limit` / `--sample --seed`)
- Gate A validation (build correctness)
- Gate B capability sweeps (feasible-by-design slices)

## Artifact Root

Corpus artifacts resolve via `runtime_paths.resolve_corpora_root()`.

- If no machine-local override is configured:
  - active path: `dossiers/wonton-soup/artifacts/corpora/` (gitignored)
- If `SPCTR_LOCAL_ARTIFACT_ROOT` is set:
  - active path: `$SPCTR_LOCAL_ARTIFACT_ROOT/wonton-soup/artifacts/corpora/`
- If `SPECTER_ARTIFACT_ROOT` is set:
  - active local staging path: `$SPECTER_RUNTIME_ROOT/wonton-soup/corpora/` when `SPECTER_RUNTIME_ROOT` is set, otherwise `tmp/runtime-artifacts/wonton-soup/corpora/`
  - remote target root: `$SPECTER_ARTIFACT_ROOT/wonton-soup/corpora/`

Checkouts under `research-registry-workspaces/` resolve the unset-env local path
to the sibling main `research-registry/dossiers` tree. Corpus commands keep
outputs local by default; use `--sync` when you want staged outputs copied to
the remote target.

## Directory Layout

Base build:

- `<root>/<backend>/<corpus_id>/<build_id>/manifest.json`
- `<root>/<backend>/<corpus_id>/<build_id>/items.jsonl`
- `<root>/<backend>/<corpus_id>/<build_id>/validation.jsonl` (optional; Gate A output)
- `<root>/<backend>/<corpus_id>/<build_id>/capability.jsonl` (optional; Gate B output)
- `<root>/<backend>/<corpus_id>/CURRENT` (active build id)

Derived build (for example `valid`, `feasible`):

- `<build_dir>/derived/<kind>/<derived_build_id>/manifest.json`
- `<build_dir>/derived/<kind>/<derived_build_id>/items.jsonl`
- `<build_dir>/derived/<kind>/CURRENT`

## Corpus Ref Syntax

Corpus refs use:

- `<backend>:<corpus_id>[@<build_id>][#<derived_path>]`

Examples:

- `lean:mathlib4` (uses `CURRENT`)
- `lean:mathlib4@<build_id>#valid`
- `lean:mathlib4@<build_id>#feasible`

Lean runs accept refs via `wonton.py lean run --corpus ...` (or `-c ...`).

## `manifest.json` (format_version = 1)

`manifest.json` is the source of truth for rebuild provenance and deterministic identity.

Required fields:

- `format_version` (`1`)
- `backend` (`lean|tptp|smtlib|coq`)
- `corpus_id`, `build_id`
- `created_at` (informational; excluded from build-id hashing)
- `provenance` (pinned source descriptors)
- `build_config` (builder params that affect contents)
- `counts.items_total`
- `items_file` (typically `items.jsonl`)
- `items_sha256`
- `item_id_scheme`
- `split_scheme`

## `items.jsonl`

`items.jsonl` is sorted lexicographically by `item_id`, one JSON object per line.

Lean payload v1 fields:

- `item_id`: stable Lean identifier (used as theorem name at run time)
- `payload.statement`: Lean declaration string containing `{name}` (bound at run time)

Other backends store backend-specific payloads (TPTP relpaths, SMT-LIB relpaths + logic, Coq
qualnames).

## Deterministic Selection

All backends use the same selection behavior:

- head mode: sort by `item_id`, then apply `--offset`, then `--limit`
- hash-sample mode: sort by `sha256(f"{seed}:{item_id}")`, then apply `--offset`, then `--sample`

When `--sample` is used, `--seed` is required.

## Build (Lean/mathlib)

Build from the pinned checkout under `lean_project/.lake/packages/mathlib`:

```
uv run python wonton.py corpus build-lean-mathlib --corpus-id mathlib4 --limit 500
```

## Gate A: Validation

Validation emits `validation.jsonl` and a derived-valid slice:

```
uv run python wonton.py corpus validate --ref lean:<corpus_id>@<build_id>
```

## Gate B: Capability Sweep (Lean)

Capability sweeps run basin analysis across provider x MCTS mode and emit `capability.jsonl` plus
a derived-feasible slice:

```
uv run python wonton.py corpus sweep-lean-capability \
  --ref lean:<corpus_id>@<build_id>#valid \
  --provider reprover --provider deepseek \
  --budget deep \
  --basin-seeds 5
```

`capability.jsonl` is keyed by `item_id`; an item is `reachable` if any matrix point meets the
configured reachability threshold.

### `--basin-seeds`

`--basin-seeds N` controls independent seeded runs per theorem per matrix point.
Runtime scales roughly linearly in `N`.

### Distributed MCTS (optional)

```
uv run python wonton.py corpus sweep-lean-capability \
  --ref lean:<corpus_id>@<build_id>#valid \
  --provider reprover \
  --mcts-mode distributed \
  --distributed-agents 8 \
  --distributed-inflight 64
```

### Resume

If a sweep root already exists and is incomplete, re-run with `--resume`.

## Gate B: Capability Sweep (External)

TPTP:

```
uv run python wonton.py corpus sweep-tptp-capability --ref tptp:<corpus_id>@<build_id> --timeout 10
```

SMT-LIB:

```
uv run python wonton.py corpus sweep-smtlib-capability --ref smtlib:<corpus_id>@<build_id> --timeout 10
uv run python wonton.py corpus sweep-smtlib-capability --ref smtlib:<corpus_id>@<build_id> --timeout 10 --require-proof
```

## Source Links

- mathlib4: https://github.com/leanprover-community/mathlib4
- miniF2F-lean4: https://github.com/yangky11/miniF2F-lean4
- DeepSeek-Prover-V1: https://huggingface.co/datasets/deepseek-ai/DeepSeek-Prover-V1
- DeepSeek-ProverBench: https://huggingface.co/datasets/deepseek-ai/DeepSeek-ProverBench
- SMT-LIB Zenodo record: https://zenodo.org/records/15493090
- TPTP: https://www.tptp.org/
