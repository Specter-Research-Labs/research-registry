#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'install-lenia-studio-app: %s\n' "$*" >&2
  exit 1
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

APP_NAME="${APP_NAME:-Lenia Studio}"
APP_PATH="${APP_PATH:-/Applications/${APP_NAME}.app}"
CONFIGURATION="${CONFIGURATION:-release}"
PRODUCT="LeniaStudio"
PACKAGE_RESOURCE_PREFIX="LeniaSwarm_"
BUILD_VERSION="$(date -u +%Y%m%d%H%M%S)"

case "$APP_PATH" in
  /*.app) ;;
  *) die "APP_PATH must be an absolute .app path: $APP_PATH" ;;
esac

install_parent="$(dirname -- "$APP_PATH")"
[[ -d "$install_parent" ]] || die "Install parent does not exist: $install_parent"
[[ -w "$install_parent" ]] || die "Install parent is not writable: $install_parent"

if pgrep -x "$PRODUCT" >/dev/null; then
  die "Quit Lenia Studio before installing: $PRODUCT is still running"
fi

cd "$PACKAGE_ROOT"

xcrun swift build --configuration "$CONFIGURATION" --product "$PRODUCT"
build_dir="$(xcrun swift build --configuration "$CONFIGURATION" --show-bin-path)"
executable_path="$build_dir/$PRODUCT"
required_bundle="$build_dir/${PACKAGE_RESOURCE_PREFIX}${PRODUCT}.bundle"

[[ -x "$executable_path" ]] || die "Built executable missing: $executable_path"
[[ -d "$required_bundle" ]] || die "Required resource bundle missing: $required_bundle"

tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/lenia-studio-app.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

app_root="$tmp_root/${APP_NAME}.app"
contents_dir="$app_root/Contents"
macos_dir="$contents_dir/MacOS"
resources_dir="$contents_dir/Resources"

mkdir -p "$macos_dir" "$resources_dir"
cp "$executable_path" "$macos_dir/$PRODUCT"
chmod +x "$macos_dir/$PRODUCT"

shopt -s nullglob
resource_bundles=("$build_dir"/${PACKAGE_RESOURCE_PREFIX}*.bundle)
[[ "${#resource_bundles[@]}" -gt 0 ]] || die "No package resource bundles found in: $build_dir"

for resource_bundle in "${resource_bundles[@]}"; do
  ditto "$resource_bundle" "$resources_dir/$(basename -- "$resource_bundle")"
done

cat > "$contents_dir/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>${PRODUCT}</string>
  <key>CFBundleIdentifier</key>
  <string>com.specterlabs.leniastudio</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>${BUILD_VERSION}</string>
  <key>LSMinimumSystemVersion</key>
  <string>15.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

rm -rf "$APP_PATH"
ditto "$app_root" "$APP_PATH"

printf 'Installed %s\n' "$APP_PATH"
