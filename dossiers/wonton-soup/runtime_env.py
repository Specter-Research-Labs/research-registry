from __future__ import annotations

import os
import sys
from pathlib import Path

EXPECTED_PYTHON = (3, 12)


def expected_python_version() -> str:
    major, minor = EXPECTED_PYTHON
    return f"{major}.{minor}"


def flake_recovery_instructions(dossier_root: Path, command_name: str) -> str:
    return (
        f"cd {dossier_root}\n"
        'uv sync --python "$(which python)"\n'
        f"uv run python {command_name} ..."
    )


def assert_wonton_python_runtime(*, dossier_root: Path, command_name: str) -> None:
    current = sys.version_info[:2]
    if current == EXPECTED_PYTHON:
        return
    executable = Path(sys.executable).resolve()
    uv_python = os.environ.get("UV_PYTHON")
    uv_note = f"\nUV_PYTHON={uv_python}" if uv_python else ""
    raise SystemExit(
        f"{command_name} requires Python {expected_python_version()} from the wonton-soup flake.\n"
        f"Current interpreter: {executable} ({sys.version.split()[0]}){uv_note}\n"
        "Re-enter the dossier shell and rebuild the environment with the flake interpreter:\n"
        f"{flake_recovery_instructions(dossier_root, command_name)}"
    )
