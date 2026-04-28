from __future__ import annotations

from pathlib import Path

import pytest

from prover.providers.deepseek import MLX_MODEL_DIRNAME, _resolve_model_path


def test_resolve_model_path_prefers_explicit_and_deepseek_artifact_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit = "/tmp/deepseek-model"
    assert _resolve_model_path(explicit) == explicit

    deepseek_root = tmp_path / "deepseek-root"
    model_dir = deepseek_root / "wonton-soup" / "models" / MLX_MODEL_DIRNAME
    model_dir.mkdir(parents=True)

    monkeypatch.setenv("DEEPSEEK_ARTIFACT_ROOT", str(deepseek_root))
    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", "/tmp/locked-root")

    orig_is_dir = Path.is_dir

    def _fake_is_dir(self: Path) -> bool:
        if str(self).startswith("/tmp/locked-root"):
            raise OSError(77, "No locks available")
        return orig_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", _fake_is_dir)

    assert _resolve_model_path() == str(model_dir)


def test_resolve_model_path_raises_without_artifact_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("SPECTER_ARTIFACT_ROOT", raising=False)

    with pytest.raises(FileNotFoundError):
        _resolve_model_path()
