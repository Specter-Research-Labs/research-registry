# Follow-Up Run Program (March 2026)

Provides the operational answer to the follow-up thesis constraints in
`site/blog/wonton-soup-follow-up/index.md`:

- broaden theorem coverage to hundreds of shared items,
- pair centralized and distributed MCTS on matched slices,
- expand basin coverage (wide and deep),
- add external-backend pilots,
- score with explicit locked references.

The intended read of the phases follows the main dossier framing. Centralized MCTS establishes the structural baseline for the shared theorem slice. Distributed MCTS then tests whether coordination changes access to that same landscape. The program is not organized around two unrelated search systems; it is organized around one proof-space model with two control regimes.

## Entry Point

Use:

```bash
cd dossiers/wonton-soup
scripts/followup_run_program.sh
```

The script defaults to dry-run and prints every command.
Run with `--execute` to actually launch.

For deepseek provider on an external artifacts volume, set:

```bash
DEEPSEEK_ARTIFACT_ROOT=/path/to/specter-archive
```

This root must contain:
`wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-bf16`.

## Cohort Contract

- Program namespace: `PROGRAM_ID` (default: `followup-2026-03`)
- All run ids are nested under `PROGRAM_ID/...`.
- Lake/postprocess/K commands are scoped to one logs root:
  `resolve_logs_root()/<PROGRAM_ID>`
- Run-id date prefix is frozen at program start, so cohorts do not split at UTC date rollover.
- Use one pinned Lean corpus ref (`LEAN_CORPUS_REF`) across phases.
  Prefer a pinned artifact ref such as `lean:<corpus_id>@<build_id>#feasible`.

## Phases

`scripts/followup_run_program.sh --phase p1 --execute`

- `p1`: shared Lean panel (centralized MCTS), provider parity (`reprover/heuristic/deepseek`)
- `p2`: paired centralized vs distributed MCTS on matched theorem slice to measure coordination effects against the `p1` baseline
- `p3`: basin wide (`--seeds 10 --blind`) on the broad panel
- `p4`: basin deep (`--seeds 50 --blind`) on a focused subset
- `p5`: external backend pilots (`e`, `vampire`, `z3`, optional `coq stdlib`)
- `p6`: `postprocess` + `lake reconcile` scoped to this cohort logs root
- `p7`: locked-reference K jobs via lake job presets

Run all phases in order:

```bash
scripts/followup_run_program.sh --execute
```

## K Calibration Presets

Phase `p7` executes:

- `analysis/lake/presets/73_followup_k_ref_reprover_v1.json`
- `analysis/lake/presets/74_followup_k_ref_deepseek_v1.json`
- `analysis/lake/presets/75_followup_k_ref_heuristic_v1.json`
- `analysis/lake/presets/76_followup_k_ref_pooled_v1.json`

Each preset:

- selects completed Lean runs from this cohort logs root,
- builds an explicit goal-outcomes reference (provider-specific or pooled),
- scores K against that reference,
- exports deterministic JSONL datasets for row-level and aggregate analysis.

## External Backend Inputs

`p5` is opt-in (`ENABLE_EXTERNAL_PILOTS=1`) and uses:

- `TPTP_ROOT` for `e` and `vampire`
- `SMTLIB_ROOT` for `z3`
- `ENABLE_COQ_STDLIB=1` for Coq stdlib pilot

Unset inputs are skipped explicitly (fail-loud behavior by phase output).
