#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

LEAN_PROJECT_PATH="${LEAN_PROJECT_PATH:-${ROOT_DIR}/lean_project}"
export LEAN_PROJECT_PATH

if ! command -v lake >/dev/null 2>&1 && [ -x "${HOME}/.elan/bin/lake" ]; then
  export PATH="${HOME}/.elan/bin:${PATH}"
fi

EXECUTE=0
PHASE="all"

usage() {
  cat <<'USAGE'
Usage: scripts/abstract_evidence_run_program.sh [--execute] [--phase PHASE]

  --execute      Run commands (default is dry-run print only)
  --phase        One of:
                   all
                   p1  shared panel
                   p2  freeze matched 160-theorem slice
                   p3  centralized/distributed controls
                   p4  distributed scheduler lesions + matrix summary
                   p5  basin wide
                   p6  freeze deep 40-theorem slice
                   p7  basin deep
                   p8  repeat stability cohort
                   p9  Lean↔Rocq paired benchmark refresh
                   post  deferred postprocess + reconcile queue

Environment (key defaults):
  PROGRAM_ID=2026-03-23-abstract
  LEAN_CORPUS_REF=lean:mathlib4#feasible
  LEAN_RESUME=0
  LEAN_PROVIDERS_CSV=reprover,deepseek,heuristic
  PRIMARY_LLM_PROVIDERS_CSV=reprover,deepseek
  P1_PROVIDERS_CSV=${PRIMARY_LLM_PROVIDERS_CSV}
  P3_PROVIDERS_CSV=${PRIMARY_LLM_PROVIDERS_CSV}
  P5_PROVIDERS_CSV=${PRIMARY_LLM_PROVIDERS_CSV}
  P7_PROVIDERS_CSV=${PRIMARY_LLM_PROVIDERS_CSV}
  INLINE_POSTPROCESS=0
  PANEL_SAMPLE=400
  PANEL_SELECTION_SEED=20260323
  MATCHED_SLICE_SIZE=160
  MATCHED_SELECTION_SEED=20260323
  BASIN_WIDE_SEEDS=10
  BASIN_DEEP_SEEDS=50
  BASIN_DEEP_SIZE=40
  REPEAT_SEEDS=20
  DIST_MCTS_AGENTS=8
  DIST_MCTS_INFLIGHT=64
  DIST_MCTS_VIRTUAL_LOSS=1
  PAIR_CORPUS_ID=coq-paired-micro-v1
  PAIRS_PATH=analysis/benchmarks/lean_coq_logic_micro_v1.json
  DEEPSEEK_ARTIFACT_ROOT=<root containing wonton-soup/models/...>

Notes:
  - Cohort E uses `wonton.py lean run --search-seed` for seeded theorem repeats.
  - The distributed baseline cell for Cohort C is the distributed control run from phase p3.
  - Phase-specific provider CSVs keep the critical path on LLM providers by default.
  - Deferred postprocess roots can be flushed later with `--phase post`.
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
  all|p1|p2|p3|p4|p5|p6|p7|p8|p9|post) ;;
  *)
    echo "Invalid --phase: ${PHASE}" >&2
    usage
    exit 2
    ;;
esac

PROGRAM_ID="${PROGRAM_ID:-2026-03-23-abstract}"
LEAN_CORPUS_REF="${LEAN_CORPUS_REF:-lean:mathlib4#feasible}"
LEAN_RESUME="${LEAN_RESUME:-0}"
LEAN_PROVIDERS_CSV="${LEAN_PROVIDERS_CSV:-reprover,deepseek,heuristic}"
PRIMARY_LLM_PROVIDERS_CSV="${PRIMARY_LLM_PROVIDERS_CSV:-reprover,deepseek}"
P1_PROVIDERS_CSV="${P1_PROVIDERS_CSV:-${PRIMARY_LLM_PROVIDERS_CSV}}"
P3_PROVIDERS_CSV="${P3_PROVIDERS_CSV:-${PRIMARY_LLM_PROVIDERS_CSV}}"
P5_PROVIDERS_CSV="${P5_PROVIDERS_CSV:-${PRIMARY_LLM_PROVIDERS_CSV}}"
P7_PROVIDERS_CSV="${P7_PROVIDERS_CSV:-${PRIMARY_LLM_PROVIDERS_CSV}}"
INLINE_POSTPROCESS="${INLINE_POSTPROCESS:-0}"
RESEARCH_BUDGET="${RESEARCH_BUDGET:-standard}"
LEAN_WORKERS="${LEAN_WORKERS:-1}"
SKIP_COMPLETED_RUNS="${SKIP_COMPLETED_RUNS:-1}"

PANEL_SAMPLE="${PANEL_SAMPLE:-400}"
PANEL_SELECTION_SEED="${PANEL_SELECTION_SEED:-20260323}"
MATCHED_SLICE_SIZE="${MATCHED_SLICE_SIZE:-160}"
MATCHED_SELECTOR="${MATCHED_SELECTOR:-abstract-evidence/matched-160}"
MATCHED_SELECTION_SEED="${MATCHED_SELECTION_SEED:-20260323}"

