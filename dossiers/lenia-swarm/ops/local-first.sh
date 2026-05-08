#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dossier_root="$repo_root/dossiers/lenia-swarm"

artifact_parent="${SPCTR_LOCAL_ARTIFACT_ROOT-${SPECTER_ARTIFACT_ROOT-$repo_root/dossiers}}"
if [[ -z "$artifact_parent" ]]; then
  echo "local artifact root is set but empty" >&2
  exit 2
fi
artifact_root="${artifact_parent%/}/lenia-swarm/artifacts"
runs_root="$artifact_root/runs"
logs_root="$artifact_root/logs"
bundles_root="$artifact_root/bundles"
db_path="$artifact_root/compendium.sqlite"

resolve_cli() {
  if [[ -n "${LENIA_CLI_BIN-}" ]]; then
    echo "$LENIA_CLI_BIN"
    return
  fi
  if [[ -n "${SPECTER_RUNTIME_ROOT-}" ]]; then
    local runtime_cli="${SPECTER_RUNTIME_ROOT%/}/lenia-swarm/verify-dd/Build/Products/Release/LeniaCLI"
    if [[ -x "$runtime_cli" ]]; then
      echo "$runtime_cli"
      return
    fi
  fi
  if [[ -x "/tmp/verify-dd/Build/Products/Release/LeniaCLI" ]]; then
    echo "/tmp/verify-dd/Build/Products/Release/LeniaCLI"
    return
  fi
  if [[ -x "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI" ]]; then
    echo "$dossier_root/.build/arm64-apple-macosx/release/LeniaCLI"
    return
  fi
  echo "missing LeniaCLI binary. Set LENIA_CLI_BIN or build LeniaCLI first." >&2
  exit 2
}

usage() {
  cat <<'EOF'
Usage:
  local-first.sh search --config <base.json> --search <search.json> [--count N] [--tag NAME] [--render-top-k N] [--fps N] [--tar]
  local-first.sh evolve --config <base.json> --es <es.json> [--tag NAME]
  local-first.sh sweep [args passed through to ops/sweep.sh]
  local-first.sh index --run-dir <path>

Notes:
  - All outputs are local under the shared lenia-swarm artifacts root.
  - search runs media export for the top-N results, indexes into local compendium.sqlite, and optionally creates tarballs.
EOF
}

require_ffmpeg() {
  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg not found in PATH" >&2
    exit 2
  fi
}

stamp() {
  date +%Y%m%d-%H%M%S
}

make_gifs() {
  local render_root="$1"
  local rank_dir
  for rank_dir in "$render_root"/rank_*; do
    [[ -d "$rank_dir" ]] || continue
    ffmpeg -y -i "$rank_dir/video.mp4" \
      -vf "fps=15,scale=512:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5" \
      "$rank_dir/creature.gif" >/dev/null 2>&1
  done
}

cmd="${1-}"
if [[ -z "$cmd" ]]; then
  usage
  exit 2
fi
shift || true

mkdir -p "$runs_root" "$logs_root" "$bundles_root"
cli_bin="$(resolve_cli)"

case "$cmd" in
  search)
    config=""
    search=""
    count=""
    tag="search"
    render_top_k=3
    fps=20
    tar_enabled=0
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --config) config="$2"; shift 2 ;;
        --search) search="$2"; shift 2 ;;
        --count) count="$2"; shift 2 ;;
        --tag) tag="$2"; shift 2 ;;
        --render-top-k) render_top_k="$2"; shift 2 ;;
        --fps) fps="$2"; shift 2 ;;
        --tar) tar_enabled=1; shift ;;
        *) echo "unknown flag for search: $1" >&2; exit 2 ;;
      esac
    done
    if [[ -z "$config" || -z "$search" ]]; then
      echo "search requires --config and --search" >&2
      exit 2
    fi
    if [[ "$render_top_k" -gt 0 ]]; then
      require_ffmpeg
    fi
    run_id="${tag}-$(stamp)"
    local_args=(
      discover local
      --config "$config"
      --search "$search"
      --output "$runs_root"
      --run-id "$run_id"
      --log-dir "$logs_root"
      --no-log-console
    )
    if [[ -n "$count" ]]; then
      local_args+=(--count "$count")
    fi
    "$cli_bin" "${local_args[@]}"

    run_dir="$runs_root/$run_id"
    if [[ "$render_top_k" -gt 0 ]]; then
      "$cli_bin" publish media \
        --config "$run_dir/config.json" \
        --search "$run_dir/search.json" \
        --results "$run_dir/results.jsonl" \
        --output "$run_dir/media" \
        --limit "$render_top_k" \
        --video \
        --fps "$fps" \
        --log-dir "$logs_root" \
        --run-id "media-$run_id" \
        --no-log-console
      make_gifs "$run_dir/media"
    fi

    "$cli_bin" index --run-dir "$run_dir" --db "$db_path" --include-results --stats

    if [[ "$tar_enabled" -eq 1 ]]; then
      tarball="$bundles_root/$run_id.tar.gz"
      tar -C "$runs_root" -czf "$tarball" "$run_id"
      shasum -a 256 "$tarball" > "$tarball.sha256"
      echo "tarball: $tarball"
      echo "checksum: $tarball.sha256"
    fi

    echo "run_dir: $run_dir"
    echo "db: $db_path"
    ;;

  evolve)
    config=""
    es=""
    tag="evolve"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --config) config="$2"; shift 2 ;;
        --es) es="$2"; shift 2 ;;
        --tag) tag="$2"; shift 2 ;;
        *) echo "unknown flag for evolve: $1" >&2; exit 2 ;;
      esac
    done
    if [[ -z "$config" || -z "$es" ]]; then
      echo "evolve requires --config and --es" >&2
      exit 2
    fi
    out_dir="$artifact_root/evolve/${tag}-$(stamp)"
    mkdir -p "$out_dir"
    "$cli_bin" discover evolve \
      --config "$config" \
      --es "$es" \
      --output "$out_dir" \
      --log-dir "$logs_root" \
      --run-id "${tag}-$(stamp)" \
      --no-log-console
    echo "evolve_out: $out_dir"
    ;;

  sweep)
    "$dossier_root/ops/sweep.sh" --output "$artifact_root/sweeps" "$@"
    ;;

  index)
    run_dir=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --run-dir) run_dir="$2"; shift 2 ;;
        *) echo "unknown flag for index: $1" >&2; exit 2 ;;
      esac
    done
    if [[ -z "$run_dir" ]]; then
      echo "index requires --run-dir" >&2
      exit 2
    fi
    "$cli_bin" index --run-dir "$run_dir" --db "$db_path" --include-results --stats
    echo "db: $db_path"
    ;;

  *)
    usage
    exit 2
    ;;
esac
