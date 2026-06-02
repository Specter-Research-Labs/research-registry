# Wonton Soup

`wonton-soup` studies proof-search structure in Lean by perturbing MCTS theorem proving. Controlled lesions expose proof families, basin stability, rerouting, collapse, and blind-relative efficiency.

Centralized MCTS maps the single-controller landscape. Distributed MCTS tests whether coordinated controllers reach that landscape differently.

## Start Here

1. Enter the project shell from `dossiers/wonton-soup/`:
   - `nix develop`
   - or `direnv allow` if you use direnv
2. The local shell auto-runs `uv sync` and provides the Coq-backed toolchain (`coqc`, `coqtop`,
   `sertop`, `coq-lsp`).
3. Environment setup: `docs/ops/setup.md`
4. Corpus pipeline and reproducible artifact refs: `docs/ops/corpus.md`
5. Run the standard verification check:

```
./scripts/verify.sh
```

If you want the ad hoc smoke test instead:

```
uv run python wonton.py lean run -m dev --sample 5 --seed 123
```

## Lean Runtime Paths

`wonton-soup` now supports externalizing both the warmed Lean project and the built REPL binary.
If you do nothing, `uv run python setup_lean.py` still creates `./lean_project`. If you want a
single durable runtime root, export these first:

```
export WONTON_SOUP_RUNTIME_ROOT="${WONTON_SOUP_RUNTIME_ROOT:-$HOME/.local/state/wonton-soup}"
export LEAN_PROJECT_PATH="${LEAN_PROJECT_PATH:-$WONTON_SOUP_RUNTIME_ROOT/lean_project}"
export LEAN_REPL_EXE="${LEAN_REPL_EXE:-$WONTON_SOUP_RUNTIME_ROOT/bin/repl}"
```

Then run:

```
uv run python setup_lean.py
```

On shared lab storage, the better split is:

```
export LEAN_PROJECT_PATH=/shared/specter-runtime/common/wonton-soup/lean_project
export LEAN_REPL_EXE=/shared/specter-runtime/machines/<machine>/wonton-soup/bin/repl
```

The full setup and verification path is in `docs/ops/setup.md`.

## Documentation Index

Use [Wonton Soup Docs](docs/README.md) for runbooks, internals, ADRs, and provider/backend notes.

## Project Paths

- `prover/`: core search engine, adapters, proof/trace artifacts
- `orchestrator/`: CLI-facing run orchestration
- `corpus/`: corpus definitions and artifact pipeline
- `analysis/`: postprocess, metrics, lake extraction/export
- `experiments/`: experiment-specific runners and analyses
- `paper/`: Typst manuscript source for the perturbation / proto-cognition paper
- `docs/`: canonical project documentation

`wonton.py` computes proof-search logs and the local Wonton lake under the
canonical local Wonton roots: `wonton-soup/logs` and
`wonton-soup/artifacts/lake/lake.duckdb`. A checkout under
`research-registry-workspaces/` resolves those roots to the sibling main
`research-registry/dossiers` tree, so workspace runs append to the same local
lake and logs instead of duplicating them. `local_artifact_root` and
`local_log_root` in the machine `spctr` config are only for machines whose
checkout layout differs.

```
spctr surface status wonton-lake
spctr surface sync wonton-lake
```

## Dev Tooling

```
cd /path/to/specter-labs/research-registry
cd dossiers/wonton-soup && nix develop --command true
cd dossiers/wonton-soup && ./scripts/verify.sh
```
