#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIEWER_APP="$ROOT_DIR/build/JoltRecordingViewer.app"
VIEWER_BIN="$VIEWER_APP/Contents/MacOS/JoltRecordingViewer"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <recording.jor> [viewer args...]" >&2
  exit 2
fi

if [[ ! -x "$VIEWER_BIN" ]]; then
  echo "Viewer binary not found at $VIEWER_BIN" >&2
  echo "Run ./scripts/build_jolt_viewer.sh first." >&2
  exit 2
fi

python - "$VIEWER_BIN" "$@" <<'PY'
import os
import pathlib
import sys

viewer = pathlib.Path(sys.argv[1])
recording_arg = pathlib.Path(sys.argv[2])
extra_args = sys.argv[3:]
recording = recording_arg if recording_arg.is_absolute() else (pathlib.Path.cwd() / recording_arg)
recording = recording.resolve()

if not recording.exists():
    print(f"Recording not found: {recording}", file=sys.stderr)
    sys.exit(2)

os.execv(str(viewer), [str(viewer), str(recording), *extra_args])
PY
