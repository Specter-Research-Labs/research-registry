#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

: "${INDEX:?INDEX is required}"
: "${SUITE_CONFIG:?SUITE_CONFIG is required}"
: "${RELEASE_ROOT:?RELEASE_ROOT is required}"

SPLIT_OUT="${SPLIT_OUT:-${RELEASE_ROOT}/split}"
SUITE_OUT="${SUITE_OUT:-${RELEASE_ROOT}/suite}"
BUNDLE_OUT="${BUNDLE_OUT:-${RELEASE_ROOT}/baseline-bundle}"

SEED="${SEED:-7}"
REPO_HOLDOUT_FRACTION="${REPO_HOLDOUT_FRACTION:-0.2}"
NEAR_DUP_JACCARD_THRESHOLD="${NEAR_DUP_JACCARD_THRESHOLD:-0.9}"
CHAR_NGRAM_JACCARD_THRESHOLD="${CHAR_NGRAM_JACCARD_THRESHOLD:-0.85}"
MAX_LEAK_FRACTION="${MAX_LEAK_FRACTION:-0.0}"
LICENSE_POLICY="${LICENSE_POLICY:-open_only}"
RELEASE_VISIBILITY="${RELEASE_VISIBILITY:-public}"
MAX_PARALLEL_RUNS="${MAX_PARALLEL_RUNS:-1}"
REQUIRE_CLEAN_BASELINE="${REQUIRE_CLEAN_BASELINE:-1}"

CREATE_TAGS="${CREATE_TAGS:-0}"
DATA_TAG="${DATA_TAG:-}"
BASELINE_TAG="${BASELINE_TAG:-}"

mkdir -p "${RELEASE_ROOT}" "${SPLIT_OUT}" "${SUITE_OUT}" "${BUNDLE_OUT}"

uv run python -m lean_sorry_repos_benchmark split-artifacts \
  --index "${INDEX}" \
  --out-dir "${SPLIT_OUT}" \
  --seed "${SEED}" \
  --repo-holdout-fraction "${REPO_HOLDOUT_FRACTION}" \
  --near-dup-jaccard-threshold "${NEAR_DUP_JACCARD_THRESHOLD}" \
  --char-ngram-jaccard-threshold "${CHAR_NGRAM_JACCARD_THRESHOLD}" \
  --max-leak-fraction "${MAX_LEAK_FRACTION}" \
  --license-policy "${LICENSE_POLICY}" \
  --release-visibility "${RELEASE_VISIBILITY}"

uv run python - "${SPLIT_OUT}/split_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
counts = manifest.get("counts")
if not isinstance(counts, dict):
    raise SystemExit("split_manifest.json missing counts object")
public_dev_rows = counts.get("public_dev_rows")
if not isinstance(public_dev_rows, int):
    raise SystemExit("split_manifest.json missing integer counts.public_dev_rows")
if public_dev_rows <= 0:
    raise SystemExit(
        "split produced zero public_dev rows; adjust license_policy, input index, or "
        "repo_holdout_fraction"
    )
PY

uv run python -m lean_sorry_repos_benchmark.suite_runner \
  --config "${SUITE_CONFIG}" \
  --out-dir "${SUITE_OUT}" \
  --max-parallel-runs "${MAX_PARALLEL_RUNS}"

uv run python - "${SUITE_OUT}/suite_results.json" "${REQUIRE_CLEAN_BASELINE}" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
require_clean = sys.argv[2] == "1"

payload = json.loads(summary_path.read_text(encoding="utf-8"))
runs = payload.get("runs")
if not isinstance(runs, list):
    raise SystemExit("suite_results.json missing runs array")
failed = [row for row in runs if row.get("status") != "success"]
if failed:
    names = ", ".join(str(row.get("name", "unknown")) for row in failed[:5])
    more = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
    raise SystemExit(f"suite run failures present: {names}{more}")
if require_clean and int(payload.get("model_error_run_count", 0)) > 0:
    raise SystemExit("model_error_run_count > 0 blocks clean baseline claim")
PY

REQUIRED_FILES=(
  "${SPLIT_OUT}/public_dev.jsonl"
  "${SPLIT_OUT}/heldout_test_commitments.json"
  "${SPLIT_OUT}/split_manifest.json"
  "${SPLIT_OUT}/contamination_report.json"
  "${SPLIT_OUT}/artifact_checksums.json"
  "${SUITE_OUT}/suite_results.json"
  "${SUITE_OUT}/suite_results.jsonl"
  "${SUITE_OUT}/suite_summary.md"
  "${SUITE_CONFIG}"
)

for file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${file}" ]]; then
    echo "missing required file: ${file}" >&2
    exit 1
  fi
done

cp "${SPLIT_OUT}/public_dev.jsonl" "${BUNDLE_OUT}/"
if [[ -f "${SPLIT_OUT}/heldout_test.jsonl" ]]; then
  cp "${SPLIT_OUT}/heldout_test.jsonl" "${BUNDLE_OUT}/"
fi
cp "${SPLIT_OUT}/heldout_test_commitments.json" "${BUNDLE_OUT}/"
cp "${SPLIT_OUT}/split_manifest.json" "${BUNDLE_OUT}/"
cp "${SPLIT_OUT}/contamination_report.json" "${BUNDLE_OUT}/"
cp "${SPLIT_OUT}/artifact_checksums.json" "${BUNDLE_OUT}/"
cp "${SUITE_OUT}/suite_results.json" "${BUNDLE_OUT}/"
cp "${SUITE_OUT}/suite_results.jsonl" "${BUNDLE_OUT}/"
cp "${SUITE_OUT}/suite_summary.md" "${BUNDLE_OUT}/"
cp "${SUITE_CONFIG}" "${BUNDLE_OUT}/suite_config.json"

(
  cd "${BUNDLE_OUT}"
  FILES=(
    public_dev.jsonl
    heldout_test_commitments.json
    split_manifest.json
    contamination_report.json
    artifact_checksums.json
    suite_results.json
    suite_results.jsonl
    suite_summary.md
    suite_config.json
  )
  if [[ -f heldout_test.jsonl ]]; then
    FILES+=(heldout_test.jsonl)
  fi
  shasum -a 256 "${FILES[@]}" > SHA256SUMS
  shasum -a 256 -c SHA256SUMS
)

if [[ "${CREATE_TAGS}" == "1" ]]; then
  if [[ -z "${DATA_TAG}" || -z "${BASELINE_TAG}" ]]; then
    echo "DATA_TAG and BASELINE_TAG are required when CREATE_TAGS=1" >&2
    exit 1
  fi
  git tag -a "${DATA_TAG}" -m "lean sorry split release: ${DATA_TAG}"
  git tag -a "${BASELINE_TAG}" -m "lean sorry baseline release: ${BASELINE_TAG}"
fi

echo "split_out=${SPLIT_OUT}"
echo "suite_out=${SUITE_OUT}"
echo "bundle_out=${BUNDLE_OUT}"
