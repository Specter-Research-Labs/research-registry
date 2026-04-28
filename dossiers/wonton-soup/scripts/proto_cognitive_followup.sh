#!/usr/bin/env bash
set -euo pipefail

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
Usage: scripts/proto_cognitive_followup.sh [--execute] [--phase PHASE]

  --execute      Run commands (default is dry-run print only)
  --phase        One of:
                   all
                   prep    derive easy/mid theorem slices + build subset corpora
                   matrix  matched centralized vs distributed controls
                   lesions distributed scheduler lesion set on matched slice
                   basin   seeded basin runs on stable easy slice
                   paired  Lean↔Rocq paired benchmark refresh

Intended use:
  Run this inside a repo workspace on quietbox, typically via dispatch:

  dispatch run --on quietbox --project specter-labs --sync-workspace --isolated-workspace \
    --batch --name proto-cognitive-prep -- \
    bash research-registry/dossiers/wonton-soup/scripts/proto_cognitive_followup.sh \
      --phase prep --execute

Key defaults:
  PROGRAM_ID=proto-cognitive-followup
  SOURCE_RUN_ID=2026-04-06-solvable-1000
  SOURCE_CORPUS_REF=lean:solvable-1000-v1
  MATRIX_CORPUS_ID=proto-cognitive-matrix-easy-v1
  BASIN_CORPUS_ID=proto-cognitive-basin-easy-v1
  MATRIX_MIN_SOLVES_ANY=4
  MATRIX_SIZE=72
  BASIN_MIN_SOLVES_WILD=4
  BASIN_SIZE=20
  LEAN_WORKERS=8
  DIST_MCTS_AGENTS=8
  DIST_MCTS_INFLIGHT=64
  BASIN_SEEDS=20
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
  all|prep|matrix|lesions|basin|paired) ;;
  *)
    echo "Invalid --phase: ${PHASE}" >&2
    usage
    exit 2
    ;;
esac

PROGRAM_ID="${PROGRAM_ID:-proto-cognitive-followup}"
SOURCE_RUN_ID="${SOURCE_RUN_ID:-2026-04-06-solvable-1000}"
SOURCE_LOGS_ROOT="${SOURCE_LOGS_ROOT:-/shared/dev/specter-labs-wonton-abstract-runfix/dossiers/wonton-soup/logs}"
SOURCE_CORPUS_REF="${SOURCE_CORPUS_REF:-lean:solvable-1000-v1}"

MATRIX_CORPUS_ID="${MATRIX_CORPUS_ID:-proto-cognitive-matrix-easy-v1}"
BASIN_CORPUS_ID="${BASIN_CORPUS_ID:-proto-cognitive-basin-easy-v1}"
MATRIX_MIN_SOLVES_ANY="${MATRIX_MIN_SOLVES_ANY:-4}"
MATRIX_SIZE="${MATRIX_SIZE:-72}"
MATRIX_SELECTION_SEED="${MATRIX_SELECTION_SEED:-20260411}"
BASIN_MIN_SOLVES_WILD="${BASIN_MIN_SOLVES_WILD:-4}"
BASIN_SIZE="${BASIN_SIZE:-20}"
BASIN_SELECTION_SEED="${BASIN_SELECTION_SEED:-20260411}"

LEAN_PROVIDERS_CSV="${LEAN_PROVIDERS_CSV:-reprover,deepseek}"
IFS=',' read -r -a LEAN_PROVIDERS <<< "${LEAN_PROVIDERS_CSV}"

LEAN_WORKERS="${LEAN_WORKERS:-8}"
RESEARCH_BUDGET="${RESEARCH_BUDGET:-standard}"
LEAN_RESUME="${LEAN_RESUME:-0}"
DEEPSEEK_SAMPLES="${DEEPSEEK_SAMPLES:-10}"
DEEPSEEK_ENDPOINTS_CSV="${DEEPSEEK_ENDPOINTS_CSV:-http://localhost:8000,http://localhost:8001,http://localhost:8002,http://localhost:8003}"

