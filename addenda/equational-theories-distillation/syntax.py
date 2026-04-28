import re
from collections import Counter
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[A-Za-z]+|[()*◇=]")


@dataclass(frozen=True)
class Variable:
    name: str


@dataclass(frozen=True)
class Binary:
    left: "Term"
    right: "Term"


Term = Variable | Binary


@dataclass(frozen=True)
class Equation:
    left: Term
    right: Term


@dataclass(frozen=True)
class EquationFeatures:
    canonical: str
    shape: str
    distinct_variables: int
    variable_multiplicity: tuple[int, ...]
    operation_count: int
    depth: int
    leaf_pattern: tuple[int, ...]
    left_shape: str
    right_shape: str
    left_operation_count: int
    right_operation_count: int


def leftmost_variable_name(term: Term) -> str:
    cursor = term
    while isinstance(cursor, Binary):
        cursor = cursor.left
    return cursor.name


def count_variable_occurrences(term: Term, name: str) -> int:
    if isinstance(term, Variable):
        return int(term.name == name)
    return count_variable_occurrences(term.left, name) + count_variable_occurrences(
        term.right,
        name,
    )


class _TokenStream:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._index = 0

    def peek(self) -> str | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def pop(self) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of equation")
        self._index += 1
        return token


def parse_equation(text: str) -> Equation:
    tokens = TOKEN_RE.findall(text.replace("*", "◇"))
    if not tokens:
        raise ValueError("equation is empty")
    stream = _TokenStream(tokens)
    left = _parse_term(stream)
    if stream.pop() != "=":
        raise ValueError(f"expected '=', got {stream.peek()!r}")
    right = _parse_term(stream)
    if stream.peek() is not None:
        raise ValueError(f"unexpected trailing token {stream.peek()!r}")
    return Equation(left=left, right=right)


def _parse_term(stream: _TokenStream) -> Term:
    term = _parse_atom(stream)
    while stream.peek() == "◇":
        stream.pop()
        term = Binary(left=term, right=_parse_atom(stream))
    return term


def _parse_atom(stream: _TokenStream) -> Term:
    token = stream.pop()
    if token == "(":
        nested = _parse_term(stream)
        if stream.pop() != ")":
            raise ValueError("expected ')'")
        return nested
    if token in {"=", "◇", ")"}:
        raise ValueError(f"unexpected token {token!r}")
    return Variable(name=token)


def extract_features(equation: Equation) -> EquationFeatures:
    names: dict[str, int] = {}
    leaf_pattern = tuple(_leaf_pattern(equation, names))
    ordered_names = {name: index for index, name in enumerate(names)}
    counts = Counter(_variable_names(equation))
    multiplicity = tuple(sorted(counts.values(), reverse=True))
    return EquationFeatures(
        canonical=_canonical_equation(equation),
        shape=f"{_shape(equation.left)} = {_shape(equation.right)}",
        distinct_variables=len(ordered_names),
        variable_multiplicity=multiplicity,
        operation_count=_operation_count(equation.left) + _operation_count(equation.right),
        depth=max(_depth(equation.left), _depth(equation.right)),
        leaf_pattern=leaf_pattern,
        left_shape=_shape(equation.left),
        right_shape=_shape(equation.right),
        left_operation_count=_operation_count(equation.left),
        right_operation_count=_operation_count(equation.right),
    )


def _canonical_equation(equation: Equation) -> str:
    mapping: dict[str, str] = {}
    return f"{_canonical_term(equation.left, mapping)} = {_canonical_term(equation.right, mapping)}"


def _canonical_term(term: Term, mapping: dict[str, str]) -> str:
    if isinstance(term, Variable):
        if term.name not in mapping:
            mapping[term.name] = f"v{len(mapping)}"
        return mapping[term.name]
    return f"({_canonical_term(term.left, mapping)} ◇ {_canonical_term(term.right, mapping)})"


def _shape(term: Term) -> str:
    if isinstance(term, Variable):
        return "v"
    return f"({_shape(term.left)} ◇ {_shape(term.right)})"


def _operation_count(term: Term) -> int:
    if isinstance(term, Variable):
        return 0
    return 1 + _operation_count(term.left) + _operation_count(term.right)


def _depth(term: Term) -> int:
    if isinstance(term, Variable):
        return 0
    return 1 + max(_depth(term.left), _depth(term.right))


def _leaf_pattern(equation: Equation, names: dict[str, int]) -> list[int]:
    return _leaf_pattern_term(equation.left, names) + _leaf_pattern_term(equation.right, names)


def _leaf_pattern_term(term: Term, names: dict[str, int]) -> list[int]:
    if isinstance(term, Variable):
        names.setdefault(term.name, len(names))
        return [names[term.name]]
    return _leaf_pattern_term(term.left, names) + _leaf_pattern_term(term.right, names)


def _variable_names(equation: Equation) -> list[str]:
    return _variable_names_term(equation.left) + _variable_names_term(equation.right)


def _variable_names_term(term: Term) -> list[str]:
    if isinstance(term, Variable):
        return [term.name]
    return _variable_names_term(term.left) + _variable_names_term(term.right)
