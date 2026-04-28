#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/.." && pwd)"
parent_root="$(CDPATH= cd -- "${repo_root}/.." && pwd)"

init_repo() {
  local dir="$1"
  local title="$2"
  local body="$3"
  mkdir -p "${dir}"
  if [[ ! -d "${dir}/.git" ]]; then
    git init -b main "${dir}" >/dev/null
  fi
  if [[ ! -f "${dir}/README.md" ]]; then
    cat >"${dir}/README.md" <<EOF
# ${title}

${body}
EOF
  fi
  if [[ ! -f "${dir}/.gitignore" ]]; then
    printf '.DS_Store\n' >"${dir}/.gitignore"
  fi
}

init_repo \
  "${parent_root}/synthetic-bureau" \
  "synthetic-bureau" \
  "Private Specter Labs repository for synthetic reports."
init_repo \
  "${parent_root}/records-bureau" \
  "records-bureau" \
  "Private Specter Labs repository for the records corpus that is published to \`https://releases.specterlab.org/records/\`."

printf 'private sibling repos ready:\n'
printf '  %s\n' "${parent_root}/synthetic-bureau"
printf '  %s\n' "${parent_root}/records-bureau"
