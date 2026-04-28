#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"
manifest_path="$dossier_root/configs/sweeps/discovery_sweeps.json"
workspace="$dossier_root/artifacts/discovery-sweep"
db_path=""
target_creatures=100
max_cycles=0
log_level="info"
skip_postprocess=0
sync_remote=0
prebuilt_cli="${LENIA_CLI_BIN-}"
swift_scratch_path="${LENIA_SWIFT_SCRATCH_PATH-}"
swift_tmpdir="${LENIA_SWIFT_TMPDIR-}"

usage() {
  cat <<EOF
usage: sweep.sh [options]

options:
  --output <dir>             local staging root for runs, db, logs, and ecology output
  --db <path>                explicit local compendium sqlite path (defaults to <output>/compendium.sqlite)
  --manifest <path>          discovery sweep manifest json (default: $manifest_path)
  --target-creatures <n>     stop once indexed creature count reaches n (default: $target_creatures)
  --batches <n>              maximum full manifest cycles to run (0 = until target)
  --max-cycles <n>           alias for --batches
  --log-level <level>        LeniaCLI local log level (default: $log_level)
  --skip-postprocess         do not run sanity, taxonomy, and ecology after the sweep
  --sync-remote              rsync the staged workspace to \$SPECTER_ARTIFACT_ROOT and sync compendium.sqlite
  -h, --help                 show this help

environment:
  LENIA_CLI_BIN              use a prebuilt LeniaCLI binary and skip swift build
  LENIA_SWIFT_SCRATCH_PATH   pass --scratch-path to swift build/show-bin-path
  LENIA_SWIFT_TMPDIR         set TMPDIR while building LeniaCLI
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      workspace="$2"
      shift 2
      ;;
    --db)
      db_path="$2"
      shift 2
      ;;
    --manifest)
      manifest_path="$2"
      shift 2
      ;;
    --target-creatures)
      target_creatures="$2"
      shift 2
      ;;
    --batches|--max-cycles)
      max_cycles="$2"
      shift 2
      ;;
    --log-level)
      log_level="$2"
      shift 2
      ;;
    --skip-postprocess)
      skip_postprocess=1
      shift
      ;;
    --sync-remote)
      sync_remote=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${LENIA_CLI_BIN+x}" == x && -z "$prebuilt_cli" ]]; then
  echo "LENIA_CLI_BIN is set but empty" >&2
  exit 2
fi
if [[ "${LENIA_SWIFT_SCRATCH_PATH+x}" == x && -z "$swift_scratch_path" ]]; then
  echo "LENIA_SWIFT_SCRATCH_PATH is set but empty" >&2
  exit 2
fi
if [[ "${LENIA_SWIFT_TMPDIR+x}" == x && -z "$swift_tmpdir" ]]; then
  echo "LENIA_SWIFT_TMPDIR is set but empty" >&2
  exit 2
fi

resolve_path() {
  python3 -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

workspace="$(resolve_path "$workspace")"
manifest_path="$(resolve_path "$manifest_path")"
if [[ -z "$db_path" ]]; then
  db_path="$workspace/compendium.sqlite"
else
  db_path="$(resolve_path "$db_path")"
fi
if [[ -n "$prebuilt_cli" ]]; then
  prebuilt_cli="$(resolve_path "$prebuilt_cli")"
fi
if [[ -n "$swift_scratch_path" ]]; then
  swift_scratch_path="$(resolve_path "$swift_scratch_path")"
fi
if [[ -n "$swift_tmpdir" ]]; then
  swift_tmpdir="$(resolve_path "$swift_tmpdir")"
fi

if [[ ! -f "$manifest_path" ]]; then
  echo "missing sweep manifest: $manifest_path" >&2
  exit 2
fi
if [[ "$target_creatures" -le 0 ]]; then
  echo "target_creatures must be > 0" >&2
  exit 2
fi
if [[ "$max_cycles" -lt 0 ]]; then
  echo "max_cycles must be >= 0" >&2
  exit 2
fi

mkdir -p "$workspace" "$workspace/runs"

state_file="$workspace/sweep-state.json"
summary_file="$workspace/sweep-summary.json"

variant_ids=()
variant_configs=()
variant_searches=()
variant_counts=()

while IFS=$'\t' read -r variant_id variant_config variant_search variant_count; do
  variant_ids+=("$variant_id")
  variant_configs+=("$variant_config")
  variant_searches+=("$variant_search")
  variant_counts+=("$variant_count")
done < <(
  python3 - "$manifest_path" "$dossier_root" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
dossier_root = pathlib.Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text())
variants = manifest.get("variants")
if not isinstance(variants, list) or not variants:
    raise SystemExit(f"manifest has no variants: {manifest_path}")

for variant in variants:
    variant_id = variant["id"]
    count = int(variant["count"])
    if count <= 0:
        raise SystemExit(f"variant {variant_id} has invalid count: {count}")
    config = pathlib.Path(variant["config"])
    search = pathlib.Path(variant["search"])
    if not config.is_absolute():
        config = dossier_root / config
    if not search.is_absolute():
        search = dossier_root / search
    if not config.is_file():
        raise SystemExit(f"missing config for {variant_id}: {config}")
    if not search.is_file():
        raise SystemExit(f"missing search for {variant_id}: {search}")
    print("\t".join([variant_id, str(config), str(search), str(count)]))
PY
)

