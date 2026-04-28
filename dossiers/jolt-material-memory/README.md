# Jolt Material Memory

Tests whether local, history-dependent material updates produce retention, hysteresis, and better
search efficiency (`K`) without a centralized controller. The baseline is deliberately narrow:
compare memory-bearing material rules against memory-free and damping-only controls.

## Runs

- Engine: Jolt rigid-body simulation in `engine/src/main.cpp`
- Backends: `cpu` scalar C++ updates, `metal` compute updates on Apple Silicon
- Memory modes: `off`, `on`, `inertial_control`
- Scenarios: `imprint`, `hysteresis`, `damage`

Each run writes NDJSON step records plus one summary record. Step records include
`body_positions` for video rendering.

For each `(scenario, backend, seed)`, campaigns run:

- `blind + memory=off` (null baseline)
- `directed + memory=off` (policy control)
- `directed + memory=on` (treatment)
- `directed + memory=inertial_control` (damping-only control)

This separates material memory from directionality alone and persistence from extra damping alone.

## Environment

```bash
cd dossiers/jolt-material-memory
nix develop
```

`direnv allow` from `dossiers/jolt-material-memory/` is equivalent; the shell runs `uv sync`.

## Build

```bash
./scripts/build.sh
```

## Single Run

```bash
./build/jolt_memory_lab \
  --scenario imprint \
  --policy directed \
  --backend metal \
  --memory on \
  --seed 41000 \
  --steps 1200 \
  --dt 0.0166667 \
  --out data/smoke.ndjson
```

Add `--jor-out data/smoke.jor` to record a native Jolt viewer stream.

## Campaign

```bash
uv run python scripts/run_campaign.py --config configs/paper_track_v1.json
```

Outputs:
- `data/<campaign>/runs/*.ndjson`
- `data/<campaign>/campaign_manifest.json`
- `logs/<campaign>/*.stdout.log|*.stderr.log`

If `SPECTER_ARTIFACT_ROOT` or `SPECTER_LOG_ROOT` is set, outputs route there. Empty values fail
loudly.

## Analysis

```bash
uv run python scripts/analyze_campaign.py --manifest data/paper_track_v1/campaign_manifest.json
```

Outputs:
- `data/paper_track_v1/analysis/metrics_table.csv`
- `data/paper_track_v1/analysis/analysis_summary.json`
- `data/paper_track_v1/analysis/plots/*.png`
- `data/paper_track_v1/analysis/plots/delta_k_controls.png`
- `data/paper_track_v1/analysis/plots/damage_recovery_bar.png`

## Acceptance Gate

- HLA CI lower bound > 0 for `hysteresis`
- MRI CI lower bound > 0 for `imprint`
- `delta_k_on_vs_off` CI lower bound > 0 in at least 2 scenario/backend groups
- `delta_k_on_vs_inertial_control` CI lower bound > 0 in at least 2 scenario/backend groups

`analysis_summary.json` emits these as `primary_gate_met` and
`control_separation_gate_met`.

CI summaries use:

- `kind=bootstrap` for genuinely variable groups
- `kind=exact` when all seeds collapse to the same measured value

## Provenance

Each campaign manifest records:

- manifest version and full config snapshot
- full command line per run
- JJ change and commit IDs (when available)
- Jolt revision tag
- per-run stdout/stderr logs
- return code and timestamps

The manifest is written before the first run and updated after every run. Each run NDJSON also
includes a `meta` record with material-memory parameters and scenario timing/amplitude parameters.

Follow-up configs in `configs/`:

- `damage_ablation_v1.json`: damage-only plasticity ablation over named memory variants
- `layout_generalization_v1.json`: line vs staggered body-layout sweep

See:
- `docs/experiment-matrix.md`
- `docs/metric-spec.md`

## Video Rendering

Render NDJSON to MP4:

```bash
uv run python scripts/render_run.py \
  --ndjson data/smoke_cpu.ndjson \
  --out data/smoke_cpu.mp4 \
  --fps 24 \
  --stride 2
```

Record a native Jolt `.jor` stream:

```bash
./build/jolt_memory_lab \
  --scenario imprint \
  --policy directed \
  --backend cpu \
  --memory on \
  --seed 41000 \
  --steps 1200 \
  --dt 0.0166667 \
  --out data/smoke.ndjson \
  --jor-out data/smoke.jor
```

Build and open the viewer:

```bash
./scripts/build_jolt_viewer.sh
./scripts/open_jolt_recording.sh data/smoke.jor
```

Fixed camera:

```bash
./scripts/open_jolt_recording.sh data/smoke.jor \
  --camera-pos 8,4.5,16 \
  --camera-target 0,0,0 \
  --fps 60 \
  --autoplay
```

Native MP4:

```bash
./scripts/render_jolt_recording.sh \
  data/smoke.jor \
  data/smoke-native.mp4 \
  --camera-pos 8,4.5,16 \
  --camera-target 0,0,0 \
  --fps 60
```

GIF:

```bash
uv run python scripts/render_run.py \
  --ndjson data/smoke_cpu.ndjson \
  --out data/smoke_cpu.gif \
  --fps 18 \
  --stride 3
```

Offline Blender:

```bash
BLENDER_INSTALL_ROOT=/path/to/blender-apps \
  bash scripts/install_blender.sh

SPECTER_ARTIFACT_ROOT=/path/to/artifacts \
  uv run python scripts/export_render_bundle.py \
    --ndjson data/smoke_cpu.ndjson \
    --name smoke-hq \
    --stride 2

BLENDER_APP=/path/to/blender-apps/Blender-5.0.1.app \
BLENDER_RUNTIME_ROOT=/path/to/blender-runtime \
  bash scripts/run_blender_render.sh \
    /path/to/artifacts/jolt-material-memory/render-bundles/smoke-hq \
    /path/to/output/smoke-hq.png \
    --mode still \
    --samples 96

BLENDER_APP=/path/to/blender-apps/Blender-5.0.1.app \
BLENDER_RUNTIME_ROOT=/path/to/blender-runtime \
  bash scripts/run_blender_render.sh \
    /path/to/artifacts/jolt-material-memory/render-bundles/smoke-hq \
    /path/to/output/smoke-hq.mp4 \
    --mode animation \
    --fps 24 \
    --samples 32
```

Fresh run NDJSON includes per-body `body_plasticity`, `body_stiffness`, `body_friction`,
`body_contact`, and `body_strain`. The Blender renderer maps those channels to substrate
thickness, glow, contact footprints, and damage/event markers. MP4 output is assembled from a PNG
sequence with `ffmpeg`.
