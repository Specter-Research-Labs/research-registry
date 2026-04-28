# Verification Matrix

`PR-01` freezes the current Wonton Soup surface before structural refactors. This is not a feature spec; it is a compact map of what exists today, which tests exercise it, and which families should keep representative smoke coverage as the runtime code shrinks.

## Command Families

| Family | Representative commands | Primary coverage today | Notes |
| --- | --- | --- | --- |
| Lean proving workflows | `lean run`, `lean basin`, `lean suite` | [`tests/test_cli_args.py`](../../../../dossiers/wonton-soup/tests/test_cli_args.py), [`prover/tests/test_wonton_cli_wrappers.py`](../../../../dossiers/wonton-soup/prover/tests/test_wonton_cli_wrappers.py) | Core orchestration surface; wrapper and help smoke should stay intact through refactors. |
| External backends | `run`, `e`, `vampire`, `z3`, `coq` | [`prover/tests/test_wonton_cli_wrappers.py`](../../../../dossiers/wonton-soup/prover/tests/test_wonton_cli_wrappers.py), [`prover/tests/test_wonton_validate_backend_args.py`](../../../../dossiers/wonton-soup/prover/tests/test_wonton_validate_backend_args.py) | Mostly wrapper-level today; keep one representative CLI smoke path. |
| Corpus pipeline | `corpus build-*`, `corpus validate`, `corpus list`, `corpus sweep-*` | [`corpus/tests/test_build_1000_plus.py`](../../../../dossiers/wonton-soup/corpus/tests/test_build_1000_plus.py), [`corpus/tests/test_selection.py`](../../../../dossiers/wonton-soup/corpus/tests/test_selection.py), [`corpus/tests/test_artifacts_list.py`](../../../../dossiers/wonton-soup/corpus/tests/test_artifacts_list.py) | Data-heavy builders do not need full end-to-end goldens; representative help and selection checks are enough. |
| Surface preservation | `spctr surface status`, `spctr surface refresh`, `spctr surface checkpoint` | [`ops/spctr/tests/surface.rs`](../../../../ops/spctr/tests/surface.rs), [`prover/tests/test_runtime_paths.py`](../../../../dossiers/wonton-soup/prover/tests/test_runtime_paths.py) | Agents should use the manifest-declared `wonton-lake` surface for cross-project preservation. |
| Lake indexing and exports | `lake reconcile`, `lake export-parquet`, `lake score-k` | [`analysis/tests/test_lake_smoke.py`](../../../../dossiers/wonton-soup/analysis/tests/test_lake_smoke.py), [`analysis/tests/test_export_parquet.py`](../../../../dossiers/wonton-soup/analysis/tests/test_export_parquet.py), [`analysis/tests/test_k_reference_score.py`](../../../../dossiers/wonton-soup/analysis/tests/test_k_reference_score.py) | Best current synthetic end-to-end surface. |
| Lake references and jobs | `lake reference build-outcomes`, `lake job run`, `lake job presets` | [`analysis/tests/test_lake_job.py`](../../../../dossiers/wonton-soup/analysis/tests/test_lake_job.py), [`analysis/tests/test_lake_job_config.py`](../../../../dossiers/wonton-soup/analysis/tests/test_lake_job_config.py) | Good target for typed-schema refactors; keep job config compatibility visible. |
| Analysis and reporting | `postprocess`, `verify-run-local`, `analyze`, `analysis`, `inspect-proof-ir` | [`analysis/tests/test_verify_run_local.py`](../../../../dossiers/wonton-soup/analysis/tests/test_verify_run_local.py), [`analysis/tests/test_inspect_proof_ir.py`](../../../../dossiers/wonton-soup/analysis/tests/test_inspect_proof_ir.py), [`analysis/tests/test_export_dashboard.py`](../../../../dossiers/wonton-soup/analysis/tests/test_export_dashboard.py) | Shared payload logic should keep these outputs aligned. |
| Comparison and benchmarks | `compare`, `compare-cross-assistant`, `benchmark-cross-assistant` | [`analysis/tests/test_cross_assistant_alignment.py`](../../../../dossiers/wonton-soup/analysis/tests/test_cross_assistant_alignment.py), [`analysis/tests/test_cross_assistant_paired_benchmark.py`](../../../../dossiers/wonton-soup/analysis/tests/test_cross_assistant_paired_benchmark.py) | High-value read model for future manifest/cohort work. |
| Meta and operator UX | `watch`, `list`, `setup` | [`tests/test_cli_args.py`](../../../../dossiers/wonton-soup/tests/test_cli_args.py), [`prover/tests/test_lean_setup.py`](../../../../dossiers/wonton-soup/prover/tests/test_lean_setup.py), [`prover/tests/test_wonton_logs_dir.py`](../../../../dossiers/wonton-soup/prover/tests/test_wonton_logs_dir.py) | These commands are thin, but they are part of the public operator surface. |

## Representative Golden Slices

The current suite is strong on wrappers and synthetic lake fixtures. Before larger refactors, the most important behavior slices to preserve are:

1. Lean run surface: command construction, help rendering, and argument wiring.
2. Sync surface: one representative status command and one aggregate push/pull command.
3. Lake surface: reconcile, reference build, and job run over a tiny synthetic log root.
4. Comparison surface: one cross-assistant benchmark/alignment path over synthetic fixtures.

Anything deeper than that should pay for itself with deletion, not with more scaffolding.
