# Architecture

Current split:

- C++ writes deterministic summary binaries for parity lanes.
- Python stages legacy runs, parses snapshots, and writes comparisons.

There is no binding layer. We compare the summary binary output.

## C++ Kernel

The kernel lives under `kernel/`.

Built binaries:

- `em2_legacy_cell_sorting_summary`
- `em2_legacy_invagination_summary`

Implemented lanes:

- cell sorting: legacy-style neighbor construction, mesenchymal pair forces,
  RK4 stepping, and post-mechanics noise.
- invagination: fixed-topology epithelial bootstrap and step summaries.

C++ owns hot state, force loops, neighbor construction, and the RNG-compatible
behavior needed by the active lanes.

## Python Tools

The Python package owns the surrounding tools:

- `baseline_cli.py`: stages original EmbryoMaker runs and writes comparisons.
- `baseline_support.py`: recipes, staged runner generation, Docker wrapper
  generation, and executable calls.
- `legacy_snapshot.py`: parses the stable legacy `.dat` subset.
- `comparison.py`: compares legacy summaries against v2 summaries.

Python does not run the simulation loop.

## Adding a Lane

A lane counts when it has:

1. a legacy baseline run,
2. a v2 summary executable,
3. a parser for the needed legacy output,
4. explicit comparison tolerances,
5. tests for the parser and comparison path.

Add new lanes in this form before growing the runtime.
