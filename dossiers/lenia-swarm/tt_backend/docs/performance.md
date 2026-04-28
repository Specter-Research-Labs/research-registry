# TT Backend Performance Notes

These notes capture measured quietbox results for the TT-Lang/TTNN backend so
we keep optimizing from facts rather than re-testing the same branches.

## Current Baseline

- Fresh quietbox measurements from `2026-04-26` use the TT-Lang container,
  warmup `2`, batch `1`, and card `0`; timed step counts are noted where they
  differ from the original `20`-step stage profiles.
- The latest sparse-growth-route specialization artifacts live under
  `tmp/tt-bench-20260426/*growth-specialized*.json` on quietbox.
- Stage-profile synchronization overhead makes profiled step time higher than
  warm throughput, but the stage split is still useful.
- Single-chip `run()` now keeps canonical TT state packed as
  `[batch*channels*sx, sy]` between steps and restores only for host output.
  On multi-device mesh runs, the front half still works from replicated state,
  while reintegration now partitions spatial rows, exchanges row halos, runs
  rectangular TT-Lang kernels per chip, and gathers the result for the next
  step.
- At `256x256`, `1c/10k`, single-chip stage-profile timing after row-factored
  reintegration was `8.70 ms/step`: prepare `0.32`, FFT `0.44`, spectra
  `0.53`, IFFT `1.22`, growth `0.91`, flow `1.26`, reintegration `3.41`,
  finalize `0.18`.
- At `256x256`, `2c/20k`, single-chip stage-profile timing after sparse
  growth-route specialization is `9.70 ms/step`: prepare `0.33`, FFT `0.36`,
  spectra `0.73`, IFFT `1.78`, growth `1.17`, flow `1.01`, reintegration
  `3.92`, finalize `0.12`.
- At `256x256`, `2c/20k`, `1x2` mesh stage-profile timing after sparse
  growth-route specialization is `10.10 ms/step`: prepare `0.31`, FFT `0.87`,
  spectra `0.54`, IFFT `1.86`, growth `1.13`, flow `0.95`, reintegration
  `2.92`, finalize `0.46`.

Warm TT throughput measured on quietbox:

| shape | single chip | `1x2` mesh |
| --- | ---: | ---: |
| `128x128`, `1c/1k` | `2.77 ms/step` | `3.59 ms/step` |
| `256x256`, `1c/1k` | `4.18 ms/step` | `5.73 ms/step` |
| `512x512`, `1c/1k` | `12.89 ms/step` | `14.31 ms/step` |
| `128x128`, `1c/3k` | `2.77 ms/step` | `4.53 ms/step` |
| `256x256`, `1c/3k` | `4.39 ms/step` | `4.29 ms/step` |
| `512x512`, `1c/3k` | `13.35 ms/step` | `14.71 ms/step` |
| `128x128`, `1c/10k` | `2.80 ms/step` | `3.65 ms/step` |
| `256x256`, `1c/10k` | `4.81 ms/step` | `3.78 ms/step` |
| `512x512`, `1c/10k` | `12.92 ms/step` | `10.98 ms/step` |
| `128x128`, `2c/4k` | `3.40 ms/step` | `3.73 ms/step` |
| `256x256`, `2c/4k` | `6.06 ms/step` | `6.45 ms/step` |
| `512x512`, `2c/4k` | `21.12 ms/step` | `24.09 ms/step` |
| `128x128`, `2c/20k` | `3.70 ms/step` | `4.80 ms/step` |
| `256x256`, `2c/20k` | `5.90 ms/step` | `5.80 ms/step` |
| `512x512`, `2c/20k` | `16.80 ms/step` | `16.80 ms/step` |

The `1c/10k` rows use `paper_base_10k_1c_128.json`; the fresh `2c/20k`
rows use `paper_random_2c_20k_128.json`. The latest `2c/20k` rows were
measured with warmup `2`, timed steps `50`, and artifacts under
`tmp/tt-bench-20260426/packed-state-warm-single-2c20k-sweep.json` and
`tmp/tt-bench-20260426/mesh-normalpath-2c20k-sweep.json`. A follow-up
same-length `256x256` single-chip recheck after cleanup measured
`6.41 ms/step`, so treat the `5.90 ms/step` sweep value as the best observed
run rather than a guaranteed median.

