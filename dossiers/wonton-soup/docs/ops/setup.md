# Setup

Setup for the Lean runtime used by `wonton-soup`.

## Contract

- Lean is pinned by `lean-toolchain` (`4.25.0`).
- `leantree` is pinned by `pyproject.toml` and `uv.lock`.
- `LEAN_PROJECT_PATH` points to the warmed Lean project. If unset, `setup_lean.py`
  creates `lean_project/`.
- `LEAN_REPL_EXE` may point to a prebuilt REPL binary.

## Requirements

- Python 3.12+
- `uv`
- `elan`

Install the pinned Lean toolchain if needed:

```bash
elan install leanprover/lean4:v4.25.0
elan default leanprover/lean4:v4.25.0
lean --version
```

From `dossiers/wonton-soup/`:

```bash
uv sync
uv run python setup_lean.py
```

Shared runtime roots are explicit:

```bash
export WONTON_SOUP_RUNTIME_ROOT="${WONTON_SOUP_RUNTIME_ROOT:-$HOME/.local/state/wonton-soup}"
export LEAN_PROJECT_PATH="${LEAN_PROJECT_PATH:-$WONTON_SOUP_RUNTIME_ROOT/lean_project}"
export LEAN_REPL_EXE="${LEAN_REPL_EXE:-$WONTON_SOUP_RUNTIME_ROOT/bin/repl}"
uv run python setup_lean.py
```

## Smoke Test

```bash
uv run python wonton.py lean run -m dev --sample 3 --seed 123 --plain
```

Expected output:

- `logs/corpus-YYYY-MM-DD-HHMMSS/`
- `run_status.json` with `status: completed`
- `summary.json.gz`

## Failure Checks

- `lake not found`: prepend `$HOME/.elan/bin` to `PATH`.
- Lean mismatch: run `elan override set leanprover/lean4:v4.25.0`.
- Wrong Python: run `uv sync --python "$(which python)"`.
- REPL build failure: run `lake exe cache get && lake build` inside
  `lean_project/`.
- Wrong Lean project: print `LEAN_PROJECT_PATH` and confirm it resolves to this
  dossier's project.
