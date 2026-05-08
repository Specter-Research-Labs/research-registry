from __future__ import annotations

from pathlib import Path

import pytest

import runtime_paths as rp


@pytest.fixture(autouse=True)
def _clear_remote_ssh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECTER_REMOTE_SSH", raising=False)
    monkeypatch.delenv("SPCTR_LOCAL_LOG_ROOT", raising=False)
    monkeypatch.delenv("SPCTR_LOCAL_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_LOG_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_RUNTIME_ROOT", raising=False)
    monkeypatch.setattr(rp, "_ssh_config_cache", rp._UNSET)


def test_default_persistent_root_uses_current_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "research-registry"
    dossier_root = repo_root / "dossiers" / rp.DOSSIER_NAME
    dossier_root.mkdir(parents=True)
    monkeypatch.setattr(rp, "REPO_ROOT", repo_root)
    monkeypatch.setattr(rp, "DOSSIER_ROOT", dossier_root)

    assert rp.default_persistent_root() == dossier_root.resolve()
    assert rp.resolve_logs_root() == dossier_root.resolve() / "logs"
    assert rp.resolve_artifacts_root() == dossier_root.resolve() / "artifacts"
    assert rp.resolve_corpora_root() == dossier_root.resolve() / "artifacts" / "corpora"


def test_default_persistent_root_uses_sibling_main_checkout(tmp_path: Path) -> None:
    main_dossiers = tmp_path / "research-registry" / "dossiers"
    workspace_repo = tmp_path / "research-registry-workspaces" / "wonton-workspace"
    main_dossiers.mkdir(parents=True)
    workspace_repo.mkdir(parents=True)

    assert rp.default_persistent_dossier_parent(workspace_repo) == main_dossiers.resolve()


def test_resolve_logs_root_uses_local_runtime_when_remote_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECTER_LOG_ROOT", str(tmp_path))
    local_root = rp.resolve_logs_root()
    assert local_root == rp.local_runtime_logs_root()


def test_local_roots_win_over_remote_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    monkeypatch.setenv("SPCTR_LOCAL_LOG_ROOT", str(local_root))
    monkeypatch.setenv("SPCTR_LOCAL_ARTIFACT_ROOT", str(local_root))
    monkeypatch.setenv("SPECTER_LOG_ROOT", str(remote_root))
    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(remote_root))

    assert rp.resolve_logs_root() == local_root.resolve() / rp.DOSSIER_NAME / "logs"
    assert (
        rp.resolve_artifacts_root()
        == local_root.resolve() / rp.DOSSIER_NAME / "artifacts"
    )
    assert (
        rp.resolve_corpora_root()
        == local_root.resolve() / rp.DOSSIER_NAME / "artifacts" / "corpora"
    )


def test_local_runtime_roots_use_runtime_env_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECTER_RUNTIME_ROOT", str(tmp_path))
    runtime_root = tmp_path / rp.DOSSIER_NAME
    assert rp.local_runtime_logs_root() == runtime_root / "logs"
    assert rp.local_runtime_log_archives_root() == runtime_root / "log-archives"
    assert rp.local_runtime_artifacts_root() == runtime_root / "artifacts"
    assert rp.local_runtime_corpora_root() == runtime_root / "corpora"


def test_resolve_synthetic_bureau_root_prefers_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit = tmp_path / "synthetic-bureau-private"
    monkeypatch.setenv("SPECTER_SYNTHETIC_BUREAU_ROOT", str(explicit))
    assert rp.resolve_synthetic_bureau_root() == explicit.resolve()


def test_resolve_synthetic_bureau_root_uses_private_sibling_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sibling = tmp_path / "synthetic-bureau"
    sibling.mkdir()
    monkeypatch.setattr(rp, "REPO_ROOT", tmp_path / "specter")
    assert rp.resolve_synthetic_bureau_root() == sibling.resolve()


def test_configured_remote_logs_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECTER_LOG_ROOT", str(tmp_path))
    assert rp.configured_remote_logs_root() == tmp_path / rp.DOSSIER_NAME / "logs"


def test_configured_remote_artifacts_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(tmp_path))
    assert rp.configured_remote_artifacts_root() == tmp_path / rp.DOSSIER_NAME / "artifacts"


def test_read_root_raises_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECTER_LOG_ROOT", "   ")
    with pytest.raises(ValueError, match="set but empty"):
        rp.configured_remote_logs_root()


def test_sync_to_remote_returns_none_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SPECTER_LOG_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_ARTIFACT_ROOT", raising=False)
    assert rp.sync_logs_to_remote(tmp_path) is None


def test_sync_to_remote_raises_on_missing_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECTER_LOG_ROOT", str(tmp_path / "remote"))
    with pytest.raises(FileNotFoundError, match="does not exist"):
        rp.sync_logs_to_remote(tmp_path / "missing", require_src=True)
