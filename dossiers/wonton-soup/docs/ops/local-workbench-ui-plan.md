# Local Workbench UI Plan

Purpose: make the local browser UI the main operator surface for Wonton runs.

Excluded:

- `site/` published dashboard
- dispatch/control-plane integration
- Marimo and lake notebooks as primary runtime UI

## Scope

- Start runs from a GUI.
- Observe running runs live.
- Inspect theorem- and intervention-level artifacts.
- Compare wild type vs intervention per theorem.
- Surface run-level behavior fractions and summary distributions.
- Keep `wonton.py` as the only execution engine.

## Current State

- `wonton.py` CLI starts runs and analysis jobs.
- `wonton.py watch` is the current live observer.
- `analysis/viz_server.py` serves local read-only browser/API views over run artifacts.
- The old local dashboard frontend is not present as maintained source in tracked `main`.

## Target Architecture

- Backend: extend `analysis/viz_server.py`.
- Frontend: add a maintained local UI source tree under `dossiers/wonton-soup/dashboard/`.
- Execution: spawn `uv run python wonton.py ... --agent` as subprocess jobs.
- Source of truth: run directories and their artifacts.

## Work Packages

### 1. Re-establish the local browser UI

- Add a source-backed frontend for the local workbench.
- Keep the initial route set small: `Runs`, `New Run`, `Run`, `Theorem`.
- Reuse existing read endpoints from `viz_server.py`.

### 2. Add run launch

- Add local POST endpoints for job creation and cancellation.
- Start with `lean run` and `lean basin`.
- Use presets for common runs and an advanced panel for low-level flags.
- Parse `--agent` JSONL events to map jobs to `run_dir`.

### 3. Add live observation

- Add polling or SSE for run updates.
- Read `run_status.json` as the live status source.
- Show current theorem, phase, tier, intervention, counters, speed, restarts, and memory.
- Support attach-to-existing-run and follow-latest-run.

### 4. Add theorem and intervention drilldown

- Use theorem index + file endpoints already present in `viz_server.py`.
- Add direct views for history, MCTS tree, graph, comparison, proof term, and assembly trace.
- Make wild-type vs intervention comparison a first-class surface.
- Gate views by capability and artifact presence.

### 5. Add run-level behavior views

- Surface percentages for:
  - wild solved / failed / aborted
  - intervention solved on wild-failed
  - intervention solved on wild-solved
  - crash / timeout / missing-artifact buckets
- Keep rescue matrix, GED histograms, and goal/tactic summaries visible at run level.

### 6. Add global graph distribution views

- Add run-wide graph summaries only after theorem drilldown is stable.
- First pass: motif counts, graph size/depth distributions, cluster membership, GED distributions.
- Layered graph overlays are optional and should only be added if graph normalization is explicit and readable.

### 7. Add analysis-job integration

- Add launch surfaces for `postprocess`, `verify-run-local`, `compare`, `inspect-proof-ir`, `compare-cross-assistant`, and `benchmark-cross-assistant`.
- Treat these as jobs with report outputs, not as run views.
- Link generated reports back into the selected run.

## Build Order

1. Maintained local frontend over existing read API
2. Run launch
3. Live updates
4. Theorem and intervention drilldown
5. Run-level behavior summaries
6. Analysis-job integration
7. Optional global graph distribution views

## Non-Goals

- No second execution stack.
- No dependency on the published site dashboard.
- No dependency on lake/parquet for local runtime observation.
- No attempt to revive the old compiled dashboard bundle as the primary codebase.

## Main Risks

- The old local dashboard frontend source is missing.
- In-progress runs expose partial artifacts by design.
- Graph naming and graph-family labeling are currently inconsistent across parts of Wonton.
