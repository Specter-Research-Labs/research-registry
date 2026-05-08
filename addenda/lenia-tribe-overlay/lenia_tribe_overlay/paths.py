from __future__ import annotations

import os
from pathlib import Path

ADDENDUM_NAME = "lenia-tribe-overlay"


def _addendum_root() -> Path:
    return Path(__file__).resolve().parent.parent


def artifact_root() -> Path:
    env = os.environ.get("SPECTER_ARTIFACT_ROOT")
    if env:
        return Path(env) / ADDENDUM_NAME
    return _addendum_root() / ".artifacts"


def log_root() -> Path:
    env = os.environ.get("SPECTER_LOG_ROOT")
    if env:
        return Path(env) / ADDENDUM_NAME
    return _addendum_root() / ".logs"


def runtime_root() -> Path:
    env = os.environ.get("SPECTER_RUNTIME_ROOT")
    if env:
        return Path(env) / ADDENDUM_NAME
    return _addendum_root() / "tmp"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
