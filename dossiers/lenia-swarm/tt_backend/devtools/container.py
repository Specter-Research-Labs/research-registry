"""Run a command in the pinned TT-Metal container with every TT card mapped in.

Usage:
    python3 tt_backend/devtools/container.py -- \
        python3 -m tt_lenia.sfpu.replay --input /repo/... --output /repo/... --cards 0,1,2,3 ...

The whole device tree is mapped because the driver numbers the nodes it sees from zero, so a
partial mapping would renumber cards; the payload picks its cards with TT_VISIBLE_DEVICES. The
dossier is mounted at /repo, the working directory is /repo/tt_backend, and the TT-Metal kernel
cache persists under the runtime root so that repeated runs skip compilation.
"""

from __future__ import annotations

import argparse
import glob
import os
import shlex
import subprocess
from pathlib import Path

IMAGE = (
    "ghcr.io/tenstorrent/tt-lang/tt-lang-dist-ubuntu-22-04"
    "@sha256:b09cc8ea618356bc2b97b0b1d629c05473b00d3ff5fe866749025cbf65064a6c"
)
HUGEPAGES = "/dev/hugepages-1G"
DOSSIER_ROOT = Path(__file__).resolve().parents[2]


def _held(path: str) -> bool:
    return subprocess.run(["fuser", path], capture_output=True).returncode == 0


def clear_stale_hugepages() -> None:
    """Remove hugepage files that no process holds, because a crashed run leaves its pages
    allocated and the next device open fails without them. Held files belong to live runs on
    other cards and stay. A runner starting at the same time may remove a file first."""
    for path in glob.glob(f"{HUGEPAGES}/*tenstorrent"):
        if not _held(path):
            Path(path).unlink(missing_ok=True)


def cache_dir() -> Path:
    root = os.environ.get("SPECTER_RUNTIME_ROOT")
    return (Path(root) if root else DOSSIER_ROOT / "tmp") / "tt-metal-cache"


def docker_command(command: list[str]) -> list[str]:
    args = ["docker", "run", "--rm", "--network", "none", "--device", "/dev/tenstorrent"]
    args += ["-v", f"{HUGEPAGES}:{HUGEPAGES}", "-v", f"{DOSSIER_ROOT}:/repo"]
    args += ["-v", f"{cache_dir()}:/root/.cache"]
    env = {
        "TT_METAL_HOME": "/opt/ttlang-toolchain/tt-metal",
        "MESH_DEVICE": "N300",
        "TT_METAL_INSPECTOR": "0",
        "TT_METAL_INSPECTOR_RPC": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    return args + ["-w", "/repo/tt_backend", IMAGE, *command]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run, after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("no command given after --")
    if not Path(HUGEPAGES).is_dir():
        raise SystemExit(f"missing {HUGEPAGES}; TT runs need the 1G hugepage mount")
    clear_stale_hugepages()
    cache_dir().mkdir(parents=True, exist_ok=True)
    full = docker_command(command)
    print("+", shlex.join(full), flush=True)
    return subprocess.run(full).returncode


if __name__ == "__main__":
    raise SystemExit(main())
