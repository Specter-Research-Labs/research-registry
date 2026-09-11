# Report evidence audit

September 2026. Code and draft inspection; no simulation rerun.

The report narrative is in [report-draft.md](report-draft.md). Preserve the original Typst draft as the record of its earlier claims until reproduction resolves them.

| Draft claim or presentation | Implementation evidence | Editorial consequence |
| --- | --- | --- |
| Settle the connected graph, then sever it | `grid_patch_isolation_demo` passes `initial_state`, not `connected` state, to `_factorized_graph_snapshot` | Describe altered wiring from initialization, not injury to a mature pattern. |
| Compositional ranking predicts severity | `_calibrate_severity!` uses simulated outcome measurements and per-regime maxima across all candidates | Present a retrospective outcome map. A prospective ranking needs an independently fixed score or explicit simulation cost accounting. |
| Winner differs from connectivity winner in most regimes | Connectivity ties are broken by `placement.top`, then `placement.left` | Remove winner-disagreement rates as headline evidence. Show within-tie variation and compare against random tie-breaking if evaluating search efficiency. |
| Robust vulnerability ordering | Tables summarize ranges and winner disagreement, not agreement between severity rankings | Say that variation persists under the reported metrics; measure rank correlations and winner stability before claiming ordering robustness. |
| Exact factorization | Disconnected graph ODEs have no cross-component terms | Distinguish exact equations from numerical output agreement. Check full versus separate integration at fixed time and with early stopping. |
| Every simulation settles | Integrator can stop on derivative tolerance or at time 300; return codes are not inspected by snapshot wrappers | Save solver status, termination time, and final derivative norm. Do not call all endpoints equilibria without those checks. |
| 480 regimes / 4320 threshold-metric cases | Counts match the stated Cartesian products; original raw outputs were not found locally | Treat numbers as draft-reported until a per-placement export and aggregation reproduce the tables. |
| Category theory supplies predictive advantage | No matched graph-solver performance or prospective-prediction comparison appears in the experiment | Explain composition concretely; do not infer an empirical advantage from a flat scalar connectivity baseline. |

## Reproduction sequence

1. Restore the declared Julia 1.11 environment and run existing graph/factorization tests. The README references a Nix shell that must be checked against the current repository configuration.
2. Reproduce the fifteen 2x2 placements on the 4x6 grid at seed 33, activator diffusion 1.0, inhibitor diffusion 30. Save initial and final fields, cut edges, component membership, raw metrics, solver status, and derivative norms.
3. Compare direct disconnected integration with separately integrated components. Use identical terminal times first; assess the effect of independent early stopping separately.
4. Reproduce the 480-regime sweep. Derive all three thresholds and all three metrics from exported fields, without unnecessarily rerunning unchanged dynamics.
5. Recompute raw and normalized ranges. Add cross-metric ranking agreement; drop arbitrary connectivity winner-disagreement summaries.
6. Generate the linked grid/field comparison and sweep distributions from those exports. Only then replace the draft status with a dated, reproducible report and link it from Writing and Addenda.

The mature-pattern injury extension is a separate experiment, not a silent correction to the original protocol.
