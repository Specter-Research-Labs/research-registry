---
summary: "Replaying Flow Lenia export bundles on Tenstorrent N300 cards with the fp32 SFPU engine, and validating and benchmarking it."
---

# TT Backend

Flow Lenia on Tenstorrent Wormhole runs in `tt_backend/tt_lenia/sfpu`. Every
operation is IEEE float32 on the SFPU vector units; the matrix unit, which
truncates to tf32, is never used. One SFPU lane holds one body, so 32 bodies
form a group, and each group gets an equal share of the chip's 64 cores.

The engine follows the Metal pipeline's semantics (`MetalSpectral.swift`,
`MetalPipeline.swift`) for the configuration the large searches run: torus
border, `flowlenia_2022_paper_equations`, explicit parameters, sides of 128 or
256, mass-weighted alpha. The replay runner refuses any other config feature
rather than approximating it.

## Replay

The user-facing entrypoint is `LeniaCLI tt replay`. It reads the
`index.jsonl` that `LeniaCLI publish replay --input` reads and writes the same
campaign layout (`config.json`, `replay-manifest.json`,
`development-trace.jsonl` per body, and `summary.json`), so
`assess-creatures` and `classify-creatures` read TT replays and Metal replays
alike. Paths must lie under the dossier root, which the container mounts at
`/repo`.

```bash
export LENIA_TT_REMOTE_ROOT=<dossier root on the TT host>

LeniaCLI tt replay \
  --host <tt-host> \
  --input tmp/requal/input/n128-torus128/index.jsonl \
  --output tmp/tt-replays/n128-torus128 \
  --steps 40000 \
  --trace-interval 400 \
  --cards 0,1,2,3 \
  --seeds 0-8 \
  --batch 4096
```

On the TT host the same run is

```bash
python3 tt_backend/devtools/container.py -- \
  python3 -m tt_lenia.sfpu.replay \
  --input /repo/tmp/requal/input/n128-torus128/index.jsonl \
  --output /repo/tmp/tt-replays/n128-torus128 \
  --steps 40000 --trace-interval 400 --cards 0,1,2,3 --seeds 0-8 --batch 4096
```

Every body runs as an ensemble with one member per seed. Member `k` is
`lenia_swarm_analysis.perturbation.one_ulp_member(field, k, 0)`, which moves one
percent of the occupied cells by one float32 ulp per channel; seed 0 is the
unperturbed body. Each member is a campaign named `<campaign>-u<seed>`. Its
`config.json` carries the member's exact initial field as a full-grid state
patch, so Metal replays it unchanged, and its `replay-manifest.json` records the
seed, the role index, the sha256 of the initial field and the lanes it ran in.

Members form one queue, cut into rounds of whole 64-lane units of at most
`--batch` lanes and dealt round-robin to the cards. Each card runs its rounds
one engine at a time. Lanes share no data, so a member's trajectory does not
depend on where it runs or what runs beside it; `validate.py` checks this bit
for bit. Only the last unit of the queue holds filler: zero-mass, zero-spectrum
lanes that are checked to stay zero and are never written out, and that
`summary.json` lists by card, round, chip, group and lane.

Bodies in one replay must share their grid, connectivity and flow parameters,
because those are compiled into the SFPU code; spectra and growth parameters
are per lane. A round of 4096 lanes fills all 64 cores of both chips.

## Devices

An N300 card holds two Wormhole chips and is opened as one `(1, 2)` mesh with
`MESH_DEVICE=N300`. Cards run as separate processes selected by
`TT_VISIBLE_DEVICES`, because bodies never interact and a fleet of independent
cards scales linearly with no fabric between cards.

`tt_backend/devtools/container.py` runs a command in the pinned TT-Lang
distribution image with the whole `/dev/tenstorrent` tree mapped, so card
indices mean the same inside and outside the container. It removes hugepage
files that no process holds before starting, and keeps the TT-Metal kernel cache
under `$SPECTER_RUNTIME_ROOT/tt-metal-cache` (or the dossier's `tmp/`), so the
roughly 12 s first-step compilation happens once per kernel variant.

## Validation and benchmarks

```bash
python3 tt_backend/devtools/container.py -- \
  python3 devtools/validate.py --input /repo/<index.jsonl> --card 0
python3 tt_backend/devtools/container.py -- \
  python3 devtools/bench.py --input /repo/<index.jsonl> --cards 0,1,2,3 --batches 256,3584
```

`validate.py` compares potential, affinity, flow and mass after one step for
every body (64 by default) against the float64 reference in
`tt_lenia/numpy_ref/metal.py`, and the mass after a 16-step rollout for the
first four. It also rolls out the last body alone and requires its state to
match its packed lane bit for bit, and requires filler lanes to stay zero. The float32 reference runs alongside as the yardstick, and each
quantity passes when the largest device error stays within three times the
largest float32 error. `bench.py` runs the same batches on all listed cards at
once and reports per-card and box rates with a per-pass split.

Results are recorded in [TT Backend Performance](./TTBackendPerformance.md).