Canonical M5 Max Apple Metal-full comparison, measured locally with
`LeniaCLI benchmark --paper-flow`, release build, steps `50`, `1c/10k` paper
lane with parameter embedding enabled:

| shape | Metal full throughput | Metal full stage-profile total |
| --- | ---: | ---: |
| `128x128`, `1c/10k` | `0.30 ms/step` | `0.90 ms/step` |
| `256x256`, `1c/10k` | `0.20 ms/step` | `1.12 ms/step` |
| `512x512`, `1c/10k` | `0.54 ms/step` | `2.36 ms/step` |

The Apple comparison is not perfectly apples-to-apples yet: the Swift paper
benchmark uses parameter embedding, while the TT config-driven benchmark
currently ignores that embedding. It is still the right reference for the
current best Apple lane.

Fresh `2026-04-27` default-path recheck for `2c/20k`, batch 1, warmup `2`,
timed steps `50`, TT-Lang dist container:

| shape | single chip | `1x4` mesh |
| --- | ---: | ---: |
| `256x256` | `6.4 ms/step` | `5.4 ms/step` |
| `512x512` | `19.2 ms/step` | `16.8 ms/step` |

The matching synchronized stage profiles still point at reintegration as the
largest stage. Single-chip measured `11.1 ms/step` at `256x256` with
reintegration `4.29 ms`, and `23.6 ms/step` at `512x512` with reintegration
`11.06 ms`. `1x4` mesh measured `10.8 ms/step` at `256x256` with
reintegration `2.96 ms`, and `23.3 ms/step` at `512x512` with reintegration
`9.41 ms`. The `1x4` path is still reported as `mesh-replicated-spmd`: useful
runtime speedup for this workload, not true mesh-resident spatial ownership.

Fresh `2026-04-27` first row-sharded mesh-reintegration validation, `1c/3k`,
batch 1, warmup `1`, TT-Lang dist container:

| shape | single chip | `1x2` mesh with row-sharded reintegration |
| --- | ---: | ---: |
| `128x128` | `7.8 ms/step` | `11.2 ms/step` |
| `256x256` | `6.4 ms/step` | `17.9 ms/step` |

The `128x128` mesh correctness sanity check against single-chip after one step
was `max=0.03125`, `mean=0.000438851`, with mass sums `805.780` vs `805.724`.
This proves the TTNN mesh tensor plus TT-Lang rectangular halo path is
functional, but it is not yet a speed win: the first implementation still pays
for per-step mesh partition/all-gather around a replicated front half.

A fresh attempt to use the older fused single-channel
`TTLangPackedSobelFlow` in the runtime was rejected by hardware code size:
the generated read NCRISC was `0x4260 > 0x4000` at `128x128` and
`0x4318 > 0x4000` at `256x256`. Keep the split gradient/combine flow path
until the fused read path is explicitly split or shrunk.

Current conclusion:

- The TT backend is usable for interactive quietbox runs at `128x128` and
  `256x256`, including two-channel cases.
- Kernel count is not the dominant cost up to `1c/10k`; channel count and
  reintegration/data movement dominate.
- The current mesh path opens and runs, and reintegration now does real
  row-sharded spatial work. It is still slower than single-chip in the first
  `1x2` implementation because state is repartitioned and gathered each step;
  treat it as correctness groundwork, not the final scaling result.
- Packed state is a kept single-chip optimization for long runs and exports.
  The fresh `2c/20k` sweep moved warm wall time from
  `3.90/6.70/20.00 ms` to `3.70/5.90/16.80 ms` at `128/256/512`, with a
  follow-up `256x256` repeat at `6.41 ms`. A synchronized stage profile of the
  packed path showed `10.4 ms/step` at `256x256` because sync boundaries made
  flow/reintegration look worse; prefer non-stage wall time for accepted/reject
  decisions and use stage profiles only to localize bottlenecks.
