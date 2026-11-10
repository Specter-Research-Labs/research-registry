#!/usr/bin/env bash
set -euo pipefail

exec uv run --project "$(dirname "$0")/.." fly-competency-atlas backend start "$@"
