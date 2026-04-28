from __future__ import annotations

import os
from pathlib import Path

DOSSIER_NAME = "jolt-material-memory"
ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"
LOG_ENV = "SPECTER_LOG_ROOT"


def _root_from_env(env_name: str) -> Path | None:
    raw = os.environ.get(env_name)
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{env_name} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / DOSSIER_NAME


def resolve_artifact_dir(name: str, fallback: Path) -> Path:
    root = _root_from_env(ARTIFACT_ENV)
    if root is None:
        return fallback
    return root / name


def resolve_log_dir(name: str, fallback: Path) -> Path:
    root = _root_from_env(LOG_ENV)
    if root is None:
        return fallback
    return root / name
