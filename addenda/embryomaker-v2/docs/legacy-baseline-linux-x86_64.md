# Legacy Baseline: Linux x86_64

This is the preferred first host for running the original EmbryoMaker baseline.

On Apple Silicon, the preferred way to reach that target is a `linux/amd64`
container through Docker or OrbStack, not the legacy macOS build script.

## Build

- install `gfortran`
- install `freeglut3-dev`
- install `gnuplot` only if you need the legacy plotting path
- run `./compile_EmbryoMaker.sh` from the original EmbryoMaker root

## Staged Runner

The addendum now exposes a staging command that writes a disposable baseline
runner and manifest:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline stage-cell-sorting /path/to/EmbryoMaker
bash tmp/legacy-cell-sorting-baseline/run_legacy_cell_sorting.sh
```

The same staging surface now exists for invagination:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline stage-invagination /path/to/EmbryoMaker
bash tmp/legacy-invagination-baseline/run_legacy_invagination.sh
```

For Apple Silicon hosts with Docker or OrbStack, use the generated container
wrapper instead:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline stage-cell-sorting-docker /path/to/EmbryoMaker
bash tmp/legacy-cell-sorting-baseline/run_legacy_cell_sorting_docker.sh
```

Or for invagination on Apple Silicon:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline stage-invagination-docker /path/to/EmbryoMaker
bash tmp/legacy-invagination-baseline/run_legacy_invagination_docker.sh
```

For repeated runs on Apple Silicon, build the toolchain image once and then
stage against that cached image so the emulated run does not pay `apt-get`
every time:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline build-docker-image
uv run embryomaker-v2 baseline stage-cell-sorting-docker \
  /path/to/EmbryoMaker \
  --image embryomaker-v2-legacy-baseline:bookworm-slim \
  --skip-install-packages
bash tmp/legacy-cell-sorting-baseline/run_legacy_cell_sorting_docker.sh
```

The Docker wrapper:

- stages the same native Linux runner under `tmp/legacy-<lane>-baseline`
- mounts the legacy checkout and staged bundle back into the same absolute paths
  inside the container
- runs `docker --platform linux/amd64` so Apple Silicon hosts can produce the
  same baseline lane we want from a native Linux `x86_64` machine
- installs `gfortran`, `freeglut3-dev`, `libglu1-mesa-dev`, `libgl1-mesa-dev`,
  and `python3` in a disposable `debian:bookworm-slim` container before
  executing the staged runner
- can skip the in-container package install step when the image already
  contains that toolchain, which is the preferred repeat-run path on Apple
  Silicon

The staged runner:

- copies the legacy checkout into `tmp/legacy-<lane>-baseline/workspace`
- patches `config_file.txt` line 5 to `2`
- the invagination staging command sets that same line to `3`
- inserts a final zero-valued draw flag before the preselection section when
  the checked-in legacy config only provides 40 flags, because the parser now
  expects 41
- runs the legacy compile script in the disposable workspace
- resolves the legacy executable at `./bin` on a fresh checkout, or
  `./bin/EMaker` if `bin` already exists as a directory
- invokes that executable through the relative path inside the workspace,
  because the legacy `getarg(0)` handling truncates long absolute executable
  paths and breaks automatic mode
- executes `./bin 0 01 10 100`
- captures logs, exit code, patched config, and output artifacts under
  `tmp/legacy-<lane>-baseline/artifacts`

## Trajectory Compare

Once the staged baseline bundle exists, compare the full legacy snapshot
directory against the v2 lane with:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline compare-cell-sorting-trajectory \
  tmp/legacy-cell-sorting-baseline/artifacts \
  --json-out tmp/legacy-cell-sorting-baseline/artifacts/cell_sorting_v2_comparison.json
```

Current status on this repository as of 2026-03-22:

- the staged Linux baseline bundle passes the declared 5% tolerance on all 101
  cell-sorting frames
- the JSON artifact is written to
  `tmp/legacy-cell-sorting-baseline/artifacts/cell_sorting_v2_comparison.json`

For the invagination lane, the first comparison surface is the fixed-topology
bootstrap state rather than a trajectory run. After building the kernel, compare
the staged legacy `0.dat` against the v2 bootstrap summary with:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline compare-invagination-bootstrap \
  tmp/legacy-invagination-baseline/workspace/EmbryoMaker/output/<run-id>/<run-id>bin________________0.dat \
  --json-out tmp/legacy-invagination-baseline/artifacts/invagination_bootstrap_comparison.json
