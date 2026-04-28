from __future__ import annotations

from types import SimpleNamespace

import click
import pytest


def _base_args(*, backend):
    # Minimal args object for `wonton._validate_backend_args`.
    return SimpleNamespace(
        backend=backend,
        theorem=None,
        theorem_file=None,
        source=None,
        limit=None,
        sample=None,
        seed=None,
        wild_only=False,
        with_interventions=False,
        trace_mcts=False,
        no_trace_mcts=False,
    )


@pytest.mark.parametrize(
    ("validator_name", "backend_name", "attrs", "message"),
    [
        (
            "_validate_backend_args",
            "z3",
            {"domains": ["arith"]},
            "--domains is not valid for --backend z3",
        ),
        (
            "_validate_backend_args",
            "z3",
            {"sample": 10},
            "--seed is required when --sample is set",
        ),
        (
            "_validate_backend_args",
            "z3",
            {"sample": 10, "seed": 123, "limit": 5},
            "Use --sample or --limit, not both",
        ),
        (
            "_validate_backend_args",
            "lean",
            {},
            "`run --backend lean` is unsupported",
        ),
        (
            "_validate_lean_args",
            "lean",
            {"sample": 10},
            "--seed is required when --sample is set",
        ),
        (
            "_validate_lean_args",
            "lean",
            {"sample": 10, "seed": 123, "limit": 5},
            "Use --sample or --limit, not both",
        ),
        (
            "_validate_lean_args",
            "lean",
            {"trace_mcts": True, "no_trace_mcts": True},
            "--trace-mcts and --no-trace-mcts are mutually exclusive",
        ),
    ],
)
def test_validate_args_reports_invalid_option_combinations(
    validator_name: str,
    backend_name: str,
    attrs: dict[str, object],
    message: str,
    capsys,
) -> None:
    import wonton
    from wonton import Backend

    args = _base_args(backend=getattr(Backend, backend_name))
    for name, value in attrs.items():
        setattr(args, name, value)

    with pytest.raises(click.exceptions.Exit) as excinfo:
        getattr(wonton, validator_name)(args)
    assert excinfo.value.exit_code == 1

    captured = capsys.readouterr()
    assert message in captured.err
