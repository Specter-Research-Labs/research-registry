#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"

phase="${1-}"
if [[ -z "$phase" ]]; then
  echo "usage: run-corpus-v1.sh <core-neutral|qd-me|qd-aurora|replay|all> [--input PATH] [--seed-base N] [--output-root DIR] [--db PATH]" >&2
  exit 2
fi
shift

seed_base=0
input_path=""
output_root=""
db_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      input_path="$2"
      shift 2
      ;;
    --seed-base)
      seed_base="$2"
      shift 2
      ;;
    --output-root)
      output_root="$2"
      shift 2
      ;;
    --db)
      db_path="$2"
      shift 2
      ;;
    *)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
  esac
done

require_nonempty_env() {
  local name="$1"
  if [[ "${!name+x}" == x && -z "${!name}" ]]; then
    echo "$name is set but empty" >&2
    exit 2
  fi
}

require_nonempty_env "SPECTER_ARTIFACT_ROOT"
require_nonempty_env "SPECTER_LOG_ROOT"
require_nonempty_env "SPECTER_RUNTIME_ROOT"
require_nonempty_env "LENIA_CLI_BIN"

resolve_path() {
  python3 -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

resolve_cli() {
  if [[ -n "${LENIA_CLI_BIN-}" ]]; then
    local explicit_cli
    explicit_cli="$(resolve_path "$LENIA_CLI_BIN")"
    if [[ ! -x "$explicit_cli" ]]; then
      echo "LENIA_CLI_BIN is not executable: $explicit_cli" >&2
      exit 2
    fi
    echo "$explicit_cli"
    return
  fi
  if [[ -n "${SPECTER_RUNTIME_ROOT-}" ]]; then
    local runtime_cli="${SPECTER_RUNTIME_ROOT%/}/lenia-swarm/verify-dd/Build/Products/Release/LeniaCLI"
    if [[ -x "$runtime_cli" ]]; then
      echo "$runtime_cli"
      return
    fi
  fi
  if [[ -x "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI" ]]; then
    echo "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI"
    return
  fi
  echo "missing LeniaCLI binary. Set LENIA_CLI_BIN or build LeniaCLI first." >&2
  exit 2
}

stamp() {
  printf '%s-%s\n' "$(date +%Y%m%d-%H%M%S)" "$$"
}

if [[ -z "$output_root" ]]; then
  if [[ -n "${SPECTER_ARTIFACT_ROOT-}" ]]; then
    output_root="${SPECTER_ARTIFACT_ROOT%/}/lenia-swarm/outputs/corpus-v1"
  else
    output_root="$dossier_root/artifacts/corpus-v1"
  fi
fi
if [[ -z "$db_path" ]]; then
  if [[ -n "${SPECTER_ARTIFACT_ROOT-}" ]]; then
    db_path="${SPECTER_ARTIFACT_ROOT%/}/lenia-swarm/outputs/compendium.sqlite"
  else
    db_path="$dossier_root/outputs/compendium.sqlite"
  fi
fi

if [[ -n "${SPECTER_LOG_ROOT-}" ]]; then
  log_root="${SPECTER_LOG_ROOT%/}/lenia-swarm/corpus-v1"
else
  log_root="$dossier_root/outputs/logs/corpus-v1"
fi

output_root="$(resolve_path "$output_root")"
db_path="$(resolve_path "$db_path")"
log_root="$(resolve_path "$log_root")"
if [[ -n "$input_path" ]]; then
  input_path="$(resolve_path "$input_path")"
fi

mkdir -p "$output_root" "$log_root" "$(dirname "$db_path")"

base_config="$dossier_root/configs/base/paper_base_1c_128.json"
core_search_config="$dossier_root/configs/search/search_corpus_v1_core_neutral.json"
qd_config_dir="$dossier_root/configs/papers/leniabreeder-2024"

for required_path in \
  "$base_config" \
  "$core_search_config" \
  "$qd_config_dir"; do
  if [[ ! -e "$required_path" ]]; then
    echo "missing required corpus-v1 input: $required_path" >&2
    exit 2
  fi
done

cli_bin="$(resolve_cli)"
LAST_RUN_DIR=""

index_run() {
  local run_dir="$1"
  "$cli_bin" index --run-dir "$run_dir" --db "$db_path" --include-results --stats
}

run_core_neutral() {
  local run_id="corpus-v1-core-neutral-$(stamp)"
  local phase_root="$output_root/core-neutral"
  mkdir -p "$phase_root"
  "$cli_bin" discover local \
    --config "$base_config" \
    --search "$core_search_config" \
    --output "$phase_root" \
    --seed "$seed_base" \
    --run-id "$run_id" \
    --log-dir "$log_root/core-neutral" \
    --no-log-console \
    --no-promotion
  LAST_RUN_DIR="$phase_root/$run_id"
  index_run "$LAST_RUN_DIR"
}

run_qd() {
  local algorithm="$1"
  local phase_name="qd-$algorithm"
  local phase_seed="$2"
  local run_id="corpus-v1-$phase_name-$(stamp)"
  local run_dir="$output_root/$phase_name/$run_id"
  mkdir -p "$(dirname "$run_dir")"
  "$cli_bin" discover qd-2024 \
    --config-dir "$qd_config_dir" \
    --algorithm "$algorithm" \
    --seed "$phase_seed" \
    --output "$run_dir" \
    --run-id "$run_id" \
    --log-dir "$log_root/$phase_name" \
    --no-log-console
  LAST_RUN_DIR="$run_dir"
  index_run "$LAST_RUN_DIR"
}

run_replay() {
  local label="$1"
  local replay_input="$2"
  if [[ ! -f "$replay_input" ]]; then
    echo "missing replay input: $replay_input" >&2
    exit 2
  fi
  local run_id="corpus-v1-replay-$label-$(stamp)"
  local run_dir="$output_root/replays/$run_id"
  mkdir -p "$(dirname "$run_dir")"
  "$cli_bin" publish replay \
    --input "$replay_input" \
    --output "$run_dir" \
    --db "$db_path" \
    --run-id "$run_id" \
    --log-dir "$log_root/replays" \
    --no-log-console
  LAST_RUN_DIR="$run_dir"
}

case "$phase" in
  core-neutral)
    run_core_neutral
    ;;
  qd-me)
    run_qd "me" "$seed_base"
    ;;
  qd-aurora)
    run_qd "aurora" "$seed_base"
    ;;
  replay)
    if [[ -z "$input_path" ]]; then
      echo "replay requires --input <exports/index.jsonl or library/index.jsonl>" >&2
      exit 2
    fi
    run_replay "manual" "$input_path"
    ;;
  all)
    run_core_neutral
    core_neutral_dir="$LAST_RUN_DIR"
    run_qd "me" "$seed_base"
    qd_me_dir="$LAST_RUN_DIR"
    run_replay "qd-me" "$qd_me_dir/exports/index.jsonl"
    replay_me_dir="$LAST_RUN_DIR"
    run_qd "aurora" "$((seed_base + 1000))"
    qd_aurora_dir="$LAST_RUN_DIR"
    run_replay "qd-aurora" "$qd_aurora_dir/exports/index.jsonl"
    replay_aurora_dir="$LAST_RUN_DIR"
    echo "core-neutral: $core_neutral_dir"
    echo "qd-me: $qd_me_dir"
    echo "replay-qd-me: $replay_me_dir"
    echo "qd-aurora: $qd_aurora_dir"
    echo "replay-qd-aurora: $replay_aurora_dir"
    ;;
  *)
    echo "unknown phase: $phase" >&2
    exit 2
    ;;
esac

"$cli_bin" index sanity --db "$db_path"
echo "db: $db_path"
if [[ -n "$LAST_RUN_DIR" && "$phase" != "all" ]]; then
  echo "run_dir: $LAST_RUN_DIR"
fi
