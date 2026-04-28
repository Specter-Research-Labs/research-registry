# ruff: noqa: I001
from __future__ import annotations

import gzip
from pathlib import Path

from shared import (
    import_wonton_symbol,
    iter_jsonl_objects,
    iter_trace_paths,
    iter_variant_prefixes,
    load_json_object,
    read_run_id,
    resolve_repo_root,
    resolve_single_provider_run,
    trace_path_for_prefix,
    write_json_object,
)


def test_resolve_repo_root_and_import_symbol(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    wonton_root = repo_root / "dossiers" / "wonton-soup"
    wonton_root.mkdir(parents=True)
    (wonton_root / "fake_module.py").write_text("answer = 42\n", encoding="utf-8")

    resolved = resolve_repo_root(str(repo_root))
    assert resolved == repo_root
    assert import_wonton_symbol(repo_root, "fake_module", "answer") == 42


def test_json_helpers_support_plain_and_gz_jsonl(tmp_path: Path) -> None:
    plain = tmp_path / "rows.jsonl"
    plain.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    gz = tmp_path / "rows.jsonl.gz"
    with gzip.open(gz, "wt") as handle:
        handle.write('{"c": 3}\n')

    assert list(iter_jsonl_objects(plain)) == [{"a": 1}, {"b": 2}]
    assert list(iter_jsonl_objects(gz)) == [{"c": 3}]

    manifest = tmp_path / "manifest.json"
    write_json_object(manifest, {"ok": True})
    assert load_json_object(manifest) == {"ok": True}


def test_run_and_trace_helpers(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    provider_dir = run_dir / "provider=modal"
    theorem_dir = provider_dir / "Example.Theorem"
    theorem_dir.mkdir(parents=True)
    (provider_dir / "run_config.json").write_text('{"run_id":"run-1"}\n', encoding="utf-8")
    (theorem_dir / "alpha_mcts_tree.json").write_text('{"tree": true}\n', encoding="utf-8")
    (theorem_dir / "alpha_mcts_trace.jsonl").write_text('{"event":"iteration"}\n', encoding="utf-8")
    (theorem_dir / "beta_mcts_trace.jsonl.gz").write_bytes(
        gzip.compress(b'{"event":"iteration"}\n')
    )

    assert read_run_id(provider_dir) == "run-1"
    assert resolve_single_provider_run(run_dir, "modal") == provider_dir
    assert iter_trace_paths(provider_dir) == [
        theorem_dir / "alpha_mcts_trace.jsonl",
        theorem_dir / "beta_mcts_trace.jsonl.gz",
    ]
    assert iter_variant_prefixes(theorem_dir) == ["alpha", "beta"]
    assert trace_path_for_prefix(theorem_dir, "alpha") == theorem_dir / "alpha_mcts_trace.jsonl"
    assert trace_path_for_prefix(theorem_dir, "beta") == theorem_dir / "beta_mcts_trace.jsonl.gz"
