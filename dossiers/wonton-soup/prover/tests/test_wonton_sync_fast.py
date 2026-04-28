from __future__ import annotations

from pathlib import Path

import pytest
import typer

import runtime_paths
import wonton


def _reset_ssh_cache() -> None:
    runtime_paths._ssh_config_cache = runtime_paths._UNSET
    runtime_paths._ssh_config_cache_raw = runtime_paths._UNSET


def test_parse_ssh_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_ssh_cache()
    monkeypatch.setenv("SPECTER_REMOTE_SSH", "user@host.example.com:23")
    cfg = runtime_paths.configured_remote_ssh()
    assert cfg is not None
    assert cfg.user == "user"
    assert cfg.host == "host.example.com"
    assert cfg.port == 23
    _reset_ssh_cache()


def test_parse_ssh_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_ssh_cache()
    monkeypatch.delenv("SPECTER_REMOTE_SSH", raising=False)
    assert runtime_paths.configured_remote_ssh() is None
    _reset_ssh_cache()


def test_parse_ssh_config_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_ssh_cache()
    monkeypatch.setenv("SPECTER_REMOTE_SSH", "badformat")
    with pytest.raises(ValueError, match="user@host:port"):
        runtime_paths.configured_remote_ssh()
    _reset_ssh_cache()


def test_ssh_config_for_root_prefers_local_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_ssh_cache()
    monkeypatch.setenv("SPECTER_REMOTE_SSH", "user@host.example.com:23")
    cfg = runtime_paths.ssh_config_for_root(tmp_path)
    assert cfg is None
    _reset_ssh_cache()


def test_ssh_config_for_root_returns_config_when_path_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_ssh_cache()
    monkeypatch.setenv("SPECTER_REMOTE_SSH", "user@host.example.com:23")
    cfg = runtime_paths.ssh_config_for_root(tmp_path / "nonexistent")
    assert cfg is not None
    assert cfg.host == "host.example.com"
    _reset_ssh_cache()


def test_ssh_target_formatting() -> None:
    cfg = runtime_paths.RemoteSSHConfig(user="u1", host="box.example.com", port=23)
    assert cfg.target(Path("/data/logs")) == "u1@box.example.com:/data/logs"
    assert cfg.ssh_cmd() == ["ssh", "-p", "23"]


def test_ensure_remote_accessible_passes_with_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_ssh_cache()
    monkeypatch.setenv("SPECTER_REMOTE_SSH", "user@host:22")
    wonton._ensure_remote_accessible(
        Path("/nonexistent/remote/path"), label="TEST",
    )
    _reset_ssh_cache()


def test_ensure_remote_accessible_fails_without_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_ssh_cache()
    monkeypatch.delenv("SPECTER_REMOTE_SSH", raising=False)
    with pytest.raises(typer.Exit):
        wonton._ensure_remote_accessible(
            Path("/nonexistent/remote/path"), label="TEST",
        )
    _reset_ssh_cache()