DIST_MCTS_AGENTS="${DIST_MCTS_AGENTS:-8}"
DIST_MCTS_INFLIGHT="${DIST_MCTS_INFLIGHT:-64}"
DIST_MCTS_VIRTUAL_LOSS="${DIST_MCTS_VIRTUAL_LOSS:-1}"
DIST_MCTS_DETERMINISTIC_INFERENCE="${DIST_MCTS_DETERMINISTIC_INFERENCE:-1}"
MCTS_BLOCK_DURATION="${MCTS_BLOCK_DURATION:-20}"
MCTS_BLOCK_SEED="${MCTS_BLOCK_SEED:-20260411}"
MCTS_DELAY_DURATION="${MCTS_DELAY_DURATION:-5}"
MCTS_DELAY_SEED="${MCTS_DELAY_SEED:-20260411}"
MCTS_REROUTE_MAX="${MCTS_REROUTE_MAX:-4}"
SCHEDULER_CONDITIONS_CSV="${SCHEDULER_CONDITIONS_CSV:-damage-block-f0.1,damage-block-f0.3,adapt-block-f0.3,damage-delay-p0.3}"
IFS=',' read -r -a SCHEDULER_CONDITIONS <<< "${SCHEDULER_CONDITIONS_CSV}"

BASIN_SEEDS="${BASIN_SEEDS:-20}"

PAIR_CORPUS_ID="${PAIR_CORPUS_ID:-coq-paired-micro-v1}"
PAIRS_PATH="${PAIRS_PATH:-${ROOT_DIR}/analysis/benchmarks/lean_coq_logic_micro_v1.json}"
SERAPI_BINARY="${SERAPI_BINARY:-sertop}"

if [[ "${LEAN_RESUME}" == "1" ]]; then
  RESUME_ARGS=(--resume)
else
  RESUME_ARGS=()
fi

ensure_workspace_sane() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "Workspace sanity check failed: uv is not on PATH" >&2
    exit 1
  fi

  if [[ -f "${ROOT_DIR}/orchestrator/lean.py" && -d "${ROOT_DIR}/orchestrator/lean" ]]; then
    echo "Workspace sanity check failed: ${ROOT_DIR}/orchestrator/lean.py shadows the split orchestrator/lean package" >&2
    echo "Remove the stale shadow module or sync the workspace cleanly before running follow-up jobs." >&2
    exit 1
  fi

  local -a required_files=(
    "wonton.py"
    "orchestrator/lean/__init__.py"
    "orchestrator/lean/metadata.py"
    "orchestrator/lean/runner.py"
    "orchestrator/lean/runtime.py"
    "experiments/distributed_mcts/core.py"
  )
  local -a missing=()
  local rel
  for rel in "${required_files[@]}"; do
    if [[ ! -f "${ROOT_DIR}/${rel}" ]]; then
      missing+=("${rel}")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    echo "Workspace sanity check failed: missing required files in ${ROOT_DIR}" >&2
    printf '  %s\n' "${missing[@]}" >&2
    echo "This usually means the workspace sync is incomplete." >&2
    exit 1
  fi
}

ensure_workspace_sane

ACTIVE_LOGS_ROOT="$(
  uv run python -c 'from runtime_paths import resolve_logs_root; print(resolve_logs_root().resolve())'
)"
ACTIVE_LAKE_DB="$(
  uv run python -c 'from analysis.lake.db import resolve_lake_paths; print(resolve_lake_paths().db_path.resolve())'
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
META_DIR="${PROGRAM_LOGS_DIR}/meta"
MATRIX_THEOREMS_FILE="${META_DIR}/matrix_theorems.txt"
BASIN_THEOREMS_FILE="${META_DIR}/basin_theorems.txt"
SELECTION_SUMMARY_JSON="${META_DIR}/selection_summary.json"

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

ensure_lean_repl_ready() {
  local repl_dir
  repl_dir="$(uv run python -c 'from leantree.core.project import LeanProject; print(LeanProject._get_default_repl_path())')"
  local repl_bin="${repl_dir}/.lake/build/bin/repl"
  if [[ -x "${repl_bin}" ]]; then
    return
  fi

  phase_header "Bootstrap Lean REPL"
  run_cmd bash -lc "cd ${repl_dir@Q} && lake build"

  if [[ "${EXECUTE}" -eq 1 && ! -x "${repl_bin}" ]]; then
    echo "Lean REPL build did not produce expected executable: ${repl_bin}" >&2
    exit 1
  fi
}

provider_run_cmd() {
  local provider="$1"
  shift
  if [[ "${provider}" == "deepseek" && -z "${VLLM_ENDPOINTS:-}${VLLM_ENDPOINT:-}" ]]; then
    run_cmd env VLLM_ENDPOINTS="${DEEPSEEK_ENDPOINTS_CSV}" "$@"
  else
    run_cmd "$@"
  fi
}

