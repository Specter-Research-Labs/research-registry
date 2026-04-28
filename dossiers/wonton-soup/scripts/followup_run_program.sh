#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Lean tools are often installed via elan but not present on non-interactive PATHs.
if ! command -v lake >/dev/null 2>&1 && [ -x "${HOME}/.elan/bin/lake" ]; then
  export PATH="${HOME}/.elan/bin:${PATH}"
fi

EXECUTE=0
PHASE="all"

usage() {
  cat <<'USAGE'
Usage: scripts/followup_run_program.sh [--execute] [--phase PHASE]

  --execute      Run commands (default is dry-run print only)
  --phase        One of: all, p1, p2, p3, p4, p5, p6, p7

Environment (key defaults):
  PROGRAM_ID=followup-2026-03
  LEAN_CORPUS_REF=lean:mathlib4#feasible
  PANEL_SAMPLE=400
  PANEL_SELECTION_SEED=20260301
  DISTRIBUTED_SAMPLE=160
  DISTRIBUTED_SELECTION_SEED=20260301
  DIST_MCTS_AGENTS=8
  DIST_MCTS_INFLIGHT=64
  BASIN_WIDE_SEEDS=10
  BASIN_DEEP_SEEDS=50
  BASIN_DEEP_SAMPLE=120
  DEEPSEEK_ARTIFACT_ROOT=<root containing wonton-soup/models/...>
  ENABLE_EXTERNAL_PILOTS=0
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --phase)
      PHASE="${2:-}"
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

case "${PHASE}" in
  all|p1|p2|p3|p4|p5|p6|p7) ;;
  *)
    echo "Invalid --phase: ${PHASE}" >&2
    usage
    exit 2
    ;;
esac

PROGRAM_ID="${PROGRAM_ID:-followup-2026-03}"
LEAN_CORPUS_REF="${LEAN_CORPUS_REF:-lean:mathlib4#feasible}"
LEAN_WORKERS="${LEAN_WORKERS:-1}"
RESEARCH_BUDGET="${RESEARCH_BUDGET:-standard}"

LEAN_PROVIDERS_CSV="${LEAN_PROVIDERS_CSV:-reprover,heuristic,deepseek}"
IFS=',' read -r -a LEAN_PROVIDERS <<< "${LEAN_PROVIDERS_CSV}"

PANEL_SAMPLE="${PANEL_SAMPLE:-400}"
PANEL_SELECTION_SEED="${PANEL_SELECTION_SEED:-20260301}"

DISTRIBUTED_SAMPLE="${DISTRIBUTED_SAMPLE:-160}"
DISTRIBUTED_SELECTION_SEED="${DISTRIBUTED_SELECTION_SEED:-20260301}"
DIST_MCTS_AGENTS="${DIST_MCTS_AGENTS:-8}"
DIST_MCTS_INFLIGHT="${DIST_MCTS_INFLIGHT:-64}"
DIST_MCTS_VIRTUAL_LOSS="${DIST_MCTS_VIRTUAL_LOSS:-1}"
DIST_MCTS_DEPTH_BIAS="${DIST_MCTS_DEPTH_BIAS:-0}"
DIST_MCTS_PATH_BIAS="${DIST_MCTS_PATH_BIAS:-0}"
DIST_MCTS_HISTORY_CACHE="${DIST_MCTS_HISTORY_CACHE:-0}"

BASIN_WIDE_SEEDS="${BASIN_WIDE_SEEDS:-10}"
BASIN_DEEP_SEEDS="${BASIN_DEEP_SEEDS:-50}"
BASIN_DEEP_SAMPLE="${BASIN_DEEP_SAMPLE:-120}"
BASIN_DEEP_SELECTION_SEED="${BASIN_DEEP_SELECTION_SEED:-20260311}"

