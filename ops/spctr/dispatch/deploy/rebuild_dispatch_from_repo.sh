#!/usr/bin/env bash
set -euo pipefail

repo_root="${SPECTER_REPO_ROOT:-/srv/specterlab/research-registry}"
spctr_root="${repo_root}/ops/spctr"
dispatch_root="${spctr_root}/dispatch"

if [[ ! -f "${spctr_root}/Cargo.toml" ]]; then
  echo "spctr manifest is missing at ${spctr_root}" >&2
  exit 1
fi

cargo build --release --manifest-path "${spctr_root}/Cargo.toml"
sudo install -m 0755 "${spctr_root}/target/release/spctr" /usr/local/bin/spctr
bash "${dispatch_root}/deploy/apply_repo_configs.sh"
sudo systemctl daemon-reload
sudo systemctl restart specter-dispatch
