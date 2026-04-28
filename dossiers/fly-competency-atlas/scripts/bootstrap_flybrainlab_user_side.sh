#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 /path/to/python3.9 /path/to/env-dir" >&2
  exit 1
fi

PYTHON_BIN="$1"
ENV_DIR="$2"

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info[:2] != (3, 9):
    raise SystemExit(
        "FlyBrainLab upstream documents Python 3.9 for the user-side stack. "
        f"Got {sys.version.split()[0]}."
    )
PY

"$PYTHON_BIN" -m venv "$ENV_DIR"
"$ENV_DIR/bin/pip" install --upgrade pip
"$ENV_DIR/bin/pip" install \
  "git+https://github.com/mkturkcan/autobahn-sync.git" \
  "git+https://github.com/FlyBrainLab/Neuroballad.git" \
  "nxt_gem==2.0.1" \
  "git+https://github.com/mkturkcan/nxcontrol" \
  "flybrainlab[full]==1.1.11" \
  "neuromynerva==0.2.17"

"$ENV_DIR/bin/pip" install "setuptools<81"

echo "FlyBrainLab user-side env created at $ENV_DIR"
echo "Activate it before import so flybrainlab can find the bundled jupyter executable:"
echo "  source $ENV_DIR/bin/activate"
