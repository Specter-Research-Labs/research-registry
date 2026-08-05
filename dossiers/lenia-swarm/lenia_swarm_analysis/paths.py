from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

DOSSIER_SLUG = "lenia-swarm"
_ARTIFACT_ROOT_ENVS = ("SPCTR_LOCAL_ARTIFACT_ROOT", "SPECTER_ARTIFACT_ROOT")
_LOG_ROOT_ENVS = ("SPCTR_LOCAL_LOG_ROOT", "SPECTER_LOG_ROOT")
_PERSISTENT_PREFIXES = {"artifacts", "outputs", "logs"}


def dossier_root() -> Path:
    return Path(__file__).resolve().parent.parent


def persistent_dossier_root() -> Path:
    current = dossier_root()
    repo_root = current.parent.parent
    workspace_parent = repo_root.parent
    if workspace_parent.name == "research-registry-workspaces":
        candidate = workspace_parent.parent / "research-registry" / "dossiers" / DOSSIER_SLUG
        if candidate.is_dir():
            return candidate
    return current


def artifact_root() -> Path:
    configured = _first_configured_root(_ARTIFACT_ROOT_ENVS)
    if configured is not None:
        return configured / DOSSIER_SLUG
    return persistent_dossier_root()


def log_root() -> Path:
    configured = _first_configured_root(_LOG_ROOT_ENVS)
    if configured is not None:
        return configured / DOSSIER_SLUG
    return persistent_dossier_root() / "outputs"


def runtime_root() -> Path:
    configured = _configured_root("SPECTER_RUNTIME_ROOT")
    if configured is not None:
        return configured / DOSSIER_SLUG
    return dossier_root() / "tmp"


def resolve_input_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    parts = path.parts
    if not parts:
        return path
    prefix = parts[0]
    if prefix not in _PERSISTENT_PREFIXES and prefix != "tmp":
        return path

    configured_candidates: list[Path] = []
    for candidate in _configured_routed_paths(path):
        configured_candidates.append(candidate)
        if candidate.exists():
            return candidate

    fallback = (
        _persistent_input_path(path) if prefix in _PERSISTENT_PREFIXES else dossier_root() / path
    ).resolve()
    if fallback.exists():
        return fallback
    return configured_candidates[0] if configured_candidates else fallback


def route_output_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    parts = path.parts
    if not parts:
        return path
    prefix, suffix = parts[0], parts[1:]
    if prefix in {"artifacts", "outputs"}:
        return artifact_root().joinpath(prefix, *suffix)
    if prefix == "logs":
        return log_root().joinpath("logs", *suffix)
    if prefix == "tmp":
        return runtime_root().joinpath(*suffix)
    return path


def _configured_routed_paths(path: Path) -> Iterator[Path]:
    prefix, suffix = path.parts[0], path.parts[1:]
    if prefix in {"artifacts", "outputs"}:
        for name in _ARTIFACT_ROOT_ENVS:
            root = _configured_root(name)
            if root is not None:
                yield root.joinpath(DOSSIER_SLUG, prefix, *suffix)
    elif prefix == "logs":
        for name in _LOG_ROOT_ENVS:
            root = _configured_root(name)
            if root is not None:
                yield root.joinpath(DOSSIER_SLUG, "logs", *suffix)
    elif prefix == "tmp":
        configured = _configured_root("SPECTER_RUNTIME_ROOT")
        if configured is not None:
            yield configured.joinpath(DOSSIER_SLUG, *suffix)


def _configured_root(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    if not raw.strip():
        raise RuntimeError(f"{name} is set but empty")
    return Path(raw).expanduser().resolve()


def _first_configured_root(names: tuple[str, ...]) -> Path | None:
    for name in names:
        configured = _configured_root(name)
        if configured is not None:
            return configured
    return None


def _persistent_input_path(path: Path) -> Path:
    prefix, suffix = path.parts[0], path.parts[1:]
    if prefix == "logs":
        return persistent_dossier_root().joinpath("outputs", "logs", *suffix)
    return persistent_dossier_root() / path
