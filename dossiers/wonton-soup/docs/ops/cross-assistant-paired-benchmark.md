# Cross-Assistant Paired Benchmark (Primary Gate)

`wonton.py benchmark-cross-assistant` is the primary cross-assistant quality gate.

Unlike unpaired nearest-neighbor alignment, this benchmark evaluates against an explicit Lean↔Coq
pair set and reports retrieval metrics (`Recall@k`, `MRR`, rank stats) globally and by kind
(`same_kind`, `cross_kind`).

Graph source is configurable per side:

- `wild_type_graph` (default): search/proof graph artifact
- `search_trace_graph`: derived from replayed `*_search_trace_graph.json`
- `proof_term_graph`: derived from `wild_type_proof_term.json(.gz)` term DAG
- theorem-level proof aggregation: `--proof-aggregation single|best_of|consensus`
- optional proof cap: `--max-proofs-per-theorem N` (used when aggregation is not `single`)
- gate claim selector: `--gate-claim all|global|cross_kind|same_kind`
- gate axis selector: `--gate-axis all|coverage|quality`

Run Coq-backed extraction and paired benchmarks from `dossiers/wonton-soup/` inside the local
project shell (`nix develop` or `direnv allow`) so the toolchain is pinned and `coqc`, `coqtop`,
`sertop`, and `coq-lsp` are all present.

## Benchmark Asset

- Pair spec: `analysis/benchmarks/lean_coq_logic_micro_v1.json`
- Pair count: `84`
- Gate thresholds (in-file):
  - `min_recall_at_1 = 0.02`
  - `min_recall_at_10 = 0.30`
  - `min_mrr = 0.12`
  - `gate.by_kind.cross_kind`: separate thresholds for cross-kind claims
  - `gate.by_kind.same_kind`: optional minimum support threshold

## End-to-End Runbook

1. Build the Lean paired corpus from the pair spec.

```bash
uv run python wonton.py corpus build-lean-coq-paired-micro \
  --corpus-id coq-paired-micro-v1 \
  --pairs-path analysis/benchmarks/lean_coq_logic_micro_v1.json
```

2. Run Lean on that corpus (wild-type only, deterministic run id recommended).

```bash
uv run python wonton.py lean run \
  -m dev \
  -p heuristic \
  -c lean:coq-paired-micro-v1 \
  -n 84 \
  --wild-only \
  --run-id 2026-03-02-coq-paired-lean-heuristic
```

3. Build Coq theorem list from the same pair spec and run Coq extraction.

```bash
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
```

4. Run the paired benchmark gate.

Set `SPECTER_SYNTHETIC_BUREAU_ROOT` first if you keep generated reports in the private sibling repo.

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --proof-aggregation single \
  --gate-claim all \
  --gate-axis all \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark.json"
```

If any threshold fails and `--fail-on-gate` is enabled (default), command exit code is non-zero.

### Same-Kind (Term-DAG vs Term-DAG) Diagnostic

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --graph-source-lean proof_term_graph \
  --graph-source-coq proof_term_graph \
  --solved-only \
  --gate-claim same_kind \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_same_kind_term_dag.json" \
  --no-fail-on-gate
```

Use this to inspect `summary.by_kind.same_kind` directly.

### Multi-Proof Theorem Matching

When a run includes solved intervention variants (`<name>_graph.json` / `<name>_proof_term.json`),
you can evaluate theorem pairs with pooled proof artifacts:

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --proof-aggregation best_of \
  --max-proofs-per-theorem 4 \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_best_of.json"
```

Aggregation modes:

- `single`: use wild-type entries only (provider pools may still contribute multiple proofs/theorem)
- `best_of`: theorem distance is the minimum proof-to-proof distance
- `consensus`: theorem distance is median nearest-neighbor distance across both proof pools

### Name-Obfuscated Stress Run

To reduce theorem-name leakage and force stronger graph contribution:

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --name-obfuscation names \
  --name-obfuscation-salt wonton-obf-v1 \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_obfuscated.json"
```

This obfuscates theorem/display/constant names in lexical channels while preserving pair identity.

### Lexically Ablated Stress Runs

To test whether the proof/tactic IRs still carry signal after removing lexical overlap:

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --lexical-ablation drop_tokens \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_drop_tokens.json"
```

For a graph-only stress run, remove both lexical tokens and connective profiles:

```bash
uv run python wonton.py benchmark-cross-assistant \
  --run-lean /abs/path/to/lean/run \
  --run-coq /abs/path/to/coq/run \
  --pairs analysis/benchmarks/lean_coq_logic_micro_v1.json \
  --lexical-ablation graph_only \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_graph_only.json"
```

The report records the chosen mode under `lexical_ablation.mode`.

For replayed Coq extraction runs, prefer `--graph-source-coq search_trace_graph` when you want the
closest available proxy to Lean proof-process structure. Use `proof_term_graph` when you want a
term-structure diagnostic instead.

### Coverage vs Quality Gate Axes

Use `--gate-axis coverage` to enforce only support/coverage thresholds (for example
`min_pairs_evaluated`, `min_eval_rate`) and `--gate-axis quality` to enforce only ranking metrics.
`--gate-axis all` enforces both.

The report includes:

- `summary.cohorts.global` with denominator = all benchmark pairs
- `summary.cohorts.same_kind` / `summary.cohorts.cross_kind` with denominators restricted to rows
  where both theorems are present and the representative aggregated pair falls in that kind

## Diagnostic Companion

Keep unpaired alignment as a diagnostic only:

```bash
uv run python wonton.py compare-cross-assistant \
  --run-a /abs/path/to/lean/run \
  --run-b /abs/path/to/coq/run \
  --top-k 84 \
  --one-to-one \
  --output "$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_alignment_diagnostic.json"
```

Use this report to inspect collapse/coverage behavior, not as the release gate.

## Theorem-Level Inspection

When one benchmark pair looks surprising, inspect the theorem directly:

```bash
uv run python wonton.py inspect-proof-ir \
  --run-dir /abs/path/to/lean/run \
  --theorem <lean_theorem> \
  --compare-run-dir /abs/path/to/coq/run \
  --compare-theorem <coq_theorem>
```

This prints the typed action trace, graph-IR profiles, and pair-distance components for that
specific theorem pair.
