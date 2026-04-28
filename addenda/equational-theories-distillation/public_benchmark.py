from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from graph import ImplicationGraph
from laws import LawCatalog


@dataclass(frozen=True)
class PublicProblem:
    problem_id: str
    index: int
    difficulty: str
    equation1: str
    equation2: str
    answer: bool
    equation1_id: int
    equation2_id: int
    graph_status: int
    graph_status_name: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_public_problems(
    normal_path: Path,
    hard_path: Path,
    catalog: LawCatalog,
    graph: ImplicationGraph,
) -> list[PublicProblem]:
    rows = _load_jsonl(normal_path) + _load_jsonl(hard_path)
    problems: list[PublicProblem] = []
    for row in rows:
        equation1 = cast(str, row["equation1"])
        equation2 = cast(str, row["equation2"])
        equation1_id = catalog.lookup_id(equation1)
        equation2_id = catalog.lookup_id(equation2)
        graph_status = graph.status(equation1_id, equation2_id)
        problems.append(
            PublicProblem(
                problem_id=cast(str, row["id"]),
                index=cast(int, row["index"]),
                difficulty=cast(str, row["difficulty"]),
                equation1=equation1,
                equation2=equation2,
                answer=bool(row["answer"]),
                equation1_id=equation1_id,
                equation2_id=equation2_id,
                graph_status=graph_status,
                graph_status_name=graph.status_name(equation1_id, equation2_id),
            )
        )
    return problems


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
