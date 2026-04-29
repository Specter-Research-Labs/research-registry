# Baseline

Baseline capture uses the original EmbryoMaker runtime as the reference. Run it
on Linux x86_64. On Apple Silicon, use the generated `linux/amd64` Docker
wrapper.

## Toolchain

Native baseline runs need:

- `gfortran`
- `freeglut3-dev`
- `libglu1-mesa-dev`
- `libgl1-mesa-dev`
- `python3`

The legacy binary still links OpenGL and GLUT even for headless runs.

## Stage

From this addendum:

```bash
uv run embryomaker-v2 baseline stage-cell-sorting /path/to/EmbryoMaker
bash tmp/legacy-cell-sorting-baseline/run_legacy_cell_sorting.sh

uv run embryomaker-v2 baseline stage-invagination /path/to/EmbryoMaker
bash tmp/legacy-invagination-baseline/run_legacy_invagination.sh
```

On Apple Silicon:

```bash
uv run embryomaker-v2 baseline build-docker-image
uv run embryomaker-v2 baseline stage-cell-sorting-docker \
  /path/to/EmbryoMaker \
  --image embryomaker-v2-legacy-baseline:bookworm-slim \
  --skip-install-packages
bash tmp/legacy-cell-sorting-baseline/run_legacy_cell_sorting_docker.sh
```

The staged runner copies the legacy checkout into `tmp/legacy-<lane>-baseline`,
patches the preset line in `config_file.txt`, builds the original, runs the
selected lane, and stores logs plus snapshots under `artifacts/`.

## Compare

Cell sorting trajectory:

```bash
uv run embryomaker-v2 baseline compare-cell-sorting-trajectory \
  tmp/legacy-cell-sorting-baseline/artifacts \
  --json-out tmp/legacy-cell-sorting-baseline/artifacts/cell_sorting_v2_comparison.json
```

Invagination bootstrap:

```bash
uv run embryomaker-v2 baseline compare-invagination-bootstrap \
  /path/to/0.dat \
  --json-out tmp/legacy-invagination-baseline/artifacts/invagination_bootstrap_comparison.json
```

Invagination post-bootstrap:

```bash
uv run embryomaker-v2 baseline compare-invagination \
  /path/to/5802.dat \
  --bootstrap-snapshot /path/to/0.dat \
  --json-out tmp/legacy-invagination-baseline/artifacts/invagination_v2_comparison.json
```

## Legacy Notes

- Cell sorting uses automatic mode `./bin 0 01 10 100`.
- The legacy automatic path exits with code `231` after a successful run.
- The checked-in legacy config must select preset `2` for cell sorting and
  preset `3` for invagination.
- Fresh legacy checkouts put the executable at top-level `./bin`; checkouts
  with an existing `bin/` directory may produce `./bin/EMaker`.
- The legacy macOS build path targets an obsolete MacPorts/GCC era toolchain;
  it is not the baseline target.