BASIN_WIDE_SEEDS="${BASIN_WIDE_SEEDS:-10}"
BASIN_DEEP_SEEDS="${BASIN_DEEP_SEEDS:-50}"
BASIN_DEEP_SIZE="${BASIN_DEEP_SIZE:-40}"
DEEP_SELECTOR="${DEEP_SELECTOR:-abstract-evidence/deep-40}"

DIST_MCTS_AGENTS="${DIST_MCTS_AGENTS:-8}"
DIST_MCTS_INFLIGHT="${DIST_MCTS_INFLIGHT:-64}"
DIST_MCTS_VIRTUAL_LOSS="${DIST_MCTS_VIRTUAL_LOSS:-1}"
DIST_MCTS_DETERMINISTIC_INFERENCE="${DIST_MCTS_DETERMINISTIC_INFERENCE:-1}"
MCTS_BLOCK_DURATION="${MCTS_BLOCK_DURATION:-20}"
MCTS_BLOCK_SEED="${MCTS_BLOCK_SEED:-20260323}"
MCTS_DELAY_DURATION="${MCTS_DELAY_DURATION:-5}"
MCTS_DELAY_SEED="${MCTS_DELAY_SEED:-20260323}"
MCTS_REROUTE_MAX="${MCTS_REROUTE_MAX:-4}"
DEEPSEEK_P1_SAMPLES="${DEEPSEEK_P1_SAMPLES:-10}"

REPEAT_SEEDS="${REPEAT_SEEDS:-20}"

PAIR_CORPUS_ID="${PAIR_CORPUS_ID:-coq-paired-micro-v1}"
PAIRS_PATH="${PAIRS_PATH:-${ROOT_DIR}/analysis/benchmarks/lean_coq_logic_micro_v1.json}"
DEEPSEEK_ARTIFACT_ROOT="${DEEPSEEK_ARTIFACT_ROOT:-${SPECTER_ARTIFACT_ROOT:-}}"
SERAPI_BINARY="${SERAPI_BINARY:-sertop}"

RESUME_ARGS=()
if [[ "${LEAN_RESUME}" == "1" ]]; then
  RESUME_ARGS+=(--resume)
fi

if [[ -z "${P1_RUN_LABEL_DEEPSEEK:-}" ]]; then
  P1_RUN_LABEL_DEEPSEEK="mcts=distributed-deterministic"
fi
if [[ -z "${P1_EXTRA_ARGS_DEEPSEEK:-}" ]]; then
  P1_EXTRA_ARGS_DEEPSEEK="--wild-only --no-solution-artifacts --deepseek-samples ${DEEPSEEK_P1_SAMPLES} --mcts-mode distributed --mcts-agents ${DIST_MCTS_AGENTS} --mcts-inflight ${DIST_MCTS_INFLIGHT} --mcts-virtual-loss ${DIST_MCTS_VIRTUAL_LOSS} --mcts-deterministic-inference"
fi

IFS=',' read -r -a LEAN_PROVIDERS <<< "${LEAN_PROVIDERS_CSV}"
IFS=',' read -r -a PRIMARY_LLM_PROVIDERS <<< "${PRIMARY_LLM_PROVIDERS_CSV}"
IFS=',' read -r -a P1_PROVIDERS <<< "${P1_PROVIDERS_CSV}"

SCHEDULER_CONDITIONS=(
  "damage-block-f0.1"
  "damage-block-f0.3"
  "damage-block-f0.5"
  "adapt-block-f0.1"
  "adapt-block-f0.3"
  "adapt-block-f0.5"
  "damage-delay-p0.1"
  "damage-delay-p0.3"
)

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
MATCHED_SLICE_JSON="${META_DIR}/matched-slice.json"
SCHEDULER_MATRIX_JSON="${META_DIR}/scheduler-matrix-summary.json"
DEEP_SLICE_JSON="${META_DIR}/deep-slice.json"
REPEAT_PLAN_JSON="${META_DIR}/repeat-plan.json"
POSTPROCESS_QUEUE_FILE="${META_DIR}/deferred-postprocess-roots.txt"

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
    run_cmd env DEEPSEEK_ARTIFACT_ROOT="${DEEPSEEK_ARTIFACT_ROOT}" SPECTER_ARTIFACT_ROOT="${DEEPSEEK_ARTIFACT_ROOT}" "$@"
  else
    run_cmd "$@"
  fi
}

env_value() {
  local name="$1"
  printf '%s' "${!name:-}"
}

provider_var_name() {
  local phase="$1"
  local kind="$2"
  local provider="$3"
  local provider_key="${provider^^}"
  provider_key="${provider_key//[^A-Z0-9]/_}"
  printf '%s_%s_%s\n' "${phase}" "${kind}" "${provider_key}"
}

