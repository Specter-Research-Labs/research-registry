# TT Backend Performance Record

This record keeps the Tenstorrent backend optimization state in the dossier
docs tree. It is an evidence log for current implementation choices, not a
runbook and not a target specification.

## Current Status

- `single` mode is usable for interactive QuietBox runs at `128x128` and
  `256x256`, including two-channel cases.
- `fleet` mode remains the practical way to run independent simulations across
  several Wormhole chips.
- `mesh` mode opens and runs. Reintegration now performs real row-sharded work,
  but the full simulation is not mesh-resident because the spectral front half
  still repartitions or gathers state around replicated work.
- The next performance work is structural: keep state, mass, and flow
  resident across mesh steps before chasing more local TT-Lang kernel variants.

## Baseline Measurements

QuietBox measurements from `2026-04-26` used the TT-Lang container, batch `1`,
warmup `2`, and card `0` unless noted otherwise. Stage-profile totals are
higher than warm wall time because stage synchronization adds overhead; use
stage splits to find bottlenecks, not to accept or reject throughput changes.

Warm TT throughput:

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

The `1c/10k` rows used `paper_base_10k_1c_128.json`. The `2c/20k` rows used
`paper_random_2c_20k_128.json`. A same-length `256x256` single-chip recheck
after cleanup measured `6.41 ms/step`, so treat `5.90 ms/step` as the best
observed run rather than a stable median.

Apple Metal remains the local comparison point for the paper benchmark:

| shape | Metal full throughput | Metal full stage-profile total |
| --- | ---: | ---: |
| `128x128`, `1c/10k` | `0.30 ms/step` | `0.90 ms/step` |
| `256x256`, `1c/10k` | `0.20 ms/step` | `1.12 ms/step` |
| `512x512`, `1c/10k` | `0.54 ms/step` | `2.36 ms/step` |

This is not an exact apples-to-apples comparison because the Swift paper
benchmark uses parameter embedding while the current TT config-driven benchmark
does not.

## Kept Implementation Facts

- Single-chip `run()` keeps canonical TT state packed as
  `[batch*channels*sx, sy]` between steps and restores only for host output.
- Sparse binary channel routes use generated TT-Lang per-channel route chunks,
  so `2c/20k` configs compute only the ten routed kernels per output channel.
  Weighted route matrices still use the generic route kernel.
- The grouped halo/block reintegration kernel is the active runtime path. For
  `dd=5`, it runs four offset groups with `25`, `30`, `30`, and `36` offsets.
- The accepted halo/block path stages a one-tile torus halo, then uses one
  block kernel for interior and wrapped boundary tiles.
- Row-factoring the halo/block kernel is the kept reintegration optimization:
  it keeps one row selector and row-shift tile live across each row-offset's
  column offsets.

Measured isolated `256x256`, one-channel, all-group halo/block times after row
factoring:

| group | offsets | halo/block time |
| --- | ---: | ---: |
| `0` | `25` | `0.51 ms` |
| `1` | `30` | `0.51 ms` |
| `2` | `30` | `0.52 ms` |
| `3` | `36` | `0.63 ms` |

Runtime-scale `256x256`, `2c`, `dd=5` profiling still points at selector and
shift tile traffic. For group `3`, the block kernel measured about `839 us`,
`36.5 MB` DRAM read, `18,688` uniform 2 KB reads, `256 KB` write, and `5,760`
read barriers. Halo padding was about `15 us`, so it is not the bottleneck.

## Mesh Findings

The first row-sharded mesh reintegration validation on `2026-04-27` was
correct but slower than single chip because the front half still repartitions
and gathers state around replicated work:

| shape | single chip | `1x2` row-sharded mesh |
| --- | ---: | ---: |
| `128x128`, `1c/3k` | `7.8 ms/step` | `11.2 ms/step` |
| `256x256`, `1c/3k` | `6.4 ms/step` | `17.9 ms/step` |

The halo exchange primitive is viable. `probe_mesh_halo.py` row-shards
`[planes, sx, sy]`, exchanges only top and bottom tile-row boundaries with
`ttnn.all_gather`, and measured `0.260 ms` at `128x128` and `0.359 ms` at
`256x256` for two planes on `1x2` mesh, with bf16-level max diffs below
`0.008`.

The clean halo assembly path is:

1. rotate gathered boundary blocks,
2. `ttnn.mesh_partition` the rotated slab,
3. mesh-wide `ttnn.concat` with the local shard.

This produces a mesh tensor whose per-device shard contains the correct
neighbor halo. Direct rank-local `get_device_tensors` plus
`combine_device_tensors` is not acceptable because the concatenated shards do
not share one mesh buffer, and `ttnn.concat(..., output_tensor=...)` is not
currently supported.

Mesh DFT primitives are correctness-viable but not a runtime win yet. On `1x4`
mesh, resident warm probes measured:

| probe | `256x256` | `512x512` | `1024x1024` |
| --- | ---: | ---: | ---: |
| row-sharded `A @ B` | `0.34 ms` | `0.35 ms` | `0.64 ms` |
| K-sharded `A @ B` + `all_reduce` | `0.74 ms` | `0.78 ms` | `0.96 ms` |
| real separable `W @ X @ W.T` | `0.90 ms` | `0.83 ms` | `1.21 ms` |

`LENIA_TT_MESH_DFT=1` uses `mesh_partition -> TTNNMeshDFTMatmul` for FFT/IFFT.
Full-engine validation passed for the default `128x128` config on `1x4`, but
`2c/20k` stage-profile mode measured `12.2 ms/step` at `256x256` and
`26.0 ms/step` at `512x512`, slower than the default engine.

## Rejected Probes

- Do not return to the older fused single-channel `TTLangPackedSobelFlow`
  without splitting or shrinking the read path. Hardware rejected it with read
  NCRISC size over `0x4000`.
- Do not pursue the two-output-column halo/block selector/broadcast shape. It
  reduced read traffic but regressed wall time.
- Do not use TT-Lang scalar-fill constants as a drop-in replacement for scalar
  parameter DFB reads. Correctness held in the fresh shift-y-fill probe, but
  wall time regressed.
- Do not treat L1 selector/parameter placement as a current win. It was neutral
  or slower in both the split kernel and halo/block kernel measurements.
- Do not use a static `initial_zero` branch inside the separable TT-Lang
  operation. Hardware compilation rejected the boolean branch shape.
- Do not use the column-block reduction prototype. It was mathematically wrong:
  `reduce_sum` reduced spatial columns because the offset axis was packed into
  horizontal tiles, and the direct rank-3 shape was unsupported in the current
  TT-Lang container.
- Do not force an `8x8` TT-Lang kernel grid on the current QuietBox Wormhole
  card. The device reports `compute_with_storage_grid_size == (x=8,y=7)`.
- Do not rely on `ttl.GroupTransfer` in the current container; it is not
  exposed there.

## Remaining Work

1. Keep single-simulation mesh state resident across steps.
2. Replace full-state repartition/gather boundaries with halo exchange wherever
   the algorithm only needs neighboring rows.
3. Revisit lower-level generated kernels only after residency removes the
   current structural traffic.
