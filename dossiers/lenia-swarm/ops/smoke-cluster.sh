#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for v in $(env | cut -d= -f1 | grep "^NIX_" || true); do unset "$v"; done
unset CC CXX DEVELOPER_DIR SDKROOT TOOLCHAINS LD LD_DYLD_PATH LIBRARY_PATH
if [[ -d "/Applications/Xcode.app/Contents/Developer" ]]; then
  export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"
fi

HOST="${HOST:-127.0.0.1}"
CONTROLLER_PORT="${CONTROLLER_PORT:-}"
WORKERS="${WORKERS:-2}"
WORKER_PORT_BASE="${WORKER_PORT_BASE:-}"
BUILD_CONFIG="${BUILD_CONFIG:-Release}"
SKIP_BUILD="${SKIP_BUILD:-}"

RUN_ID="${RUN_ID:-smoke-$(date +%Y%m%d-%H%M%S)}"
BASE_CONFIG="${BASE_CONFIG:-$ROOT_DIR/configs/base/paper_base_1c_128.json}"
SEARCH_TEMPLATE="${SEARCH_TEMPLATE:-$ROOT_DIR/configs/base/paper_search_random.json}"

SMOKE_ROOT="${SMOKE_ROOT:-$(mktemp -d "$ROOT_DIR/.build/smoke.XXXXXX")}"
DERIVED_DATA_DIR="$SMOKE_ROOT/DerivedData"
LOG_DIR="$SMOKE_ROOT/logs"
OUTPUT_DIR="$SMOKE_ROOT/output"
SEARCH_CONFIG="$SMOKE_ROOT/search.smoke.json"

controller_pid=""
worker_pids=()

pick_free_port() {
  python3 - "$HOST" <<'PY'
import socket
import sys

host = sys.argv[1]
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((host, 0))
    s.listen(1)
    print(s.getsockname()[1])
PY
}

cleanup() {
  set +e
  for pid in "${worker_pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  if [[ -n "${controller_pid:-}" ]]; then
    kill "$controller_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "$SMOKE_ROOT" "$LOG_DIR" "$OUTPUT_DIR"

python3 - "$SEARCH_TEMPLATE" "$SEARCH_CONFIG" <<'PY'
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8") as f:
    cfg = json.load(f)

cfg["count"] = int(cfg.get("count", 256))
cfg["count"] = min(cfg["count"], 16)
cfg["steps"] = min(int(cfg.get("steps", 200)), 80)
cfg["warmup_steps"] = min(int(cfg.get("warmup_steps", 0)), 40)
cfg["record_interval"] = min(int(cfg.get("record_interval", 50)), 20)
cfg["top_k"] = min(int(cfg.get("top_k", 10)), 5)
cfg["batch_size"] = min(int(cfg.get("batch_size", 1)), 4)
cfg["seeds_per_job"] = 1

with open(dst, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
    f.write("\n")
PY

if [[ ! -f "$BASE_CONFIG" ]]; then
  echo "Base config not found: $BASE_CONFIG" >&2
  exit 1
fi
if [[ ! -f "$SEARCH_CONFIG" ]]; then
  echo "Search config not found: $SEARCH_CONFIG" >&2
  exit 1
fi

if [[ -z "${CONTROLLER_PORT:-}" ]]; then
  CONTROLLER_PORT="$(pick_free_port)"
fi

worker_ports=()
if [[ -n "${WORKER_PORT_BASE:-}" ]]; then
  for ((i=0; i<WORKERS; i++)); do
    worker_ports+=($((WORKER_PORT_BASE + i)))
  done
else
  for ((i=0; i<WORKERS; i++)); do
    worker_ports+=("$(pick_free_port)")
  done
fi

if [[ -z "$SKIP_BUILD" ]]; then
  xcodebuild build \
    -scheme LeniaCLI \
    -destination 'platform=OS X' \
    -configuration "$BUILD_CONFIG" \
    -derivedDataPath "$DERIVED_DATA_DIR" \
    >"$SMOKE_ROOT/build.log" 2>&1
fi

LENIA_CLI="$DERIVED_DATA_DIR/Build/Products/$BUILD_CONFIG/LeniaCLI"
if [[ ! -x "$LENIA_CLI" ]]; then
  echo "LeniaCLI not found or not executable: $LENIA_CLI" >&2
  echo "Build log: $SMOKE_ROOT/build.log" >&2
  exit 1
fi

set +e
"$LENIA_CLI" orchestrate controller \
  --host "$HOST" \
  --port "$CONTROLLER_PORT" \
  --config "$BASE_CONFIG" \
  --search "$SEARCH_CONFIG" \
  --output "$OUTPUT_DIR" \
  --seeds-per-job 1 \
  --auto-exit \
  --run-id "$RUN_ID" \
  --log-dir "$LOG_DIR" \
  --log-level info \
  >"$SMOKE_ROOT/controller.stdout.log" 2>&1 &
controller_pid="$!"
set -e

sleep 1

for ((i=0; i<WORKERS; i++)); do
  port="${worker_ports[$i]}"
  set +e
  "$LENIA_CLI" orchestrate worker \
    --host "$HOST" \
    --port "$port" \
    --controller "$HOST" \
    --controller-port "$CONTROLLER_PORT" \
    --run-id "$RUN_ID" \
    --log-dir "$LOG_DIR" \
    --log-level info \
    >"$SMOKE_ROOT/worker-$port.stdout.log" 2>&1 &
  worker_pids+=("$!")
  set -e
done

wait "$controller_pid"
controller_rc="$?"
controller_pid=""

summary_path="$OUTPUT_DIR/overall/summary.json"
if [[ "$controller_rc" -ne 0 ]]; then
  echo "Controller exited non-zero: $controller_rc" >&2
  echo "Controller stdout/stderr: $SMOKE_ROOT/controller.stdout.log" >&2
  exit "$controller_rc"
fi
if [[ ! -f "$summary_path" ]]; then
  echo "Smoke run did not produce expected summary: $summary_path" >&2
  echo "Controller stdout/stderr: $SMOKE_ROOT/controller.stdout.log" >&2
  exit 1
fi

echo "OK: controller+workers smoke run completed"
echo "Artifacts: $SMOKE_ROOT"
echo "Summary:   $summary_path"
