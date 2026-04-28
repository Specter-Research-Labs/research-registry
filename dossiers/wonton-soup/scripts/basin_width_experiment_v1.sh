#!/usr/bin/env bash
set -euo pipefail

# Basin-Width Correlation Experiment v1
# Tests the hypothesis: broader proof basins predict greater lesion resilience
#
# This script:
# 1. Creates a corpus from the curated 306 theorems with known multi-proof structure
# 2. Runs 20-seed basin sweeps to establish basin width distribution
# 3. Runs lesion interventions on the same theorems
# 4. Results can be analyzed to fit basin-width vs recovery correlation
#
# Run on quietbox via dispatch:
#   dispatch run --on quietbox --project specter-labs --sync-workspace --isolated-workspace \
#     --batch --name basin-width-v1 -- \
#     bash research-registry/dossiers/wonton-soup/scripts/basin_width_experiment_v1.sh \
#       --phase all --execute

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v lake >/dev/null 2>&1 && [ -x "${HOME}/.elan/bin/lake" ]; then
  export PATH="${HOME}/.elan/bin:${PATH}"
fi

if ! command -v uv >/dev/null 2>&1 && [ -x "${HOME}/.local/bin/uv" ]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi

if [[ -d "/shared/specter-runtime" ]]; then
  export SPECTER_RUNTIME_ROOT="${SPECTER_RUNTIME_ROOT:-/shared/specter-runtime}"
  export SPECTER_LOG_ROOT="${SPECTER_LOG_ROOT:-/shared/specter-runtime}"
  export SPECTER_ARTIFACT_ROOT="${SPECTER_ARTIFACT_ROOT:-/shared/specter-runtime}"
fi

EXECUTE=0
PHASE="all"

usage() {
  cat <<'USAGE'
Usage: scripts/basin_width_experiment_v1.sh [--execute] [--phase PHASE]

  --execute      Run commands (default is dry-run print only)
  --phase        One of:
                   all       Run all phases
                   corpus    Build corpus from curated theorems
                   basin     Run 20-seed basin sweeps
                   lesion    Run lesion interventions
                   analyze   Fit basin-width vs recovery correlation

Key parameters:
  PROGRAM_ID=basin-width-experiment-v1
  CURATED_THEOREMS=experiments/basin_width_curated_v1.json
  CORPUS_ID=basin-width-curated-v1
  BASIN_SEEDS=20
  PROVIDERS=reprover (single provider for cleaner correlation)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --phase) PHASE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

case "${PHASE}" in
  all|corpus|basin|lesion|analyze) ;;
  *) echo "Invalid --phase: ${PHASE}" >&2; usage; exit 2 ;;
esac

PROGRAM_ID="${PROGRAM_ID:-basin-width-experiment-v1}"
CURATED_JSON="${ROOT_DIR}/experiments/basin_width_curated_v1.json"
CORPUS_ID="${CORPUS_ID:-basin-width-curated-v1}"
BASIN_SEEDS="${BASIN_SEEDS:-20}"
LEAN_WORKERS="${LEAN_WORKERS:-8}"
RESEARCH_BUDGET="${RESEARCH_BUDGET:-standard}"
PROVIDER="${PROVIDER:-reprover}"

PROGRAM_RUN_ROOT="$(date +%Y-%m-%d)-${PROGRAM_ID}"

quote_cmd() {
  local out=""
  for token in "$@"; do
    if [[ -z "${out}" ]]; then
      out="$(printf '%q' "${token}")"
    else
      out="${out} $(printf '%q' "${token}")"
    fi
  done
  printf '%s\n' "${out}"
}

run_cmd() {
  echo "+ $(quote_cmd "$@")"
  if [[ "${EXECUTE}" -eq 1 ]]; then
    "$@"
  fi
}

phase_header() {
  echo
  echo "== $1 =="
}

build_corpus_from_curated() {
  phase_header "Build Corpus From Curated Theorems"

  if [[ ! -f "${CURATED_JSON}" ]]; then
    echo "Error: Curated theorems file not found: ${CURATED_JSON}" >&2
    exit 1
  fi

  local theorem_count
  theorem_count="$(python3 -c "import json; print(len(json.load(open('${CURATED_JSON}'))['theorems']))")"
  echo "Curated theorems: ${theorem_count}"

  local tmp_theorems="${ROOT_DIR}/experiments/.tmp_basin_width_theorems.txt"
  python3 -c "
import json
with open('${CURATED_JSON}') as f:
    data = json.load(f)
with open('${tmp_theorems}', 'w') as f:
    f.write('\n'.join(data['theorems']) + '\n')
"

  run_cmd uv run python wonton.py corpus build-lean-subset \
    --corpus-id "${CORPUS_ID}" \
    --source-ref "lean:solvable-1000-v1" \
    --theorems-path "${tmp_theorems}"
}

