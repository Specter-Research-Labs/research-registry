#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIEWER_BIN="$ROOT_DIR/build/JoltRecordingViewer.app/Contents/MacOS/JoltRecordingViewer"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <recording.jor> <out.mp4> [viewer args...]" >&2
  exit 2
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required but was not found in PATH." >&2
  exit 2
fi

RECORDING="$1"
OUT_MP4="$2"
shift 2

FPS=60
VIEWER_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fps)
      if [[ $# -lt 2 ]]; then
        echo "--fps requires a value." >&2
        exit 2
      fi
      FPS="$2"
      VIEWER_ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      VIEWER_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -x "$VIEWER_BIN" ]]; then
  "$ROOT_DIR/scripts/build_jolt_viewer.sh"
fi

TMP_ROOT="${TMPDIR:-/tmp}"
FRAMES_DIR="$(mktemp -d "$TMP_ROOT/jolt-recording-frames.XXXXXX")"
cleanup() {
  rm -rf "$FRAMES_DIR"
}
trap cleanup EXIT

mkdir -p "$(dirname "$OUT_MP4")"

"$VIEWER_BIN" "$RECORDING" --frames-out "$FRAMES_DIR" --autoplay --stop-after-last-frame "${VIEWER_ARGS[@]}"

ffmpeg \
  -y \
  -framerate "$FPS" \
  -i "$FRAMES_DIR/frame_%06d.png" \
  -pix_fmt yuv420p \
  "$OUT_MP4"

echo "Wrote: $OUT_MP4"