- Sparse binary channel routes now use generated TT-Lang per-channel route
  chunks, so `2c/20k` configs compute only the 10 routed kernels per output
  channel instead of computing all 20 and multiplying half by zero. The
  specialization is kept to binary Lenia routes; weighted route matrices still
  use the generic TT-Lang route kernel.
- The obvious low-risk probes around the current halo/block reintegration shape
  are mostly exhausted: direct halo/block, barrier batching, source-block reuse,
  and row-factored selector reuse are kept; L1 constants, TT-Lang scalar fills,
  and two-output-column selector/broadcast shape are not.
- Two fresh cheap probes also failed to produce a keepable win. A static
  `initial_zero` branch inside the separable TT-Lang operation failed hardware
  compilation with `Cannot Compare Non-Integer Values`; if we revisit first
  group zero-initialization it needs a separate generated kernel, not a boolean
  branch inside one operation. Replacing the reintegration scratch `zeros_like`
  with `allocate_tensor_on_device` was correctness-safe but measured as noise:
  `6.418 ms/step` parent vs `6.422 ms/step` patched for `256x256`, `2c/20k`,
  single chip, warmup `2`, steps `50`, artifacts
  `tmp/tt-bench-20260427/scratch-{parent,patched}.json` on quietbox.
- A column-block reduction prototype compiled and ran quickly for isolated
  group 3 (`1.10 ms` vs `1.25 ms` for the local separable check), but it was
  mathematically invalid: TT-Lang `reduce_sum` reduces a tensor dimension, not
  a private offset-tile axis, so packing offsets into horizontal tiles also
  reduced spatial columns. The probe produced `actual_sum=472842` vs
  `expected_sum=245022` for `256x256`, `2c`, `dd=5`, group 3, and should not be
  kept in the runtime. If we batch offsets in TT-Lang later, the offset axis
  must be a real non-spatial tensor dimension with an explicit squeeze/accumulate
  plan. A follow-up compile probe showed the current TT-Lang container rejects
  that direct shape too: `reduce only supports 2D tensors, got rank 3`.
- The next meaningful wins are structural: avoid per-offset selector/shift tile
  traffic further, make single-sim mesh sharding resident with halo exchange,
  and only then revisit lower-level exported/generated kernels if TT-Lang output
  still leaves obvious dataflow waste.

Fresh `2026-04-27` mesh sanity numbers for `1c/10k`, batch 1, TT-Lang dist
container, stage-profile mode:

| grid | single | `1x2` mesh | `1x4` mesh |
| --- | ---: | ---: | ---: |
| `256x256` | `9.2 ms/step` | `7.5 ms/step` | `8.8 ms/step` |
| `512x512` | `17.4 ms/step` | `15.7 ms/step` | `16.5 ms/step` |
| `1024x1024` | `86.8 ms/step` | `83.4 ms/step` | `79.0 ms/step` |

A quick `2026-04-27` CLI smoke after adding `--mesh-dft` showed the flag is
wired through the container path. With `128x128`, `1c`, batch 1, warmup `1`,
steps `2`, and synchronized stage profiling, single chip measured
`6.3 ms/step`, `1x2` mesh without mesh DFT measured `9.4 ms/step`, and `1x2`
mesh with `--mesh-dft` measured `8.8 ms/step`. Treat these as smoke numbers,
not final tuning data.

The first mesh-resident reintegration brick is viable: `probe_mesh_halo.py`
row-shards `[planes, sx, sy]`, slices only top/bottom tile-row boundaries, and
uses `ttnn.all_gather` for a small halo exchange instead of gathering the full
state. On `1x2` mesh, 2 planes measured `0.260 ms` at `128x128` and `0.359 ms`
at `256x256` for top+bottom boundary exchange, with bf16-level max diffs
below `0.008`.

