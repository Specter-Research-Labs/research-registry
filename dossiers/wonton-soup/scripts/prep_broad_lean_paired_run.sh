#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v lake >/dev/null 2>&1 && [ -x "${HOME}/.elan/bin/lake" ]; then
  export PATH="${HOME}/.elan/bin:${PATH}"
fi

EXECUTE=0

usage() {
  cat <<'USAGE'
Usage: scripts/prep_broad_lean_paired_run.sh [--execute]

Build and validate a broad Lean corpus, then print the paired centralized/distributed
follow-up runner command for the resulting pinned corpus ref.

Default behavior is dry-run. Use --execute to perform the build/validate steps.

Environment:
  LEAN_CORPUS_SOURCE=mathlib|minif2f   default: mathlib
  LEAN_CORPUS_ID=<artifact corpus id>  default: broad-lean-paired-2026-03
  LEAN_BUILD_LIMIT=<count>             default: 256
  LEAN_MATHLIB_ELEMENTARY_ONLY=0|1     default: 1
  LEAN_PROVIDERS_CSV=<csv>             default: reprover,deepseek,bfs,internlm,heuristic
  PROGRAM_ID=<run namespace>           default: broad-lean-paired-2026-03
  RESEARCH_BUDGET=<preset>             default: standard
  DISTRIBUTED_SAMPLE=<count>           default: 220
  DISTRIBUTED_SELECTION_SEED=<seed>    default: 20260308
  DIST_MCTS_AGENTS=<count>             default: 8
  DIST_MCTS_INFLIGHT=<count>           default: 64
  MINIF2F_REV=<commit>                 required when LEAN_CORPUS_SOURCE=minif2f
  MINIF2F_SPLITS=<csv>                 default: Test,Valid

Notes:
  - This wrapper prepares a validated corpus and prints the exact `followup_run_program.sh`
    handoff for phase `p2`.
  - It does not start the hours-long provider run unless you run that printed command yourself.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
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

LEAN_CORPUS_SOURCE="${LEAN_CORPUS_SOURCE:-mathlib}"
LEAN_CORPUS_ID="${LEAN_CORPUS_ID:-broad-lean-paired-2026-03}"
LEAN_BUILD_LIMIT="${LEAN_BUILD_LIMIT:-256}"
LEAN_MATHLIB_ELEMENTARY_ONLY="${LEAN_MATHLIB_ELEMENTARY_ONLY:-1}"
LEAN_PROVIDERS_CSV="${LEAN_PROVIDERS_CSV:-reprover,deepseek,bfs,internlm,heuristic}"
PROGRAM_ID="${PROGRAM_ID:-broad-lean-paired-2026-03}"
RESEARCH_BUDGET="${RESEARCH_BUDGET:-standard}"
DISTRIBUTED_SAMPLE="${DISTRIBUTED_SAMPLE:-220}"
DISTRIBUTED_SELECTION_SEED="${DISTRIBUTED_SELECTION_SEED:-20260308}"
DIST_MCTS_AGENTS="${DIST_MCTS_AGENTS:-8}"
DIST_MCTS_INFLIGHT="${DIST_MCTS_INFLIGHT:-64}"
MINIF2F_REV="${MINIF2F_REV:-}"
MINIF2F_SPLITS="${MINIF2F_SPLITS:-Test,Valid}"

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

corpora_root() {
  uv run python - <<'PY'
from runtime_paths import resolve_corpora_root
print(resolve_corpora_root().resolve())
PY
}

current_build_id() {
  local corpus_id="$1"
  local current_path
  current_path="$(corpora_root)/lean/${corpus_id}/CURRENT"
  if [[ ! -f "${current_path}" ]]; then
    echo "CURRENT pointer not found for corpus ${corpus_id}: ${current_path}" >&2
    exit 1
  fi
  tr -d '\n' < "${current_path}"
}

build_mathlib() {
  local cmd=(
    uv run python wonton.py corpus build-lean-mathlib
    --corpus-id "${LEAN_CORPUS_ID}"
    --limit "${LEAN_BUILD_LIMIT}"
  )
  if [[ "${LEAN_MATHLIB_ELEMENTARY_ONLY}" != "1" ]]; then
    cmd+=(--no-elementary-only)
  fi
  run_cmd "${cmd[@]}"
}

build_minif2f() {
  if [[ -z "${MINIF2F_REV}" ]]; then
    echo "MINIF2F_REV is required when LEAN_CORPUS_SOURCE=minif2f" >&2
    exit 2
  fi
  local cmd=(
    uv run python wonton.py corpus build-lean-minif2f
    --corpus-id "${LEAN_CORPUS_ID}"
    --rev "${MINIF2F_REV}"
    --limit "${LEAN_BUILD_LIMIT}"
  )
  IFS=',' read -r -a splits <<< "${MINIF2F_SPLITS}"
  for split in "${splits[@]}"; do
    split="${split// /}"
    if [[ -n "${split}" ]]; then
      cmd+=(--split "${split}")
    fi
  done
  run_cmd "${cmd[@]}"
}

validate_corpus() {
  local base_ref="$1"
  run_cmd uv run python wonton.py corpus validate --ref "${base_ref}"
}

echo "Lean corpus source: ${LEAN_CORPUS_SOURCE}"
echo "Lean corpus id:     ${LEAN_CORPUS_ID}"
echo "Build limit:        ${LEAN_BUILD_LIMIT}"
if [[ "${LEAN_CORPUS_SOURCE}" == "mathlib" ]]; then
  echo "Elementary only:    ${LEAN_MATHLIB_ELEMENTARY_ONLY}"
fi
echo "Providers:          ${LEAN_PROVIDERS_CSV}"
echo "Program ID:         ${PROGRAM_ID}"
echo "Dry run mode:       $([[ "${EXECUTE}" -eq 1 ]] && echo no || echo yes)"

case "${LEAN_CORPUS_SOURCE}" in
  mathlib)
    build_mathlib
    ;;
  minif2f)
    build_minif2f
    ;;
  *)
    echo "Unsupported LEAN_CORPUS_SOURCE: ${LEAN_CORPUS_SOURCE}" >&2
    exit 2
    ;;
esac

if [[ "${EXECUTE}" -eq 0 ]]; then
  echo
  echo "Build id is resolved only after --execute."
  exit 0
fi

BUILD_ID="$(current_build_id "${LEAN_CORPUS_ID}")"
BASE_REF="lean:${LEAN_CORPUS_ID}@${BUILD_ID}"
VALID_REF="${BASE_REF}#valid"

validate_corpus "${BASE_REF}"

echo
echo "Pinned base ref:    ${BASE_REF}"
echo "Pinned valid ref:   ${VALID_REF}"
echo
echo "Paired run handoff (phase p2):"
echo "  PROGRAM_ID=${PROGRAM_ID} \\"
echo "  LEAN_CORPUS_REF=${VALID_REF} \\"
echo "  LEAN_PROVIDERS_CSV=${LEAN_PROVIDERS_CSV} \\"
echo "  RESEARCH_BUDGET=${RESEARCH_BUDGET} \\"
echo "  DISTRIBUTED_SAMPLE=${DISTRIBUTED_SAMPLE} \\"
echo "  DISTRIBUTED_SELECTION_SEED=${DISTRIBUTED_SELECTION_SEED} \\"
echo "  DIST_MCTS_AGENTS=${DIST_MCTS_AGENTS} \\"
echo "  DIST_MCTS_INFLIGHT=${DIST_MCTS_INFLIGHT} \\"
echo "  scripts/followup_run_program.sh --phase p2 --execute"
