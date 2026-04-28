# Metric Spec

## Primary Metrics

### 1) Search Efficiency (K)
- `K = log10(tau_blind / tau_agent)`
- `tau_blind` is the median `tau_proxy` across runs with `policy=blind` and `memory=off` for the same `(scenario, backend)`.
- `tau_agent` is per-run `tau_proxy` for directed policies.

`tau_proxy` is computed as:
- `tau_proxy = cumulative_goal_distance + 0.05 * cumulative_energy`

where each term is accumulated across all simulation steps.

Primary `DeltaK` compares `memory=on` against `memory=off`. The `memory=inertial_control`
condition is reported as an explicit control to separate damping-only persistence from
history-dependent material memory.

### 2) Memory Retention Index (MRI)
For `imprint` runs only:
- detect pulse window by `abs(drive_signal) >= 0.5 * max(abs(drive_signal))`
- baseline: pre-pulse `com_x`
- pulse response: mean `com_x` during pulse
- tail response: mean `com_x` in first post-pulse window
- `MRI = (tail - baseline) / (pulse - baseline)`

Interpretation:
- `MRI > 0`: persistent trace after pulse
- `MRI ~= 0`: no measurable retention

### 3) Hysteresis Loop Area (HLA)
For `hysteresis` runs only:
- treat `(drive_signal(t), com_x(t))` as a closed trajectory
- compute normalized contour area via discrete line integral
- normalize by `(drive span * response span)`

Interpretation:
- `HLA > 0`: path dependence
- larger values indicate stronger history dependence

## Confidence Intervals
- Bootstrap medians with 2000 resamples.
- 95% CI reported as `[low, high]`.
- If every seed yields the same value, report `kind=exact` with `low = high = median` instead of
  pretending there is a stochastic interval.

## Damage Recovery Index (DRI)
For `damage` runs only:
- read `damage_step` from the run `meta` record
- baseline: mean `goal_distance` in the pre-damage window
- spike: mean `goal_distance` immediately after damage
- tail: mean `goal_distance` in the final window
- `DRI = (spike - tail) / (spike - baseline)`

Interpretation:
- `DRI > 0`: recovery after perturbation
- `DRI ~= 0`: little net recovery
- `DRI < 0`: damage trace persists or worsens

## Acceptance Criteria
- `HLA.low > 0`
- `MRI.low > 0`
- At least 2 scenario/backend groups with `DeltaK_on_vs_off.low > 0`, where
  `DeltaK_on_vs_off = K_memory_on - K_directed_off`.

## Control-Separation Readout
- Report `DeltaK_on_vs_inertial_control = K_memory_on - K_inertial_control`.
- Track whether at least 2 scenario/backend groups have
  `DeltaK_on_vs_inertial_control.low > 0`.

## Related Docs
- [Experiment Matrix](./experiment-matrix.md)
