#!/usr/bin/env bash
set -euo pipefail

VERSION=${BLENDER_VERSION:-5.0.1}
INSTALL_ROOT=${BLENDER_INSTALL_ROOT:-}

if [[ -z "$INSTALL_ROOT" ]]; then
  echo "BLENDER_INSTALL_ROOT must point to a writable install directory" >&2
  exit 1
fi

DMG_NAME="blender-$VERSION-macos-arm64.dmg"
DMG_URL="https://download.blender.org/release/Blender${VERSION%.*}/$DMG_NAME"
DMG_PATH="$INSTALL_ROOT/$DMG_NAME"
APP_PATH="$INSTALL_ROOT/Blender-$VERSION.app"
MOUNT_ROOT=${BLENDER_MOUNT_ROOT:-${TMPDIR:-/tmp}/blender-dmg-mount}

mkdir -p "$INSTALL_ROOT"
curl -L -A 'Mozilla/5.0' "$DMG_URL" -o "$DMG_PATH"

mkdir -p "$MOUNT_ROOT"
DEVICE=$(hdiutil attach "$DMG_PATH" -nobrowse -readonly -mountpoint "$MOUNT_ROOT" | awk '/Apple_HFS|APFS/ {print $1; exit}')
trap 'if [[ -n "${DEVICE:-}" ]]; then hdiutil detach "$DEVICE" >/dev/null 2>&1 || true; fi' EXIT

SOURCE_APP=$(find "$MOUNT_ROOT" -maxdepth 1 -name 'Blender*.app' -print -quit)
if [[ -z "$SOURCE_APP" ]]; then
  echo "Could not find Blender.app in mounted dmg" >&2
  exit 1
fi

if [[ -d "$APP_PATH" ]]; then
  echo "Blender already installed at $APP_PATH"
  exit 0
fi

ditto "$SOURCE_APP" "$APP_PATH"
echo "Installed Blender to $APP_PATH"