distributed_base_args() {
  DISTRIBUTED_ARGS=(
    --mcts-mode distributed
    --mcts-agents "${DIST_MCTS_AGENTS}"
    --mcts-inflight "${DIST_MCTS_INFLIGHT}"
  )
  if [[ -n "${DIST_MCTS_VIRTUAL_LOSS}" ]]; then
    DISTRIBUTED_ARGS+=(--mcts-virtual-loss "${DIST_MCTS_VIRTUAL_LOSS}")
  fi
  if [[ "${DIST_MCTS_DETERMINISTIC_INFERENCE}" == "1" ]]; then
    DISTRIBUTED_ARGS+=(--mcts-deterministic-inference)
  fi
}

condition_args() {
  local condition="$1"
  CONDITION_ARGS=()
  case "${condition}" in
    damage-block-f0.1|damage-block-f0.3|damage-block-f0.5)
      CONDITION_ARGS+=(
        --mcts-block-fraction "${condition##*-f}"
        --mcts-block-duration "${MCTS_BLOCK_DURATION}"
        --mcts-block-seed "${MCTS_BLOCK_SEED}"
      )
      ;;
    adapt-block-f0.1|adapt-block-f0.3|adapt-block-f0.5)
      CONDITION_ARGS+=(
        --mcts-block-fraction "${condition##*-f}"
        --mcts-block-duration "${MCTS_BLOCK_DURATION}"
        --mcts-block-seed "${MCTS_BLOCK_SEED}"
        --mcts-reroute-blocked
        --mcts-reroute-max "${MCTS_REROUTE_MAX}"
      )
      ;;
    damage-delay-p0.1|damage-delay-p0.3)
      CONDITION_ARGS+=(
        --mcts-delay-prob "${condition##*-p}"
        --mcts-delay-duration "${MCTS_DELAY_DURATION}"
        --mcts-delay-seed "${MCTS_DELAY_SEED}"
      )
      ;;
    *)
      echo "Unknown scheduler condition: ${condition}" >&2
      exit 2
      ;;
  esac
}

ensure_meta_dir() {
  run_cmd mkdir -p "${META_DIR}"
}

