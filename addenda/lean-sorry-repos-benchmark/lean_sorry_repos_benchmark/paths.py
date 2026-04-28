from __future__ import annotations

import os
from pathlib import Path

ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"
RUNTIME_ENV = "SPECTER_RUNTIME_ROOT"
ADDENDUM_NAME = "lean-sorry-repos-benchmark"


def resolve_artifact_root(fallback: Path) -> Path:
    raw = os.environ.get(ARTIFACT_ENV)
    if raw is None:
        return fallback
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{ARTIFACT_ENV} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / ADDENDUM_NAME


def resolve_runtime_dir(name: str, fallback: Path) -> Path:
    raw = os.environ.get(RUNTIME_ENV)
    if raw is None:
        return fallback
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{RUNTIME_ENV} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / ADDENDUM_NAME / name
