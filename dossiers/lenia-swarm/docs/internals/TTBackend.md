# TT Backend

Tenstorrent execution for Flow Lenia. The user-facing entrypoint is
`LeniaCLI tt run`; Lenia Studio remains the replay and inspection surface.

## Modes

- `single`: one simulation on one TT device.
- `fleet`: independent simulations split across TT devices.
- `mesh`: one simulation over a TTNN/TT-Lang mesh. Reintegration is row-sharded;
  the spectral front half is still replicated/gathered.

Mesh mode is correctness-enabled. It is not yet the default performance path.

## Run

Remote runs require `--remote-root` or `LENIA_TT_REMOTE_ROOT` pointing at this
dossier on the target host.

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

Each run writes `tt_run.json` with backend mode, device selection, seeds,
timing, and final mass summaries.

## Device Rules

QuietBox N300 cards expose two Wormhole chips per card. Mesh shapes count chips,
so four cards are `--mesh-shape 1,8`.

The TT-Lang dist container maps `single` mode to `/dev/tenstorrent/0`.
`fleet` and `mesh` need explicit reservations:

```bash
dispatch run --on quietbox --device wormhole:0,1 -- ...
dispatch run --on quietbox --device wormhole:all -- ...
```

`LeniaCLI --host` and `dispatch run` are separate launchers. Use
`LeniaCLI tt run --host quietbox` for Studio/export artifacts. Use
`dispatch run` for backend profiling when dispatch owns the Wormhole
reservation; in that mode the command is already running in the remote
workspace.

## Developer Tools

`tt_backend/devtools/` is for bringup, profiling, and hardware debugging. It is
not the user workflow.

```bash
python devtools/run.py --backend tt --execution-mode mesh --device-list 0,1,2,3 --mesh-shape 1,8 ...
python devtools/bench.py --backend tt --execution-mode single --grid-sizes 128,256 --batch-sizes 1 ...
python devtools/probe_mesh_halo.py --mesh-shape 1,2 --tt-visible-devices 0 --size 256 --planes 2 --assemble
python devtools/probe_mesh_dft.py --mesh-shape 1,4 --tt-visible-devices 0,1 --size 512 --planes 20 --mode partition-complex-dft
```

`--mesh-dft` enables the experimental mesh-partitioned DFT path for
`devtools/run.py` and `devtools/bench.py`. It is correctness-validated but
slower than the default front half.

Accepted performance facts and rejected probes are tracked in
[TT Backend Performance](./TTBackendPerformance.md).
