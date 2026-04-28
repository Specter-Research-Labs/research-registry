from __future__ import annotations

from atp.coq.source import collect_theorem_blocks


def test_collect_theorem_blocks_captures_prelude_and_proof_block() -> None:
    source = """
Require Import Coq.Init.Logic.

Module Foo.
Theorem bar : True.
Proof.
  exact I.
Qed.
End Foo.
""".strip()

    blocks = collect_theorem_blocks(source, source_path="sample.v")
    assert len(blocks) == 1
    block = blocks[0]
    assert block.qualname == "Foo.bar"
    assert block.terminator == "Qed"
    assert block.source_path == "sample.v"
    assert block.prelude_sentences == ("Require Import Coq.Init.Logic.", "Module Foo.")
    assert block.block_sentences == (
        "Theorem bar : True.",
        "Proof.",
        "exact I.",
        "Qed.",
    )
    assert block.replayable is True


def test_collect_theorem_blocks_marks_inline_proof_term_as_not_replayable() -> None:
    source = "Theorem demo : True := I."
    blocks = collect_theorem_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].qualname == "demo"
    assert blocks[0].block_sentences == ("Theorem demo : True := I.",)
    assert blocks[0].replayable is False