provider_run_label() {
  local phase="$1"
  local provider="$2"
  local var_name
  var_name="$(provider_var_name "${phase}" RUN_LABEL "${provider}")"
  local value
  value="$(env_value "${var_name}")"
  if [[ -n "${value}" ]]; then
    printf '%s\n' "${value}"
  else
    printf 'mcts=centralized\n'
  fi
}

provider_extra_args() {
  local phase="$1"
  local provider="$2"
  local var_name
  var_name="$(provider_var_name "${phase}" EXTRA_ARGS "${provider}")"
  local value
  value="$(env_value "${var_name}")"
  local -n out_ref="$3"
  out_ref=()
  if [[ -n "${value}" ]]; then
    # shellcheck disable=SC2206
    out_ref=(${value})
  fi
}

run_dir_completed() {
  local run_dir="$1"
  local status_path="${run_dir}/run_status.json"
  [[ -f "${status_path}" ]] || return 1
  python - "${status_path}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("status") == "completed" else 1)
PY
}

resolve_deepseek_artifact_root() {
  local preferred_root="$1"
  uv run python - "${preferred_root}" <<'PY'
import sys
from pathlib import Path

from runtime_paths import find_root_containing

preferred_root = sys.argv[1].strip()
candidate_roots = [Path(preferred_root)] if preferred_root else None

for model_dirname in ("ntp-mathlib-deepseek-1.3b-mlx-bf16", "ntp-mathlib-deepseek-1.3b-mlx-4bit"):
    root = find_root_containing(
        Path("wonton-soup") / "models" / model_dirname,
        candidate_roots=candidate_roots,
    )
    if root is not None:
        print(root)
        raise SystemExit(0)

raise SystemExit(1)
PY
}

phase_header() {
  echo
  echo "== $1 =="
}

provider_enabled() {
  local needle="$1"
  for provider in "${P1_PROVIDERS[@]}"; do
    if [[ "${provider}" == "${needle}" ]]; then
      return 0
    fi
  done
  return 1
}

ensure_meta_dir() {
  run_cmd mkdir -p "${META_DIR}"
}

queue_deferred_postprocess() {
  local logs_dir="$1"
  ensure_meta_dir
  if [[ "${EXECUTE}" -eq 1 ]]; then
    touch "${POSTPROCESS_QUEUE_FILE}"
    if ! grep -Fxq "${logs_dir}" "${POSTPROCESS_QUEUE_FILE}"; then
      printf '%s\n' "${logs_dir}" >> "${POSTPROCESS_QUEUE_FILE}"
    fi
  fi
  echo "Deferred postprocess/reconcile for ${logs_dir}"
}

run_deferred_postprocess_queue() {
  phase_header "Deferred Postprocess Queue"
  ensure_meta_dir
  if [[ ! -s "${POSTPROCESS_QUEUE_FILE}" ]]; then
    echo "No queued logs roots at ${POSTPROCESS_QUEUE_FILE}"
    return
  fi

  mapfile -t queued_roots < <(awk 'NF {print}' "${POSTPROCESS_QUEUE_FILE}")
  if [[ "${#queued_roots[@]}" -eq 0 ]]; then
    echo "No queued logs roots at ${POSTPROCESS_QUEUE_FILE}"
    return
  fi

  local logs_dir
  for logs_dir in "${queued_roots[@]}"; do
    run_cmd uv run python wonton.py postprocess --logs-dir "${logs_dir}"
    run_cmd uv run python wonton.py lake reconcile --logs-dir "${logs_dir}"
  done

  if [[ "${EXECUTE}" -eq 1 ]]; then
    rm -f "${POSTPROCESS_QUEUE_FILE}"
  fi
}

json_string_field() {
  local path="$1"
  local key="$2"
  python - "${path}" "${key}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
payload = json.loads(path.read_text(encoding="utf-8"))
value = payload
for part in key.split("."):
    if not isinstance(value, dict) or part not in value:
        raise KeyError(key)
    value = value[part]
if not isinstance(value, str):
    raise TypeError(key)
print(value)
PY
}

resolve_json_string() {
  local path="$1"
  local key="$2"
  local fallback="$3"
  if [[ -f "${path}" ]]; then
    json_string_field "${path}" "${key}"
  else
    printf '%s\n' "${fallback}"
  fi
}

pair_limit() {
  python - "${PAIRS_PATH}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
pairs = payload.get("pairs")
if not isinstance(pairs, list):
    raise SystemExit("pairs file missing pairs list")
print(len(pairs))
PY
}

resolve_current_corpus_ref() {
  local corpus_id="$1"
  python - "${corpus_id}" <<'PY'
import sys
from pathlib import Path

from runtime_paths import resolve_corpora_root

corpus_id = sys.argv[1]
current_path = resolve_corpora_root() / "lean" / corpus_id / "CURRENT"
if not current_path.exists():
    raise SystemExit(1)
build_id = current_path.read_text(encoding="utf-8").strip()
if not build_id:
    raise SystemExit(1)
print(f"lean:{corpus_id}@{build_id}")
PY
}

