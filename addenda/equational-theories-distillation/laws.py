from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from syntax import (
    Equation,
    EquationFeatures,
    extract_features,
    parse_equation,
)


def normalize_equation_text(text: str) -> str:
    return " ".join(text.replace("*", "◇").split())


@dataclass(frozen=True)
class LawCatalog:
    equations: tuple[str, ...]
    parsed_equations: tuple[Equation, ...]
    features: tuple[EquationFeatures, ...]
    equation_to_id: dict[str, int]

    def law_text(self, law_id: int) -> str:
        return self.equations[law_id - 1]

    def law_features(self, law_id: int) -> EquationFeatures:
        return self.features[law_id - 1]

    def law_equation(self, law_id: int) -> Equation:
        return self.parsed_equations[law_id - 1]

    def lookup_id(self, equation_text: str) -> int:
        normalized = normalize_equation_text(equation_text)
        try:
            return self.equation_to_id[normalized]
        except KeyError as error:
            raise KeyError(f"equation not found in law catalog: {equation_text}") from error


def load_law_catalog(path: Path) -> LawCatalog:
    equations = tuple(
        normalize_equation_text(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    parsed = tuple(parse_equation(text) for text in equations)
    features = tuple(extract_features(equation) for equation in parsed)
    lookup = {text: index + 1 for index, text in enumerate(equations)}
    return LawCatalog(
        equations=equations,
        parsed_equations=parsed,
        features=features,
        equation_to_id=lookup,
    )