The follow-up `--assemble` probe found the clean rank-correct construction:
rotate the gathered boundary blocks, `ttnn.mesh_partition` the rotated slab,
then mesh-wide `ttnn.concat` with the local shard. This produces a real mesh
tensor whose per-device shard contains the correct neighbor halo. On `1x2`,
`256x256`, 2 planes, both `pad=before` and `pad=after` validated with
`local_padded_shape=(2, 160, 256)` and max diff below `0.008`. Direct
rank-local `get_device_tensors` plus `combine_device_tensors` was rejected by
TTNN because the newly concatenated shards do not share one mesh buffer, and
`ttnn.concat(..., output_tensor=...)` is currently unsupported; keep the
rotate-partition path.

These runs now report `execution_strategy=mesh-replicated-spmd`. That is an
honest current-state label: fabric mesh opens and executes, and larger grids can
benefit modestly, but the single sim is not yet spatially owned by separate
chips.

Fresh `2026-04-27` DFT mesh probes show the TTNN primitives needed for a
distributed spectral front-half are viable on a `1x4` mesh. These are resident
warm timings after one warmup run, using bfloat16 inputs and PCC correctness
against host matmul:

| probe | `256x256` | `512x512` | `1024x1024` |
| --- | ---: | ---: | ---: |
| row-sharded `A @ B` | `0.34 ms` | `0.35 ms` | `0.64 ms` |
| K-sharded `A @ B` + `all_reduce` | `0.74 ms` | `0.78 ms` | `0.96 ms` |
| real separable `W @ X @ W.T` | `0.90 ms` | `0.83 ms` | `1.21 ms` |

The reusable complex primitive now lives in `TTNNMeshDFTMatmul` and follows the
same upstream pattern. It was hardware-validated on `1x4` with warm resident
timing:

| probe | `128x128` | `256x256` | `512x512` |
| --- | ---: | ---: | ---: |
| complex `W @ X @ W.T` | `1.90 ms`, PCC `0.999966` | `1.78 ms`, PCC `0.999962` | - |
| replicated input + `mesh_partition` + complex DFT | - | `1.84 ms`, PCC `0.999962` | - |
| replicated input + `mesh_partition` + complex DFT, 20 planes | - | `3.19 ms`, PCC `0.999960` | `6.07 ms`, PCC `0.999965` |

`ttnn.mesh_partition` is available in the TT-Lang container and is the clean
replicated-copy-to-row-shard bridge for this path. The engine has a guarded
experimental path behind `LENIA_TT_MESH_DFT=1` that uses
`mesh_partition -> TTNNMeshDFTMatmul` for FFT/IFFT. Full-engine validation on
`1x4` passed for the default `128x128` config: one-step max diff `2.99e-02`,
two-step max drift `7.20e-02` with tolerance `8.0e-01`.

Do not make this path default yet. On `2026-04-27`, `2c/20k`, `1x4`, stage
profile mode with `LENIA_TT_MESH_DFT=1` measured `12.2 ms/step` at `256x256`
and `26.0 ms/step` at `512x512`. The DFT math and redistribution are now
correct, but this hybrid still loses to the default engine at these sizes.

## Reintegration Findings

The active runtime path is the grouped halo/block TT-Lang reintegration kernel:
four offset groups for `dd=5`, with 25, 30, 30, and 36 offsets. Each group
first stages a one-tile torus halo, then computes every output tile with a 2x2
source block and block selector matrices.

Fresh `2026-04-26` TT-Lang perf dumps for `256x256`, `2c`, `dd=5` show the
same pattern at runtime scale. The block kernels are memory/DFB-traffic
dominated: uniform 2 KB reads, 48 cores, and cost scaling almost linearly with
offset count. Logs are on quietbox under
`tmp/tt-bench-20260426/reintegration-perf-groups/`.

Use `tt_backend/devtools/profile_reintegration_group.py` for isolated
TT-Lang group timings and `TTLANG_PERF_DUMP=1` NOC-event summaries, for
example `TTLANG_PERF_DUMP=1 python tt_backend/devtools/profile_reintegration_group.py --sx 256 --sy 256 --channels 2 --dd 5 --impl block-halo-separable --group-index 3 --runs 20`.
The quietbox container wrapper sets `TT_METAL_HOME` for the TT-Lang dist image
so this perf mode works without extra environment boilerplate.

