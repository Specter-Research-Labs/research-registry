#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"

base_config="$dossier_root/configs/base/paper_base_1c_128.json"
search_config="$dossier_root/configs/search/search_smoke.json"

if [[ ! -f "$base_config" ]]; then
  echo "missing base config: $base_config" >&2
  exit 2
fi
if [[ ! -f "$search_config" ]]; then
  echo "missing search config: $search_config" >&2
  exit 2
fi

out_root="$dossier_root/artifacts/smoke"

stamp="$(date +%Y%m%d-%H%M%S)"
out_dir="$out_root/$stamp"
mkdir -p "$out_dir"

derived="$out_dir/DerivedData"

for v in $(env | cut -d= -f1 | grep "^NIX_" || true); do unset "$v"; done
unset CC CXX DEVELOPER_DIR SDKROOT TOOLCHAINS LD LD_DYLD_PATH LIBRARY_PATH
if [[ -d "/Applications/Xcode.app/Contents/Developer" ]]; then
  export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"
fi

if [[ -z "${MLX_METAL_PATH-}" ]]; then
  echo "warning: MLX_METAL_PATH is not set; builds/runs may fail outside Nix devshell." >&2
fi

cd "$dossier_root"

/usr/bin/xcrun xcodebuild build \
  -scheme LeniaCLI \
  -destination 'platform=OS X' \
  -configuration Release \
  -derivedDataPath "$derived" \
  -quiet

cli_bin="$derived/Build/Products/Release/LeniaCLI"
if [[ ! -x "$cli_bin" ]]; then
  echo "missing built CLI at: $cli_bin" >&2
  exit 2
fi

run_one() {
  local run_id="$1"
  "$cli_bin" discover local \
    --config "$base_config" \
    --search "$search_config" \
    --output "$out_dir" \
    --run-id "$run_id" \
    --log-level error \
    --no-log-console \
    --frames \
    --frame-stride 5
}

run_one "smoke-a"
run_one "smoke-b"

a_dir="$out_dir/smoke-a"
b_dir="$out_dir/smoke-b"

for p in "$a_dir/results.jsonl" "$b_dir/results.jsonl" "$a_dir/summary.json" "$b_dir/summary.json"; do
  if [[ ! -f "$p" ]]; then
    echo "missing expected artifact: $p" >&2
    exit 3
  fi
done

hash_file() {
  /usr/bin/shasum -a 256 "$1" | awk '{print $1}'
}

hash_tree() {
  local dir="$1"
  (cd "$dir" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 /usr/bin/shasum -a 256) | /usr/bin/shasum -a 256 | awk '{print $1}'
}

a_results_hash="$(hash_file "$a_dir/results.jsonl")"
b_results_hash="$(hash_file "$b_dir/results.jsonl")"

if [[ "$a_results_hash" != "$b_results_hash" ]]; then
  echo "determinism FAILED: results.jsonl hash mismatch" >&2
  echo "smoke-a: $a_results_hash" >&2
  echo "smoke-b: $b_results_hash" >&2
  exit 4
fi

a_frames="$a_dir/frames"
b_frames="$b_dir/frames"
if [[ ! -d "$a_frames" || ! -d "$b_frames" ]]; then
  echo "missing frames dir(s): $a_frames $b_frames" >&2
  exit 3
fi

a_frames_hash="$(hash_tree "$a_frames")"
b_frames_hash="$(hash_tree "$b_frames")"
if [[ "$a_frames_hash" != "$b_frames_hash" ]]; then
  echo "determinism FAILED: frames/ hash mismatch" >&2
  echo "smoke-a: $a_frames_hash" >&2
  echo "smoke-b: $b_frames_hash" >&2
  exit 4
fi

echo "determinism OK"
echo "artifacts: $out_dir"