corpus_item_total() {
  local corpus_ref="$1"
  python - "${corpus_ref}" <<'PY'
import json
import sys
from pathlib import Path

from corpus.artifacts import parse_corpus_ref, resolve_build_dir

ref = parse_corpus_ref(sys.argv[1])
build_ref = resolve_build_dir(ref.backend, ref.corpus_id, build_id=ref.build_id)
items_dir = build_ref.build_dir
if ref.derived:
    derived_root = items_dir / "derived" / ref.derived
    if not derived_root.exists():
        raise SystemExit(f"Derived path not found for corpus ref: {sys.argv[1]}")
    current = derived_root / "CURRENT"
    if current.exists():
        derived_build_id = current.read_text(encoding="utf-8").strip()
        if not derived_build_id:
            raise SystemExit(f"Empty CURRENT pointer in derived path: {derived_root}")
        items_dir = derived_root / derived_build_id
    else:
        items_dir = derived_root

manifest_path = items_dir / "manifest.json"
if manifest_path.exists():
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = payload.get("counts")
    total = counts.get("items_total") if isinstance(counts, dict) else None
    if isinstance(total, int):
        print(total)
        raise SystemExit(0)

items_path = items_dir / "items.jsonl"
if not items_path.exists():
    raise SystemExit(f"items.jsonl not found for corpus ref: {sys.argv[1]}")
with items_path.open("r", encoding="utf-8") as handle:
    print(sum(1 for line in handle if line.strip()))
PY
}

require_corpus_items() {
  local corpus_ref="$1"
  local minimum="$2"
  local label="$3"
  local total
  total="$(corpus_item_total "${corpus_ref}")"
  if [[ "${total}" -lt "${minimum}" ]]; then
    echo "${label} requires at least ${minimum} items, but ${corpus_ref} resolves to ${total}." >&2
    exit 2
  fi
}

matched_ref() {
  resolve_json_string "${MATCHED_SLICE_JSON}" "derived_corpus_ref" "lean:<matched-slice>"
}

deep_ref() {
  resolve_json_string "${DEEP_SLICE_JSON}" "derived_corpus_ref" "lean:<deep-slice>"
}

p2_centralized_run_dir() {
  local provider="$1"
  printf '%s\n' "${PROGRAM_LOGS_DIR}/p2-paired/provider=${provider}/control=centralized"
}

p1_run_dir() {
  local provider="$1"
  printf '%s\n' "${PROGRAM_LOGS_DIR}/p1-shared/provider=${provider}/$(provider_run_label P1 "${provider}")"
}

p2_distributed_run_dir() {
  local provider="$1"
  printf '%s\n' "${PROGRAM_LOGS_DIR}/p2-paired/provider=${provider}/distributed-a${DIST_MCTS_AGENTS}-i${DIST_MCTS_INFLIGHT}"
}

p3_basin_run_dir() {
  local provider="$1"
  printf '%s\n' "${PROGRAM_LOGS_DIR}/p3-basin-wide/provider=${provider}/seeds=${BASIN_WIDE_SEEDS}"
}

run_postprocess_and_reconcile() {
  local logs_dir="$1"
  if [[ "${INLINE_POSTPROCESS}" != "1" ]]; then
    queue_deferred_postprocess "${logs_dir}"
    return
  fi
  run_cmd uv run python wonton.py postprocess --logs-dir "${logs_dir}"
  run_cmd uv run python wonton.py lake reconcile --logs-dir "${logs_dir}"
}

