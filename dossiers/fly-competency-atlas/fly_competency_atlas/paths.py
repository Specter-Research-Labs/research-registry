from __future__ import annotations

import os
from pathlib import Path

DOSSIER_SLUG = "fly-competency-atlas"


def dossier_root() -> Path:
    return Path(__file__).resolve().parent.parent


def artifact_root() -> Path:
    configured = _configured_root("SPECTER_ARTIFACT_ROOT")
    if configured is None:
        return dossier_root() / "data"
    return configured / DOSSIER_SLUG


def _configured_root(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    if not raw.strip():
        raise RuntimeError(f"{name} is set but empty")
    return Path(raw).expanduser().resolve()
