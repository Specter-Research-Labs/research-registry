from __future__ import annotations

from pathlib import Path

from analysis.lake.index import discover_run_dirs


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_discover_run_dirs_finds_nested_wrapper_run(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    _touch(logs_root / "wrapper-run" / "run" / "run_config.json")
    _touch(logs_root / "wrapper-run" / "run" / "summary.json.gz")

    runs = discover_run_dirs(logs_root)
    rels = sorted(r.run_dir.relative_to(logs_root.resolve()).as_posix() for r in runs)
    assert rels == ["wrapper-run/run"]


def test_discover_run_dirs_finds_nested_provider_runs(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    _touch(logs_root / "capability-root" / "sample=25" / "provider=deepseek" / "run_config.json")
    _touch(logs_root / "capability-root" / "sample=25" / "provider=reprover" / "run_config.json")

    runs = discover_run_dirs(logs_root)
    rels = sorted(r.run_dir.relative_to(logs_root.resolve()).as_posix() for r in runs)
    assert rels == [
        "capability-root/sample=25/provider=deepseek",
        "capability-root/sample=25/provider=reprover",
    ]


def test_discover_run_dirs_ignores_hidden_nested_paths(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    _touch(logs_root / "hidden-root" / ".cache" / "run_config.json")
    _touch(logs_root / "good-root" / "run_config.json")

    runs = discover_run_dirs(logs_root)
    rels = sorted(r.run_dir.relative_to(logs_root.resolve()).as_posix() for r in runs)
    assert rels == ["good-root"]
