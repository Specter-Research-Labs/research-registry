# EmbryoMaker v2

Staging surface for a modern EmbryoMaker remake.

Focuses on:
- fixing the kernel boundary
- scaffolding the `C++23` and Python split
- defining the parity plan against the original mathematics
- preparing a clean baseline lane for legacy code

Serves as the workbench to pin down the compiled kernel, Python control plane, and mathematical parity before full simulator implementation.

## Documentation

- `docs/architecture.md`: compiled boundary, module tree, memory layout, and public API
- `docs/legacy-baseline-linux-x86_64.md`: preferred original baseline host and run recipe
- `docs/parity-plan.md`: how to match the original mathematics and scheduler 1:1
- `docs/parity-ledger-v0.md`: concrete original source surfaces to transcribe first

## Project Surfaces

- `kernel/`: typed `C++23` parity surfaces, including the first legacy cell-sorting lane
- `embryomaker_v2/`: Python control-plane CLI for toolchain checks and parity surfaces
- `tests/`: Python CLI tests

## Start Here

```bash
cd addenda/embryomaker-v2
nix develop
uv run embryomaker-v2 doctor
uv run embryomaker-v2 layout
uv run embryomaker-v2 preset cell-sorting
uv run embryomaker-v2 baseline doctor
uv run embryomaker-v2 baseline recipe
uv run embryomaker-v2 baseline lanes
uv run embryomaker-v2 baseline build-docker-image
uv run embryomaker-v2 baseline stage-cell-sorting /path/to/EmbryoMaker
uv run embryomaker-v2 baseline stage-cell-sorting-docker /path/to/EmbryoMaker
uv run embryomaker-v2 baseline snapshot-summary /path/to/10.dat
uv run embryomaker-v2 baseline compare-cell-sorting /path/to/10.dat --json-out /tmp/cell-sorting-compare.json
uv run embryomaker-v2 baseline compare-cell-sorting-trajectory /path/to/output-or-artifacts --json-out /tmp/cell-sorting-trajectory.json
```

If you use direnv, `direnv allow` from `addenda/embryomaker-v2/` is equivalent. The shell
auto-runs `uv sync`.

To build the current kernel scaffold:

```bash
cd addenda/embryomaker-v2
cmake -S kernel -B kernel/build
cmake --build kernel/build
ctest --test-dir kernel/build --output-on-failure
./kernel/build/em2_legacy_cell_sorting_summary 10 1234 77
```

## Dev Tooling

```bash
cd addenda/embryomaker-v2
uv run ruff check .
uv run ty check
uv run pytest
```

## Scope

- `C++23` kernel
- Python control plane
- one typed experiment surface
- one checkpoint surface
- explicit parity lanes against the original EmbryoMaker code

## Non-Goals

- no GUI-first runtime yet
- no positional config files
- no legacy snapshot compatibility layer
- no promise of full math parity with every historical mode before we pin the benchmark lanes
