from __future__ import annotations

import os
from pathlib import Path

DOSSIER_NAME = "zang-levin-playground"
ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"


def _artifact_root() -> Path | None:
    raw = os.environ.get(ARTIFACT_ENV)
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{ARTIFACT_ENV} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / DOSSIER_NAME


def resolve_artifact_dir(name: str, fallback: Path) -> Path:
    root = _artifact_root()
    if root is None:
        return fallback
    return root / name