| group | offsets | block time | DRAM read | 2 KB reads | read barriers |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 25 | `599.9 us` | `27.5 MB` | `14080` | `4224` |
| 1 | 30 | `704.8 us` | `31.2 MB` | `16000` | `4864` |
| 2 | 30 | `712.5 us` | `32.0 MB` | `16384` | `4992` |
| 3 | 36 | `839.8 us` | `36.5 MB` | `18688` | `5760` |

Fresh `2026-04-27` isolated runtime-matching `block-halo-separable` timings
for `256x256`, `2c`, `dd=5`, warmup `2`, runs `20`, were
`0.649/0.778/0.764/0.915 ms` for groups 0-3. A group-3 perf dump measured the
halo pad at `14.9 us` and the hot block kernel at `839.4 us`, `48` cores,
`36.5 MB` DRAM read via `18,688` uniform 2 KB reads, `256 KB` write, and
`5,760` read barriers. The bottleneck remains tiny selector/shift reads in
the block kernel; halo padding is not the target.

Non-profiled isolated group timings for the same `2c` shape were
`0.672/0.835/0.827/0.966 ms` for groups 0-3.

Measured isolated `256x256`, 1 channel, group 3, 36 offsets:

- Previous split kernel: about `2.1 ms`.
- Previous TT-Lang perf dump after scalar-param hoisting: `100 MB` DRAM read,
  `128 KB` DRAM write, `51200` 2KB reads, `11648` read barriers, `8x4`
  auto grid.
- Current halo/block kernel with direct per-offset parts, including halo pad:
  about `0.82 ms`.
- Current TT-Lang perf dump for the group-3 block kernel: `82 MB` DRAM read,
  `128 KB` DRAM write, `41984` 2KB reads, `2432` read barriers, `8x4`
  auto grid, and about `119 GB/s` effective read bandwidth. The separate halo
  pad is small: about `10 us`, `486 KB` read, and `486 KB` write.
- Reusing each output tile's shared 2x2 source blocks across all offsets reduced
  the group-3 block-kernel perf dump to `29.5 MB` DRAM read and `15104` 2KB
  reads, while wall time stayed around `0.72-0.80 ms`. Source tensor traffic is
  no longer the primary limiter for this kernel shape; the remaining traffic is
  dominated by per-offset row/column selector tiles and shift tiles.
- Row-factoring the current halo/block kernel keeps one row selector and
  row-shift tile live across each row-offset's column offsets. Group 3 now
  reads `18.2 MB` via `9344` 2KB transfers with `2880` read barriers and takes
  about `0.56 ms` in `TTLANG_PERF_DUMP=1` mode. Non-profiled isolated timings
  improved from `0.566/0.676/0.646/0.763 ms` to
  `0.514/0.514/0.516/0.625 ms` for groups 0-3 at `256x256`, 1 channel.
- Direct per-offset parts removed zero-fill plus single-part accumulator DFBs
  from the block kernel. This reduced group-3 block time from about `938 us` to
  about `723 us` without changing the measured DRAM traffic.
- Batching each offset's source, selector, and shift copies into one wait group
  reduced group-3 read barriers from `4736` to `2432`, but did not materially
  change wall time. The remaining bottleneck is the `82 MB` / `41984` tiny
  reads, not barrier count alone.
- A two-output-column halo/block prototype reduced group-3 `256x256` read
  traffic from `82 MB` / `41984` reads to `63.6 MB` / `32544` reads, but
  regressed wall time: `0.869 ms` vs `0.817 ms` at `256x256`, and `3.027 ms`
  vs `2.333 ms` at `512x512`. Do not pursue that exact selector/broadcast DFB
  shape.
- TT-Lang line-level auto-profiling currently overflows the group-3 read
  NCRISC once instrumentation is injected (`0x4fa4 > 0x4000`). Use
  `TTLANG_PERF_DUMP=1`/NOC-event summaries for this kernel until the read path
  is split or made smaller.