```

Current status on this repository as of 2026-03-22:

- the real staged invagination `0.dat` passes this bootstrap comparison exactly
- the JSON artifact is written to
  `tmp/legacy-invagination-baseline/artifacts/invagination_bootstrap_comparison.json`

The next invagination surface is the first post-bootstrap target frame. After
building the kernel, compare the staged legacy `5802.dat` against the v2
fixed-topology invagination stepper with:

```bash
cd addenda/embryomaker-v2
uv run embryomaker-v2 baseline compare-invagination \
  tmp/legacy-invagination-baseline-short/artifacts/output/<run-id>/<run-id>bin_______________5802.dat \
  --bootstrap-snapshot \
  tmp/legacy-invagination-baseline-short/artifacts/output/<run-id>/<run-id>bin________________0.dat \
  --json-out tmp/legacy-invagination-baseline-short/artifacts/invagination_v2_comparison.json
```

Current status on this repository as of 2026-03-22:

- the v2 invagination stepper matches the staged legacy `5802.dat` summary
  surface exactly at `rtime≈10`
- geometry is not yet closed: the current artifact reports
  `max_position_error=0.18375603110506017`,
  `mean_position_error=0.04696190706123148`, and
  `rms_position_error=0.059864304491794515`
- the JSON artifact is written to
  `tmp/legacy-invagination-baseline-short/artifacts/invagination_v2_comparison.json`
- the remaining drift is concentrated in the 98-node contractile patch where
  legacy evolves `eqd`, `add`, and `cod`

## Cell Sorting Run

- use `arg1=0` so the legacy binary loads the default preset path rather than a
  snapshot file
- use `arg2=01` to enter automatic mode
- the legacy startup path treats any parseable non-single-character automatic
  argument as mode `1`, and `01` is important here because it forces the
  program to allocate `idum` and `idumoriginal` before `default_ic`
- set `config_file.txt` line 5 to `2` so `default_ic` selects the cell-sorting
  preset
- the checked-in `config_file.txt` currently selects preset `1`, so baseline
  cell sorting requires changing that line in the baseline workspace
- pass `arg3` as iterations per snapshot
- pass `arg4` as number of snapshots
- the checked-in compile script does `mv src/core/EMaker bin`, so on a fresh
  checkout the executable ends up at top-level `./bin`
- if a checkout already has a `bin/` directory, the staged runner also accepts
  `./bin/EMaker`
- example: `./bin 0 01 10 100`

## Expected Behavior

- the automatic path writes an initial snapshot through `writesnapini`
- it then runs repeated `iteracio` calls and writes a snapshot after each batch
- the legacy automatic path exits with code `231`, not `0`
- with `./bin 0 01 10 100`, the automatic files are `_0.dat`, then
  `10.dat`, `20.dat`, ..., `1000.dat`
- the cell-sorting preset uses `ffu(5)=0` and therefore takes the RK4 branch in
  `iteracio`
- `ffu(27)=0` on this preset, so neighbor construction happens once before RK4
  and later stages reuse the same neighbor graph while recalculating distances
- `ffu(24)=0` does call `restore_neighbors`, but it is inert here because the
  preset is mesenchymal-only (`tipus=3`)
- post-mechanics noise is still active on this preset: `c=nd*prop_noise` in
  fixed-delta mode, each `itera` proposal moves one node isotropically, and
  `ffu(15)=1` keeps the energy-based accept or reject step active

## Default Outputs

- `output/<run-id>/*.dat`
- `name.dat`, which points at the initial snapshot path

## Caveats

- the build still links OpenGL and GLUT even when the runtime path is headless
- the legacy compile scripts are ad hoc shell scripts, not a modern build
  system
- the first cold `linux/amd64` container run on Apple Silicon can spend most of
  its wall-clock time in package installation and emulation overhead, which is
  why the cached-image path is the practical baseline workflow here
- the checked-in macOS build path is stale: it still targets `MacPort`,
  `gcc46`, and an `OS X 10.6` era toolchain rather than a maintained Apple
  Silicon flow
- a concrete macOS `arm64` probe with `nix shell nixpkgs#gfortran
  nixpkgs#freeglut nixpkgs#mesa` reached the final link step here but failed on
  `ld: library not found for -lGL`, which is consistent with the legacy script
  assuming Linux-style OpenGL libraries
- the main program always links the OpenGL modules, so the cell-sorting baseline
  is headless only after the binary exists
