#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

RELEASE_ROOT="${1:-artifacts/publish/release-candidate-fixture}"
INDEX="${ROOT_DIR}/tests/fixtures/release_index.jsonl"
SUITE_CONFIG="${RELEASE_ROOT}/suite_config.json"

mkdir -p "${RELEASE_ROOT}"

cat > "${SUITE_CONFIG}" <<JSON
{
  "schema_version": 1,
  "common_args": [
    "run",
    "--index", "${RELEASE_ROOT}/split/public_dev.jsonl",
    "--verification-mode", "none",
    "--samples-per-item", "1",
    "--pass-at-k", "1"
  ],
  "runs": [
    {"name": "mock-v1", "adapter": "mock", "model": "mock-v1"}
  ]
}
JSON

INDEX="${INDEX}" \
SUITE_CONFIG="${SUITE_CONFIG}" \
RELEASE_ROOT="${RELEASE_ROOT}" \
REPO_HOLDOUT_FRACTION=0.000001 \
LICENSE_POLICY=open_only \
RELEASE_VISIBILITY=public \
REQUIRE_CLEAN_BASELINE=1 \
CREATE_TAGS=0 \
./scripts/run_release_candidate.sh
