from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SmtlibProblem:
    name: str
    path: Path


def list_smtlib_problems(
    root: Path,
    limit: int | None = None,
) -> list[SmtlibProblem]:
    if not root.exists():
        raise FileNotFoundError(f"SMT-LIB root not found: {root}")

    problems: list[SmtlibProblem] = []
    for path in sorted(root.rglob("*.smt2")):
        rel = path.relative_to(root).with_suffix("")
        name = rel.as_posix()
        problems.append(SmtlibProblem(name=name, path=path))
        if limit is not None and len(problems) >= limit:
            return problems
    return problems
