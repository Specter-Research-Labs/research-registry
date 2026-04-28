#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT_DIR/build}"
APP_BUNDLE="$BUILD_DIR/JoltRecordingViewer.app"

"$ROOT_DIR/scripts/build.sh" "$BUILD_DIR" JoltRecordingViewer

echo "Built: $APP_BUNDLE"
