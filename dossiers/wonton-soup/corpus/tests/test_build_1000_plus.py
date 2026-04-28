from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import corpus.pipeline.build as build_mod


def _write_lean_project(lean_project: Path) -> None:
    lean_project.mkdir(parents=True, exist_ok=True)
    (lean_project / "lean-toolchain").write_text(
        "leanprover/lean4:nightly-2025-01-01\n",
        encoding="utf-8",
    )
    (lean_project / "lake-manifest.json").write_text(
        json.dumps({"packages": [{"name": "mathlib", "rev": "mathlib-rev-test"}]}),
        encoding="utf-8",
    )


def _prepare_1000_plus_repo(artifacts_root: Path, rev: str, entries: dict[str, str]) -> None:
    thm_root = artifacts_root / "sources" / "git" / "1000-plus.github.io" / rev / "_thm"
    thm_root.mkdir(parents=True, exist_ok=True)
    for name, payload in entries.items():
        (thm_root / name).write_text(textwrap.dedent(payload).strip() + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _stub_extractor_row(qualname: str) -> dict[str, Any]:
    safe_item = build_mod._lean_ident_component(qualname)
    return {
        "item_id": safe_item,
        "display_name": qualname,
        "payload": {
            "statement": "theorem {name} : True := by\n  sorry",
            "source": {"kind": "lean_env", "module": "Mathlib", "qualname": qualname},
        },
    }


def test_resolve_lake_binary_uses_path_when_available(monkeypatch) -> None:
    monkeypatch.setattr(build_mod.shutil, "which", lambda name: "/usr/local/bin/lake")
    assert build_mod._resolve_lake_binary() == "/usr/local/bin/lake"


def test_resolve_lake_binary_falls_back_to_elan(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(build_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(build_mod.Path, "home", lambda: tmp_path)
    lake = tmp_path / ".elan" / "bin" / "lake"
    lake.parent.mkdir(parents=True, exist_ok=True)
    lake.write_text("", encoding="utf-8")
    assert build_mod._resolve_lake_binary() == str(lake)


def test_build_lean_1000_plus_uses_only_formalized_entries_with_identifiers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    lean_project = tmp_path / "lean_project"
    rev = "deadbeef"
    _write_lean_project(lean_project)
    _prepare_1000_plus_repo(
        artifacts_root,
        rev,
        {
            "Q1.md": """
                ---
                # Eligible theorem

                wikidata: Q1
                wikipedia_links:
                - '[[Eligible theorem]]'
                lean:
                - status: formalized
                  library: L
                  url: https://lean.example/Q1
                  identifiers:
                  - Foo.bar
                ---
            """,
            "Q2.md": """
                ---
                # No identifiers theorem

                wikidata: Q2
                wikipedia_links:
                - '[[No identifiers theorem]]'
                lean:
                - status: formalized
                  library: L
                  url: https://lean.example/Q2
                ---
            """,
            "Q3.md": """
                ---
                # Statement only theorem

                wikidata: Q3
                wikipedia_links:
                - '[[Statement only theorem]]'
                lean:
                - status: statement
                  library: L
                  url: https://lean.example/Q3
                  identifiers:
                  - Ignored.ident
                ---
            """,
            "Q4.md": """
                ---
                # No lean block theorem

                wikidata: Q4
                wikipedia_links:
                - '[[No lean block theorem]]'
                ---
            """,
        },
    )
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    monkeypatch.setattr(build_mod, "_ensure_git_checkout", lambda **_: None)

    captured: dict[str, list[str]] = {}

    def _fake_extract(*, lean_project: Path, names: list[str]) -> list[dict[str, Any]]:
        captured["names"] = list(names)
        return [_stub_extractor_row("Foo.bar")]

    monkeypatch.setattr(build_mod, "_extract_lean_named_theorems", _fake_extract)

    built = build_mod.build_lean_1000_plus(
        corpus_id="1000-plus-test",
        rev=rev,
        lean_project=lean_project,
    )

    assert captured["names"] == ["Foo.bar"]
    manifest = json.loads((built.build_dir / "manifest.json").read_text(encoding="utf-8"))
    cfg = manifest["build_config"]
    assert cfg["identifier_candidate_total"] == 1
    assert cfg["identifier_requested_count"] == 1
    assert cfg["identifier_resolved_count"] == 1
    assert cfg["identifier_unresolved_count"] == 0


def test_build_lean_1000_plus_tracks_unresolved_identifiers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    lean_project = tmp_path / "lean_project"
    rev = "cafebabe"
    _write_lean_project(lean_project)
    _prepare_1000_plus_repo(
        artifacts_root,
        rev,
        {
            "Q10.md": """
                ---
                # Mixed resolution theorem

                wikidata: Q10
                wikipedia_links:
                - '[[Mixed resolution theorem]]'
                lean:
                - status: formalized
                  library: L
                  url: https://lean.example/Q10
                  identifiers:
                  - Foo.bar
                  - Missing.name
                ---
            """
        },
    )
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    monkeypatch.setattr(build_mod, "_ensure_git_checkout", lambda **_: None)
    monkeypatch.setattr(
        build_mod,
        "_extract_lean_named_theorems",
        lambda **_: [_stub_extractor_row("Foo.bar")],
    )

    built = build_mod.build_lean_1000_plus(
        corpus_id="1000-plus-test",
        rev=rev,
        lean_project=lean_project,
    )

    manifest = json.loads((built.build_dir / "manifest.json").read_text(encoding="utf-8"))
    cfg = manifest["build_config"]
    assert cfg["identifier_requested_count"] == 2
    assert cfg["identifier_resolved_count"] == 1
    assert cfg["identifier_unresolved_count"] == 1
    assert cfg["identifier_unresolved_preview"] == ["Missing.name"]
    items = _read_jsonl(built.build_dir / "items.jsonl")
    assert len(items) == 1
    assert items[0]["display_name"] == "Foo.bar"


def test_build_lean_1000_plus_aggregates_duplicate_identifier_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    lean_project = tmp_path / "lean_project"
    rev = "feedface"
    _write_lean_project(lean_project)
    _prepare_1000_plus_repo(
        artifacts_root,
        rev,
        {
            "Q20.md": """
                ---
                # First duplicate theorem

                wikidata: Q20
                wikipedia_links:
                - '[[First duplicate theorem]]'
                lean:
                - status: formalized
                  library: L
                  url: https://lean.example/Q20
                  identifiers:
                  - Shared.ident
                ---
            """,
            "Q21.md": """
                ---
                # Second duplicate theorem

                wikidata: Q21
                id_suffix: X
                wikipedia_links:
                - '[[Second duplicate theorem]]'
                lean:
                - status: formalized
                  library: X
                  url: https://lean.example/Q21X
                  identifiers:
                  - Shared.ident
                ---
            """,
        },
    )
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    monkeypatch.setattr(build_mod, "_ensure_git_checkout", lambda **_: None)
    monkeypatch.setattr(
        build_mod,
        "_extract_lean_named_theorems",
        lambda **_: [_stub_extractor_row("Shared.ident")],
    )

    built = build_mod.build_lean_1000_plus(
        corpus_id="1000-plus-test",
        rev=rev,
        lean_project=lean_project,
    )

    items = _read_jsonl(built.build_dir / "items.jsonl")
    assert len(items) == 1
    refs = items[0]["payload"]["source"]["thm_refs"]
    assert len(refs) == 2
    assert [ref["wikidata"] for ref in refs] == ["Q20", "Q21"]
    assert refs[1]["id_suffix"] == "X"


def test_build_lean_1000_plus_can_fail_on_missing_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    lean_project = tmp_path / "lean_project"
    rev = "beadfeed"
    _write_lean_project(lean_project)
    _prepare_1000_plus_repo(
        artifacts_root,
        rev,
        {
            "Q30.md": """
                ---
                # Missing theorem

                wikidata: Q30
                wikipedia_links:
                - '[[Missing theorem]]'
                lean:
                - status: formalized
                  library: L
                  url: https://lean.example/Q30
                  identifiers:
                  - Missing.only
                ---
            """
        },
    )
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    monkeypatch.setattr(build_mod, "_ensure_git_checkout", lambda **_: None)
    monkeypatch.setattr(build_mod, "_extract_lean_named_theorems", lambda **_: [])

    try:
        build_mod.build_lean_1000_plus(
            corpus_id="1000-plus-test",
            rev=rev,
            lean_project=lean_project,
            allow_missing_resolution=False,
        )
    except RuntimeError as exc:
        assert "Unresolved Lean identifiers" in str(exc)
    else:
        raise AssertionError("expected unresolved identifier failure")