ENABLE_EXTERNAL_PILOTS="${ENABLE_EXTERNAL_PILOTS:-0}"
TPTP_ROOT="${TPTP_ROOT:-}"
SMTLIB_ROOT="${SMTLIB_ROOT:-}"
ENABLE_COQ_STDLIB="${ENABLE_COQ_STDLIB:-0}"
EXTERNAL_SAMPLE="${EXTERNAL_SAMPLE:-100}"
EXTERNAL_SELECTION_SEED="${EXTERNAL_SELECTION_SEED:-20260321}"
EXTERNAL_TIMEOUT="${EXTERNAL_TIMEOUT:-20}"
COQ_LIMIT_TOTAL="${COQ_LIMIT_TOTAL:-100}"
COQ_LIMIT_PER_MODULE="${COQ_LIMIT_PER_MODULE:-50}"
DEEPSEEK_ARTIFACT_ROOT="${DEEPSEEK_ARTIFACT_ROOT:-${SPECTER_ARTIFACT_ROOT:-}}"

K_PRESET_DIR="analysis/lake/presets"
K_PRESETS=(
  "73_followup_k_ref_reprover_v1.json"
  "74_followup_k_ref_deepseek_v1.json"
  "75_followup_k_ref_heuristic_v1.json"
  "76_followup_k_ref_pooled_v1.json"
)

ACTIVE_LOGS_ROOT="$(
  uv run python - <<'PY'
from runtime_paths import resolve_logs_root
print(resolve_logs_root().resolve())
PY
)"

ACTIVE_LAKE_DB="$(
  uv run python - <<'PY'
from analysis.lake.db import resolve_lake_paths
print(resolve_lake_paths().db_path.resolve())
PY
)"

