# Log Query Cookbook

Operational query recipes for inspecting run artifacts.
Canonical file schemas live in [Log File Schemas](docs/contracts/logs/log-file-schemas.md).

## Reading Gzipped Files

Note: Use `gzcat` on macOS, `zcat` on Linux.

```bash
# View full contents
gzcat file.json.gz | jq .

# Pretty-print with less
gzcat file.json.gz | jq . | less

# Query specific fields
gzcat summary.json.gz | jq '.theorems[] | select(.wild_type.solved) | .name'

# Count nodes in proof term
gzcat wild_type_proof_term.json.gz | jq '.nodes | length'

# Search for text patterns in gzipped files
gzcat goal_cache.json.gz | rg "pattern"

# Extract just the keys
gzcat goal_cache.json.gz | jq 'keys'
```

For Python scripts, the analysis modules handle gzip transparently:
```bash
uv run python -c "
from analysis.summary import CorpusRun
from pathlib import Path
run = CorpusRun.load(Path('logs/corpus-.../'))
print(f'Solved: {len([t for t in run.theorems if t.wild_type_solved])}/{len(run.theorems)}')
"
```

---

## Interpretation Workflows

### 1. "How well did the run go?"

**Start with:** `summary.json.gz`

```bash
gzcat summary.json.gz | jq '{
  total: .aggregates.theorem_count,
  solve_rate: .aggregates.wild_type_solve_rate,
  interventions: .aggregates.intervention_count,
  int_rate: .aggregates.intervention_solve_rate
}'
```

**Check:**
- Wild-type solve rate (baseline capability)
- Intervention solve rate (robustness)
- If wild-type is low, check `failure_analysis.json` for patterns

**Red flags:**
- `MODEL_HALLUCINATION` > 0 suggests inference bugs (check provider settings)
- High `TACTIC_DESERT` suggests model lacks tactics for these goal types
- Wild-type much lower than expected suggests corpus mismatch or model issues

---

### 2. "Why did theorem X fail?"

**Start with:** `<theorem>/wild_type_history.json`

```bash
cat theorem_name/wild_type_history.json | jq '.iterations[-5:] | map({iteration, attempts: [.attempts[]? | {tactic, outcome}]})'
```

**Look for:**
- Last few tactics tried - are they sensible?
- `attempts[].outcome == "failure"` patterns - same tactic failing repeatedly?
- `attempts[].goal_type` near the end - is it within the model's capability envelope?

**Then check:** `<theorem>/wild_type_metrics.json`

```bash
cat theorem_name/wild_type_metrics.json | jq '{
  failure_ratio: .detour.failure_ratio,
  unique_tactics: .trajectory.tactic_diversity,
  max_depth: .trajectory.max_depth_reached
}'
```

**Interpretation:**
- `failure_ratio` > 0.8 with low `tactic_diversity` = model stuck in a rut
- `failure_ratio` > 0.8 with high `tactic_diversity` = genuinely hard problem
- `max_depth` = 0 means couldn't even make progress on root goal

---

### 3. "Did blocking tactic X change the proof?"

**Start with:** `<theorem>/<intervention>_comparison.json`

```bash
cat theorem_name/block_simp_comparison.json | jq '{
  ged: .ged_search_graph.value,
  iter_delta: .trajectory_diff.iteration_diff,
  new_axioms: .axiom_delta
}'
```

