#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

OUT_DIR="${1:-artifacts/smoke/mock-run}"
mkdir -p "${OUT_DIR}"

uv run python -m lean_sorry_repos_benchmark \
  run \
  --index tests/fixtures/smoke_index.jsonl \
  --adapter mock \
  --model mock-v1 \
  --max-items 1 \
  --samples-per-item 2 \
  --pass-at-k 1 2 \
  --verification-mode none \
  --out-dir "${OUT_DIR}"

uv run python - "${OUT_DIR}/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
verify = summary["verification"]["metrics"]
assert "verification_success_rate_total_ci" in verify
assert "verification_pass_at_k_success_rate_ci" in verify
assert summary["verification"]["statistical"]["method"] == "bootstrap_percentile"
PY
