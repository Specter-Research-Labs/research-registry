#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

IMAGE_TAG="${1:-lean-sorry-repos-benchmark-replay:local}"
OUT_DIR="${2:-artifacts/replay-runtime}"

mkdir -p "${OUT_DIR}"

docker build -f Dockerfile.replay -t "${IMAGE_TAG}" .

MANIFEST_PATH="${OUT_DIR}/runtime_manifest.json"
IMAGE_ID="$(docker image inspect "${IMAGE_TAG}" --format '{{.Id}}')"

docker run --rm -i "${IMAGE_TAG}" python - <<'PY' > "${MANIFEST_PATH}.tmp"
import json
import subprocess
from datetime import datetime, timezone


def _cmd(argv: list[str]) -> str:
    return subprocess.check_output(argv, text=True).strip()


payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "versions": {
        "python": _cmd(["python", "--version"]),
        "uv": _cmd(["uv", "--version"]),
        "git": _cmd(["git", "--version"]),
        "lean": _cmd(["lean", "--version"]),
        "lake": _cmd(["lake", "--version"]),
        "elan": _cmd(["elan", "--version"]),
    },
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY

python - "${MANIFEST_PATH}.tmp" "${MANIFEST_PATH}" "${IMAGE_TAG}" "${IMAGE_ID}" <<'PY'
import json
import sys
from pathlib import Path

tmp_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
image_tag = sys.argv[3]
image_id = sys.argv[4]

payload = json.loads(tmp_path.read_text(encoding="utf-8"))
payload["image"] = {"tag": image_tag, "id": image_id}
out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp_path.unlink(missing_ok=True)
PY

echo "replay_runtime_image=${IMAGE_TAG}"
echo "runtime_manifest=${MANIFEST_PATH}"
