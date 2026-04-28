#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MLX_SRC="$ROOT_DIR/.build/checkouts/mlx-swift/Source/Cmlx/mlx"
BUILD_DIR="$ROOT_DIR/.build/mlx-metallib"

while IFS= read -r var; do
  unset "$var"
done < <(env | awk -F= '/^NIX_/ {print $1}')
unset CC CXX SDKROOT TOOLCHAINS LD LD_DYLD_PATH LIBRARY_PATH
if [[ -d /Applications/Xcode.app/Contents/Developer ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

cmake -S "$MLX_SRC" -B "$BUILD_DIR" \
  -DMLX_BUILD_METAL=ON \
  -DMLX_BUILD_CUDA=OFF \
  -DMLX_BUILD_EXAMPLES=OFF \
  -DMLX_METAL_JIT=OFF

cmake --build "$BUILD_DIR" --target mlx-metallib

METALLIB="$(find "$BUILD_DIR" -name "mlx.metallib" -print -quit)"
if [[ -z "$METALLIB" ]]; then
  echo "mlx.metallib not found under $BUILD_DIR" >&2
  exit 1
fi

while IFS= read -r bundle; do
  cp "$METALLIB" "$bundle/Contents/MacOS/mlx.metallib"
done < <(find "$ROOT_DIR/.build" -maxdepth 10 -name "*.xctest")

for bin in "$ROOT_DIR"/.build/*/debug/LeniaCLI "$ROOT_DIR"/.build/*/debug/LeniaStudio; do
  if [[ -f "$bin" ]]; then
    cp "$METALLIB" "$(dirname "$bin")/mlx.metallib"
  fi
done

printf 'mlx.metallib copied for SwiftPM tests and debug binaries.\n'
