from __future__ import annotations

from pathlib import Path

from atp.coq.stdlib import extract_theorems_from_file


def test_extract_theorems_with_modules_and_sections(tmp_path: Path) -> None:
    source = tmp_path / "sample.v"
    source.write_text(
        """
Module Foo.
Theorem bar : True.
End Foo.

Section S.
Lemma baz : True.
End S.

Module Alias := Foo.
Theorem top : True.
"""
    )
    theorems = extract_theorems_from_file(source)
    assert "Foo.bar" in theorems
    assert "baz" in theorems
    assert "top" in theorems
