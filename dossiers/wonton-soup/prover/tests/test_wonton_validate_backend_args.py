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
    )


@pytest.mark.parametrize(
    ("validator_name", "backend_name", "attrs", "message"),
    [
        (
            "_validate_backend_args",
            "coq",
            {"limit": 5},
            "--limit is not valid for --backend coq",
        ),
        (
            "_validate_backend_args",
            "coq",
            {"sample": 10},
            "--seed is required when --sample is set",
        ),
        (
            "_validate_backend_args",
            "lean",
            {},
            "`run --backend lean` is unsupported",
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
