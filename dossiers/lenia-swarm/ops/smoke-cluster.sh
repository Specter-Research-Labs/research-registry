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
  LENIA_CLI="${LENIA_CLI:-$DERIVED_DATA_DIR/Build/Products/$BUILD_CONFIG/LeniaCLI}"
else
  LENIA_CLI="${LENIA_CLI:-$ROOT_DIR/.build/$(tr '[:upper:]' '[:lower:]' <<<"$BUILD_CONFIG")/LeniaCLI}"
fi

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
echo "Summary:   $summary_path"

kill "${worker_pids[@]}" >/dev/null 2>&1 || true
wait "${worker_pids[@]}" 2>/dev/null || true
worker_pids=()

CAMPAIGN_DIR="$SMOKE_ROOT/campaign"
CAMPAIGN_CONFIG="$CAMPAIGN_DIR/campaign.json"
mkdir -p "$CAMPAIGN_DIR"
python3 - "$CAMPAIGN_DIR" "$BASE_CONFIG" "$SEARCH_CONFIG" <<'PY'
import json
import sys
from pathlib import Path

out, base, search = Path(sys.argv[1]), sys.argv[2], sys.argv[3]

def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

search_cfg = json.loads(Path(search).read_text(encoding="utf-8"))
search_cfg.update({"count": 2, "steps": 40, "warmup_steps": 0, "record_interval": 10, "top_k": 2})
write("search.json", search_cfg)
write("sweep.json", {
    "variants": [
        {"id": "a", "config": base, "search": str(out / "search.json"), "count": 2},
        {"id": "b", "config": base, "search": str(out / "search.json"), "count": 2},
    ],
    "target_creatures": 2,
    "max_cycles": 2,
    "keep_best": 2,
    "rank_by": "score",
})
write("intervention.json", {
    "mode": "search",
    "base_config": base,
    "search_config": str(out / "search.json"),
    "warmup_steps": 4,
    "observation_steps": 12,
    "record_every_steps": 4,
    "repeats": 1,
    "environments": [{"id": "plain", "overrides": {}}],
    "perturbations": [
        {"id": "chem-shift", "family": "chem_field_variant", "overrides": {"params.seed": 99.0}, "payload": {"target_shift": 1.0}},
    ],
})
write("campaign.json", {
    "name": "smoke-campaign",
    "phases": [
        {"name": "sweep", "type": "sweep", "manifest": str(out / "sweep.json")},
        {"name": "intervention", "type": "intervention-battery", "config": str(out / "intervention.json")},
    ],
    "phase_isolation": False,
})
PY

CAMPAIGN_RUN_ID="$RUN_ID-campaign"
"$LENIA_CLI" orchestrate campaign \
  --campaign "$CAMPAIGN_CONFIG" \
  -o "$CAMPAIGN_DIR/local" \
  --run-id "$CAMPAIGN_RUN_ID" \
  --log-dir "$LOG_DIR" \
  --log-level info \
  >"$SMOKE_ROOT/campaign-local.stdout.log" 2>&1

CAMPAIGN_PORT="$(pick_free_port)"
set +e
"$LENIA_CLI" orchestrate campaign \
  --campaign "$CAMPAIGN_CONFIG" \
  -o "$CAMPAIGN_DIR/distributed" \
  --distributed \
  --host "$HOST" \
  --port "$CAMPAIGN_PORT" \
  --min-workers "$WORKERS" \
  --run-id "$CAMPAIGN_RUN_ID" \
  --log-dir "$LOG_DIR" \
  --log-level info \
  >"$SMOKE_ROOT/campaign-distributed.stdout.log" 2>&1 &
controller_pid="$!"
set -e

sleep 1

