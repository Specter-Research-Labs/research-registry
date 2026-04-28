# Poly Morphogenesis

This addendum is a Julia workbench for the "RD cell as polynomial functor" proof of concept.

It has four goals:

- represent mode-dependent cell interfaces with a small custom Poly layer
- compile active modes into fixed-port executable machines
- use AlgebraicJulia wiring/composition for the executable phase programs
- reproduce the closed-loop reaction-diffusion peak-counting controller at the algorithmic level

The claim is now source-oriented rather than metaphorical. This addendum aligns all three executable
phases to the BITSEY code path behind Grodstein, McMillen, and Levin (2023):

- the RD phase follows the Werner-style Hill-ratio activator/inhibitor model used in `bitsey/RD`
- the RD initializer now includes a source-style `spread_pattern!` that mirrors BITSEY's
  `spread(shape, ions)` seeding rule over both the simple `LH` template and the official `cc_init`
  template pair used in the what-sticks experiments
- the controller uses the paper's `1.21` diffusion rescaling, `linear_spread()` reseeding rule,
  and `set_preseed_LXH()` boundary bias before each RD settle
- the counting wave uses the source Pre/Sig/amDr gate equations and the source `GRN_N_peaks`
  readout convention over `pre*` in the head cell

When fetched executable source and prose notes disagree, the executable source wins. The parity suite
now follows the actual BITSEY `linear_spread()+set_preseed_LXH()+sim(300)` outcomes rather than the
stale summary values in `RD_0readme.txt`.

The default closed-loop implementation now follows the fetched `bitsey/RD` controller more closely:

- the counting wave reads raw RD activator values by default rather than renormalizing them
- the first controller loop applies the source diffusion decrease plus `linear_spread()` bootstrap
- the RD field length scales as `40 * n_cells / 200` in the closed-loop configuration so the source
  cell spacing is preserved across tissue sizes
- the source-timed controller loop now uses the source explicit adaptive step policy
  (`base_dt = 5e-5`, `max_delta_cc = 3e-3`) across both the RD settle and the GRN clear/run phases

The controller is now compiled as a typed hybrid machine rather than an outer handwritten loop:

- `compile_closed_loop_machine` packages one RD compiled phase, a fast-`pre_decay` GRN-clear phase,
  and a normal counting-GRN phase into a single executable controller object
- `ClosedLoopMachineState` carries both the RD field and the GRN execution state across iterations,
  so the Julia loop mirrors BITSEY's "clear the previous GRN, then seed and run again" semantics
- the core execution path now accepts typed `PhaseState{<:AbstractCellState}` values instead of
  requiring `Dict{Symbol,Any}` node states in hot paths

Executable correspondence checks are explicit in the code and tests:

- `hybrid_cell_object(:cell)` is a single polynomial object with distinct `rd`, `wave`, and `done`
  response schemas
- `spread_pattern!` seeds RD tissues with the same alternating-shape interpolation rule used by
  BITSEY's `spread(shape, ions)` so the what-sticks experiments are reproducible inside Julia
- `test/test_closed_loop.jl` now checks the compiled controller machine's separate GRN-clear and
  GRN-run phases as well as the recorded controller history
- `wiring_bistability_demo()` holds the cell law and diffusion scale fixed and changes only the chain
  wiring, showing `LH` for the connected tissue and `LHLH` for the severed tissue
- `test/test_source_parity.jl`, `test/test_phase_lenses.jl`, and `test/test_act_claims.jl` lock down
  documented RD tables, RD→wave→controller lens composition, and severed-chain wiring laws
- the source-parity suite now follows the executable upstream code path rather than the stale
  prose summary in `RD_0readme.txt`, including the high-`L` `linear_spread()+set_preseed_LXH()`
  cases

## Toolchain

Use the repo root flake shell:

