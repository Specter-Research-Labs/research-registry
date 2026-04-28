from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def addendum_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return Path(stripped)


def default_runtime_root() -> Path:
    runtime_root = _env_path("SPECTER_RUNTIME_ROOT")
    if runtime_root is not None:
        return runtime_root / "equational-theories-distillation"
    return repository_root() / "tmp" / "equational-theories-distillation"


@dataclass(frozen=True)
class RuntimeLayout:
    root: Path
    sources_dir: Path
    analysis_dir: Path


def runtime_layout(root: Path | None = None) -> RuntimeLayout:
    resolved_root = default_runtime_root() if root is None else root
    return RuntimeLayout(
        root=resolved_root,
        sources_dir=resolved_root / "sources",
        analysis_dir=resolved_root / "analysis",
    )
