#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v lake >/dev/null 2>&1 && [ -x "${HOME}/.elan/bin/lake" ]; then
  export PATH="${HOME}/.elan/bin:${PATH}"
fi

EXECUTE=0
POOL_ID="${POOL_ID:-step1-rerun-2026-03}"
PAIRS_PATH="${PAIRS_PATH:-${ROOT_DIR}/analysis/benchmarks/lean_coq_logic_micro_v1.json}"
OUTPUT_STEM="${OUTPUT_STEM:-cross_assistant_paired_benchmark_step1_rerun}"
COQ_RUN="${COQ_RUN:-}"
POOL_DIR="${POOL_DIR:-${ROOT_DIR}/tmp/lean-provider-pool-${POOL_ID}}"
LOGS_ROOT=""
declare -a RUN_SPECS=()

usage() {
  cat <<'USAGE'
Usage: scripts/run_cross_assistant_step1_suite.sh [--execute] [--run label=/abs/path]...

Build a synthetic multi-provider Lean run root, then run the paired Lean↔Coq
benchmark suite used for the step-1 cross-assistant gate.

Default behavior is dry-run. Use --execute to create the pool dir and write the
benchmark JSON reports under the synthetic-bureau sibling repo.

Options:
  --run label=/abs/path   Add one Lean run to the provider pool. May be repeated.
  --coq-run /abs/path     Override the Coq run dir.
  --pool-dir /abs/path    Override the provider-pool root.
  --output-stem NAME      Prefix for synthetic-bureau *.json outputs.
  --execute               Run commands instead of printing them.
  -h, --help              Show this help.

Environment:
  POOL_ID                 Provider-pool suffix (default: step1-rerun-2026-03)
  PAIRS_PATH              Benchmark pair spec JSON
  OUTPUT_STEM             Output basename prefix in synthetic-bureau

Notes:
  - The synthetic pool root only needs provider=<label>/ subdirs with
    run_config.json and summary.json(.gz).
  - The default Lean run set mirrors the historical step-1 pooled benchmark:
    main DeepSeek + heuristic plus the recovery slices that improved same-kind
    coverage on the unresolved frontier.
  - The script fails if POOL_DIR already exists so reruns stay explicit.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --run)
      if [[ $# -lt 2 ]]; then
        echo "--run requires label=/abs/path" >&2
        exit 2
      fi
      RUN_SPECS+=("$2")
      shift 2
      ;;
    --coq-run)
      if [[ $# -lt 2 ]]; then
        echo "--coq-run requires a path" >&2
        exit 2
      fi
      COQ_RUN="$2"
      shift 2
      ;;
    --pool-dir)
      if [[ $# -lt 2 ]]; then
        echo "--pool-dir requires a path" >&2
        exit 2
      fi
      POOL_DIR="$2"
      shift 2
      ;;
    --output-stem)
      if [[ $# -lt 2 ]]; then
        echo "--output-stem requires a value" >&2
        exit 2
      fi
      OUTPUT_STEM="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

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

logs_root() {
  uv run python - <<'PY'
from runtime_paths import resolve_logs_root
print(resolve_logs_root().resolve())
PY
}

synthetic_bureau_root() {
  uv run python - <<'PY'
from runtime_paths import resolve_synthetic_bureau_root
print(resolve_synthetic_bureau_root().resolve())
PY
}

default_coq_run() {
  local runtime_candidate="${LOGS_ROOT}/2026-03-02-coq-paired-coq-logic-v3"
  local repo_candidate="${ROOT_DIR}/logs/2026-03-02-coq-paired-coq-logic-v3"
  if [[ -d "${runtime_candidate}" ]]; then
    printf '%s\n' "${runtime_candidate}"
    return 0
  fi
  printf '%s\n' "${repo_candidate}"
}

require_run_dir() {
  local label="$1"
  local path="$2"
  if [[ ! -d "${path}" ]]; then
    echo "Missing run dir for ${label}: ${path}" >&2
    exit 1
  fi
  if [[ ! -f "${path}/run_config.json" ]]; then
    echo "Missing run_config.json for ${label}: ${path}" >&2
    exit 1
  fi
  if [[ ! -f "${path}/summary.json.gz" && ! -f "${path}/summary.json" ]]; then
    echo "Missing summary.json(.gz) for ${label}: ${path}" >&2
    exit 1
  fi
}

LOGS_ROOT="$(logs_root)"
SYNTHETIC_BUREAU_ROOT="$(synthetic_bureau_root)"
if [[ -z "${COQ_RUN}" ]]; then
  COQ_RUN="$(default_coq_run)"
fi

if [[ "${#RUN_SPECS[@]}" -eq 0 ]]; then
  RUN_SPECS=(
    "deepseek-main=${LOGS_ROOT}/2026-03-02-coq-paired-lean-deepseek-full84-notrace"
    "heuristic-main=${LOGS_ROOT}/2026-03-02-coq-paired-lean-heuristic-allow-easy-v2-notrace"
    "deepseek-missing10-deep-s2-proofterm=${LOGS_ROOT}/2026-03-03-coq-paired-lean-deepseek-missing10-deep-s2-proofterm"
    "deepseek-missing7-deep-s8-proofterm=${LOGS_ROOT}/2026-03-03-coq-paired-lean-deepseek-missing7-deep-s8-proofterm"
    "deepseek-missing8-deep-s4-proofterm=${LOGS_ROOT}/2026-03-03-coq-paired-lean-deepseek-missing8-deep-s4-proofterm"
    "heuristic-unresolved13-deep=${LOGS_ROOT}/2026-03-03-coq-paired-lean-heuristic-unresolved13-deep"
    "deepseek-unresolved13-prooftermfix=${LOGS_ROOT}/2026-03-03-coq-paired-lean-deepseek-unresolved13-s2-prooftermfix-full"
  )
fi

echo "Dry run mode: $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"
echo "Pool dir:     ${POOL_DIR}"
echo "Coq run:      ${COQ_RUN}"
echo "Pairs path:   ${PAIRS_PATH}"
echo "Output stem:  ${OUTPUT_STEM}"
echo "Synthetic:    ${SYNTHETIC_BUREAU_ROOT}"

require_run_dir "coq" "${COQ_RUN}"
if [[ ! -f "${PAIRS_PATH}" ]]; then
  echo "Missing pairs file: ${PAIRS_PATH}" >&2
  exit 1
fi
if [[ -e "${POOL_DIR}" ]]; then
  echo "Pool dir already exists: ${POOL_DIR}" >&2
  echo "Choose a new POOL_ID/--pool-dir or remove it manually." >&2
  exit 1
fi

if [[ "${EXECUTE}" -eq 1 ]]; then
  mkdir -p "${POOL_DIR}"
  mkdir -p "${SYNTHETIC_BUREAU_ROOT}"
fi

for spec in "${RUN_SPECS[@]}"; do
  if [[ "${spec}" != *=* ]]; then
    echo "Invalid --run spec (expected label=/abs/path): ${spec}" >&2
    exit 2
  fi
  label="${spec%%=*}"
  path="${spec#*=}"
  if [[ -z "${label}" || -z "${path}" ]]; then
    echo "Invalid --run spec (empty label or path): ${spec}" >&2
    exit 2
  fi
  require_run_dir "${label}" "${path}"
  run_cmd ln -s "${path}" "${POOL_DIR}/provider=${label}"
done

run_benchmark() {
  local output="$1"
  shift
  run_cmd \
    uv run python wonton.py benchmark-cross-assistant \
    --run-lean "${POOL_DIR}" \
    --run-coq "${COQ_RUN}" \
    --pairs "${PAIRS_PATH}" \
    --output "${SYNTHETIC_BUREAU_ROOT}/${output}" \
    --no-fail-on-gate \
    "$@"
}

run_benchmark \
  "${OUTPUT_STEM}_cross_kind_single.json" \
  --graph-source-lean wild_type_graph \
  --graph-source-coq wild_type_graph \
  --proof-aggregation single

run_benchmark \
  "${OUTPUT_STEM}_same_kind_single.json" \
  --graph-source-lean proof_term_graph \
  --graph-source-coq proof_term_graph \
  --gate-claim same_kind \
  --proof-aggregation single

run_benchmark \
  "${OUTPUT_STEM}_same_kind_best_of.json" \
  --graph-source-lean proof_term_graph \
  --graph-source-coq proof_term_graph \
  --gate-claim same_kind \
  --proof-aggregation best_of \
  --max-proofs-per-theorem 4

run_benchmark \
  "${OUTPUT_STEM}_same_kind_consensus.json" \
  --graph-source-lean proof_term_graph \
  --graph-source-coq proof_term_graph \
  --gate-claim same_kind \
  --proof-aggregation consensus \
  --max-proofs-per-theorem 4

run_benchmark \
  "${OUTPUT_STEM}_same_kind_best_of_name_obf.json" \
  --graph-source-lean proof_term_graph \
  --graph-source-coq proof_term_graph \
  --gate-claim same_kind \
  --proof-aggregation best_of \
  --max-proofs-per-theorem 4 \
  --name-obfuscation names
