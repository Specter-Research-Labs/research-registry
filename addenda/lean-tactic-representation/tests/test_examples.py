from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

from cli import main
from core.engine import execute_program
from examples.catalog import get_examples


def test_all_examples_execute_with_passing_invariants() -> None:
    for example in get_examples().values():
        node = execute_program(example.program, example.root, example.rules)
        assert node.final_type == example.root.target
        _assert_all_invariants_pass(node)


def test_coupled_example_exposes_shared_metavariable() -> None:
    example = get_examples()["apply_coupled_pack"]
    node = execute_program(example.program, example.root, example.rules)
    assert node.optic_step.decomposition.coupling.kind == "coupled"
    assert node.optic_step.decomposition.coupling.shared_metavars == ("?w",)


def test_independent_examples_report_independent_branching() -> None:
    for name in ("constructor_and", "apply_mk_pair"):
        example = get_examples()[name]
        node = execute_program(example.program, example.root, example.rules)
        assert node.optic_step.decomposition.coupling.kind == "independent"


def test_cli_check_json_has_no_failures() -> None:
    stdout = StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["check", "nested_constructor_apply", "--format", "json"])
    rendered = stdout.getvalue()
    assert exit_code == 0
    assert '"failed_count": 0' in rendered


def _assert_all_invariants_pass(node) -> None:
    for invariant in node.invariants:
        assert invariant.passed, invariant
    for child in node.child_nodes:
        _assert_all_invariants_pass(child)
