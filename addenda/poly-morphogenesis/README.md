# Poly Morphogenesis

Julia implementation of the BITSEY reaction-diffusion controller, written as
composed RD, GRN-clear, and GRN-run phases.

The target is modest: reproduce the closed-loop peak-counting controller at the
algorithmic level, then express the phase composition with a small Poly-style
layer.

Start by running the test suite. The key result is the single-cut wiring
search near the end of this README.

The [report draft](docs/report-draft.md) develops the later 2D patch-isolation
experiment into a public narrative. Its [evidence audit](docs/report-audit.md)
records protocol corrections and the reproduction checks still needed before
publication; the original numerical sweep has not been rerun for that draft.

## Current Model

The implementation follows the executable `bitsey/RD` path:

- Werner-style Hill-ratio activator/inhibitor RD equations.
- `spread_pattern!`, matching BITSEY's `spread(shape, ions)` seeding rule for
  the `LH` template and official `cc_init` template pair.
- The paper's `1.21` diffusion rescaling.
- `linear_spread()` reseeding and `set_preseed_LXH()` boundary bias before each
  RD settle.
- Source Pre/Sig/amDr gate equations and the `GRN_N_peaks` readout convention
  over `pre*` in the head cell.

When source code and prose notes disagree, the executable source wins.

## Implementation Notes

- `compile_closed_loop_machine`: packages the RD phase, fast `pre_decay`
  GRN-clear phase, and normal counting-GRN phase into one controller.
- `ClosedLoopMachineState`: carries the RD field and GRN state across
  controller iterations.
- `PhaseState{<:AbstractCellState}`: typed execution state for the hot path.
- `hybrid_cell_object(:cell)`: one polynomial object with `rd`, `wave`, and
  `done` response schemas.

## Check

```bash
cd /path/to/research-registry
nix develop .#poly-morphogenesis
cd addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

The shell pins Julia 1.11 via `julia_111-bin`.

Optional upstream oracle:

```bash
POLY_RUN_UPSTREAM_ORACLE=1 julia --project=. -e 'using Pkg; Pkg.test()'
```

Set `POLY_ORACLE_PYTHON` if the Python interpreter with `numpy` is not the
repo-root `.venv/bin/python3`.

Optional full CLI smoke:

```bash
POLY_RUN_FULL_CLI_SMOKE=1 julia --project=. -e 'using Pkg; Pkg.test()'
```

## Tests

- `test/test_source_parity.jl`: source RD tables and controller behavior.
- `test/test_closed_loop.jl`: compiled controller phases and history.
- `test/test_phase_lenses.jl`: RD to wave to controller lens composition.
- `test/test_act_claims.jl`: severed-chain wiring laws.

The default suite checks the parity and law claims. The upstream oracle and full
demo sweep are opt-in because they are slower.

## Demos

```bash
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "rd-pattern", "--n-cells", "100", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "wave-count", "--peaks", "3"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "closed-loop", "--n-cells", "100", "--target-peaks", "5", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "bistability", "--n-cells", "100", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "cut-sweep", "--n-cells", "30", "--seed", "0", "--cut-count", "1"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "fragment-family", "--n-cells", "30", "--seed", "0", "--fragment-size", "6"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "severity-scan", "--n-cells", "30", "--seed", "0", "--d-a-values", "7.5,8.5,9.849732675807608", "--top-k", "1"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "wiring-k", "--n-cells", "30", "--seed", "0", "--trials", "4", "--cut-count", "1", "--target-top-k", "1"])'
```

## Current Result

The documented 20-cell top-severity example compares two precomputed rankings.
Connectivity ranks cut `10` first; outcome-based severity ranks cut `16` first.
With `--target-top-k 1`, the target is defined using that same severity ordering.
It therefore appears first in the severity ranking and twelfth in the connectivity
ranking. These are lookup positions after the outcome sweep, not end-to-end costs
of predicting an unseen outcome. Any predictive-efficiency comparison must include
the simulations needed to construct the severity ranking or use an independently
specified predictor.

The [implementation audit](docs/report-audit.md) distinguishes exact factorization
of the disconnected dynamics from claims about prospective prediction and biological
injury. The [revised report draft](docs/report-draft.md) preserves those limits.

The code uses Catlab wiring diagrams, AlgebraicDynamics where it fits, SciML
ODE integration for RD settling, and a custom Poly/dependent-lens layer for the
mode-dependent cell interface. It does not try to be a full BITSEY clone.