```bash
cd /path/to/research-registry
nix develop .#poly-morphogenesis
cd addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

That shell pins Julia 1.11 via nixpkgs' `julia_111-bin`, matching the package compat and manifest.

The vendored Python oracle for `grn_count1.py` is intentionally heavier than the default Julia suite,
because it runs the original explicit BITSEY simulator in a subprocess. Run it explicitly when you want
loop-by-loop controller parity against the upstream code:

```bash
POLY_RUN_UPSTREAM_ORACLE=1 julia --project=. -e 'using Pkg; Pkg.test()'
```

If your Python with `numpy` is not at the repo-root `.venv/bin/python3`, point
`POLY_ORACLE_PYTHON` at the interpreter you want the oracle test to use.

That oracle compares the Julia controller trace against the vendored upstream Python trace on matching
observables, including source-physical `D_A`/`D_I`, RD profiles, head-cell `pre*`, and the stop rule.

The default CLI test covers one representative demo path plus help and parser errors. The full
demo-command smoke sweep is opt-in:

```bash
POLY_RUN_FULL_CLI_SMOKE=1 julia --project=. -e 'using Pkg; Pkg.test()'
```

That keeps the default suite focused on the parity/law claims rather than repeatedly rerunning every
demo workflow.

## Planned demos

- `demo rd-pattern`
- `demo wave-count`
- `demo closed-loop`
- `demo bistability`
- `demo cut-sweep`
- `demo fragment-family`
- `demo severity-scan`
- `demo wiring-k`

Example commands:

```bash
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "rd-pattern", "--n-cells", "100", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "wave-count", "--peaks", "3"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "closed-loop", "--n-cells", "100", "--target-peaks", "5", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "bistability", "--n-cells", "100", "--seed", "0"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "cut-sweep", "--n-cells", "30", "--seed", "0", "--cut-count", "1"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "fragment-family", "--n-cells", "30", "--seed", "0", "--fragment-size", "6"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "severity-scan", "--n-cells", "30", "--seed", "0", "--d-a-values", "7.5,8.5,9.849732675807608", "--top-k", "1"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "wiring-k", "--n-cells", "30", "--seed", "0", "--trials", "4", "--cut-count", "1", "--target-peaks", "2"])'
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "wiring-k", "--n-cells", "30", "--seed", "0", "--trials", "4", "--cut-count", "1", "--target-top-k", "1"])'
```

`cut-sweep` now uses exact severed-chain factorization: each cut response is assembled from independently settled contiguous segments rather than rerunning the full severed chain for every candidate, and the output includes both connectivity-ranked and decomposition-ranked orderings. For small candidate families, the factorized path is auto-validated against direct severed-chain simulation and reports that in `validation_scope` / `validation`. `wiring-k` compares three orderings over the same intervention family: blind random order, the original connectivity-loss heuristic, and a decomposition-ranked order based on calibrated phenotypic severity.

`fragment-family` fixes a middle fragment size and slides that isolated fragment through the tissue, so double-cut questions can be asked without changing the size of the central severed component. `severity-scan` repeats the decomposition ranking over a supplied `D_a` grid and returns both a compact best-cut trace and the `D_a` intervals where the top-ranked cut family changes.

Two `wiring-k` targets are useful:

- `--target-peaks N` asks for any intervention that lands in a specified attractor class.
- `--target-top-k 1` asks for the most catastrophic cut under the decomposition-ranked severity functional, which is the sharper predictive question when many cuts all produce the same peak count.

In the verified 20-cell single-cut top-severity check, the connectivity heuristic ranks cut `10` first, while the decomposition-ranked severity functional ranks cut `16` first. Under `--target-top-k 1`, the decomposition policy finds the target in one test and the connectivity policy needs twelve. That is the first nontrivial prediction this addendum now makes.

## Scope

- Catlab wiring diagrams and AlgebraicDynamics execution where they fit
- SciML ODE integration for RD settling
- custom Poly/dependent-lens layer for mode-dependent interfaces
- source alignment against `bitsey/RD/RD.py`, `bitsey/RD/grn_count1.py`, and `bitsey/RD/werner_common.py`
- reproducible 100-cell closed-loop convergence for target peak counts `1` through `5`
- reproducible connected-versus-severed wiring split from `LH` to `LHLH` at fixed diffusion scale
- single-cut wiring sweep and intervention-search K over cut orderings derived from the chain wiring, including top-severity search for the most catastrophic cuts

## Non-goals

- no full BITSEY clone
- no symbolic PDE stack
- no plotting or GUI in v1
- no claim that this already captures full planarian regeneration biology beyond the minimal wiring-driven attractor split
