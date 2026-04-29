# Parity Targets

Parity means a benchmark lane keeps the legacy state variables, update order,
event semantics, and numerical mode that change its output. Old storage layout
and old APIs are not part of the target unless a lane depends on them.

## Active Lanes

| Lane | Target | Status |
| --- | --- | --- |
| cell sorting | mesenchymal contacts, RK4 mechanics, post-mechanics noise | trajectory comparison wired |
| invagination | epithelial bootstrap, fixed topology, early mechanics | bootstrap/state comparison wired; geometry open |

Recorded baseline:

- cell sorting passed the declared 5% trajectory tolerance across 101 staged
  frames.
- invagination bootstrap matched exactly.
- invagination at `rtime~=10` matched the summary fields, but geometry drift
  remained: `max_position_error=0.18375603110506017`,
  `mean_position_error=0.04696190706123148`,
  `rms_position_error=0.059864304491794515`.

## Legacy Files

Start with these legacy files:

- `src/core/model.mod.f90`: `iteracio`, the scheduler.
- `src/core/biomechanic.mod.f90`: force accumulation and integration.
- `src/core/neighboring.mod.f90`: contact candidate construction.
- `src/core/genetic.mod.f90`: gene and diffusion semantics where a lane uses
  them.
- `src/core/nexus.mod.f03`: gene-to-behavior updates.
- `src/core/growth.mod.f90`, `mitosis.mod.f90`, `death.mod.f90`, `ecm.mod.f90`:
  topology and cell-state events for later lanes.

For active lanes, preserve behavior that changes benchmark summaries. Ignore
legacy APIs that only expose old indexing conventions.

## Comparisons

Compare structured outputs:

- counts over time,
- selected node or cell summary fields,
- centroids and geometry error when the lane needs shape parity,
- event counts when topology changes enter the lane.

Screenshots are not a parity check for this addendum.

## Non-Goals

- no GUI runtime,
- no full EmbryoMaker rewrite claim,
- no compatibility layer for every historical snapshot shape,
- no preservation of old Fortran storage layout unless a benchmark depends on
  it.