for ((i=0; i<WORKERS; i++)); do
  port="$(pick_free_port)"
  set +e
  "$LENIA_CLI" orchestrate worker \
    --host "$HOST" \
    --port "$port" \
    --controller "$HOST" \
    --controller-port "$CAMPAIGN_PORT" \
    --run-id "$CAMPAIGN_RUN_ID" \
    --log-dir "$LOG_DIR" \
    --log-level info \
    >"$SMOKE_ROOT/campaign-worker-$port.stdout.log" 2>&1 &
  worker_pids+=("$!")
  set -e
done

set +e
wait "$controller_pid"
campaign_rc="$?"
set -e
controller_pid=""
if [[ "$campaign_rc" -ne 0 ]]; then
  echo "Distributed campaign exited non-zero: $campaign_rc" >&2
  echo "Campaign stdout/stderr: $SMOKE_ROOT/campaign-distributed.stdout.log" >&2
  exit "$campaign_rc"
fi

# Invariant: worker placement must not change results. Every JSON artifact must match the local
# run once output paths, per-run workerID and wall-clock phase timings are set aside. Exports also
# mint a random creature UUID and an export timestamp on every run, local or not, so exports/ and
# library/ compare with those replaced by their position in exports/index.jsonl.
python3 - "$CAMPAIGN_DIR/local" "$CAMPAIGN_DIR/distributed" "$WORKERS" <<'PY'
import json
import re
import sys
from pathlib import Path

local, distributed, workers = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
EXPORT_CLOCK_KEYS = {"exportedAt", "recordedAt", "recorded_at", "timestamp"}

def creature_tokens(root):
    tokens = {}
    for index in sorted(root.glob("*/exports/index.jsonl")):
        for line in index.read_text(encoding="utf-8").splitlines():
            uuid = json.loads(line)["creatureId"]
            token = f"<creature-{index.parent.parent.name}-{len(tokens)}>"
            tokens[uuid] = token
            tokens[uuid[:8]] = token
    return tokens

def normalize(value, root, tokens, exported):
    if isinstance(value, dict):
        return {
            key: "<clock>" if exported and key in EXPORT_CLOCK_KEYS else normalize(item, root, tokens, exported)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize(item, root, tokens, exported) for item in value]
    if isinstance(value, str):
        value = value.replace(str(root), "<OUT>")
        if exported:
            for raw, token in tokens.items():
                value = value.replace(raw, token)
        return value
    return value

def artifacts(root):
    tokens = creature_tokens(root)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".json", ".jsonl"}:
            continue
        name = str(path.relative_to(root))
        exported = "/exports/" in f"/{name}" or "/library/" in f"/{name}"
        key = normalize(name, root, tokens, exported)
        text = path.read_text(encoding="utf-8")
        values = [json.loads(line) for line in text.splitlines()] if path.suffix == ".jsonl" else json.loads(text)
        files[key] = normalize(values, root, tokens, exported)
    return files

left, right = artifacts(local), artifacts(distributed)
seen_workers = set()
for name, records in right.items():
    if not name.endswith("runs.jsonl"):
        continue
    for record in records:
        if record["status"] != "completed":
            sys.exit(f"{name}: run {record['runID']} is {record['status']}: {record.get('errorMessage')}")
        seen_workers.add(record.pop("workerID"))
for summary in (left["campaign-summary.json"], right["campaign-summary.json"]):
    summary.pop("totalElapsedSeconds")
    for phase in summary["phases"]:
        phase.pop("elapsedSeconds")

problems = sorted(set(left) ^ set(right))
problems += [name for name in sorted(set(left) & set(right)) if left[name] != right[name]]
if right["campaign-summary.json"]["failedPhases"] != 0:
    problems.append("distributed campaign reported failed phases")
if len(seen_workers) != workers:
    problems.append(f"expected jobs on {workers} workers, saw {sorted(seen_workers)}")
if problems:
    sys.exit("Distributed campaign differs from local run: " + ", ".join(problems))
print(f"compared {len(left)} JSON artifacts; workers used: {sorted(seen_workers)}")
PY

echo "OK: distributed campaign matches local run"
echo "Artifacts: $SMOKE_ROOT"
