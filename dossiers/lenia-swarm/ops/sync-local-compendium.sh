#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"
local_outputs="$dossier_root/outputs"
local_db="$local_outputs/compendium.sqlite"
local_bundles="$local_outputs/bundles"

with_bundles=0
explicit_db=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --db" >&2
        exit 2
      fi
      explicit_db="$2"
      shift 2
      ;;
    --with-bundles)
      with_bundles=1
      shift
      ;;
    *)
      echo "unknown flag: $1" >&2
      echo "usage: sync-local-compendium.sh [--db PATH] [--with-bundles]" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$explicit_db" ]]; then
  local_db="$(python3 -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$explicit_db")"
fi

if [[ ! -f "$local_db" ]]; then
  echo "missing local compendium db: $local_db" >&2
  exit 2
fi

if [[ -z "${SPECTER_ARTIFACT_ROOT-}" ]]; then
  echo "SPECTER_ARTIFACT_ROOT is unset; cannot sync to remote volume" >&2
  exit 2
fi
if [[ -z "$SPECTER_ARTIFACT_ROOT" ]]; then
  echo "SPECTER_ARTIFACT_ROOT is set but empty" >&2
  exit 2
fi

remote_root="$SPECTER_ARTIFACT_ROOT/lenia-swarm"
remote_outputs="$remote_root/outputs"
remote_db="$remote_outputs/compendium.sqlite"
remote_bundles="$remote_root/run-bundles"

mkdir -p "$remote_outputs"

# Write via temp file so readers never see a partially written SQLite file.
tmp_db="$remote_db.tmp"
cp -f "$local_db" "$tmp_db"
mv -f "$tmp_db" "$remote_db"
echo "synced compendium: $remote_db"

if [[ "$with_bundles" -eq 1 ]]; then
  if [[ ! -d "$local_bundles" ]]; then
    echo "missing local bundles dir: $local_bundles" >&2
    exit 2
  fi
  mkdir -p "$remote_bundles"
  rsync -a --delete "$local_bundles/" "$remote_bundles/"
  echo "synced bundles: $remote_bundles"
fi
