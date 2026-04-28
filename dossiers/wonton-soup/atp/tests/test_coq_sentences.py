from __future__ import annotations

from atp.coq.sentences import split_coq_sentences


def test_split_coq_sentences_keeps_dotted_require_import_paths() -> None:
    source = """
Require Import Coq.Init.Logic.
Require Import Coq.Init.Datatypes.
Require Import Coq.Bool.Bool.
Check eq_sym.
""".strip()

    assert split_coq_sentences(source) == [
        "Require Import Coq.Init.Logic.",
        "Require Import Coq.Init.Datatypes.",
        "Require Import Coq.Bool.Bool.",
        "Check eq_sym.",
    ]


def test_split_coq_sentences_splits_before_comment_block() -> None:
    source = "Check eq_sym.(* comment *)Check eq_trans."
    assert split_coq_sentences(source) == [
        "Check eq_sym.",
        "(* comment *)Check eq_trans.",
    ]
