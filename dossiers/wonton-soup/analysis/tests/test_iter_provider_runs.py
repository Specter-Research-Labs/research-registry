from __future__ import annotations

from pathlib import Path

import pytest

from analysis.logs import ProviderRun, iter_provider_runs


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_iter_provider_runs_single_provider(tmp_path: Path) -> None:
    run_dir = tmp_path / "corpus-2026-01-01-000000"
    _touch(run_dir / "run_config.json")

    runs = iter_provider_runs(run_dir)
    assert runs == [ProviderRun(run_dir=run_dir.resolve(), provider=None)]


def test_iter_provider_runs_prefers_provider_subruns(tmp_path: Path) -> None:
    root = tmp_path / "corpus-2026-01-01-000000"
    _touch(root / "run_config.json")
    _touch(root / "provider=reprover" / "run_config.json")
    _touch(root / "provider=deepseek" / "run_config.json")
    (root / "provider=broken").mkdir(parents=True, exist_ok=True)

    runs = iter_provider_runs(root)
    assert [r.provider for r in runs] == ["deepseek", "reprover"]
    assert [r.run_dir.name for r in runs] == ["provider=deepseek", "provider=reprover"]


def test_iter_provider_runs_missing_run_config_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        iter_provider_runs(tmp_path / "empty")

