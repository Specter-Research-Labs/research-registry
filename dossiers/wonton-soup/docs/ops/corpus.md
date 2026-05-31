# Corpus

Corpus artifacts keep theorem selections reproducible without committing large
datasets.

## Guarantees

- deterministic builds from pinned provenance and stable `build_id`
- deterministic selection by `--offset`, `--limit`, `--sample`, and `--seed`
- Gate A validation
- Gate B capability sweeps

## Storage

Corpus roots resolve through `runtime_paths.resolve_corpora_root()`.

- default: `dossiers/wonton-soup/artifacts/corpora/`
- `SPCTR_LOCAL_ARTIFACT_ROOT`: `$SPCTR_LOCAL_ARTIFACT_ROOT/wonton-soup/artifacts/corpora/`
- `SPECTER_ARTIFACT_ROOT`: staged locally under `SPECTER_RUNTIME_ROOT` or
  `tmp/runtime-artifacts/wonton-soup/corpora/`, then synced to
  `$SPECTER_ARTIFACT_ROOT/wonton-soup/corpora/`

Workspace checkouts under `research-registry-workspaces/` resolve the default
path to the sibling main checkout. Commands stay local unless `--sync` is set.

## Layout

Base build:

- `<root>/<backend>/<corpus_id>/<build_id>/manifest.json`
- `<root>/<backend>/<corpus_id>/<build_id>/items.jsonl`
- `<root>/<backend>/<corpus_id>/<build_id>/validation.jsonl`
- `<root>/<backend>/<corpus_id>/<build_id>/capability.jsonl`
- `<root>/<backend>/<corpus_id>/CURRENT`

Derived build:

- `<build_dir>/derived/<kind>/<derived_build_id>/manifest.json`
- `<build_dir>/derived/<kind>/<derived_build_id>/items.jsonl`
- `<build_dir>/derived/<kind>/CURRENT`

## Ref Syntax

```text
<backend>:<corpus_id>[@<build_id>][#<derived_path>]
```

Examples:

- `lean:mathlib4`
- `lean:mathlib4@<build_id>#valid`
- `lean:mathlib4@<build_id>#feasible`

## Commands

Build a Lean/mathlib slice:

```bash
uv run python wonton.py corpus build-lean-mathlib \
  --corpus-id mathlib4 \
  --limit 500
```

Validate it:

```bash
uv run python wonton.py corpus validate \
  --ref lean:<corpus_id>@<build_id>
```

Sweep Lean capability:

```bash
uv run python wonton.py corpus sweep-lean-capability \
  --ref lean:<corpus_id>@<build_id>#valid \
  --provider reprover --provider deepseek \
  --budget deep \
  --basin-seeds 5
```

Resume an incomplete sweep with `--resume`.

External backend sweeps:

```bash
uv run python wonton.py corpus sweep-tptp-capability \
  --ref tptp:<corpus_id>@<build_id> \
  --timeout 10

uv run python wonton.py corpus sweep-smtlib-capability \
  --ref smtlib:<corpus_id>@<build_id> \
  --timeout 10
```

## Manifest

`manifest.json` is the source of truth. It records format version, backend,
corpus id, build id, source provenance, build config, item count, item file,
item hash, item-id scheme, and split scheme.

`items.jsonl` is sorted by `item_id`. Lean items carry
`payload.statement`, a declaration string with `{name}` bound at run time.
