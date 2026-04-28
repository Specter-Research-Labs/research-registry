from pathlib import Path
from typing import cast

from analysis import (
    _canonical_equivalent_law_id,
    _kernel_bridge_analysis,
    _kernel_micro_rewrite_analysis,
    _kernel_micro_rewrite_candidate_surface,
    _public_pair_duplicates,
    _theorem_backed_true_rules,
)
from graph import ImplicationGraph
from laws import load_law_catalog
from proof_catalog import build_constructive_proof_catalog
from public_benchmark import PublicProblem


def _write_catalog(tmp_path: Path, equations: list[str]):
    path = tmp_path / "equations.txt"
    path.write_text("\n".join(equations) + "\n", encoding="utf-8")
    return load_law_catalog(path)


def _write_constructive_catalog(tmp_path: Path, extra_equations: list[str]):
    equations = [
        "x = y ◇ (z ◇ ((w ◇ u) ◇ x))",
        "x = (y ◇ y) ◇ (y ◇ (z ◇ x))",
        "x = ((y ◇ x) ◇ y) ◇ (z ◇ z)",
        "x = (y ◇ (z ◇ (x ◇ w))) ◇ x",
        "x = (y ◇ (z ◇ (z ◇ x))) ◇ x",
        "x = (y ◇ (z ◇ (z ◇ x))) ◇ y",
        "x = (((x ◇ x) ◇ y) ◇ z) ◇ y",
        "x ◇ x = (y ◇ (z ◇ z)) ◇ z",
        "x ◇ x = ((y ◇ x) ◇ x) ◇ z",
        "x ◇ (y ◇ z) = y ◇ (w ◇ u)",
        "x ◇ y = z ◇ y",
        "x = x ◇ (((y ◇ z) ◇ y) ◇ z)",
        "x ◇ y = x ◇ (x ◇ y)",
        "x = (y ◇ ((z ◇ x) ◇ x)) ◇ x",
        "x = (x ◇ y) ◇ y",
        "x ◇ y = x ◇ z",
        "x ◇ x = (x ◇ (y ◇ y)) ◇ z",
        "x ◇ x = ((y ◇ z) ◇ z) ◇ w",
        "x ◇ (y ◇ z) = w ◇ (u ◇ v)",
        "x = y ◇ (y ◇ ((x ◇ z) ◇ z))",
        "x ◇ y = y ◇ ((x ◇ z) ◇ z)",
        "x ◇ y = y ◇ x",
        "x = ((y ◇ z) ◇ x) ◇ (z ◇ y)",
        "x ◇ (x ◇ y) = (y ◇ z) ◇ z",
    ]
    return _write_catalog(tmp_path, equations + extra_equations)


def test_theorem_backed_true_rules_counts_contextual_instances_without_substitution(
    tmp_path: Path,
) -> None:
    source = "x * y = y * x"
    target = "z * (x * y) = z * (y * x)"
    catalog = _write_catalog(tmp_path, [source, target])
    problem = PublicProblem(
        problem_id="contextual_only",
        index=0,
        difficulty="normal",
        equation1=source,
        equation2=target,
        answer=True,
        equation1_id=1,
        equation2_id=2,
        graph_status=3,
        graph_status_name="explicit_proof_true",
    )

    rules = _theorem_backed_true_rules(catalog, [problem])
    substitution_rule = cast(dict[str, object], rules["substitution_instance_rule"])
    one_hole_rule = cast(dict[str, object], rules["one_hole_context_rule"])
    combined_cover = cast(dict[str, object], rules["combined_true_rule_cover"])

    assert substitution_rule["public_true_count"] == 0
    assert one_hole_rule["public_true_count"] == 1
    assert combined_cover["public_true_count"] == 1


def test_public_pair_duplicates_reports_unique_pairs_and_multiplicity() -> None:
    problems = [
        PublicProblem(
            problem_id="a",
            index=0,
            difficulty="normal",
            equation1="x = y",
            equation2="x = z",
            answer=False,
            equation1_id=1,
            equation2_id=2,
            graph_status=2,
            graph_status_name="explicit_proof_false",
        ),
        PublicProblem(
            problem_id="b",
            index=1,
            difficulty="hard",
            equation1="x = y",
            equation2="x = z",
            answer=False,
            equation1_id=1,
            equation2_id=2,
            graph_status=2,
            graph_status_name="explicit_proof_false",
        ),
        PublicProblem(
            problem_id="c",
            index=2,
            difficulty="normal",
            equation1="x = y",
            equation2="x = w",
            answer=True,
            equation1_id=1,
            equation2_id=3,
            graph_status=3,
            graph_status_name="explicit_proof_true",
        ),
    ]

    duplicates = _public_pair_duplicates(problems)

    assert duplicates == {
        "unique_pair_count": 2,
        "duplicate_instance_count": 1,
        "repeated_pair_type_count": 1,
        "max_pair_multiplicity": 2,
    }


