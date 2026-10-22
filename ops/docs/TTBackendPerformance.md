---
summary: "Precision and throughput of the fp32 SFPU Flow Lenia engine on N300 cards, and where its step time goes."
---

# TT Backend Performance Record

Measurements from 2026-10-22 on four N300 cards, with requalification bodies
(two channels, twenty kernels) from `adult-requalification-001`.

## Precision

Relative RMS error against the float64 reference after one step, over 107
bodies at `128x128` and 46 at `256x256`. The float32 column is the same
equations in numpy float32, the class in which Metal builds differ from each
other (about `2e-7` in the potential).

| quantity | device `128` median / max | float32 `128` max | device `256` median / max | float32 `256` max |
| --- | ---: | ---: | ---: | ---: |
| potential | `1.72e-7` / `1.91e-7` | `1.37e-7` | `1.93e-7` / `2.17e-7` | `1.46e-7` |
| affinity | `5.85e-8` / `1.36e-7` | `1.05e-7` | `4.55e-8` / `1.05e-7` | `8.66e-8` |
| flow | `1.17e-6` / `2.87e-6` | `2.92e-6` | `1.27e-6` / `3.55e-6` | `3.57e-6` |
| mass | `3.43e-7` / `1.49e-6` | `7.09e-7` | `3.17e-7` / `2.23e-6` | `1.10e-6` |

After 16 steps the device mass error is `6.9e-6` at most at `128` and `4.9e-6`
at `256`, against `9.5e-6` and `4.5e-6` for float32. The bf16 engine this one
replaced was at `5.4e-2` maximum absolute mass error after one step and fully
diverged within 200 steps.

Over long replays the device tracks Metal as closely as numpy float32 does.
Bodies that diverge from Metal do so at the same step in float32, because the
dynamics amplify one-ulp differences, so long-run agreement is judged on
ensemble verdicts rather than per-step fields.

## Throughput

All four cards running concurrently, per-card batch, 32 timed steps after two
warmup steps.

| grid | bodies per card | ms per step | body-steps/s per card | box (4 cards) |
| --- | ---: | ---: | ---: | ---: |
| `128x128` | 256 | `13.55` | `18,900` | `75,600` |
| `128x128` | 3584 | `211.2` | `16,960` | `67,800` |
| `256x256` | 128 | `28.22` | `4,535` | `18,100` |
| `256x256` | 896 | `218.9` | `4,093` | `16,400` |

A single card at `128x128` stays between 17,000 and 18,900 body-steps/s from
64 to 3584 bodies; batches that fill all 64 cores of both chips evenly are
fastest. Cards scale linearly.

## Where the step goes

Per-pass time at `128x128`, 3584 bodies per card:

| pass | work | ms |
| --- | --- | ---: |
| p1 | row FFT of mass | `3.7` |
| p2 | column FFT, kernel product, inverse column FFT | `28.0` |
| p3 | inverse row FFT, growth, affinity | `54.3` |
| p4 | Sobel gradients and flow | `13.7` |
| p5 | reintegration over the `(2 dd + 1)^2` window | `111.9` |

Reintegration is half the step and the first target for further speed.