run_basin_sweeps() {
  phase_header "Run Basin Sweeps (${BASIN_SEEDS} seeds)"

  run_cmd uv run python wonton.py lean basin \
    --seeds "${BASIN_SEEDS}" \
    --blind \
    --sampling \
    -m research \
    -c "lean:${CORPUS_ID}" \
    -p "${PROVIDER}" \
    -b "${RESEARCH_BUDGET}" \
    --workers "${LEAN_WORKERS}" \
    --plain \
    --run-id "${PROGRAM_RUN_ROOT}/basin/provider=${PROVIDER}/seeds=${BASIN_SEEDS}" \
    --no-sync
}

run_lesion_interventions() {
  phase_header "Run Lesion Interventions"

  run_cmd uv run python wonton.py lean run \
    -m research \
    -c "lean:${CORPUS_ID}" \
    -p "${PROVIDER}" \
    -b "${RESEARCH_BUDGET}" \
    --workers "${LEAN_WORKERS}" \
    --plain \
    --run-id "${PROGRAM_RUN_ROOT}/lesions/provider=${PROVIDER}" \
    --no-sync
}

run_postprocess_and_reconcile() {
  phase_header "Postprocess and Reconcile"

  local logs_root
  logs_root="$(uv run python -c 'from runtime_paths import resolve_logs_root; print(resolve_logs_root().resolve())')"
  local logs_dir="${logs_root}/${PROGRAM_RUN_ROOT}"

  run_cmd uv run python wonton.py postprocess --logs-dir "${logs_dir}"
  run_cmd uv run python wonton.py lake reconcile --logs-dir "${logs_dir}"
}

analyze_correlation() {
  phase_header "Analyze Basin-Width vs Recovery Correlation"

  run_cmd uv run python -c "
import duckdb
import numpy as np
from scipy import stats

conn = duckdb.connect('/Volumes/Addenda/dev/specter-labs/wonton-soup/artifacts/lake/lake.duckdb', read_only=True)

# Join basin and intervention data
results = conn.execute('''
WITH basin_agg AS (
  SELECT theorem, AVG(unique_structures) as basin_width
  FROM basin_runs
  GROUP BY theorem
),
lesion_agg AS (
  SELECT theorem,
    AVG(CASE WHEN solved THEN 1.0 ELSE 0.0 END) as recovery_rate,
    COUNT(*) as n_interventions
  FROM theorem_intervention
  WHERE baseline_solved = TRUE
    AND intervention <> 'control_null'
    AND COALESCE(is_control, FALSE) = FALSE
  GROUP BY theorem
)
SELECT b.basin_width, l.recovery_rate, l.n_interventions
FROM basin_agg b
JOIN lesion_agg l USING(theorem)
WHERE l.n_interventions >= 3
''').fetchall()

if len(results) < 10:
    print(f'Insufficient data: only {len(results)} theorems with both basin and lesion data')
else:
    basin_widths = np.array([r[0] for r in results])
    recovery_rates = np.array([r[1] for r in results])

    # Pearson correlation
    r, p = stats.pearsonr(basin_widths, recovery_rates)
    print(f'Basin-Width vs Recovery Correlation')
    print(f'  n = {len(results)} theorems')
    print(f'  Pearson r = {r:.3f}')
    print(f'  p-value = {p:.4f}')
    print(f'  Basin width range: {basin_widths.min():.1f} - {basin_widths.max():.1f}')
    print(f'  Recovery rate range: {recovery_rates.min():.1%} - {recovery_rates.max():.1%}')
"
}

echo "Program ID:        ${PROGRAM_ID}"
echo "Curated theorems:  ${CURATED_JSON}"
echo "Corpus ID:         ${CORPUS_ID}"
echo "Basin seeds:       ${BASIN_SEEDS}"
echo "Provider:          ${PROVIDER}"
echo "Dry run mode:      $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"

if [[ "${PHASE}" == "all" || "${PHASE}" == "corpus" ]]; then
  build_corpus_from_curated
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "basin" ]]; then
  run_basin_sweeps
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "lesion" ]]; then
  run_lesion_interventions
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "analyze" ]]; then
  run_postprocess_and_reconcile
  analyze_correlation
fi