def test_canonical_equivalent_law_id_prefers_smallest_sort_key(tmp_path: Path) -> None:
    catalog = _write_catalog(
        tmp_path,
        [
            "x = x",
            "x = y",
            "x = y * z",
        ],
    )
    graph = ImplicationGraph(
        law_count=3,
        statuses=bytes(
            [
                3, 2, 2,
                2, 3, 3,
                2, 3, 3,
            ]
        ),
        equivalence_classes=(),
    )

    assert _canonical_equivalent_law_id(catalog, graph, 3) == 2


def test_kernel_micro_rewrite_candidate_surface_adds_tail_cover() -> None:
    surface = _kernel_micro_rewrite_candidate_surface(
        kernel_bridge_candidate_surface={
            "decided_problem_count": 1177,
            "remaining_problem_count": 23,
            "remaining_true_problem_count": 2,
            "remaining_false_problem_count": 21,
        },
        kernel_micro_rewrite_analysis={
            "covered_public_problem_count": 2,
        },
    )

    assert surface == {
        "decided_problem_count": 1179,
        "decided_problem_rate": 0.9825,
        "remaining_problem_count": 21,
        "remaining_true_problem_count": 0,
        "remaining_false_problem_count": 21,
    }


def test_kernel_bridge_analysis_uses_only_explicit_source_rules(tmp_path: Path) -> None:
    target = "a ◇ (b ◇ c) = d ◇ (b ◇ c)"
    catalog = _write_constructive_catalog(tmp_path, [target])
    proof_catalog = build_constructive_proof_catalog(catalog)
    source_id = catalog.lookup_id("x = y ◇ (z ◇ ((w ◇ u) ◇ x))")
    target_id = catalog.lookup_id(target)

    analysis = _kernel_bridge_analysis(
        catalog=catalog,
        combined_decision_surface={
            "remaining_true_cases": [
                {
                    "problem_id": "bridge_case",
                    "equation1_id": source_id,
                    "equation2_id": target_id,
                    "equation1": catalog.law_text(source_id),
                    "equation2": target,
                }
            ]
        },
        proof_catalog=proof_catalog,
    )

    assert analysis["covered_public_problem_count"] == 1
    assert analysis["covered_unique_pair_count"] == 1
    pair_bridge = cast(list[dict[str, object]], analysis["pair_bridges"])[0]
    kernel = cast(list[dict[str, object]], pair_bridge["kernels"])[0]
    assert kernel["source_rule"] == "exact_source_match"
    assert kernel["equation"] == "x ◇ y = z ◇ y"


def test_kernel_micro_rewrite_analysis_reports_unique_pair_and_match_counts(
    tmp_path: Path,
) -> None:
    target_one = "x ◇ y = y ◇ ((z ◇ x) ◇ z)"
    target_two = "(x ◇ y) ◇ x = (y ◇ z) ◇ z"
    catalog = _write_constructive_catalog(tmp_path, [target_one, target_two])
    proof_catalog = build_constructive_proof_catalog(catalog)
    source_one = catalog.lookup_id("x = y ◇ (y ◇ ((x ◇ z) ◇ z))")
    source_two = catalog.lookup_id("x = ((y ◇ z) ◇ x) ◇ (z ◇ y)")
    target_one_id = catalog.lookup_id(target_one)
    target_two_id = catalog.lookup_id(target_two)

    analysis = _kernel_micro_rewrite_analysis(
        catalog=catalog,
        kernel_bridge_analysis={
            "remaining_true_problem_count": 2,
            "covered_public_problem_count": 0,
            "uncovered_pairs": [
                {
                    "equation1_id": source_one,
                    "equation2_id": target_one_id,
                    "problem_ids": ["rewrite_one"],
                    "source_equation": catalog.law_text(source_one),
                    "target_equation": target_one,
                },
                {
                    "equation1_id": source_two,
                    "equation2_id": target_two_id,
                    "problem_ids": ["rewrite_two"],
                    "source_equation": catalog.law_text(source_two),
                    "target_equation": target_two,
                },
            ],
        },
        proof_catalog=proof_catalog,
    )

    assert analysis["covered_public_problem_count"] == 2
    assert analysis["covered_unique_pair_count"] == 2
    top_helper = cast(list[dict[str, object]], analysis["top_helpers"])[0]
    assert top_helper["equation"] == "x ◇ y = y ◇ x"
    assert top_helper["covered_unique_pair_count"] == 2
    assert top_helper["covered_match_count"] == 2
