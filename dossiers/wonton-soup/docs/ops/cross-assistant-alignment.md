# Cross-Assistant Alignment (Diagnostic)

`wonton.py compare-cross-assistant` aligns theorem outputs across two runs even when theorem names
do not overlap.

Diagnostic-only. The paired benchmark gate is documented in
`cross-assistant-paired-benchmark.md`.

Current implementation combines a kind-aware `ProofGraphIR` with lexical signals and theorem-level
proof aggregation.

Graph source is configurable per side:

- `wild_type_graph` (default)
- `search_trace_graph` (derived from `*_search_trace_graph.json`)
- `proof_term_graph` (derived from `wild_type_proof_term.json(.gz)`)
- theorem-level aggregation:
  - `single` (wild-type entries only; provider pools may still contribute multiple proofs/theorem)
  - `best_of` (minimum proof-pair distance)
  - `consensus` (median nearest-neighbor distance across pooled proofs)

## What It Uses

Per theorem, the aligner builds a compact signature from graph artifacts plus text metadata:

- graph kind (`search_trace`, `term_dag`, `unknown`)
- run-relative rank features (node/edge/depth/leaf/branching)
- edge-role profile (tactic-family roles for search traces, structural roles for term DAGs)
- motif profile (assistant-agnostic tactic/constructor action motifs)
- WL shape hash (`hash_shape`) used only for same-kind comparisons
- theorem-name tokens (including Lean item-id decoding, e.g. `x5f -> _`)
- statement/connective profile when statement text is available (Lean corpus items and Coq
  extraction via `coqtop` check fallback)

Distance is kind-aware:

- same-kind pairs use rank features + edge-role profile + shape hash
- cross-kind pairs suppress incompatible role/shape channels and rely on rank + lexical/connective
  channels

## Command

```bash
uv run python wonton.py compare-cross-assistant \
  --run-a <run_dir_a> \
  --run-b <run_dir_b> \
  --graph-source-a wild_type_graph \
  --graph-source-b wild_type_graph \
  --proof-aggregation single \
  --top-k 100 \
  --one-to-one \
  --output <report.json>
```

Useful options:

- `--solved-only`: only include solved wild-type theorems from each run
- `--top-k N`: candidate pool per theorem before assignment (use large values for one-to-one)
- `--one-to-one` / `--allow-many-to-one`
- `--graph-source-a`, `--graph-source-b`: choose `wild_type_graph`,
  `search_trace_graph`, or `proof_term_graph`
- `--proof-aggregation`: `single|best_of|consensus`
- `--max-proofs-per-theorem`: optional cap for pooled-proof modes
- `--name-obfuscation names`: obfuscate theorem/display/constant names in lexical channels
- `--lexical-ablation drop_tokens|graph_only`: remove lexical tokens only, or remove both lexical
  and connective channels to inspect graph-only behavior

## Output Contract

The JSON report contains:

- run metadata (`run_a`, `run_b`, theorem counts, proof counts)
- obfuscation metadata (`name_obfuscation`)
- lexical-ablation metadata (`lexical_ablation`)
- aggregation metadata (`proof_aggregation`, `max_proofs_per_theorem`)
- `matches` (selected theorem pairings with total distance, component distances, and
  reciprocal-top1 flag, representative proof pair, and proof support)
- `candidates_by_theorem_a` (top-k candidate list for each theorem in run A)
- summary stats including:
  - `mean_distance`, `mean_graph_distance`, `mean_lexical_distance`,
    `mean_connective_distance`
  - `mean_lexical_overlap`
  - `reciprocal_top1_rate`, `shape_hash_equal_rate`
  - `cross_kind_rate`
  - `kind_pair_distribution`
  - `top1_unique_rate` (collapse diagnostic)
  - run-level graph kind distributions (`run_a_graph_kind_distribution`,
    `run_b_graph_kind_distribution`)
  - lexical/statement coverage for each run

## Interpretation Notes

- Low distance means structural similarity under this signature family, not semantic equivalence.
- If many theorems in one run map to the same target theorem in the other run, the signature is
  likely too coarse for semantic translation claims.
- `top1_unique_rate` near zero indicates severe nearest-neighbor collapse.
- `shape_hash_equal_rate` is a strong signal when non-zero; zero across runs is expected when
  backends induce very different proof-object constructions.
- `cross_kind_rate = 1.0` means every selected pair is cross-kind (for example Lean search trace
  vs Coq proof-term DAG). In this regime, lexical/statement channels dominate and shape-equality is
  expected to be zero.
- For replayed Coq extraction runs, `search_trace_graph` is the closest proxy to Lean proof
  process/search behavior.
- `proof_term_graph` remains the better Coq-side term-structure diagnostic when you want
  constructor-level information rather than replay/process structure.
- `--lexical-ablation graph_only` is the quickest local stress test for whether the graph/action IR
  is carrying real alignment signal or just riding theorem text.
