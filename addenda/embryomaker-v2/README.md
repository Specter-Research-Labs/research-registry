# EmbryoMaker v2

EmbryoMaker parity work for two lanes: cell sorting and invagination.

## What Lives Here

- `kernel/`: C++23 summary binaries for cell sorting and invagination.
- `embryomaker_v2/legacy_snapshot.py`: parser for the legacy `.dat` snapshot
  subset used by the active lanes.
- `embryomaker_v2/comparison.py`: comparison logic for legacy snapshots and v2
  summaries.
- `embryomaker_v2/baseline_cli.py`: legacy staging and comparison commands.

## Status

- cell sorting: staged legacy snapshots compare against v2 trajectory summaries.
- invagination: bootstrap/state comparison is wired; geometry parity is still
  open.
- baseline runs: use Linux x86_64, or the provided `linux/amd64` Docker wrapper
  on Apple Silicon.

## Docs

- `docs/architecture.md`: current C++/Python split.
- `docs/baseline.md`: legacy baseline host and commands.
- `docs/parity-targets.md`: active lanes and legacy files that matter.

## Check

```bash
cd addenda/embryomaker-v2
nix develop
uv run ruff check .
uv run ty check .
uv run python -m pytest
cmake -S kernel -B kernel/build
cmake --build kernel/build
ctest --test-dir kernel/build --output-on-failure
```

`direnv allow` from this directory enters the same flake and runs `uv sync`.

## Useful Commands

```bash
uv run embryomaker-v2 baseline lanes
uv run embryomaker-v2 baseline stage-cell-sorting /path/to/EmbryoMaker
uv run embryomaker-v2 baseline compare-cell-sorting-trajectory tmp/legacy-cell-sorting-baseline/artifacts
uv run embryomaker-v2 baseline stage-invagination /path/to/EmbryoMaker
uv run embryomaker-v2 baseline compare-invagination-bootstrap /path/to/0.dat
```
