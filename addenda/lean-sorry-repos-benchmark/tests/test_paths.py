from __future__ import annotations

from pathlib import Path

import pytest

from lean_sorry_repos_benchmark.paths import resolve_runtime_dir


def test_resolve_runtime_dir_env_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SPECTER_RUNTIME_ROOT", raising=False)
    fallback = tmp_path / "fallback"
    assert resolve_runtime_dir("cache", fallback) == fallback

    monkeypatch.setenv("SPECTER_RUNTIME_ROOT", "   ")
    with pytest.raises(ValueError, match="SPECTER_RUNTIME_ROOT is set but empty"):
        resolve_runtime_dir("cache", fallback)

    monkeypatch.setenv("SPECTER_RUNTIME_ROOT", str(tmp_path))
    assert resolve_runtime_dir("cache", fallback) == (
        tmp_path / "lean-sorry-repos-benchmark" / "cache"
    )
