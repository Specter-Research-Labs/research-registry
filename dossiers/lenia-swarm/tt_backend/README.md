# Lenia TT Backend

This backend runs Flow Lenia compute on Tenstorrent hardware. The user-facing
entrypoint is `LeniaCLI tt run`; Lenia Studio remains the place to inspect
exported trajectories and frame sequences.

## Execution Modes

- `single`: one Lenia simulation on one TT device.
- `fleet`: independent simulations split across TT devices. Use this for many
  concurrent `128x128` or `256x256` runs.
- `mesh`: one simulation on a TTNN/TT-Lang mesh. Reintegration is row-sharded
  across chips today; the spectral front half is still replicated/gathered.

Mesh execution is correctness-enabled, not fully resident yet. The next
performance target is to keep state, mass, and flow row-sharded across steps.

## Main CLI

Run TT workloads through the Swift CLI when producing artifacts for Studio or
search workflows. Remote runs require `--remote-root` or `LENIA_TT_REMOTE_ROOT`
pointing at this dossier on the target host.

```bash
export LENIA_TT_REMOTE_ROOT="$(dispatch workspace plan --on quietbox --project specter-labs --json | jq -r .remote_cwd)"

LeniaCLI tt run \
  --host quietbox \
  --config configs/base/paper_base_2c_128.json \
  --output tmp/tt-runs/orbitum-128 \
  --execution-mode single \
  --tt-card-num 0 \
  --steps 300 \
  --frame-every 5

LeniaCLI tt run \
  --host quietbox \
  --config configs/base/paper_base_2c_128.json \
  --output tmp/tt-runs/fleet-128 \
  --execution-mode fleet \
  --device-list 0,1,2,3 \
  --tt-card-list 0,1,2,3 \
  --batch-size 4 \
  --steps 300 \
  --frame-every 10
```

`tt_run.json` records backend mode, device selection, seeds, timing, and final
mass summaries for downstream provenance.

## Device Notes

QuietBox N300 cards expose two Wormhole chips per host card. Mesh shapes count
chips, not cards, so four cards are `--mesh-shape 1,8`.

The TT-Lang dist container maps `single` mode to container
`/dev/tenstorrent/0`. `fleet` and `mesh` expose multiple TT devices and should
be paired with explicit reservation when launched through dispatch, for example
`dispatch run --on quietbox --device wormhole:0,1 -- ...` or
`dispatch run --on quietbox --device wormhole:all -- ...`.

Dispatch and `LeniaCLI --host` are separate launchers. For user-facing Studio
exports, run `LeniaCLI tt run --host quietbox` from the Mac and point
`LENIA_TT_REMOTE_ROOT` at dispatch's mirrored dossier path as shown above. For
backend profiling where dispatch should own the Wormhole reservation, launch the
Python devtools inside the remote dispatch workspace and omit `--host`.

## Developer Tools

Use `tt_backend/devtools/` for runtime bringup, profiling, and quietbox
debugging. These scripts are not the user workflow.

```bash
# Direct Python runtime harness.
python devtools/run.py --backend tt --execution-mode mesh --device-list 0,1,2,3 --mesh-shape 1,8 ...

# Benchmark sweeps and stage profiles.
python devtools/bench.py --backend tt --execution-mode single --grid-sizes 128,256 --batch-sizes 1 ...

# Validate row-boundary exchange and mesh halo assembly.
python devtools/probe_mesh_halo.py --mesh-shape 1,2 --tt-visible-devices 0 --size 256 --planes 2 --assemble

# Validate the experimental mesh DFT front-half.
python devtools/probe_mesh_dft.py --mesh-shape 1,4 --tt-visible-devices 0,1 --size 512 --planes 20 --mode partition-complex-dft
```

`--mesh-dft` enables the experimental mesh-partitioned DFT path for
`devtools/run.py` and `devtools/bench.py`. It is correctness-validated but not
the default because current full-engine timings are slower than the default
front half.
