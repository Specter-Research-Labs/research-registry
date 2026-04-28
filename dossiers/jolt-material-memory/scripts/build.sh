#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT_DIR/build}"
TARGET="${2:-jolt_memory_lab}"

cmake -S "$ROOT_DIR/engine" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" --config Release -j --target "$TARGET"

case "$TARGET" in
  jolt_memory_lab)
    echo "Built: $BUILD_DIR/jolt_memory_lab"
    ;;
  JoltRecordingViewer)
    echo "Built: $BUILD_DIR/JoltRecordingViewer.app"
    ;;
  *)
    echo "Built target: $TARGET in $BUILD_DIR"
    ;;
esac
