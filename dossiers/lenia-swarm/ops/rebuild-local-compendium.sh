#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"
artifact_root="$dossier_root/artifacts"
runs_root="$artifact_root/runs"
db_path="$artifact_root/compendium.sqlite"

resolve_cli() {
  if [[ -n "${LENIA_CLI_BIN-}" ]]; then
    echo "$LENIA_CLI_BIN"
    return
  fi
  if [[ -n "${SPECTER_RUNTIME_ROOT-}" ]]; then
    local runtime_cli="${SPECTER_RUNTIME_ROOT%/}/lenia-swarm/verify-dd/Build/Products/Release/LeniaCLI"
    if [[ -x "$runtime_cli" ]]; then
      echo "$runtime_cli"
      return
    fi
  fi
  if [[ -x "/tmp/verify-dd/Build/Products/Release/LeniaCLI" ]]; then
    echo "/tmp/verify-dd/Build/Products/Release/LeniaCLI"
    return
  fi
  if [[ -x "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI" ]]; then
    echo "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI"
    return
  fi
  echo "missing LeniaCLI binary. Set LENIA_CLI_BIN or build LeniaCLI first." >&2
  exit 2
}

if [[ ! -d "$runs_root" ]]; then
  echo "missing runs root: $runs_root" >&2
  exit 2
fi

mapfile -t run_dirs < <(find "$runs_root" -mindepth 1 -maxdepth 1 -type d | sort)
if [[ "${#run_dirs[@]}" -eq 0 ]]; then
  echo "no run directories found under: $runs_root" >&2
  exit 2
fi

rm -f "$db_path"
cli_bin="$(resolve_cli)"

for run_dir in "${run_dirs[@]}"; do
  "$cli_bin" index --run-dir "$run_dir" --db "$db_path" --include-results
done

"$cli_bin" compendium sanity --db "$db_path"
echo "rebuilt compendium: $db_path"
