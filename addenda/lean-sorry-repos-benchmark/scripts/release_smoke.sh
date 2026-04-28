#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

uv run ruff check .
uv run ty check
uv run python -m pytest -q tests/test_cli.py tests/test_replay.py tests/test_suite_runner.py
