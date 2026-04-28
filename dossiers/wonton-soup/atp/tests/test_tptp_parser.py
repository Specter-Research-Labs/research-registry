from __future__ import annotations

import pytest

from atp.compare_hash import hash_clause, hash_deps, hash_goal_sig, hash_shape
from atp.tptp.parser import canonicalize_tptp_formula, parse_tstp, steps_to_graph


def test_parse_statement_with_quotes_and_thf() -> None:
    text = """
fof(q1, axiom, p('a''b')).
thf(h1, axiom, $true).
"""
    steps = parse_tstp(text)
    assert len(steps) == 2
    assert steps[0].name == "q1"
    assert steps[1].name == "h1"


def test_parse_tcf_statement() -> None:
    text = """
tcf(c0, axiom, p(a)).
cnf(c1, plain, p(a), inference(resolution,[status(thm)],[c0])).
"""
    graph = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert graph.graph.has_edge("c0", "c1")


def test_parent_extraction_inference() -> None:
    text = "cnf(c1, plain, p(a), inference(resolution,[status(thm)],[c0,c2]))."
    steps = parse_tstp(text)
    assert steps[0].rule == "resolution"
    assert steps[0].parents == ["c0", "c2"]


def test_parent_extraction_introduced() -> None:
    text = "cnf(c2, plain, p(a), introduced(definition,[new_symbols],[c1]))."
    steps = parse_tstp(text)
    assert steps[0].rule == "introduced:definition"
    assert steps[0].parents == ["c1"]


def test_pseudo_parents_are_ignored() -> None:
    text = "cnf(c2, plain, p(a), introduced(definition,[],[skolem_symbol_introduction]))."
    graph = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert graph.graph.number_of_nodes() == 1


def test_ephemeral_parents_are_ignored() -> None:
    text = "cnf(c2, plain, p(a), inference(spm,[],[c_0_-1]))."
    graph = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert graph.graph.number_of_nodes() == 1


def test_missing_parent_resolves_to_matching_input() -> None:
    text = """
cnf(ax, axiom, p(a)).
cnf(c1, plain, p(a), inference(fof_simplification,[status(thm)],[c_0_4])).
"""
    graph = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert graph.graph.has_edge("ax", "c1")


def test_parent_extraction_nested_inference() -> None:
    text = "cnf(c3, plain, p(a), inference(resolution,[status(thm)],[c1,inference(simp,[],[c0])]))."
    steps = parse_tstp(text)
    assert steps[0].rule == "resolution"
    assert set(steps[0].parents) == {"c1", "c0"}


def test_node_identity_keeps_duplicates() -> None:
    text = """
cnf(c0, axiom, p(a)).
cnf(c1, axiom, p(a)).
cnf(c2, plain, p(a), inference(resolution,[status(thm)],[c0,c1])).
"""
    graph = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert graph.graph.number_of_nodes() == 3


def test_missing_parent_raises() -> None:
    text = "cnf(c1, plain, p(a), inference(resolution,[status(thm)],[c0]))."
    with pytest.raises(ValueError):
        steps_to_graph(parse_tstp(text))


def test_cycle_detection_raises() -> None:
    text = """
cnf(c0, plain, p(a), inference(resolution,[status(thm)],[c1])).
cnf(c1, plain, p(a), inference(resolution,[status(thm)],[c0])).
"""
    with pytest.raises(ValueError):
        steps_to_graph(parse_tstp(text))


def test_canonicalization_quantifier_order() -> None:
    f1 = "! [Y,X] : p(X,Y)"
    f2 = "! [X,Y] : p(X,Y)"
    assert canonicalize_tptp_formula(f1) == canonicalize_tptp_formula(f2)


def test_canonicalization_alpha_rename_free_vars() -> None:
    f1 = "p(X,Y)"
    f2 = "p(A,B)"
    assert canonicalize_tptp_formula(f1) == canonicalize_tptp_formula(f2)


def test_canonicalization_equality_symmetry() -> None:
    assert canonicalize_tptp_formula("a=b") == canonicalize_tptp_formula("b=a")


def test_canonicalization_negation_push() -> None:
    f1 = "~(p|q)"
    f2 = "~p&~q"
    assert canonicalize_tptp_formula(f1) == canonicalize_tptp_formula(f2)


def test_canonicalization_commutative_or() -> None:
    f1 = "p|q|r"
    f2 = "r|(p|q)"
    assert canonicalize_tptp_formula(f1) == canonicalize_tptp_formula(f2)


def test_canonicalization_preserves_dollar_symbols() -> None:
    out = canonicalize_tptp_formula("p($k,X)")
    assert "$k" in out
    assert "V0" in out


def test_canonicalization_nand_nor() -> None:
    f1 = "p ~| q"
    f2 = "~(p|q)"
    assert canonicalize_tptp_formula(f1) == canonicalize_tptp_formula(f2)


def test_hash_modes_match_on_identical_graphs() -> None:
    text = """
cnf(c0, axiom, p(a)).
cnf(c1, axiom, q(a)).
cnf(c2, plain, p(a)|q(a), inference(resolution,[status(thm)],[c0,c1])).
"""
    graph_a = steps_to_graph(parse_tstp(text)).to_proof_graph()
    graph_b = steps_to_graph(parse_tstp(text)).to_proof_graph()
    assert hash_goal_sig(graph_a) == hash_goal_sig(graph_b)
    assert hash_shape(graph_a) == hash_shape(graph_b)
    assert hash_clause(graph_a) == hash_clause(graph_b)
    assert hash_deps(graph_a) == hash_deps(graph_b)