prepare_followup_lists() {
  phase_header "Prepare Easy/Mid Follow-Up Slices"
  ensure_meta_dir
  run_cmd python - "${SOURCE_LOGS_ROOT}" "${SOURCE_RUN_ID}" "${MATRIX_MIN_SOLVES_ANY}" "${MATRIX_SIZE}" "${MATRIX_SELECTION_SEED}" "${BASIN_MIN_SOLVES_WILD}" "${BASIN_SIZE}" "${BASIN_SELECTION_SEED}" "${MATRIX_THEOREMS_FILE}" "${BASIN_THEOREMS_FILE}" "${SELECTION_SUMMARY_JSON}" <<'PY'
from __future__ import annotations

import gzip
import json
import random
import sys
from pathlib import Path

logs_root = Path(sys.argv[1])
run_id = sys.argv[2]
matrix_min_any = int(sys.argv[3])
matrix_size = int(sys.argv[4])
matrix_seed = int(sys.argv[5])
basin_min_wild = int(sys.argv[6])
basin_size = int(sys.argv[7])
basin_seed = int(sys.argv[8])
matrix_out = Path(sys.argv[9])
basin_out = Path(sys.argv[10])
summary_out = Path(sys.argv[11])

run_root = logs_root / run_id
specs = [
    ("reprover", "centralized"),
    ("reprover", "distributed"),
    ("deepseek", "centralized"),
    ("deepseek", "distributed"),
]
solve_maps: dict[str, dict[str, dict[str, bool]]] = {}
all_names: set[str] = set()
for provider, mode in specs:
    summary_path = run_root / f"provider={provider}" / f"mcts={mode}" / "summary.json.gz"
    with gzip.open(summary_path, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    row_key = f"{provider}/{mode}"
    table: dict[str, dict[str, bool]] = {}
    for theorem in payload.get("theorems", []):
        name = theorem["name"]
        wild = bool(theorem.get("wild_type", {}).get("solved"))
        solved_any = wild or any(
            bool(entry.get("solved")) for entry in (theorem.get("interventions") or [])
        )
        table[name] = {"wild": wild, "any": solved_any}
        all_names.add(name)
    solve_maps[row_key] = table

def stable_pick(names: list[str], size: int, seed: int) -> list[str]:
    ordered = sorted(dict.fromkeys(names))
    if len(ordered) <= size:
        return ordered
    rng = random.Random(seed)
    picked = rng.sample(ordered, size)
    return sorted(picked)

matrix_candidates = [
    name
    for name in all_names
    if sum(1 for table in solve_maps.values() if table.get(name, {}).get("any", False)) >= matrix_min_any
]
basin_candidates = [
    name
    for name in all_names
    if sum(1 for table in solve_maps.values() if table.get(name, {}).get("wild", False)) >= basin_min_wild
]

if len(matrix_candidates) < matrix_size:
    raise SystemExit(
        f"Not enough matrix candidates: requested {matrix_size}, found {len(matrix_candidates)}"
    )
if len(basin_candidates) < basin_size:
    raise SystemExit(
        f"Not enough basin candidates: requested {basin_size}, found {len(basin_candidates)}"
    )

matrix_selected = stable_pick(matrix_candidates, matrix_size, matrix_seed)
basin_selected = stable_pick(basin_candidates, basin_size, basin_seed)

matrix_out.parent.mkdir(parents=True, exist_ok=True)
matrix_out.write_text("\n".join(matrix_selected) + "\n", encoding="utf-8")
basin_out.write_text("\n".join(basin_selected) + "\n", encoding="utf-8")
summary_out.write_text(
    json.dumps(
        {
            "source_run_id": run_id,
            "matrix": {
                "min_any_solves": matrix_min_any,
                "candidate_count": len(matrix_candidates),
                "selected_count": len(matrix_selected),
                "selection_seed": matrix_seed,
                "selected": matrix_selected,
            },
            "basin": {
                "min_wild_solves": basin_min_wild,
                "candidate_count": len(basin_candidates),
                "selected_count": len(basin_selected),
                "selection_seed": basin_seed,
                "selected": basin_selected,
            },
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(f"matrix_candidates={len(matrix_candidates)} selected={len(matrix_selected)}")
print(f"basin_candidates={len(basin_candidates)} selected={len(basin_selected)}")
PY
}

build_subset_corpora() {
  phase_header "Build Follow-Up Subset Corpora"
  run_cmd uv run python wonton.py corpus build-lean-subset \
    --corpus-id "${MATRIX_CORPUS_ID}" \
    --source-ref "${SOURCE_CORPUS_REF}" \
    --theorems-path "${MATRIX_THEOREMS_FILE}"

  run_cmd uv run python wonton.py corpus build-lean-subset \
    --corpus-id "${BASIN_CORPUS_ID}" \
    --source-ref "${SOURCE_CORPUS_REF}" \
    --theorems-path "${BASIN_THEOREMS_FILE}"
}

run_matrix_controls() {
  ensure_lean_repl_ready
  phase_header "Matched Centralized vs Distributed Controls"
  distributed_base_args
  local provider
  for provider in "${LEAN_PROVIDERS[@]}"; do
    local -a base_cmd=(
      uv run python wonton.py lean run
      -m research
      -c "lean:${MATRIX_CORPUS_ID}"
      -p "${provider}"
      -b "${RESEARCH_BUDGET}"
      --workers "${LEAN_WORKERS}"
      --plain
      --no-sync
    )
    if [[ "${provider}" == "deepseek" ]]; then
      base_cmd+=(--deepseek-samples "${DEEPSEEK_SAMPLES}")
    fi
    provider_run_cmd "${provider}" \
      "${base_cmd[@]}" \
      --run-id "${RUN_ID_ROOT}/matrix/provider=${provider}/mcts=centralized" \
      "${RESUME_ARGS[@]}"

    provider_run_cmd "${provider}" \
      "${base_cmd[@]}" \
      --run-id "${RUN_ID_ROOT}/matrix/provider=${provider}/mcts=distributed" \
      "${RESUME_ARGS[@]}" \
      "${DISTRIBUTED_ARGS[@]}"
  done
}

run_scheduler_lesions() {
  ensure_lean_repl_ready
  phase_header "Distributed Scheduler Lesions"
  local provider
  for provider in "${LEAN_PROVIDERS[@]}"; do
    for condition in "${SCHEDULER_CONDITIONS[@]}"; do
      distributed_base_args
      condition_args "${condition}"
      local -a cmd=(
        uv run python wonton.py lean run
        -m research
        -c "lean:${MATRIX_CORPUS_ID}"
        -p "${provider}"
        -b "${RESEARCH_BUDGET}"
        --workers "${LEAN_WORKERS}"
        --plain
        --run-id "${RUN_ID_ROOT}/lesions/provider=${provider}/condition=${condition}"
        --no-sync
      )
      if [[ "${provider}" == "deepseek" ]]; then
        cmd+=(--deepseek-samples "${DEEPSEEK_SAMPLES}")
      fi
      provider_run_cmd "${provider}" \
        "${cmd[@]}" \
        "${RESUME_ARGS[@]}" \
        "${DISTRIBUTED_ARGS[@]}" \
        "${CONDITION_ARGS[@]}"
    done
  done
}

run_basin_suite() {
  ensure_lean_repl_ready
  phase_header "Seeded Basin Runs"
  local provider
  for provider in "${LEAN_PROVIDERS[@]}"; do
    local -a cmd=(
      uv run python wonton.py lean basin
      --seeds "${BASIN_SEEDS}"
      --blind
      --sampling
      -m research
      -c "lean:${BASIN_CORPUS_ID}"
      -p "${provider}"
      -b "${RESEARCH_BUDGET}"
      --workers "${LEAN_WORKERS}"
      --plain
      --run-id "${RUN_ID_ROOT}/basin/provider=${provider}/seeds=${BASIN_SEEDS}"
      --no-sync
    )
    if [[ "${provider}" == "deepseek" ]]; then
      cmd+=(--deepseek-samples "${DEEPSEEK_SAMPLES}")
    fi
    provider_run_cmd "${provider}" "${cmd[@]}" "${RESUME_ARGS[@]}"
  done
}

prepare_paired_coq_inputs() {
  local tmp_dir="${PROGRAM_LOGS_DIR}/cross-assistant/tmp"
  PAIRED_COQ_THEOREM_FILE="${tmp_dir}/coq_theorems.txt"
  PAIRED_COQ_IMPORTS_FILE="${tmp_dir}/coq_imports.v"
  if [[ "${EXECUTE}" -eq 0 ]]; then
    echo "+ python build paired Coq inputs -> ${PAIRED_COQ_THEOREM_FILE} ${PAIRED_COQ_IMPORTS_FILE}"
    return
  fi
  mkdir -p "${tmp_dir}"
  python - "${PAIRS_PATH}" "${PAIRED_COQ_THEOREM_FILE}" "${PAIRED_COQ_IMPORTS_FILE}" <<'PY'
import json
import sys
from pathlib import Path

pairs_path = Path(sys.argv[1])
theorem_file = Path(sys.argv[2])
imports_file = Path(sys.argv[3])

payload = json.loads(pairs_path.read_text(encoding="utf-8"))
pairs = payload.get("pairs")
if not isinstance(pairs, list) or not pairs:
    raise SystemExit("pairs file must contain a non-empty pairs list")

coq_theorems = []
for row in pairs:
    if not isinstance(row, dict):
        continue
    theorem = row.get("coq_theorem")
    if isinstance(theorem, str) and theorem:
        coq_theorems.append(theorem)

theorem_file.write_text("\n".join(coq_theorems) + "\n", encoding="utf-8")
imports_file.write_text(
    "Require Import Coq.Init.Logic.\n"
    "Require Import Coq.Init.Datatypes.\n"
    "Require Import Coq.Bool.Bool.\n"
    "Import Bool.\n",
    encoding="utf-8",
)
PY
}

run_postprocess_and_reconcile() {
  local logs_dir="$1"
  run_cmd uv run python wonton.py postprocess --logs-dir "${logs_dir}"
  run_cmd uv run python wonton.py lake reconcile --logs-dir "${logs_dir}"
}

run_cross_assistant_refresh() {
  ensure_lean_repl_ready
  phase_header "Lean↔Rocq Paired Benchmark Refresh"
  local pair_limit
  pair_limit="$(python - "${PAIRS_PATH}" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(len(payload.get("pairs", [])))
PY
)"

  run_cmd uv run python wonton.py corpus build-lean-coq-paired-micro \
    --corpus-id "${PAIR_CORPUS_ID}" \
    --pairs-path "${PAIRS_PATH}"

  provider_run_cmd reprover \
    uv run python wonton.py lean run \
    -m research \
    -c "lean:${PAIR_CORPUS_ID}" \
    -p reprover \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --wild-only \
    --workers "${LEAN_WORKERS}" \
    --plain \
    --run-id "${RUN_ID_ROOT}/cross-assistant/lean/provider=reprover/wild-only" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  provider_run_cmd deepseek \
    uv run python wonton.py lean run \
    -m research \
    -c "lean:${PAIR_CORPUS_ID}" \
    -p deepseek \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --wild-only \
    --workers "${LEAN_WORKERS}" \
    --deepseek-samples "${DEEPSEEK_SAMPLES}" \
    --plain \
    --run-id "${RUN_ID_ROOT}/cross-assistant/lean/provider=deepseek/wild-only" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  provider_run_cmd deepseek \
    uv run python wonton.py lean run \
    -m research \
    -c "lean:${PAIR_CORPUS_ID}" \
    -p deepseek \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --workers "${LEAN_WORKERS}" \
    --deepseek-samples "${DEEPSEEK_SAMPLES}" \
    --plain \
    --run-id "${RUN_ID_ROOT}/cross-assistant/lean/provider=deepseek/with-interventions" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/cross-assistant/lean"

  prepare_paired_coq_inputs
  run_cmd uv run python wonton.py run \
    --backend coq \
    --coq-mode file \
    --source "${PAIRED_COQ_IMPORTS_FILE}" \
    --theorem-file "${PAIRED_COQ_THEOREM_FILE}" \
    --serapi-binary "${SERAPI_BINARY}" \
    --log-dir "${PROGRAM_LOGS_DIR}/cross-assistant/coq/paired-extract"

  local wild_pool="${PROGRAM_LOGS_DIR}/cross-assistant/pool-wild"
  local bestof_pool="${PROGRAM_LOGS_DIR}/cross-assistant/pool-bestof"
  local report_dir="${PROGRAM_LOGS_DIR}/cross-assistant/reports"
  run_cmd rm -rf "${wild_pool}" "${bestof_pool}" "${report_dir}"
  run_cmd mkdir -p "${wild_pool}" "${bestof_pool}" "${report_dir}"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/cross-assistant/lean/provider=reprover/wild-only" "${wild_pool}/provider=reprover-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/cross-assistant/lean/provider=deepseek/wild-only" "${wild_pool}/provider=deepseek-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/cross-assistant/lean/provider=reprover/wild-only" "${bestof_pool}/provider=reprover-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/cross-assistant/lean/provider=deepseek/wild-only" "${bestof_pool}/provider=deepseek-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/cross-assistant/lean/provider=deepseek/with-interventions" "${bestof_pool}/provider=deepseek-bestof"

  benchmark_report() {
    local lean_root="$1"
    local output_name="$2"
    shift 2
    run_cmd uv run python wonton.py benchmark-cross-assistant \
      --run-lean "${lean_root}" \
      --run-coq "${PROGRAM_LOGS_DIR}/cross-assistant/coq/paired-extract" \
      --pairs "${PAIRS_PATH}" \
      --output "${report_dir}/${output_name}" \
      --no-fail-on-gate \
      "$@"
  }

  benchmark_report \
    "${wild_pool}" \
    "paired_wild_gate.json" \
    --proof-aggregation single \
    --gate-claim all \
    --gate-axis all

  benchmark_report \
    "${wild_pool}" \
    "paired_same_kind_term_dag.json" \
    --graph-source-lean proof_term_graph \
    --graph-source-coq proof_term_graph \
    --solved-only \
    --gate-claim same_kind

  benchmark_report \
    "${bestof_pool}" \
    "paired_same_kind_best_of.json" \
    --graph-source-lean proof_term_graph \
    --graph-source-coq proof_term_graph \
    --solved-only \
    --gate-claim same_kind \
    --proof-aggregation best_of \
    --max-proofs-per-theorem 4

  benchmark_report \
    "${wild_pool}" \
    "paired_graph_only_stress.json" \
    --name-obfuscation names \
    --name-obfuscation-salt wonton-obf-proto-cognitive-v1 \
    --lexical-ablation graph_only
}

echo "Program ID:        ${PROGRAM_ID}"
echo "Run root:          ${PROGRAM_RUN_ROOT}"
echo "Logs dir:          ${PROGRAM_LOGS_DIR}"
echo "Lake DB:           ${ACTIVE_LAKE_DB}"
echo "Source run:        ${SOURCE_RUN_ID}"
echo "Source corpus:     ${SOURCE_CORPUS_REF}"
echo "Lean providers:    ${LEAN_PROVIDERS_CSV}"
echo "DeepSeek endpoints:${DEEPSEEK_ENDPOINTS_CSV}"
echo "Dry run mode:      $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"

if [[ "${PHASE}" == "all" || "${PHASE}" == "prep" ]]; then
  prepare_followup_lists
  build_subset_corpora
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "matrix" ]]; then
  run_matrix_controls
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "lesions" ]]; then
  run_scheduler_lesions
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "basin" ]]; then
  run_basin_suite
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "paired" ]]; then
  run_cross_assistant_refresh
fi
