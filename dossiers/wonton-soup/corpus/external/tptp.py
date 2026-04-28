from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TptpProblem:
    name: str
    path: Path


def list_tptp_problems(
    root: Path,
    domains: list[str] | None = None,
    limit: int | None = None,
) -> list[TptpProblem]:
    if not root.exists():
        raise FileNotFoundError(f"TPTP root not found: {root}")

    if domains:
        domain_dirs = [root / domain for domain in domains]
        for domain_dir in domain_dirs:
            if not domain_dir.exists():
                raise FileNotFoundError(f"TPTP domain not found: {domain_dir}")
        search_roots = domain_dirs
    else:
        search_roots = [root]

    problems: list[TptpProblem] = []
    for base in search_roots:
        for path in sorted(base.rglob("*.p")):
            name = path.stem
            problems.append(TptpProblem(name=name, path=path))
            if limit is not None and len(problems) >= limit:
                return problems

    return problems
