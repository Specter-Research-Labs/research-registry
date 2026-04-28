#!/usr/bin/env bash
set -euo pipefail

env_file="${SPECTER_BACKUP_ENV:-/etc/specter/backup.env}"
if [[ -f "${env_file}" ]]; then
  # shellcheck disable=SC1090
  source "${env_file}"
fi

if [[ -z "${STORAGE_BOX_TARGET:-}" ]]; then
  echo "STORAGE_BOX_TARGET is required" >&2
  exit 1
fi

if [[ -z "${STORAGE_BOX_SSH_KEY_PATH:-}" ]]; then
  echo "STORAGE_BOX_SSH_KEY_PATH is required" >&2
  exit 1
fi

ssh_port="${STORAGE_BOX_SSH_PORT:-23}"

rsync -az --delete \
  -e "ssh -p ${ssh_port} -i ${STORAGE_BOX_SSH_KEY_PATH} -o IdentitiesOnly=yes" \
  /srv/backups/ "${STORAGE_BOX_TARGET}"

rsync -az --delete \
  -e "ssh -p ${ssh_port} -i ${STORAGE_BOX_SSH_KEY_PATH} -o IdentitiesOnly=yes" \
  /srv/specterlab/data/ "${STORAGE_BOX_TARGET}data/"
