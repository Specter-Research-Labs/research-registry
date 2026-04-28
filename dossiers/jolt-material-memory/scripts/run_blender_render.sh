#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <bundle-dir> <out-path> [blender args...]" >&2
  exit 1
fi

if [[ -z "${BLENDER_APP:-}" ]]; then
  echo "BLENDER_APP must point to Blender.app" >&2
  exit 1
fi

if [[ -z "${BLENDER_RUNTIME_ROOT:-}" ]]; then
  echo "BLENDER_RUNTIME_ROOT must point to a writable runtime/cache directory" >&2
  exit 1
fi

BUNDLE_DIR=$1
OUT_PATH=$2
shift 2
BLENDER_ARGS=("$@")

BLENDER_BIN="$BLENDER_APP/Contents/MacOS/Blender"
if [[ ! -x "$BLENDER_BIN" ]]; then
  echo "Blender binary not found at $BLENDER_BIN" >&2
  exit 1
fi

mkdir -p \
  "$BLENDER_RUNTIME_ROOT/tmp" \
  "$BLENDER_RUNTIME_ROOT/config" \
  "$BLENDER_RUNTIME_ROOT/datafiles" \
  "$BLENDER_RUNTIME_ROOT/scripts" \
  "$BLENDER_RUNTIME_ROOT/cache"

export TMPDIR="$BLENDER_RUNTIME_ROOT/tmp"
export BLENDER_USER_CONFIG="$BLENDER_RUNTIME_ROOT/config"
export BLENDER_USER_DATAFILES="$BLENDER_RUNTIME_ROOT/datafiles"
export BLENDER_USER_SCRIPTS="$BLENDER_RUNTIME_ROOT/scripts"
export XDG_CACHE_HOME="$BLENDER_RUNTIME_ROOT/cache"

render_with_blender() {
  local blender_out_path=$1

  "$BLENDER_BIN" \
    --background \
    --factory-startup \
    --python "$ROOT_DIR/scripts/blender_render_bundle.py" \
    -- \
    --bundle-dir "$BUNDLE_DIR" \
    --out "$blender_out_path" \
    "${BLENDER_ARGS[@]}"
}

mode=still
fps=24
for ((i = 0; i < ${#BLENDER_ARGS[@]}; ++i)); do
  if [[ "${BLENDER_ARGS[$i]}" == "--mode" && $((i + 1)) -lt ${#BLENDER_ARGS[@]} ]]; then
    mode="${BLENDER_ARGS[$((i + 1))]}"
  fi
  if [[ "${BLENDER_ARGS[$i]}" == "--fps" && $((i + 1)) -lt ${#BLENDER_ARGS[@]} ]]; then
    fps="${BLENDER_ARGS[$((i + 1))]}"
  fi
done

if [[ "$OUT_PATH" == *.mp4 ]]; then
  if [[ "$mode" != "animation" ]]; then
    echo "MP4 output requires --mode animation" >&2
    exit 1
  fi
  frame_dir=$(mktemp -d "$BLENDER_RUNTIME_ROOT/tmp/blender-frames.XXXXXX")
  trap 'rm -rf "$frame_dir"' EXIT
  mkdir -p "$(dirname "$OUT_PATH")"
  render_with_blender "$frame_dir/frame_"
  ffmpeg \
    -y \
    -framerate "$fps" \
    -i "$frame_dir/frame_%04d.png" \
    -c:v libx264 \
    -pix_fmt yuv420p \
    "$OUT_PATH"
  exit 0
fi

mkdir -p "$(dirname "$OUT_PATH")"
render_with_blender "$OUT_PATH"
