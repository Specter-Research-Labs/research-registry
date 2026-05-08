from __future__ import annotations

from pathlib import Path

import pytest

from corpus.artifacts import resolve_corpora_root
from runtime_paths import local_runtime_corpora_root


def test_resolve_corpora_root_env_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SPCTR_LOCAL_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_RUNTIME_ROOT", raising=False)
    root = resolve_corpora_root()
    assert root.name == "corpora"
    assert "dossiers" in root.parts

    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", "   ")
    with pytest.raises(ValueError, match="SPECTER_ARTIFACT_ROOT is set but empty"):
        resolve_corpora_root()

    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.delenv("SPECTER_RUNTIME_ROOT", raising=False)
    root = resolve_corpora_root()
    assert root == local_runtime_corpora_root()

    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(tmp_path / "remote"))
    monkeypatch.setenv("SPECTER_RUNTIME_ROOT", str(tmp_path / "runtime"))
    root = resolve_corpora_root()
    assert root == (tmp_path / "runtime" / "wonton-soup" / "corpora")

    runtime_root = tmp_path / "runtime" / "specter"
    runtime_root.mkdir(parents=True)
    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("SPECTER_RUNTIME_ROOT", str(runtime_root))

    assert resolve_corpora_root() == (runtime_root / "wonton-soup" / "corpora")

    monkeypatch.setenv("SPCTR_LOCAL_ARTIFACT_ROOT", str(tmp_path / "local"))
    assert (
        resolve_corpora_root()
        == (tmp_path / "local" / "wonton-soup" / "artifacts" / "corpora").resolve()
    )