if [[ "${#variant_ids[@]}" -eq 0 ]]; then
  echo "manifest produced no variants: $manifest_path" >&2
  exit 2
fi

cycles_completed=0
variant_seeds=()
while IFS= read -r seed; do
  variant_seeds+=("$seed")
done < <(
  python3 - "$state_file" "$manifest_path" <<'PY'
import json
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
manifest_path = pathlib.Path(sys.argv[2])
variants = json.loads(manifest_path.read_text())["variants"]
variant_ids = [variant["id"] for variant in variants]

if not state_path.exists():
    print(0)
    for _ in variant_ids:
        print(0)
    raise SystemExit(0)

state = json.loads(state_path.read_text())
print(int(state.get("cycles_completed", 0)))
next_seed = state.get("next_seed_by_variant", {})
for variant_id in variant_ids:
    print(int(next_seed.get(variant_id, 0)))
PY
)

if [[ "${#variant_seeds[@]}" -ne $(( ${#variant_ids[@]} + 1 )) ]]; then
  echo "invalid state payload in $state_file" >&2
  exit 2
fi

cycles_completed="${variant_seeds[0]}"
variant_seeds=("${variant_seeds[@]:1}")

if [[ "${#variant_seeds[@]}" -ne "${#variant_ids[@]}" ]]; then
  echo "state seed count does not match manifest in $state_file" >&2
  exit 2
fi

write_state() {
  python3 - "$state_file" "$cycles_completed" "$(IFS=,; echo "${variant_ids[*]}")" "$(IFS=,; echo "${variant_seeds[*]}")" <<'PY'
import json
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
cycles_completed = int(sys.argv[2])
variant_ids = [value for value in sys.argv[3].split(",") if value]
seed_values = [value for value in sys.argv[4].split(",") if value]
variant_seeds = [int(value) for value in seed_values]
if len(variant_ids) != len(variant_seeds):
    raise SystemExit("variant/state length mismatch")

state = {
    "cycles_completed": cycles_completed,
    "next_seed_by_variant": dict(zip(variant_ids, variant_seeds)),
}
state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
PY
}

count_query() {
  local sql="$1"
  if [[ ! -f "$db_path" ]]; then
    echo 0
    return
  fi
  sqlite3 "$db_path" "$sql"
}

write_summary() {
  local creatures="$1"
  local taxonomy="$2"
  local exports="$3"
  python3 - "$summary_file" "$manifest_path" "$workspace" "$db_path" "$target_creatures" "$cycles_completed" "$creatures" "$taxonomy" "$exports" "$(IFS=,; echo "${variant_ids[*]}")" "$(IFS=,; echo "${variant_seeds[*]}")" <<'PY'
import json
import pathlib
import sys

summary_path = pathlib.Path(sys.argv[1])
manifest_path = sys.argv[2]
workspace = sys.argv[3]
db_path = sys.argv[4]
target_creatures = int(sys.argv[5])
cycles_completed = int(sys.argv[6])
creatures = int(sys.argv[7])
taxonomy = int(sys.argv[8])
exports = int(sys.argv[9])
variant_ids = [value for value in sys.argv[10].split(",") if value]
seed_values = [value for value in sys.argv[11].split(",") if value]
variant_seeds = [int(value) for value in seed_values]

summary = {
    "manifest": manifest_path,
    "workspace": workspace,
    "db": db_path,
    "target_creatures": target_creatures,
    "cycles_completed": cycles_completed,
    "creature_count": creatures,
    "taxonomy_count": taxonomy,
    "export_count": exports,
    "next_seed_by_variant": dict(zip(variant_ids, variant_seeds)),
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
}

stop=0
trap 'stop=1; echo ""; echo "interrupted, finishing current run..."' SIGINT SIGTERM

resolve_cli() {
  if [[ -n "$prebuilt_cli" ]]; then
    if [[ ! -x "$prebuilt_cli" ]]; then
      echo "LENIA_CLI_BIN is not executable: $prebuilt_cli" >&2
      exit 2
    fi
    echo "$prebuilt_cli"
    return
  fi

  local build_cmd=(xcrun swift build --package-path "$dossier_root" -c release --product LeniaCLI)
  local bin_cmd=(xcrun swift build --package-path "$dossier_root" -c release --show-bin-path)
  if [[ -n "$swift_scratch_path" ]]; then
    mkdir -p "$swift_scratch_path"
    build_cmd+=(--scratch-path "$swift_scratch_path")
    bin_cmd+=(--scratch-path "$swift_scratch_path")
  fi
  if [[ -n "$swift_tmpdir" ]]; then
    mkdir -p "$swift_tmpdir"
  fi

  echo "building LeniaCLI..." >&2
  if [[ -n "$swift_tmpdir" ]]; then
    TMPDIR="$swift_tmpdir" "${build_cmd[@]}" >/dev/null
    cli_bin_dir="$(TMPDIR="$swift_tmpdir" "${bin_cmd[@]}")"
  else
    "${build_cmd[@]}" >/dev/null
    cli_bin_dir="$("${bin_cmd[@]}")"
  fi

  local cli_path="$cli_bin_dir/LeniaCLI"
  if [[ ! -x "$cli_path" ]]; then
    echo "missing built CLI at: $cli_path" >&2
    exit 2
  fi
  echo "$cli_path"
}

cli="$(resolve_cli)"

echo "discovery sweep manifest: $manifest_path"
echo "workspace: $workspace"
echo "db: $db_path"
echo "target creatures: $target_creatures"
echo "variants:"
for ((i = 0; i < ${#variant_ids[@]}; i++)); do
  echo "  - ${variant_ids[$i]} count=${variant_counts[$i]} config=$(basename "${variant_configs[$i]}") search=$(basename "${variant_searches[$i]}") next_seed=${variant_seeds[$i]}"
done
echo ""

creature_count="$(count_query 'SELECT COUNT(*) FROM creatures;')"
while [[ "$creature_count" -lt "$target_creatures" ]]; do
  if [[ "$stop" -eq 1 ]]; then
    break
  fi
  if [[ "$max_cycles" -gt 0 && "$cycles_completed" -ge "$max_cycles" ]]; then
    break
  fi

  for ((i = 0; i < ${#variant_ids[@]}; i++)); do
    if [[ "$stop" -eq 1 || "$creature_count" -ge "$target_creatures" ]]; then
      break
    fi

    variant_id="${variant_ids[$i]}"
    variant_config="${variant_configs[$i]}"
    variant_search="${variant_searches[$i]}"
    variant_count="${variant_counts[$i]}"
    variant_seed="${variant_seeds[$i]}"
    run_id="${variant_id}-c$(printf '%03d' "$cycles_completed")-s${variant_seed}"
    run_output="$workspace/runs/$variant_id"
    mkdir -p "$run_output"

    echo "--- $run_id ($variant_count seeds from $variant_seed) ---"
    "$cli" discover local \
      --config "$variant_config" \
      --search "$variant_search" \
      --output "$run_output" \
      --seed "$variant_seed" \
      --count "$variant_count" \
      --run-id "$run_id" \
      --compendium "$db_path" \
      --log-level "$log_level"

    variant_seeds[$i]=$((variant_seed + variant_count))
    write_state

    creature_count="$(count_query 'SELECT COUNT(*) FROM creatures;')"
    export_count="$(count_query 'SELECT COUNT(*) FROM exports;')"
    echo "indexed creatures=$creature_count exports=$export_count"
    echo ""
  done

  if [[ "$stop" -eq 1 || "$creature_count" -ge "$target_creatures" ]]; then
    break
  fi

  cycles_completed=$((cycles_completed + 1))
  write_state
done

taxonomy_count="$(count_query 'SELECT COUNT(*) FROM creatures WHERE taxonomy_species_id IS NOT NULL;')"
export_count="$(count_query 'SELECT COUNT(*) FROM exports;')"

if [[ "$skip_postprocess" -eq 0 && -f "$db_path" ]]; then
  if [[ "$creature_count" -gt 0 ]]; then
    echo "assigning taxonomy..."
    "$cli" analyze taxonomy --db "$db_path"
    echo "backfilling compendium metadata..."
    "$cli" index backfill --db "$db_path"
    echo "running sanity..."
    "$cli" index sanity --db "$db_path"
    echo "exporting ecology..."
    "$cli" analyze ecology --db "$db_path" --output "$workspace/ecology"
    taxonomy_count="$(count_query 'SELECT COUNT(*) FROM creatures WHERE taxonomy_species_id IS NOT NULL;')"
  else
    echo "skipping postprocess: no creatures indexed"
  fi
fi

write_summary "$creature_count" "$taxonomy_count" "$export_count"

if [[ "$sync_remote" -eq 1 ]]; then
  if [[ -z "${SPECTER_ARTIFACT_ROOT-}" ]]; then
    echo "SPECTER_ARTIFACT_ROOT is unset; cannot sync remote workspace" >&2
    exit 2
  fi
  remote_workspace="$SPECTER_ARTIFACT_ROOT/lenia-swarm/outputs/discovery/$(basename "$workspace")"
  mkdir -p "$remote_workspace"
  if [[ "$remote_workspace" != "$workspace" ]]; then
    rsync -a "$workspace/" "$remote_workspace/"
  fi
  "$dossier_root/ops/sync-local-compendium.sh" --db "$db_path"
  echo "synced remote workspace: $remote_workspace"
fi

echo "discovery sweep complete"
echo "  creatures: $creature_count / $target_creatures"
echo "  taxonomy assigned: $taxonomy_count"
echo "  exports: $export_count"
echo "  cycles completed: $cycles_completed"
echo "  db: $db_path"
echo "  summary: $summary_file"
