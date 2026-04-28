#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ "${1:-}" == "" || "${2:-}" == "" ]]; then
  echo "usage: $0 <index.jsonl> <profile-config.json> [out-dir] [max-items]" >&2
  exit 2
fi

INDEX_PATH="$1"
PROFILE_CONFIG_PATH="$2"
OUT_DIR="${3:-artifacts/repo-replay-strict-preflight}"
MAX_ITEMS="${4:-25}"

uv run python scripts/check_repo_replay_profile_coverage.py \
  --index "${INDEX_PATH}" \
  --profile-config "${PROFILE_CONFIG_PATH}"

uv run python -m lean_sorry_repos_benchmark \
  --index "${INDEX_PATH}" \
  --adapter mock \
  --model mock-v1 \
  --verification-mode repo_replay \
  --repo-replay-profile-config "${PROFILE_CONFIG_PATH}" \
  --repo-replay-profile-strict \
  --samples-per-item 1 \
  --pass-at-k 1 \
  --max-items "${MAX_ITEMS}" \
  --out-dir "${OUT_DIR}"

echo "strict_preflight_out=${OUT_DIR}"
