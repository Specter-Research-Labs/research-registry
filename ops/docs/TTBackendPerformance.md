---
summary: "Precision and throughput of the fp32 SFPU Flow Lenia engine on N300 cards, and where its step time goes."
---

# TT Backend Performance Record

Measurements from 2026-10-22 on four N300 cards, with requalification bodies
(two channels, twenty kernels) from `adult-requalification-001`.

## Precision

Relative RMS error against the float64 reference after one step, over 107
bodies at `128x128`, 46 at `256x256` and 46 at `512x512`. The float32 column is the same
equations in numpy float32, the class in which Metal builds differ from each
other (about `2e-7` in the potential).

| quantity | device `128` median / max | float32 `128` max | device `256` median / max | float32 `256` max | device `512` median / max | float32 `512` max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| potential | `1.72e-7` / `1.91e-7` | `1.37e-7` | `1.93e-7` / `2.17e-7` | `1.46e-7` | `2.05e-7` / `2.27e-7` | `1.56e-7` |
| affinity | `5.85e-8` / `1.36e-7` | `1.05e-7` | `4.55e-8` / `1.05e-7` | `8.66e-8` | `4.38e-8` / `9.42e-8` | `8.75e-8` |
| flow | `1.17e-6` / `2.87e-6` | `2.92e-6` | `1.27e-6` / `3.55e-6` | `3.57e-6` | `1.27e-6` / `3.59e-6` | `3.56e-6` |
| mass | `3.43e-7` / `1.49e-6` | `7.09e-7` | `3.17e-7` / `2.23e-6` | `1.10e-6` | `3.09e-7` / `3.10e-6` | `1.11e-6` |

After 16 steps the device mass error is `6.9e-6` at most at `128`, `4.9e-6` at
`256` and `5.0e-6` at `512`, against `9.5e-6`, `4.5e-6` and `4.5e-6` for
float32. The bf16 engine this one
replaced was at `5.4e-2` maximum absolute mass error after one step and fully
diverged within 200 steps.

Over long replays the device tracks Metal as closely as numpy float32 does.
Bodies that diverge from Metal do so at the same step in float32, because the
dynamics amplify one-ulp differences, so long-run agreement is judged on
ensemble verdicts rather than per-step fields.

## Throughput

All four cards running concurrently, per-card batch, 32 timed steps after two
warmup steps, host load average between 2 and 5 (about 20 for `512x512`).

| grid | bodies per card | ms per step | body-steps/s per card | box (4 cards) |
| --- | ---: | ---: | ---: | ---: |
| `128x128` | 256 | `9.37` | `27,330` | `109,300` |
| `128x128` | 3584 | `138.7` | `25,850` | `103,400` |
| `128x128` | 4096 | `147.4` | `27,800` | `111,200` |
| `256x256` | 128 | `19.38` | `6,605` | `26,400` |
| `256x256` | 896 | `146.1` | `6,134` | `24,500` |
| `256x256` | 1024 | `153.7` | `6,664` | `26,700` |
| `512x512` | 64 | `41.7` | `1,535` | `6,140` |
| `512x512` | 256 | `161.3` | `1,586` | `6,340` |

Batches that fill all 64 cores of both chips evenly (multiples of 2048 lanes at
`128x128`, 512 at `256x256`) are fastest. Cards scale linearly. Per cell,
`512x512` runs at the `128x128` rate.

Transforms longer than 128 points do not fit the destination registers. Their
outer radix-2 stages run as split stages over circular buffers, a chunk of 32
positions from each half of a span at a time, and the inner 128 points run in
registers as before. The `256x256` build gives state hashes bit-identical to
the previous one at every step of a 2000-step rollout of 46 bodies, and the
`128x128` build over 107 bodies. At `512x512` pass 2 single-buffers its column
input, kernel and output to fit L1.

## Where the step goes

Per-pass time at `128x128`, 4096 bodies per card, from the host timer and from
`bench.py --profile` on one card:

| pass | work | ms | device time |
| --- | --- | ---: | ---: |
| p1 | row FFT of mass | `4.1` | `4.3` |
| p2 | column FFT, kernel product, inverse column FFT | `31.6` | `33.7` |
| p3 | inverse row FFT, growth, affinity | `57.5` | `57.0` |
| p4 | Sobel gradients and flow | `14.9` | `14.6` |
| p5 | reintegration over the `(2 dd + 1)^2` window | `39.2` | `38.8` |

p2, p3 and p5 are compute-bound. In p5 the SFPU spends `24.5` ms adding terms and
`10.1` ms weighting source rows by their x overlaps, of `38.8` ms. In p2 and p3 the unpacker spends `10.6` and about
`17` ms in `cb_wait_front`, but almost all of that is waiting for the same
core's packer between dependent stages: waits for tiles from DRAM, timed as
their own zone, total `0.07` ms in p2 and `2.5` ms in p3, and deeper input
buffers leave both passes unchanged.

Reintegration works on blocks of four target rows of one channel. Each source
row's mass is weighted once by its x overlap with every target row it reaches,
and each y overlap is then computed once and shared by up to four rows instead
of once per target row. That took p5 from `111.9` to `50.1` ms at 3584 bodies,
with state hashes bit-identical to the per-row kernel at every step of a
2000-step rollout of 107 bodies. Keeping the four row accumulators in registers
across the y overlaps, instead of loading and storing them for every term, and
computing two overlaps at a time so that each fills the other's pipeline gaps,
took p5 to `39.2` ms, again bit-identical over the same rollout. Each overlap
still costs about twelve instructions against two per term, so a cheaper
overlap clamp is the next p5 gain; in p2 and p3 it is shorter dependency chains
between the unpack, math and pack stages.
