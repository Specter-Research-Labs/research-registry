# Lean REPL Setup

Setup and verification guide for the Lean environment used by wonton-soup.

## Toolchain Contract

- Lean version pinned in `$LEAN_PROJECT_PATH/lean-toolchain` (currently `4.25.0`)
- `leantree` is pinned as a Git dependency in `pyproject.toml` and `uv.lock`.
- `LEAN_PROJECT_PATH` must point to the warmed Lean project. If unset during setup,
  `setup_lean.py` creates this dossier's `lean_project/`.

## Requirements

- Python `3.12+`
- `uv`
- `elan`

## Step 1: Install Pinned Lean

Install elan if needed:

```bash
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh
```

Install + select pinned toolchain:

```bash
elan install leanprover/lean4:v4.25.0
elan default leanprover/lean4:v4.25.0
lean --version
```

Expected: `Lean (version 4.25.x, ...)`.

## Step 2: Sync Python Dependencies

From `dossiers/wonton-soup/`:

```bash
uv sync
```

## Step 3: Build Lean REPL And Create Lean Project

From `dossiers/wonton-soup/`:

```bash
uv run python setup_lean.py
```

Builds the bundled `leantree` REPL, initializes `$LEAN_PROJECT_PATH` when set, otherwise
`lean_project/`, fetches Mathlib caches, and warms the local build. Run it from this dossier
directory inside the pinned Wonton environment so `uv` uses the flake's Python 3.12.

## Step 4: Export `LEAN_PROJECT_PATH`

```bash
export LEAN_PROJECT_PATH=/path/to/specter-labs/research-registry/dossiers/wonton-soup/lean_project
```

## Step 5: Smoke Test

From `dossiers/wonton-soup/`:

```bash
uv run python wonton.py lean run -m dev --sample 3 --seed 123 --plain
```

Expected signals:

- a new `logs/corpus-YYYY-MM-DD-HHMMSS/` directory
- `run_status.json` with `status: completed`
- `summary.json.gz` present

## Platform Notes

- macOS uses `gzcat`; most Linux distributions use `zcat`.
- if elan binaries are not discovered, prepend `$HOME/.elan/bin` to `PATH`.

## Troubleshooting

### `lake not found`

```bash
export PATH="$HOME/.elan/bin:$PATH"
```

Then verify:

```bash
lake --version
```

### Lean version mismatch

```bash
elan override set leanprover/lean4:v4.25.0
lean --version
```

### `uv run` picked the wrong Python

Rebuild the venv against the flake interpreter:

```bash
uv sync --python "$(which python)"
uv run python -V
```

### REPL build failures in `lean_project/`

```bash
cd lean_project
lake exe cache get
lake build
```

If dependency fetch/build still fails, remove transient build outputs and rebuild with the pinned
version active.

### `LEAN_PROJECT_PATH` not respected

Verify current shell value:

```bash
echo "$LEAN_PROJECT_PATH"
```

It must resolve to this dossier's `lean_project` path, not another repository.