**Interpretation:**
- `ged = 0`: Identical proof structure (tactic wasn't used anyway)
- `ged` small (1-3): Minor variation, same approach
- `ged` large (>5): Significantly different proof found
- `axiom_delta` non-empty: Different lemmas used (interesting!)

**For deeper analysis:** Compare `wild_type_graph.json` vs `block_X_graph.json`

```bash
# Compare proof lengths
echo "Wild:" && cat wild_type_graph.json | jq '.nodes | length'
echo "Intervention:" && cat block_simp_graph.json | jq '.nodes | length'
```

---

### 4. "Is the model behaving consistently?"

**Start with:** `sheaf_analysis.json`

```bash
cat sheaf_analysis.json | jq '{
  consistency: .equiv_consistency,
  problematic_families: [.per_family_residual | to_entries[] | select(.value > 20)]
}'
```

**Interpretation:**
- `equiv_consistency` > 0.95: Model responds consistently to similar goals (good)
- `equiv_consistency` < 0.90: High variance, model is unreliable
- High `per_family_residual` for a tactic family = that tactic has unpredictable effects

**Check inconsistent cases:**
```bash
cat sheaf_analysis.json | jq '.inconsistent_cases[:5]'
```

These are goal signatures where the model behaves erratically.

---

### 5. "What tactics work for what goals?"

**Start with:** `goal_cache.json.gz`

```bash
# List all unique signatures
gzcat goal_cache.json.gz | jq '.entries | keys | length'

# See which signatures have the most occurrences
gzcat goal_cache.json.gz | jq '.entries | to_entries | map({sig: .key[:30], occs: (.value.occurrences | length)}) | sort_by(-.occs) | .[:10]'

# Check outcomes for a specific signature (family 2 = intro)
gzcat goal_cache.json.gz | jq '.entries["<sig>"].occurrences | to_entries[0].value.outcomes'
```

**From summary.json.gz** (aggregated tactic matrix):
```bash
# Which goal types saw the most tactic attempts
gzcat summary.json.gz | jq '.aggregates.goal_type_tactic_matrix | to_entries | map({goal: .key[:40], tactics: (.value | keys | length)}) | sort_by(-.tactics) | .[:10]'

# Success rate for "intro" on goals containing "→"
gzcat summary.json.gz | jq '.aggregates.goal_type_tactic_matrix | to_entries | map(select(.key | contains("→"))) | .[0].value | to_entries | map({tactic: .key, success: .value.success, fail: .value.failure})'
```

---

### 6. "How did the proof actually get constructed?"

**Start with:** `<theorem>/wild_type_assembly.json.gz`

```bash
# See the theorem and step count
gzcat theorem_name/wild_type_assembly.json.gz | jq '{theorem: .theorem[:60], steps: (.steps | length)}'

# Trace each step with goals closed/opened
gzcat theorem_name/wild_type_assembly.json.gz | jq '.steps | to_entries | .[] | "\(.key + 1). \(.value.tactic)  closed=\(.value.goalsClosed | length) opened=\(.value.goalsOpened | length)"'

# See which tactics closed goals
gzcat theorem_name/wild_type_assembly.json.gz | jq '.steps | map(select(.goalsClosed | length > 0)) | .[] | {tactic, closed: (.goalsClosed | length)}'
```

**What to look for:**
- Steps that close multiple goals (powerful tactics)
- Steps that open many goals (case splits, inductions)
- The order tactics are applied (strategy)

**For proof term analysis:**
```bash
# Count node types in final proof
gzcat theorem_name/wild_type_assembly.json.gz | jq '.finalTerm.nodes | group_by(.[1].kind) | map({kind: .[0][1].kind, count: length}) | sort_by(-.count)'

# Total nodes in proof term
gzcat theorem_name/wild_type_assembly.json.gz | jq '.finalTerm.nodes | length'

# Check for incomplete proofs (mvar nodes = holes)
gzcat theorem_name/wild_type_assembly.json.gz | jq '.finalTerm.nodes | map(select(.[1].kind == "mvar")) | length'
```

Common patterns:
- Many `app` nodes = lots of function application (typical)
- Many `lam` nodes = proof involves constructing functions
- `mvar` nodes = incomplete proof term (solved proofs are expected to have zero)

---

### 7. "Compare two corpus runs"

```bash
# Set up aliases for the two runs
RUN1="logs/corpus-2026-01-06-190731"  # ReProver
RUN2="logs/corpus-2026-01-07-120200"  # DeepSeek

# Compare overall solve rates
echo "Run 1:" && gzcat $RUN1/summary.json.gz | jq '.aggregates | {theorems: .theorem_count, rate: .wild_type_solve_rate}'
echo "Run 2:" && gzcat $RUN2/summary.json.gz | jq '.aggregates | {theorems: .theorem_count, rate: .wild_type_solve_rate}'

# Get theorem names that are solved in run1 but failed in run2
comm -23 \
  <(gzcat $RUN1/summary.json.gz | jq -r '.theorems[] | select(.wild_type.solved) | .name' | sort) \
  <(gzcat $RUN2/summary.json.gz | jq -r '.theorems[] | select(.wild_type.solved) | .name' | sort)

# Get theorem names that failed in run1 but solved in run2
comm -13 \
  <(gzcat $RUN1/summary.json.gz | jq -r '.theorems[] | select(.wild_type.solved) | .name' | sort) \
  <(gzcat $RUN2/summary.json.gz | jq -r '.theorems[] | select(.wild_type.solved) | .name' | sort)

# Compare intervention solve rates
gzcat $RUN1/summary.json.gz | jq '{run: "run1", interventions: .aggregates.intervention_count, rate: .aggregates.intervention_solve_rate}'
gzcat $RUN2/summary.json.gz | jq '{run: "run2", interventions: .aggregates.intervention_count, rate: .aggregates.intervention_solve_rate}'
```

---

### 8. "Find interesting intervention effects"

**Anisomorphic proofs** (structurally different when tactic blocked):

```bash
cat analysis_report.json | jq '.by_theorem[] | .theorem as $t | .interventions[] | select(.classification == "TYPE_B_ANISOMORPHIC") | {
  theorem: $t,
  intervention: .name,
  ged: .search_dynamics.ged_search_graph,
  wild_dag: .complexity.wild.dag_size,
  int_dag: .complexity.intervention.dag_size
}'
```

**Interventions that found simpler proofs:**
```bash
cat analysis_report.json | jq '.by_theorem[] | .theorem as $t | .interventions[] | select(.complexity.intervention.dag_size < .complexity.wild.dag_size) | {
  theorem: $t,
  intervention: .name,
  reduction: (.complexity.wild.dag_size - .complexity.intervention.dag_size)
}' | head -20
```

---

### 9. "Debug a specific proof attempt"

Full replay of what happened:

```bash
# 1. See the theorem
cat theorem_name/wild_type_history.json | jq -r '.theorem'

# 2. Trace each step
cat theorem_name/wild_type_history.json | jq -r '.iterations[] | .iteration as $i | .attempts[]? | "\($i): \(.tactic) -> \(.outcome)"'

# 3. Check where it got stuck
cat theorem_name/wild_type_history.json | jq '.iterations | map(select([.attempts[].outcome] | index("success") | not)) | .[0]'

# 4. See the proof graph structure
cat theorem_name/wild_type_graph.json | jq '{
  nodes: (.nodes | length),
  edges: (.edges | length),
  root_type: .nodes[0].type
}'
```

---

### Quick Reference: What File For What Question

| Question | File(s) |
|----------|---------|
| Overall success rate | `summary.json.gz` |
| Why did X fail? | `X/wild_type_history.json`, `failure_analysis.json` |
| Did blocking Y matter? | `X/block_Y_comparison.json` |
| Model consistency | `sheaf_analysis.json`, `goal_cache.json.gz` |
| Proof structure | `X/wild_type_assembly.json.gz` |
| Tactic patterns | `goal_cache.json.gz`, `summary.json.gz` (goal_type_tactic_matrix) |
| Compare interventions | `X/ged_matrix.json`, `analysis_report.json` |