- Selector-reuse experiment reduced DRAM read to `82 MB`, but regressed wall
  time to about `2.23 ms` and increased barriers to `13952`. Do not pursue
  this exact DFB shape.
- L1 selector/parameter placement did not help: on the previous split kernel,
  group 3 moved from about `2.09 ms` with DRAM constants to about `2.14 ms`
  with L1 constants; on the direct halo/block kernel, group 3 moved from about
  `0.82 ms` with DRAM constants to about `0.87 ms` with L1 constants.
- TT-Lang scalar-fill constants are not a good drop-in replacement here. Earlier
  per-offset fill variants hit tuple-capture and DST-register limits. A fresh
  generated shift-y-fill probe compiled and preserved correctness, but regressed
  group-3 `256x256`, `2c` wall time from `0.966 ms` to `1.353 ms`; the reduced
  scalar DRAM traffic did not pay for the extra TT-Lang compute/dataflow shape.
  Keep scalar parameters as DFB reads until the kernel is split further or
  lowered/exported into a form with tighter register control.
- The currently mapped quietbox Wormhole card reports
  `compute_with_storage_grid_size == (x=8,y=7)`, so a forced `8x8` TT-Lang
  kernel grid is invalid on that device. A prior forced-`8x7` experiment
  matched auto-grid rather than improving wall time; this should be treated as
  a measurement for that kernel/device, not a general TT-Lang rule.
- Current TT-Lang container does not expose `ttl.GroupTransfer`; the local
  source checkout has examples, but this is not usable in the current container
  runtime without changing the TT-Lang environment.

Historical split-kernel measurement for `256x256`, 1 channel, group 0,
25 offsets:

- Normal accumulate kernel: about `1.451 ms`.
- Zero-initial accumulator kernel: about `1.432 ms`.
- This removed the first group's accumulator DRAM read, but the full-step win
  was small. The current halo/block runtime uses the same accumulation kernel
  for all four groups; reintroduce an initial-accumulator specialization only
  if a fresh halo/block measurement shows it matters.

## Halo-Block Reintegration

The 2x2 block-selector formulation is now the runtime path. The first
block-interior prototype proved the math was faster, but separate boundary
launches erased the win. The accepted version stages a one-tile torus halo and
uses the same block kernel for interior and wrapped boundary tiles.

Measured isolated `256x256`, 1 channel, all groups after row factoring:

| group | offsets | halo/block time |
| --- | ---: | ---: |
| 0 | 25 | `0.51 ms` |
| 1 | 30 | `0.51 ms` |
| 2 | 30 | `0.52 ms` |
| 3 | 36 | `0.63 ms` |

This shifts full runtime reintegration from about `7.4 ms/step` to about
`3.4-3.8 ms/step` on one chip depending on profiling overhead. The first
row-sharded `1x2` mesh reintegration path validates the same math on local
rectangular shards, but is slower until we keep front-half and state movement
resident across steps.

## Mesh Direction

Current mesh execution opens and runs. A single Lenia sim now has real
row-sharded TT-Lang reintegration: each chip owns rectangular spatial rows,
TTNN CCL exchanges one-tile row halos, local torus column halos are concatenated
on chip, and the rectangular TT-Lang block-halo kernel computes the local
output. The front half is still replicated/gathered, so the full pipeline is not
yet resident across the mesh.

The packed-state single-chip path is not a shortcut to mesh sharding. Sharding
the packed row dimension made TTNN reshape see only each shard's local volume,
so reshaping `[batch*channels*sx, sy]` into `[batch*channels, sx, sy]` failed.
Replicating packed state across the mesh fixed correctness but regressed
`128x128`, `2c/20k` to `6.2 ms/step`, versus `4.8 ms/step` for the shaped mesh
path. The accepted direction is now explicit spatial partitioning, not packed
row sharding. Next optimizations should remove the per-step repartition/gather,
keep mass/flow/state resident as row shards, and then extend the same resident
strategy into the DFT/front-half path.