has_ymd_prefix() {
  local value="$1"
  [[ "${value}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}- ]]
}

normalize_program_id() {
  local value="$1"
  local head="${value%%/*}"
  if has_ymd_prefix "${head}"; then
    printf '%s\n' "${value}"
  else
    printf '%s-%s\n' "$(date +%Y-%m-%d)" "${value}"
  fi
}

PROGRAM_RUN_ROOT="$(normalize_program_id "${PROGRAM_ID}")"
PROGRAM_LOGS_DIR="${ACTIVE_LOGS_ROOT%/}/${PROGRAM_RUN_ROOT}"
RUN_ID_ROOT="${PROGRAM_RUN_ROOT}"

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

run_provider_cmd() {
  local provider="$1"
  shift
  if [[ "${provider}" == "deepseek" && -n "${DEEPSEEK_ARTIFACT_ROOT}" ]]; then
    run_cmd env SPECTER_ARTIFACT_ROOT="${DEEPSEEK_ARTIFACT_ROOT}" "$@"
  else
    run_cmd "$@"
  fi
}

phase_header() {
  echo
  echo "== $1 =="
}

provider_enabled() {
  local needle="$1"
  for provider in "${LEAN_PROVIDERS[@]}"; do
    if [[ "${provider}" == "${needle}" ]]; then
      return 0
    fi
  done
  return 1
}

preflight_checks() {
  if ! provider_enabled "deepseek"; then
    return
  fi

  if [[ -z "${DEEPSEEK_ARTIFACT_ROOT}" ]]; then
    echo "DeepSeek provider enabled, but no artifact root configured for model lookup." >&2
    echo "Set DEEPSEEK_ARTIFACT_ROOT (or SPECTER_ARTIFACT_ROOT) to a root containing:" >&2
    echo "  wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-bf16" >&2
    exit 2
  fi

  local deepseek_model_dir
  deepseek_model_dir="${DEEPSEEK_ARTIFACT_ROOT%/}/wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-bf16"
  if [[ ! -d "${deepseek_model_dir}" ]]; then
    echo "DeepSeek model directory not found: ${deepseek_model_dir}" >&2
    exit 2
  fi
}

run_p1_shared_panel() {
  phase_header "P1 Shared Lean Panel (Centralized MCTS)"
  for provider in "${LEAN_PROVIDERS[@]}"; do
    run_provider_cmd "${provider}" uv run python wonton.py lean run \
      -m research \
      -c "${LEAN_CORPUS_REF}" \
      -p "${provider}" \
      -b "${RESEARCH_BUDGET}" \
      --sample "${PANEL_SAMPLE}" \
      --seed "${PANEL_SELECTION_SEED}" \
      --workers "${LEAN_WORKERS}" \
      --plain \
      --run-id "${RUN_ID_ROOT}/p1-shared/provider=${provider}/mcts=centralized" \
      --no-sync
  done
}

run_p2_distributed_pairs() {
  phase_header "P2 Paired Centralized vs Distributed"
  for provider in "${LEAN_PROVIDERS[@]}"; do
    run_provider_cmd "${provider}" uv run python wonton.py lean run \
      -m research \
      -c "${LEAN_CORPUS_REF}" \
      -p "${provider}" \
      -b "${RESEARCH_BUDGET}" \
      --sample "${DISTRIBUTED_SAMPLE}" \
      --seed "${DISTRIBUTED_SELECTION_SEED}" \
      --workers "${LEAN_WORKERS}" \
      --plain \
      --run-id "${RUN_ID_ROOT}/p2-paired/provider=${provider}/control=centralized" \
      --no-sync

    dist_cmd=(
      uv run python wonton.py lean run
      -m research
      -c "${LEAN_CORPUS_REF}"
      -p "${provider}"
      -b "${RESEARCH_BUDGET}"
      --sample "${DISTRIBUTED_SAMPLE}"
      --seed "${DISTRIBUTED_SELECTION_SEED}"
      --workers "${LEAN_WORKERS}"
      --plain
      --mcts-mode distributed
      --mcts-agents "${DIST_MCTS_AGENTS}"
      --mcts-inflight "${DIST_MCTS_INFLIGHT}"
      --run-id "${RUN_ID_ROOT}/p2-paired/provider=${provider}/distributed-a${DIST_MCTS_AGENTS}-i${DIST_MCTS_INFLIGHT}"
      --no-sync
    )
    if [[ -n "${DIST_MCTS_VIRTUAL_LOSS}" ]]; then
      dist_cmd+=(--mcts-virtual-loss "${DIST_MCTS_VIRTUAL_LOSS}")
    fi
    if [[ -n "${DIST_MCTS_DEPTH_BIAS}" ]]; then
      dist_cmd+=(--mcts-depth-bias "${DIST_MCTS_DEPTH_BIAS}")
    fi
    if [[ -n "${DIST_MCTS_PATH_BIAS}" ]]; then
      dist_cmd+=(--mcts-path-bias "${DIST_MCTS_PATH_BIAS}")
    fi
    if [[ "${DIST_MCTS_HISTORY_CACHE}" == "1" ]]; then
      dist_cmd+=(--mcts-history-cache)
    fi
    run_provider_cmd "${provider}" "${dist_cmd[@]}"
  done
}

run_p3_basin_wide() {
  phase_header "P3 Basin Wide (10 seeds)"
  for provider in "${LEAN_PROVIDERS[@]}"; do
    run_provider_cmd "${provider}" uv run python wonton.py lean basin \
      --seeds "${BASIN_WIDE_SEEDS}" \
      --blind \
      --sampling \
      -m research \
      -c "${LEAN_CORPUS_REF}" \
      -p "${provider}" \
      -b "${RESEARCH_BUDGET}" \
      --sample "${PANEL_SAMPLE}" \
      --seed "${PANEL_SELECTION_SEED}" \
      --workers "${LEAN_WORKERS}" \
      --plain \
      --run-id "${RUN_ID_ROOT}/p3-basin-wide/provider=${provider}/seeds=${BASIN_WIDE_SEEDS}" \
      --no-sync
  done
}

run_p4_basin_deep() {
  phase_header "P4 Basin Deep (50 seeds)"
  for provider in "${LEAN_PROVIDERS[@]}"; do
    run_provider_cmd "${provider}" uv run python wonton.py lean basin \
      --seeds "${BASIN_DEEP_SEEDS}" \
      --blind \
      --sampling \
      -m research \
      -c "${LEAN_CORPUS_REF}" \
      -p "${provider}" \
      -b "${RESEARCH_BUDGET}" \
      --sample "${BASIN_DEEP_SAMPLE}" \
      --seed "${BASIN_DEEP_SELECTION_SEED}" \
      --workers "${LEAN_WORKERS}" \
      --plain \
      --run-id "${RUN_ID_ROOT}/p4-basin-deep/provider=${provider}/seeds=${BASIN_DEEP_SEEDS}" \
      --no-sync
  done
}

run_p5_external_backends() {
  phase_header "P5 External Backend Pilots"
  if [[ "${ENABLE_EXTERNAL_PILOTS}" != "1" ]]; then
    echo "Skipping P5 because ENABLE_EXTERNAL_PILOTS=${ENABLE_EXTERNAL_PILOTS}"
    return
  fi

  if [[ -n "${TPTP_ROOT}" ]]; then
    run_cmd uv run python wonton.py e \
      --tptp-root "${TPTP_ROOT}" \
      --sample "${EXTERNAL_SAMPLE}" \
      --seed "${EXTERNAL_SELECTION_SEED}" \
      --timeout "${EXTERNAL_TIMEOUT}" \
      --log-dir "${PROGRAM_LOGS_DIR}/p5-external/e"
    run_cmd uv run python wonton.py vampire \
      --tptp-root "${TPTP_ROOT}" \
      --sample "${EXTERNAL_SAMPLE}" \
      --seed "${EXTERNAL_SELECTION_SEED}" \
      --timeout "${EXTERNAL_TIMEOUT}" \
      --log-dir "${PROGRAM_LOGS_DIR}/p5-external/vampire"
  else
    echo "Skipping E/Vampire: set TPTP_ROOT to enable."
  fi

  if [[ -n "${SMTLIB_ROOT}" ]]; then
    run_cmd uv run python wonton.py z3 \
      --smtlib-root "${SMTLIB_ROOT}" \
      --sample "${EXTERNAL_SAMPLE}" \
      --seed "${EXTERNAL_SELECTION_SEED}" \
      --timeout "${EXTERNAL_TIMEOUT}" \
      --log-dir "${PROGRAM_LOGS_DIR}/p5-external/z3"
  else
    echo "Skipping Z3: set SMTLIB_ROOT to enable."
  fi

  if [[ "${ENABLE_COQ_STDLIB}" == "1" ]]; then
    run_cmd uv run python wonton.py coq \
      --coq-mode stdlib \
      --limit-total "${COQ_LIMIT_TOTAL}" \
      --limit-per-module "${COQ_LIMIT_PER_MODULE}" \
      --log-dir "${PROGRAM_LOGS_DIR}/p5-external/coq-stdlib"
  else
    echo "Skipping Coq stdlib: set ENABLE_COQ_STDLIB=1 to enable."
  fi
}

run_p6_reconcile() {
  phase_header "P6 Postprocess + Reconcile"
  run_cmd uv run python wonton.py postprocess --logs-dir "${PROGRAM_LOGS_DIR}"
  run_cmd uv run python wonton.py lake reconcile --logs-dir "${PROGRAM_LOGS_DIR}"
}

run_p7_k_jobs() {
  phase_header "P7 Locked K Calibration Jobs"
  for preset in "${K_PRESETS[@]}"; do
    run_cmd uv run python wonton.py lake job run \
      --config "${K_PRESET_DIR}/${preset}" \
      --logs-dir "${PROGRAM_LOGS_DIR}"
  done
}

echo "Program ID:        ${PROGRAM_ID}"
echo "Cohort logs dir:   ${PROGRAM_LOGS_DIR}"
echo "Lake DB:           ${ACTIVE_LAKE_DB}"
echo "Lean corpus ref:   ${LEAN_CORPUS_REF}"
echo "Lean providers:    ${LEAN_PROVIDERS_CSV}"
echo "DeepSeek root:     ${DEEPSEEK_ARTIFACT_ROOT:-<unset>}"
echo "Dry run mode:      $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"

preflight_checks

if [[ "${PHASE}" == "all" || "${PHASE}" == "p1" ]]; then
  run_p1_shared_panel
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p2" ]]; then
  run_p2_distributed_pairs
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p3" ]]; then
  run_p3_basin_wide
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p4" ]]; then
  run_p4_basin_deep
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p5" ]]; then
  run_p5_external_backends
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p6" ]]; then
  run_p6_reconcile
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p7" ]]; then
  run_p7_k_jobs
fi
