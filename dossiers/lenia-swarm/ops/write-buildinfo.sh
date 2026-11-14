#!/usr/bin/env bash
# Writes <binary>.buildinfo.json (and <binary>.source.patch for a dirty tree) next to a built
# executable. LeniaCLI refuses to start a research run without a build info that matches its bytes.
set -euo pipefail

die() {
  printf 'write-buildinfo: %s\n' "$*" >&2
  exit 1
}

[[ $# -eq 1 ]] || die "usage: write-buildinfo.sh <built executable>"
binary="$1"
[[ -f "$binary" ]] || die "executable not found: $binary"

package_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
info_path="$binary.buildinfo.json"
patch_path="$binary.source.patch"
# Only these paths compile into the binary, so only they decide whether a build is dirty.
source_paths=(Package.swift Package.resolved Sources)

cd "$package_root"

patch_tmp="$(mktemp)"
trap 'rm -f "$patch_tmp"' EXIT

if jj root >/dev/null 2>&1; then
  source_commit="$(jj log --no-graph --ignore-working-copy -r @- -T 'commit_id' 2>/dev/null)" \
    || die "cannot resolve the jj parent commit"
  jj diff --git -r @ -- "${source_paths[@]}" >"$patch_tmp"
elif git rev-parse --git-dir >/dev/null 2>&1; then
  source_commit="$(git rev-parse HEAD)"
  git diff --binary HEAD -- "${source_paths[@]}" >"$patch_tmp"
  while IFS= read -r -d '' untracked; do
    git diff --binary --no-index /dev/null "$untracked" >>"$patch_tmp" || [[ $? -eq 1 ]]
  done < <(git ls-files -z --others --exclude-standard -- "${source_paths[@]}")
else
  die "$package_root is neither a jj nor a git checkout; build info needs a source commit"
fi
[[ -n "$source_commit" ]] || die "empty source commit"

binary_sha="$(shasum -a 256 "$binary" | awk '{print $1}')"
c_engine_sha="$(find Sources/CFlowLeniaCPU -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"
swift_version="$(swift --version 2>&1 | grep -m1 'Swift version')" || die "cannot read swift --version"

if [[ -s "$patch_tmp" ]]; then
  cp "$patch_tmp" "$patch_path"
  patch_sha="$(shasum -a 256 "$patch_path" | awk '{print $1}')"
else
  rm -f "$patch_path"
  patch_sha=""
fi

python3 - "$info_path" "$source_commit" "$binary_sha" "$swift_version" "$c_engine_sha" "$patch_sha" <<'PY'
import json
import sys

path, commit, binary_sha, swift_version, c_engine_sha, patch_sha = sys.argv[1:]
info = {
    "source_commit": commit,
    "dirty": bool(patch_sha),
    "binary_sha256": binary_sha,
    "swift_version": swift_version,
    "c_engine_sha256": c_engine_sha,
    "source_patch_sha256": patch_sha or None,
}
with open(path, "w") as handle:
    json.dump(info, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

printf 'wrote %s (commit %s, dirty %s)\n' "$info_path" "$source_commit" "$([[ -n "$patch_sha" ]] && echo yes || echo no)"
