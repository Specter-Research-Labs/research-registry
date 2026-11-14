---
summary: "The capacity-pilot design file: one JSON document names the runtime, bodies, study, ensemble and outcomes, and the run directory it produces."
---

# Capacity-pilot designs

`LeniaCLI discover capacity-pilot --design DESIGN.json --output RUN` runs one study over every body in the design, once per ensemble member, and writes a run directory that can be replayed from `RUN/design.json` alone. The CLI has no other options: every value a run depends on is in the design, and the design's sha256 is in the receipt. One design per study kind lives in [configs/capacity-pilot](../../configs/capacity-pilot/); they use the bundled `b0cd1441` organism at the old command's default steps.

## Schema

Every object rejects unknown keys and every key is required unless marked optional. Paths are resolved against the design file's directory, and every file reference is `{"path": ..., "sha256": ...}`; the run fails when the file's sha256 differs.

| Key | Meaning |
| --- | --- |
| `runtime.config` | File reference to a Flow Lenia runtime JSON. |
| `runtime.backend` | `metal-full`, `cpu` or `mlx`. `mlx` is accepted only for `development` and `response`, which need no resident state. |
| `runtime.border` | `wall` or `torus`. Studies that write channels need `wall` and at least two channels. |
| `bodies[]` | `specimen_id` (unique, no `/`), `init_seed`, `params` (`R`, `r`, `m`, `s`, `h`, `a`, `b`, `w`, rounded to Float32 first), optional `initial_condition` (an `init` object whose seed equals `init_seed`), `field` (file reference, required exactly by the field studies), `diameter` (required exactly when an outcome uses `centroid_path_diameters`). All bodies share grid and channels. |
| `study.kind` | One of the kinds below, with exactly that kind's keys. |
| `ensemble` | `members` (at least 1), `perturbed_cells` (at least 1), `seed` (non-negative). |
| `repeat_check.members` | How many leading members to re-run, in `1...members`. |
| `outcomes.continuous[]` | `name`, `measure` (`centroid_path`, `centroid_path_diameters`, `min_coherence`), `branches`, `from_step`, `to_step`. Both steps must be frame steps of every named branch. |
| `outcomes.binary[]` | `name`, `all`: a list of `{outcome, op, value}` with `op` `>=` or `<=`, over continuous outcomes that share their branches. |

| Kind | Study keys |
| --- | --- |
| `original` | `checkpoint_steps`, `horizon`, `probe_shear`, `probe_steps`, `challenge_shear`, `write_dose` |
| `symmetry` | `checkpoint_steps`, `transform_steps` |
| `followup` | as `original`, plus `age_offsets`, `wait_steps`, `second_write_step` |
| `development` | `horizon`, optional `phantom`, optional `ancestry` |
| `response` | `checkpoint_steps`, `horizon`, `age_offsets`, `probe_shear`, `probe_steps`, `challenge_shear` |
| `write-response` | `checkpoint_steps`, `write_mode`, `write_dose` (balanced modes only), `release_steps`, `challenge` |
| `write-release` | as `write-response` without `challenge` |
| `state-response` | `checkpoint_steps`, `challenge`; the body's `field` replaces the checkpoint |
| `state-continuation` | `horizon`; starts from the body's `field` |
| `state-flow` | `horizon`, `save_potential`, optional `phantom`; starts from the body's `field` |
| `transport` | `checkpoint_steps`, `release_steps`, `horizon`, `challenge_shear`; grid at least 256 x 256 |

`challenge` is `{horizon, shear, sign, axis}` with `sign` 1 or -1 and `axis` `x` or `y` (square grids only). `phantom` is `{source, pressure, field}` with `source` `static` or `replay`. `ancestry` is `{founders, export_steps}` plus exactly one of `labels` (an int32 file reference, one label per cell) or `founder_mass` (which needs `ensemble.members` 1). Phantom fields and ancestry exist only on `metal-full`; on `cpu` the design is rejected and the error names the missing engine feature. There is no fallback between backends.

The old command's limits that were properties of the code rather than the study, such as the 128-step minimum horizon, are gone. The 32-step frame cadence, the 0.01 body threshold, the 128-pixel preview and the 256-cell transport crop remain fixed in code.

## Ensemble members

Member 0 is the unperturbed trajectory, so a one-member design reproduces the single-trajectory run bit for bit. Member `m >= 1` starts from the same field, with `perturbed_cells` distinct positive entries moved by one ulp. The entries come from a SplitMix64 stream with state `mix(seed ^ mix(m))`, where `mix` is the SplitMix64 finalizer. Each draw adds `0x9E3779B97F4A7C15` and returns `mix(state)`. An entry index is `positive[(draw * count) >> 64]` over the positive entries in storage order, and a repeated index is drawn again. One more draw's low bit chooses `nextUp` (1) or `nextDown` (0). Only positive entries move, so no cell becomes newly occupied or negative. The perturbation applies to the seed-built initial state for seed-built studies and to the supplied field for field studies. Each member's `perturbation.json` records the entries, their directions and the sha256 of the perturbed start.

## Run directory

```text
RUN/
  design.json                 byte copy of the design
  receipt.json                build, backend, seeds, design sha256 and input sha256s
  receipt.completion.json     output hashes
  ensemble.json
  <specimen_id>/member-<m>/
    perturbation.json
    <branch>.json             frames every 32 steps, each with fieldSha256
    <branch>-step-<s>.f32, checkpoint.f32, ...   the study's fields, native [x][y][channel] Float32
```

Input files are referenced by sha256 in the receipt and are not copied into the run.

## ensemble.json

`conditions` has one entry per body and per branch named by a continuous outcome. Each entry lists every member's continuous values and binary verdicts and, for each binary outcome, `successes`, `defined`, `undefined`, `probability` and `wilson95`. A member whose window contains a frame with no thresholded body has a null value, and its verdicts are null. Null verdicts count as `undefined` and are excluded from the probability. `wilson95` is the Wilson score interval at z = 1.959963984540054, clamped to [0, 1].

`variance` splits each continuous outcome's population variance over all defined member values into `acrossMember` (mean squared deviation within each condition) and `acrossCondition` (count-weighted squared deviation of the condition means), which sum to `total`.

`repeatCheck` re-runs the first `repeat_check.members` members without writing files and compares the sha256 of every output file and every frame field. It records `compared`, `matched`, `matchRate` and the mismatched `body/member-m/output` names. The cpu engine is deterministic by contract, so on `cpu` any mismatch fails the run before `ensemble.json` is written. On `metal-full` the match rate is recorded as measured.

JSON outputs are written with sorted keys, so a repeated run reproduces them byte for byte.
