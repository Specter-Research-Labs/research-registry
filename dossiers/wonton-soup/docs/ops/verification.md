# Verification

Use this page for release checks, representative command coverage, and run
inspection.

## Standard Check

From `dossiers/wonton-soup/`:

```bash
./scripts/verify.sh
```

Fast local smoke:

```bash
uv run python wonton.py lean run -m dev --sample 5 --seed 123
```

## Command Coverage

| Family | Representative commands | Primary tests |
| --- | --- | --- |
| Lean proving | `lean run`, `lean basin`, `lean suite` | `tests/test_cli_args.py`, `prover/tests/test_wonton_cli_wrappers.py` |
| External backends | `run`, `e`, `vampire`, `z3`, `coq` | `prover/tests/test_wonton_cli_wrappers.py`, `prover/tests/test_wonton_validate_backend_args.py` |
| Corpus | `corpus build-*`, `corpus validate`, `corpus list`, `corpus sweep-*` | `corpus/tests/test_build_1000_plus.py`, `corpus/tests/test_selection.py`, `corpus/tests/test_artifacts_list.py` |
| Lake | `lake reconcile`, `lake export-parquet`, `lake score-k`, `lake job run` | `analysis/tests/test_lake_smoke.py`, `analysis/tests/test_export_parquet.py`, `analysis/tests/test_lake_job.py`, `analysis/tests/test_k_reference_score.py` |
| Analysis | `postprocess`, `verify-run-local`, `analyze`, `inspect-proof-ir` | `analysis/tests/test_verify_run_local.py`, `analysis/tests/test_inspect_proof_ir.py`, `analysis/tests/test_export_dashboard.py` |
| Comparison | `compare`, `compare-cross-assistant`, `benchmark-cross-assistant` | `analysis/tests/test_cross_assistant_alignment.py`, `analysis/tests/test_cross_assistant_paired_benchmark.py` |
| Preservation | `spctr surface status`, `spctr surface refresh`, `spctr surface checkpoint` | `ops/spctr/tests/surface.rs`, `prover/tests/test_runtime_paths.py` |

Larger refactors should preserve four slices: Lean run wiring, one preservation
path, one synthetic lake job, and one cross-assistant comparison path.

## Cross-Assistant Gate

`wonton.py benchmark-cross-assistant` is the primary Lean/Coq quality gate. It
uses an explicit pair set and reports `Recall@k`, `MRR`, rank stats, and
same-kind/cross-kind cohorts.

- pair spec: `analysis/benchmarks/lean_coq_logic_micro_v1.json`
- pair count: `84`
- gate thresholds live in the pair spec

Run from `dossiers/wonton-soup/` inside the pinned shell.

```bash
uv run python wonton.py corpus build-lean-coq-paired-micro \
  --corpus-id coq-paired-micro-v1 \
  --pairs-path analysis/benchmarks/lean_coq_logic_micro_v1.json

uv run python wonton.py lean run \
  -m dev \
  -p heuristic \
  -c lean:coq-paired-micro-v1 \
  -n 84 \
  --wild-only \
  --run-id 2026-03-02-coq-paired-lean-heuristic

jq -r '.pairs[].coq_theorem' analysis/benchmarks/lean_coq_logic_micro_v1.json \
  > /tmp/wonton_coq_pairs_theorems.txt

cat >/tmp/wonton_coq_pairs_imports.v <<'EOF'
Require Import Coq.Init.Logic.
Require Import Coq.Init.Datatypes.
Require Import Coq.Bool.Bool.
Import Bool.
EOF

uv run python wonton.py run \
  --backend coq \
  --coq-mode file \
  --source /tmp/wonton_coq_pairs_imports.v \
  --theorem-file /tmp/wonton_coq_pairs_theorems.txt \
  --serapi-binary sertop \
  --log-dir logs/2026-03-02-coq-paired-coq-logic-v3

uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --proof-aggregation single \
  --gate-claim all \
  --gate-axis all \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark.json"
```

`compare-cross-assistant` is diagnostic only. It is useful for collapse,
coverage, lexical-ablation, and graph-source stress checks; it is not the
release gate.

## Run Inspection

Use `gzcat` on macOS and `zcat` on Linux.

Overall run quality:

```bash
gzcat summary.json.gz | jq '{
  total: .aggregates.theorem_count,
  solve_rate: .aggregates.wild_type_solve_rate,
  interventions: .aggregates.intervention_count,
  int_rate: .aggregates.intervention_solve_rate
}'
```

Last tactics for a failed theorem:

```bash
cat theorem_name/wild_type_history.json |
  jq '.iterations[-5:] | map({iteration, attempts: [.attempts[]? | {tactic, outcome}]})'
```

Intervention effect:

```bash
cat theorem_name/block_simp_comparison.json | jq '{
  ged: .ged_search_graph.value,
  iter_delta: .trajectory_diff.iteration_diff,
  new_axioms: .axiom_delta
}'
```

Proof assembly:

```bash
gzcat theorem_name/wild_type_assembly.json.gz |
  jq '.steps | to_entries | .[] | "\(.key + 1). \(.value.tactic) closed=\(.value.goalsClosed | length) opened=\(.value.goalsOpened | length)"'
```

If a one-off query becomes part of a release workflow, move it into
`analysis/` or a lake job preset.
