from __future__ import annotations

import os
from pathlib import Path

ADDENDUM_NAME = "tinygrad-benchmarks"
ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"
RUNTIME_ENV = "SPECTER_RUNTIME_ROOT"


def _resolve_root(env_name: str, fallback: Path) -> Path:
    raw = os.environ.get(env_name)
    if raw is None:
        return fallback
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{env_name} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / ADDENDUM_NAME


def resolve_artifact_root(fallback: Path) -> Path:
    return _resolve_root(ARTIFACT_ENV, fallback)


def resolve_runtime_root(fallback: Path) -> Path:
    return _resolve_root(RUNTIME_ENV, fallback)
