# Pause Recap: 2026-03-23

## Current Technical State

- Cell-sorting parity is closed.
- Invagination bootstrap/state parity is closed.
- The best real invagination geometry compare is still the rtime-targeted run with:
  - `legacy_getot=5802`
  - `legacy_rtime=10.001060451284184`
  - `v2_getot=5819`
  - `v2_rtime=10.001343957631182`
  - `max_position_error=0.0023666159636699814`
- The remaining gap is not just a stop-condition mismatch.
- The v2 step trace shows a real adaptive-step drift at the same iteration count:
  - by step `2800`, v2 is behind legacy in accumulated `rtime` by `-0.040687847212914185`
  - the largest sampled checkpoint miss is at step `5600`, where
    `legacy_rtime=9.619808487305749` and `v2_rtime=9.577061519694343`
  - the sharpest 100-step trough is `2700-2800`, where legacy averages
    `delta=0.00253450` and v2 averages `delta=0.00214873`

## Artifacts

- `tmp/legacy-invagination-baseline-short/artifacts/invagination_v2_trace.txt`
- `tmp/legacy-invagination-baseline-short/artifacts/run.trace.stdout.log`
- `docs/parity-plan.md`

## Next Step

- Continue inside the recovered JJ workspace, not the old default checkout.
- Inspect and port the remaining force-scale logic that drives `dex` and therefore `delta`,
  especially in the simple-neighbor invagination lane around the `2700-2800` trough.