preflight_checks() {
  if provider_enabled "deepseek" && [[ -z "${VLLM_ENDPOINTS:-}${VLLM_ENDPOINT:-}" ]]; then
    local resolved_root
    resolved_root="$(resolve_deepseek_artifact_root "${DEEPSEEK_ARTIFACT_ROOT:-}" || true)"
    if [[ -z "${resolved_root}" ]]; then
      echo "DeepSeek provider enabled, but no model root was found under the configured roots or common mounts." >&2
      exit 2
    fi

    DEEPSEEK_ARTIFACT_ROOT="${resolved_root}"
    export DEEPSEEK_ARTIFACT_ROOT

    local model_dir
    model_dir="${DEEPSEEK_ARTIFACT_ROOT%/}/wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-bf16"
    if [[ ! -d "${model_dir}" && ! -d "${DEEPSEEK_ARTIFACT_ROOT%/}/wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-4bit" ]]; then
      echo "DeepSeek model directory not found under resolved root: ${DEEPSEEK_ARTIFACT_ROOT}" >&2
      exit 2
    fi
  fi
  if [[ ! -f "${PAIRS_PATH}" ]]; then
    echo "Pairs file not found: ${PAIRS_PATH}" >&2
    exit 2
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

prepare_paired_coq_inputs() {
  local tmp_dir="${PROGRAM_LOGS_DIR}/p5-cross-assistant/tmp"
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

run_p1_shared_panel() {
  phase_header "P1 Shared Lean Panel"
  require_corpus_items "${LEAN_CORPUS_REF}" "${PANEL_SAMPLE}" "P1 shared panel"
  local provider
  for provider in "${P1_PROVIDERS[@]}"; do
    local run_label
    run_label="$(provider_run_label P1 "${provider}")"
    local run_dir
    run_dir="${PROGRAM_LOGS_DIR}/p1-shared/provider=${provider}/${run_label}"
    if [[ "${SKIP_COMPLETED_RUNS}" == "1" ]] && run_dir_completed "${run_dir}"; then
      echo "Skipping completed p1 run: ${run_dir}"
      continue
    fi

    local -a extra_args
    provider_extra_args P1 "${provider}" extra_args
    run_provider_cmd "${provider}" \
      uv run python wonton.py lean run \
      -m research \
      -c "${LEAN_CORPUS_REF}" \
      -p "${provider}" \
      -b "${RESEARCH_BUDGET}" \
      "${SAMPLING_ARGS[@]}" \
      --sample "${PANEL_SAMPLE}" \
      --seed "${PANEL_SELECTION_SEED}" \
      --workers "${LEAN_WORKERS}" \
      --plain \
      --run-id "${RUN_ID_ROOT}/p1-shared/provider=${provider}/${run_label}" \
      --no-sync \
      "${RESUME_ARGS[@]}" \
      "${extra_args[@]}"
  done
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p1-shared"
}

run_p2_freeze_matched() {
  phase_header "P2 Freeze Matched Slice"
  ensure_meta_dir
  local -a cmd=(
    uv run python -m analysis.abstract_evidence freeze-matched
    --provider-run "reprover=$(p1_run_dir reprover)"
    --provider-run "deepseek=$(p1_run_dir deepseek)"
    --llm-provider reprover
    --llm-provider deepseek
    --size "${MATCHED_SLICE_SIZE}"
    --selector "${MATCHED_SELECTOR}"
    --output "${MATCHED_SLICE_JSON}"
  )
  run_cmd "${cmd[@]}"
}

run_p3_controls() {
  phase_header "P3 Matched Centralized vs Distributed Controls"
  local matched_corpus_ref
  matched_corpus_ref="$(matched_ref)"
  local -a cmd=(
    env
    "PROGRAM_ID=${PROGRAM_RUN_ROOT}"
    "LEAN_CORPUS_REF=${matched_corpus_ref}"
    "LEAN_PROVIDERS_CSV=${P3_PROVIDERS_CSV}"
    "RESEARCH_BUDGET=${RESEARCH_BUDGET}"
    "LEAN_WORKERS=${LEAN_WORKERS}"
    "LEAN_RESUME=${LEAN_RESUME}"
    "DISTRIBUTED_SAMPLE=${MATCHED_SLICE_SIZE}"
    "DISTRIBUTED_SELECTION_SEED=${MATCHED_SELECTION_SEED}"
    "DIST_MCTS_AGENTS=${DIST_MCTS_AGENTS}"
    "DIST_MCTS_INFLIGHT=${DIST_MCTS_INFLIGHT}"
    "DIST_MCTS_VIRTUAL_LOSS=${DIST_MCTS_VIRTUAL_LOSS}"
    "DIST_MCTS_DETERMINISTIC_INFERENCE=${DIST_MCTS_DETERMINISTIC_INFERENCE}"
    "DEEPSEEK_ARTIFACT_ROOT=${DEEPSEEK_ARTIFACT_ROOT}"
    scripts/followup_run_program.sh
    --phase
    p2
  )
  if [[ "${EXECUTE}" -eq 1 ]]; then
    cmd+=(--execute)
  fi
  run_cmd "${cmd[@]}"
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p2-paired"
}

run_p4_scheduler_matrix() {
  phase_header "P4 Distributed Scheduler Matrix"
  local matched_corpus_ref
  matched_corpus_ref="$(matched_ref)"
  for provider in "${PRIMARY_LLM_PROVIDERS[@]}"; do
    for condition in "${SCHEDULER_CONDITIONS[@]}"; do
      distributed_base_args
      condition_args "${condition}"
      run_provider_cmd "${provider}" \
        uv run python wonton.py lean run \
        -m research \
        -c "${matched_corpus_ref}" \
        -p "${provider}" \
        -b "${RESEARCH_BUDGET}" \
        --sample "${MATCHED_SLICE_SIZE}" \
        --seed "${MATCHED_SELECTION_SEED}" \
        --workers "${LEAN_WORKERS}" \
        --plain \
        --run-id "${RUN_ID_ROOT}/p2b-scheduler-matrix/provider=${provider}/condition=${condition}" \
        --no-sync \
        "${RESUME_ARGS[@]}" \
        "${DISTRIBUTED_ARGS[@]}" \
        "${CONDITION_ARGS[@]}"
    done
  done
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p2b-scheduler-matrix"
  ensure_meta_dir
  local -a cmd=(
    uv run python -m analysis.abstract_evidence summarize-matrix
    --baseline-run "reprover=$(p2_distributed_run_dir reprover)"
    --baseline-run "deepseek=$(p2_distributed_run_dir deepseek)"
    --matrix-root "${PROGRAM_LOGS_DIR}/p2b-scheduler-matrix"
    --output "${SCHEDULER_MATRIX_JSON}"
  )
  run_cmd "${cmd[@]}"
}

run_p5_basin_wide() {
  phase_header "P5 Basin Wide"
  local matched_corpus_ref
  matched_corpus_ref="$(matched_ref)"
  local -a cmd=(
    env
    "PROGRAM_ID=${PROGRAM_RUN_ROOT}"
    "LEAN_CORPUS_REF=${matched_corpus_ref}"
    "LEAN_PROVIDERS_CSV=${P5_PROVIDERS_CSV}"
    "RESEARCH_BUDGET=${RESEARCH_BUDGET}"
    "LEAN_WORKERS=${LEAN_WORKERS}"
    "LEAN_RESUME=${LEAN_RESUME}"
    "PANEL_SAMPLE=${MATCHED_SLICE_SIZE}"
    "PANEL_SELECTION_SEED=${MATCHED_SELECTION_SEED}"
    "BASIN_WIDE_SEEDS=${BASIN_WIDE_SEEDS}"
    "LEAN_SAMPLING=1"
    "DEEPSEEK_ARTIFACT_ROOT=${DEEPSEEK_ARTIFACT_ROOT}"
    scripts/followup_run_program.sh
    --phase
    p3
  )
  if [[ "${EXECUTE}" -eq 1 ]]; then
    cmd+=(--execute)
  fi
  run_cmd "${cmd[@]}"
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p3-basin-wide"
}

run_p6_freeze_deep() {
  phase_header "P6 Freeze Deep Slice"
  ensure_meta_dir
  local -a cmd=(
    uv run python -m analysis.abstract_evidence freeze-deep
    --wide-run "reprover=$(p3_basin_run_dir reprover)"
    --wide-run "deepseek=$(p3_basin_run_dir deepseek)"
    --matrix-summary "${SCHEDULER_MATRIX_JSON}"
    --matched-slice "${MATCHED_SLICE_JSON}"
    --size "${BASIN_DEEP_SIZE}"
    --selector "${DEEP_SELECTOR}"
    --output "${DEEP_SLICE_JSON}"
  )
  run_cmd "${cmd[@]}"
}

run_p7_basin_deep() {
  phase_header "P7 Basin Deep"
  local deep_corpus_ref
  deep_corpus_ref="$(deep_ref)"
  local -a cmd=(
    env
    "PROGRAM_ID=${PROGRAM_RUN_ROOT}"
    "LEAN_CORPUS_REF=${deep_corpus_ref}"
    "LEAN_PROVIDERS_CSV=${P7_PROVIDERS_CSV}"
    "RESEARCH_BUDGET=${RESEARCH_BUDGET}"
    "LEAN_WORKERS=${LEAN_WORKERS}"
    "LEAN_RESUME=${LEAN_RESUME}"
    "BASIN_DEEP_SEEDS=${BASIN_DEEP_SEEDS}"
    "BASIN_DEEP_SAMPLE=${BASIN_DEEP_SIZE}"
    "BASIN_DEEP_SELECTION_SEED=${MATCHED_SELECTION_SEED}"
    "LEAN_SAMPLING=1"
    "DEEPSEEK_ARTIFACT_ROOT=${DEEPSEEK_ARTIFACT_ROOT}"
    scripts/followup_run_program.sh
    --phase
    p4
  )
  if [[ "${EXECUTE}" -eq 1 ]]; then
    cmd+=(--execute)
  fi
  run_cmd "${cmd[@]}"
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p4-basin-deep"
}

run_p8_repeat_stability() {
  phase_header "P8 Repeat Stability Cohort"
  ensure_meta_dir
  local matched_corpus_ref
  matched_corpus_ref="$(matched_ref)"
  local -a plan_cmd=(
    uv run python -m analysis.abstract_evidence plan-repeat
    --matrix-summary "${SCHEDULER_MATRIX_JSON}"
    --matched-slice "${MATCHED_SLICE_JSON}"
    --centralized-run "reprover=$(p2_centralized_run_dir reprover)"
    --centralized-run "deepseek=$(p2_centralized_run_dir deepseek)"
    --output "${REPEAT_PLAN_JSON}"
  )
  run_cmd "${plan_cmd[@]}"

  while IFS=$'\t' read -r case_id repeat_mode provider theorem condition intervention blocked_csv classification; do
    [[ -n "${case_id}" ]] || continue
    if [[ "${repeat_mode}" == "distributed_run" ]]; then
      distributed_base_args
      condition_args "${condition}"
      for ((seed=0; seed<REPEAT_SEEDS; seed++)); do
        run_provider_cmd "${provider}" \
          uv run python wonton.py lean run \
          -m research \
          -c "${matched_corpus_ref}" \
          -p "${provider}" \
          -b "${RESEARCH_BUDGET}" \
          -t "${theorem}" \
          --wild-only \
          --sampling \
          --search-seed "${seed}" \
          --workers 1 \
          --plain \
          --run-id "${RUN_ID_ROOT}/p4b-repeat-stability/case=${case_id}/seed=${seed}/control" \
          --no-sync \
          "${RESUME_ARGS[@]}" \
          "${DISTRIBUTED_ARGS[@]}"

        run_provider_cmd "${provider}" \
          uv run python wonton.py lean run \
          -m research \
          -c "${matched_corpus_ref}" \
          -p "${provider}" \
          -b "${RESEARCH_BUDGET}" \
          -t "${theorem}" \
          --wild-only \
          --sampling \
          --search-seed "${seed}" \
          --workers 1 \
          --plain \
          --run-id "${RUN_ID_ROOT}/p4b-repeat-stability/case=${case_id}/seed=${seed}/perturbed" \
          --no-sync \
          "${RESUME_ARGS[@]}" \
          "${DISTRIBUTED_ARGS[@]}" \
          "${CONDITION_ARGS[@]}"
      done
    elif [[ "${repeat_mode}" == "centralized_run" ]]; then
      for ((seed=0; seed<REPEAT_SEEDS; seed++)); do
        run_provider_cmd "${provider}" \
          uv run python wonton.py lean run \
          -m research \
          -c "${matched_corpus_ref}" \
          -p "${provider}" \
          -b "${RESEARCH_BUDGET}" \
          -t "${theorem}" \
          --wild-only \
          --sampling \
          --search-seed "${seed}" \
          --workers 1 \
          --plain \
          --run-id "${RUN_ID_ROOT}/p4b-repeat-stability/case=${case_id}/seed=${seed}/control" \
          --no-sync \
          "${RESUME_ARGS[@]}"

        extra_args=()
        if [[ -n "${blocked_csv}" ]]; then
          extra_args+=(--extra-intervention "${intervention}=${blocked_csv}")
        fi
        run_provider_cmd "${provider}" \
          uv run python wonton.py lean run \
          -m research \
          -c "${matched_corpus_ref}" \
          -p "${provider}" \
          -b "${RESEARCH_BUDGET}" \
          -t "${theorem}" \
          --sampling \
          --search-seed "${seed}" \
          --workers 1 \
          --plain \
          --intervention-name "${intervention}" \
          --run-id "${RUN_ID_ROOT}/p4b-repeat-stability/case=${case_id}/seed=${seed}/perturbed" \
          --no-sync \
          "${RESUME_ARGS[@]}" \
          "${extra_args[@]}"
      done
    else
      echo "Unknown repeat mode: ${repeat_mode}" >&2
      exit 2
    fi
  done < <(
    python - "${REPEAT_PLAN_JSON}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for row in payload.get("cases", []):
    if not isinstance(row, dict):
        continue
    values = [
        row.get("id"),
        row.get("repeat_mode"),
        row.get("provider"),
        row.get("theorem"),
        row.get("condition") or "",
        row.get("intervention") or "",
        ",".join(row.get("blocked") or []) if isinstance(row.get("blocked"), list) else "",
        row.get("classification"),
    ]
    required = [values[0], values[1], values[2], values[3], values[7]]
    if all(isinstance(value, str) and value for value in required):
        print("\t".join(values))
PY
  )
  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p4b-repeat-stability"
}

run_p9_cross_assistant_refresh() {
  phase_header "P9 Lean↔Rocq Paired Benchmark Refresh"
  local pair_limit paired_corpus_ref
  pair_limit="$(pair_limit)"
  local -a build_cmd=(
    uv run python wonton.py corpus build-lean-coq-paired-micro
    --corpus-id "${PAIR_CORPUS_ID}"
    --pairs-path "${PAIRS_PATH}"
  )
  run_cmd "${build_cmd[@]}"
  paired_corpus_ref="$(resolve_current_corpus_ref "${PAIR_CORPUS_ID}" 2>/dev/null || printf 'lean:%s' "${PAIR_CORPUS_ID}")"

  run_provider_cmd reprover \
    uv run python wonton.py lean run \
    -m research \
    -c "${paired_corpus_ref}" \
    -p reprover \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --wild-only \
    --plain \
    --run-id "${RUN_ID_ROOT}/p5-cross-assistant/lean/provider=reprover/wild-only" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  run_provider_cmd deepseek \
    uv run python wonton.py lean run \
    -m research \
    -c "${paired_corpus_ref}" \
    -p deepseek \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --wild-only \
    --plain \
    --run-id "${RUN_ID_ROOT}/p5-cross-assistant/lean/provider=deepseek/wild-only" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  run_provider_cmd deepseek \
    uv run python wonton.py lean run \
    -m research \
    -c "${paired_corpus_ref}" \
    -p deepseek \
    -b "${RESEARCH_BUDGET}" \
    -n "${pair_limit}" \
    --plain \
    --run-id "${RUN_ID_ROOT}/p5-cross-assistant/lean/provider=deepseek/with-interventions" \
    --no-sync \
    "${RESUME_ARGS[@]}"

  run_postprocess_and_reconcile "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean"

  prepare_paired_coq_inputs
  run_cmd \
    uv run python wonton.py run \
    --backend coq \
    --coq-mode file \
    --source "${PAIRED_COQ_IMPORTS_FILE}" \
    --theorem-file "${PAIRED_COQ_THEOREM_FILE}" \
    --serapi-binary "${SERAPI_BINARY}" \
    --log-dir "${PROGRAM_LOGS_DIR}/p5-cross-assistant/coq/paired-extract"

  local wild_pool="${PROGRAM_LOGS_DIR}/p5-cross-assistant/pool-wild"
  local bestof_pool="${PROGRAM_LOGS_DIR}/p5-cross-assistant/pool-bestof"
  local report_dir="${PROGRAM_LOGS_DIR}/p5-cross-assistant/reports"
  if [[ "${EXECUTE}" -eq 1 ]]; then
    if [[ -e "${wild_pool}" || -e "${bestof_pool}" ]]; then
      echo "Provider pool dir already exists under ${PROGRAM_LOGS_DIR}/p5-cross-assistant" >&2
      exit 1
    fi
  fi
  run_cmd mkdir -p "${wild_pool}" "${bestof_pool}" "${report_dir}"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean/provider=reprover/wild-only" "${wild_pool}/provider=reprover-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean/provider=deepseek/wild-only" "${wild_pool}/provider=deepseek-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean/provider=reprover/wild-only" "${bestof_pool}/provider=reprover-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean/provider=deepseek/wild-only" "${bestof_pool}/provider=deepseek-wild"
  run_cmd ln -s "${PROGRAM_LOGS_DIR}/p5-cross-assistant/lean/provider=deepseek/with-interventions" "${bestof_pool}/provider=deepseek-bestof"

  benchmark_report() {
    local lean_root="$1"
    local output_name="$2"
    shift 2
    run_cmd \
      uv run python wonton.py benchmark-cross-assistant \
      --run-lean "${lean_root}" \
      --run-coq "${PROGRAM_LOGS_DIR}/p5-cross-assistant/coq/paired-extract" \
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
    --name-obfuscation-salt wonton-obf-abstract-v1 \
    --lexical-ablation graph_only
}

preflight_checks

echo "Program ID:        ${PROGRAM_ID}"
echo "Run root:          ${PROGRAM_RUN_ROOT}"
echo "Cohort logs dir:   ${PROGRAM_LOGS_DIR}"
echo "Lake DB:           ${ACTIVE_LAKE_DB}"
echo "Lean corpus ref:   ${LEAN_CORPUS_REF}"
echo "Lean providers:    ${LEAN_PROVIDERS_CSV}"
echo "P1 providers:      ${P1_PROVIDERS_CSV}"
echo "P3 providers:      ${P3_PROVIDERS_CSV}"
echo "P5 providers:      ${P5_PROVIDERS_CSV}"
echo "P7 providers:      ${P7_PROVIDERS_CSV}"
echo "Lean project:      ${LEAN_PROJECT_PATH}"
echo "Primary LLMs:      ${PRIMARY_LLM_PROVIDERS_CSV}"
echo "Inline postproc:   $([[ "${INLINE_POSTPROCESS}" == "1" ]] && echo yes || echo no)"
echo "Postproc queue:    ${POSTPROCESS_QUEUE_FILE}"
echo "DeepSeek root:     ${DEEPSEEK_ARTIFACT_ROOT:-<unset>}"
echo "Dry run mode:      $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"

if [[ "${PHASE}" == "all" || "${PHASE}" == "p1" ]]; then
  run_p1_shared_panel
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p2" ]]; then
  run_p2_freeze_matched
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p3" ]]; then
  run_p3_controls
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p4" ]]; then
  run_p4_scheduler_matrix
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p5" ]]; then
  run_p5_basin_wide
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p6" ]]; then
  run_p6_freeze_deep
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p7" ]]; then
  run_p7_basin_deep
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p8" ]]; then
  run_p8_repeat_stability
fi
if [[ "${PHASE}" == "all" || "${PHASE}" == "p9" ]]; then
  run_p9_cross_assistant_refresh
fi
if [[ "${PHASE}" == "post" ]]; then
  run_deferred_postprocess_queue
fi
