#!/usr/bin/env bash
set -euo pipefail

env_file="${SPECTER_BACKUP_ENV:-/etc/specter/backup.env}"
if [[ -f "${env_file}" ]]; then
  # shellcheck disable=SC1090
  source "${env_file}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

backup_root="${BACKUP_ROOT:-/srv/backups/postgres}"
mkdir -p "${backup_root}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="${backup_root}/dispatch-${stamp}.sql.gz"

pg_dump "${DATABASE_URL}" | gzip -9 > "${dump_path}"
echo "wrote ${dump_path}"
