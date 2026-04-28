from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DOSSIER_NAME = "wonton-soup"
DOSSIER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = DOSSIER_ROOT.parents[1]


@dataclass(frozen=True)
class RemoteSSHConfig:
    user: str
    host: str
    port: int

    def target(self, path: Path | str) -> str:
        return f"{self.user}@{self.host}:{path}"

    def ssh_cmd(self) -> list[str]:
        return ["ssh", "-p", str(self.port)]


@dataclass(frozen=True)
class SyncReport:
    src_root: Path
    dst_root: Path
    copied_files: int = 0
    skipped_files: int = 0
    copied_bytes: int = 0


_UNSET = object()
_ssh_config_cache: RemoteSSHConfig | None | object = _UNSET
_ssh_config_cache_raw: str | object = _UNSET


def configured_remote_ssh() -> RemoteSSHConfig | None:
    global _ssh_config_cache, _ssh_config_cache_raw
    raw = os.environ.get("SPECTER_REMOTE_SSH", "").strip()
    if _ssh_config_cache is not _UNSET and _ssh_config_cache_raw == raw:
        cached = _ssh_config_cache
        assert cached is None or isinstance(cached, RemoteSSHConfig)
        return cached
    if not raw:
        _ssh_config_cache = None
        _ssh_config_cache_raw = raw
        return None
    if "@" not in raw or ":" not in raw:
        raise ValueError(f"SPECTER_REMOTE_SSH must be user@host:port, got: {raw!r}")
    user, rest = raw.split("@", 1)
    host, port_str = rest.rsplit(":", 1)
    cfg = RemoteSSHConfig(user=user, host=host, port=int(port_str))
    _ssh_config_cache = cfg
    _ssh_config_cache_raw = raw
    return cfg


def _read_root(env_name: str) -> Path | None:
    raw = os.environ.get(env_name)
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"{env_name} is set but empty.")
    return Path(os.path.expanduser(trimmed)).resolve()


def _dossier_root(env_name: str, child: str) -> Path | None:
    root = _read_root(env_name)
    if root is None:
        return None
    return root / DOSSIER_NAME / child


def configured_remote_logs_root() -> Path | None:
    return _dossier_root("SPECTER_LOG_ROOT", "logs")


def configured_remote_log_archives_root() -> Path | None:
    return _dossier_root("SPECTER_LOG_ROOT", "log-archives")


def configured_remote_artifacts_root() -> Path | None:
    return _dossier_root("SPECTER_ARTIFACT_ROOT", "artifacts")


def configured_remote_corpora_root() -> Path | None:
    return _dossier_root("SPECTER_ARTIFACT_ROOT", "corpora")


def _local_runtime_root(child: str, *, tmp_family: str) -> Path:
    runtime_root = _dossier_root("SPECTER_RUNTIME_ROOT", "")
    if runtime_root is not None:
        return (runtime_root / child).resolve()
    return (REPO_ROOT / "tmp" / tmp_family / DOSSIER_NAME / child).resolve()


def local_runtime_logs_root() -> Path:
    return _local_runtime_root("logs", tmp_family="runtime-logs")


def local_runtime_log_archives_root() -> Path:
    return _local_runtime_root("log-archives", tmp_family="runtime-logs")


def local_runtime_artifacts_root() -> Path:
    return _local_runtime_root("artifacts", tmp_family="runtime-artifacts")


def local_runtime_corpora_root() -> Path:
    return _local_runtime_root("corpora", tmp_family="runtime-artifacts")


def resolve_logs_root() -> Path:
    if configured_remote_logs_root() is not None:
        return local_runtime_logs_root()
    return DOSSIER_ROOT / "logs"


def resolve_artifacts_root() -> Path:
    if configured_remote_artifacts_root() is not None:
        return local_runtime_artifacts_root()
    return DOSSIER_ROOT / "outputs"


def resolve_corpora_root() -> Path:
    if configured_remote_corpora_root() is not None:
        return local_runtime_corpora_root()
    return DOSSIER_ROOT / "artifacts" / "corpora"


def resolve_synthetic_bureau_root() -> Path:
    explicit = _read_root("SPECTER_SYNTHETIC_BUREAU_ROOT")
    if explicit is not None:
        return explicit
    sibling = (REPO_ROOT.parent / "synthetic-bureau").resolve()
    if sibling.exists():
        return sibling
    return sibling


def ssh_config_for_root(root: Path | None) -> RemoteSSHConfig | None:
    cfg = configured_remote_ssh()
    if cfg is None:
        return None
    if root is not None and root.exists():
        return None
    return cfg


# --- Sync: thin rsync wrapper for orchestrator hot-path usage ---


def sync_to_remote(
    local_path: Path,
    remote_root: Path | None = None,
    *,
    require_src: bool = False,
) -> SyncReport | None:
    if remote_root is None:
        remote_root = configured_remote_logs_root()
    if remote_root is None:
        return None
    if not local_path.exists():
        if require_src:
            raise FileNotFoundError(f"Sync source does not exist: {local_path}")
        return SyncReport(src_root=local_path, dst_root=remote_root)
    _rsync(local_path, remote_root, push=True)
    return SyncReport(src_root=local_path, dst_root=remote_root, copied_files=1)


def sync_from_remote(
    local_path: Path,
    remote_root: Path | None = None,
    *,
    require_src: bool = False,
) -> SyncReport | None:
    if remote_root is None:
        remote_root = configured_remote_logs_root()
    if remote_root is None:
        return None
    local_path.mkdir(parents=True, exist_ok=True)
    _rsync(remote_root, local_path, push=False)
    return SyncReport(src_root=remote_root, dst_root=local_path, copied_files=1)


def _rsync(src: Path, dst: Path, *, push: bool) -> None:
    ssh = configured_remote_ssh()
    src_str = str(src).rstrip("/") + "/"
    dst_str = str(dst).rstrip("/") + "/"
    if ssh is not None:
        if push:
            target = ssh.target(dst_str)
            source = src_str
        else:
            target = dst_str
            source = ssh.target(src_str)
        cmd = ["rsync", "-az", "-e", f"ssh -p {ssh.port}", source, target]
    else:
        cmd = ["rsync", "-a", src_str, dst_str]
    subprocess.run(cmd, check=True)


# Legacy aliases kept for callers that haven't migrated to spctr CLI yet.
# These thin wrappers match the old signature so existing orchestrator code
# continues to work without changes beyond import adjustments.

def sync_logs_to_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    remote = configured_remote_log_archives_root() or configured_remote_logs_root()
    return sync_to_remote(local_path, remote, require_src=require_src)


def sync_logs_from_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    remote = configured_remote_log_archives_root() or configured_remote_logs_root()
    return sync_from_remote(local_path, remote, require_src=require_src)


def sync_artifacts_to_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    return sync_to_remote(local_path, configured_remote_artifacts_root(), require_src=require_src)


def sync_artifacts_from_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    return sync_from_remote(local_path, configured_remote_artifacts_root(), require_src=require_src)


def sync_corpora_to_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    return sync_to_remote(local_path, configured_remote_corpora_root(), require_src=require_src)


def sync_corpora_from_remote(
    local_path: Path, *, require_src: bool = False, **_kw: object
) -> SyncReport | None:
    return sync_from_remote(local_path, configured_remote_corpora_root(), require_src=require_src)
