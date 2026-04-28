from __future__ import annotations

from orchestrator.external import _parse_coqtop_check_output


def test_parse_coqtop_check_output_parses_multiline_statement_blocks() -> None:
    output = """and_assoc
     : forall A B C : Prop, (A /\\ B) /\\ C <-> A /\\ B /\\ C
pair_equal_spec
     : forall (A B : Type) (a1 a2 : A) (b1 b2 : B),
       (a1, b1) = (a2, b2) <-> a1 = a2 /\\ b1 = b2
eq_sym
     : forall (A : Type) (x y : A), x = y -> y = x
"""
    parsed = _parse_coqtop_check_output(
        output,
        ["and_assoc", "pair_equal_spec", "eq_sym"],
    )

    assert parsed["and_assoc"] == "forall A B C : Prop, (A /\\ B) /\\ C <-> A /\\ B /\\ C"
    assert parsed["pair_equal_spec"] == (
        "forall (A B : Type) (a1 a2 : A) (b1 b2 : B), "
        "(a1, b1) = (a2, b2) <-> a1 = a2 /\\ b1 = b2"
    )
    assert parsed["eq_sym"] == "forall (A : Type) (x y : A), x = y -> y = x"


def test_parse_coqtop_check_output_skips_missing_theorems() -> None:
    output = """eq_sym
     : forall (A : Type) (x y : A), x = y -> y = x
"""
    parsed = _parse_coqtop_check_output(output, ["and_assoc", "eq_sym"])
    assert "and_assoc" not in parsed
    assert parsed["eq_sym"] == "forall (A : Type) (x y : A), x = y -> y = x"
