from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from atp.proof_objects import ProofObjectEdge, ProofObjectGraph, ProofObjectNode

PSEUDO_PARENTS = {
    "skolem_symbol_introduction",
    "avatar_definition",
}
BASE_ROLES = {
    "axiom",
    "hypothesis",
    "negated_conjecture",
    "conjecture",
    "lemma",
    "theorem",
    "definition",
}
SIMPLIFY_RULES = {
    "fof_simplification",
    "cnf_simplification",
}
PREPROCESS_RULES = SIMPLIFY_RULES | {
    "assume_negation",
    "variable_rename",
    "split_conjunct",
    "fof_nnf",
}


def _is_ephemeral_parent(name: str) -> bool:
    if not name.startswith("c_0_-"):
        return False
    return name[len("c_0_-") :].isdigit()


@dataclass(frozen=True)
class TstpStep:
    name: str
    role: str
    formula: str
    rule: str
    parents: list[str]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _tokenize_formula(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            j = i + 1
            while j < len(text):
                if text[j] == "'" and (j + 1 >= len(text) or text[j + 1] != "'"):
                    j += 1
                    break
                if text[j] == "'" and text[j + 1] == "'":
                    j += 2
                    continue
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if ch == "-" and i + 1 < len(text) and text[i + 1].isdigit():
            j = i + 1
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if ch.isalnum() or ch in {"_", "$"}:
            j = i + 1
            while j < len(text) and (text[j].isalnum() or text[j] in {"_", "$"}):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if text.startswith("~|", i):
            tokens.append("~|")
            i += 2
            continue
        if text.startswith("~&", i):
            tokens.append("~&")
            i += 2
            continue
        if text.startswith("<=>", i):
            tokens.append("<=>")
            i += 3
            continue
        if text.startswith("<~>", i):
            tokens.append("<~>")
            i += 3
            continue
        if text.startswith("=>", i):
            tokens.append("=>")
            i += 2
            continue
        if text.startswith("<=", i):
            tokens.append("<=")
            i += 2
            continue
        if text.startswith("!=", i):
            tokens.append("!=")
            i += 2
            continue
        tokens.append(ch)
        i += 1
    return tokens


def _is_variable_token(token: str) -> bool:
    if not token:
        return False
    if token[0] == "'":
        return False
    if token == "_":
        return True
    if token[0].isupper():
        return True
    if token[0] == "_" and token[1:].replace("_", "").isalnum():
        return True
    return False


@dataclass(frozen=True)
class Term:
    name: str
    args: tuple["Term", ...] = ()
    is_var: bool = False


@dataclass(frozen=True)
class Formula:
    kind: str
    args: tuple["Formula", ...] = ()
    term_args: tuple[Term, ...] = ()
    quant_vars: tuple[str, ...] = ()
    atom_name: str | None = None


class _TokenStream:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def consume(self) -> str:
        if self.index >= len(self.tokens):
            raise ValueError("Unexpected end of tokens")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def match(self, value: str) -> bool:
        if self.peek() == value:
            self.consume()
            return True
        return False


def _parse_term(stream: _TokenStream) -> Term:
    token = stream.peek()
    if token is None:
        raise ValueError("Expected term, got end of input")
    if token == "(":
        stream.consume()
        term = _parse_term(stream)
        if not stream.match(")"):
            raise ValueError("Expected ')' after term")
        return term
    token = stream.consume()
    if _is_variable_token(token):
        if stream.peek() == "(":
            raise ValueError(f"Variable used as function: {token}")
        return Term(name=token, is_var=True)
    if stream.match("("):
        args: list[Term] = []
        if not stream.match(")"):
            while True:
                args.append(_parse_term(stream))
                if stream.match(")"):
                    break
                if not stream.match(","):
                    raise ValueError("Expected ',' in term arguments")
        return Term(name=token, args=tuple(args))
    return Term(name=token)


def _parse_quantifier(stream: _TokenStream) -> Formula:
    quant = stream.consume()
    if not stream.match("["):
        raise ValueError("Expected '[' after quantifier")
    vars_list: list[str] = []
    if not stream.match("]"):
        while True:
            token = stream.consume()
            if not _is_variable_token(token):
                raise ValueError(f"Expected variable in quantifier list, got {token}")
            vars_list.append(token)
            if stream.match(":"):
                _skip_type_annotation(stream)
            if stream.match("]"):
                break
            if not stream.match(","):
                raise ValueError("Expected ',' in quantifier list")
    if not stream.match(":"):
        raise ValueError("Expected ':' after quantifier list")
    body = _parse_formula(stream)
    kind = "forall" if quant == "!" else "exists"
    return Formula(kind=kind, args=(body,), quant_vars=tuple(vars_list))


def _parse_atom(stream: _TokenStream) -> Formula:
    if stream.match("("):
        inner = _parse_formula(stream)
        if not stream.match(")"):
            raise ValueError("Expected ')' after formula")
        return inner
    if stream.peek() in {"!", "?"}:
        return _parse_quantifier(stream)
    term = _parse_term(stream)
    next_tok = stream.peek()
    if next_tok in {"=", "!="}:
        op = stream.consume()
        rhs = _parse_term(stream)
        kind = "eq" if op == "=" else "neq"
        return Formula(kind=kind, term_args=(term, rhs))
    if term.is_var:
        raise ValueError(f"Variable used as atom: {term.name}")
    return Formula(kind="atom", atom_name=term.name, term_args=term.args)


def _parse_not(stream: _TokenStream) -> Formula:
    if stream.match("~"):
        child = _parse_not(stream)
        return Formula(kind="not", args=(child,))
    return _parse_atom(stream)


def _parse_and(stream: _TokenStream) -> Formula:
    left = _parse_not(stream)
    while True:
        if stream.match("&"):
            right = _parse_not(stream)
            left = Formula(kind="and", args=(left, right))
            continue
        if stream.match("~&"):
            right = _parse_not(stream)
            left = Formula(kind="not", args=(Formula(kind="and", args=(left, right)),))
            continue
        break
    return left


def _parse_or(stream: _TokenStream) -> Formula:
    left = _parse_and(stream)
    while True:
        if stream.match("|"):
            right = _parse_and(stream)
            left = Formula(kind="or", args=(left, right))
            continue
        if stream.match("~|"):
            right = _parse_and(stream)
            left = Formula(kind="not", args=(Formula(kind="or", args=(left, right)),))
            continue
        break
    return left


def _parse_implies(stream: _TokenStream) -> Formula:
    left = _parse_or(stream)
    while stream.peek() in {"=>", "<=", "<=>", "<~>"}:
        op = stream.consume()
        right = _parse_or(stream)
        if op == "=>":
            left = Formula(kind="imp", args=(left, right))
        elif op == "<=":
            left = Formula(kind="imp", args=(right, left))
        elif op == "<=>":
            left = Formula(kind="iff", args=(left, right))
        else:
            left = Formula(kind="xor", args=(left, right))
    return left


def _parse_formula(stream: _TokenStream) -> Formula:
    return _parse_implies(stream)


def _skip_type_annotation(stream: _TokenStream) -> None:
    depth = 0
    while True:
        token = stream.peek()
        if token is None:
            raise ValueError("Unexpected end while skipping type annotation")
        if depth == 0 and token in {",", "]"}:
            return
        token = stream.consume()
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(depth - 1, 0)


def parse_tptp_formula(text: str) -> Formula:
    tokens = [t for t in _tokenize_formula(text) if t.strip()]
    stream = _TokenStream(tokens)
    formula = _parse_formula(stream)
    if stream.peek() is not None:
        raise ValueError(f"Unexpected token: {stream.peek()}")
    return formula


def _serialize_term(term: Term, var_map: dict[str, str], supply: list[int]) -> str:
    if term.is_var:
        if term.name not in var_map:
            var_map[term.name] = f"V{supply[0]}"
            supply[0] += 1
        return var_map[term.name]
    if not term.args:
        return term.name
    return f"{term.name}({','.join(_serialize_term(arg, var_map, supply) for arg in term.args)})"


def _flatten(kind: str, items: tuple[Formula, ...]) -> list[Formula]:
    flat: list[Formula] = []
    for item in items:
        if item.kind == kind:
            flat.extend(_flatten(kind, item.args))
        else:
            flat.append(item)
    return flat


def _to_nnf(formula: Formula) -> Formula:
    kind = formula.kind
    if kind == "not":
        inner = formula.args[0]
        if inner.kind == "not":
            return _to_nnf(inner.args[0])
        if inner.kind == "and":
            return Formula(
                kind="or",
                args=tuple(_to_nnf(Formula(kind="not", args=(c,))) for c in inner.args),
            )
        if inner.kind == "or":
            return Formula(
                kind="and",
                args=tuple(_to_nnf(Formula(kind="not", args=(c,))) for c in inner.args),
            )
        if inner.kind == "forall":
            return Formula(
                kind="exists",
                quant_vars=inner.quant_vars,
                args=(_to_nnf(Formula(kind="not", args=(inner.args[0],))),),
            )
        if inner.kind == "exists":
            return Formula(
                kind="forall",
                quant_vars=inner.quant_vars,
                args=(_to_nnf(Formula(kind="not", args=(inner.args[0],))),),
            )
        if inner.kind == "imp":
            left, right = inner.args
            return _to_nnf(
                Formula(kind="and", args=(left, Formula(kind="not", args=(right,))))
            )
        if inner.kind == "iff":
            left, right = inner.args
            return _to_nnf(
                Formula(
                    kind="or",
                    args=(
                        Formula(kind="and", args=(left, Formula(kind="not", args=(right,)))),
                        Formula(kind="and", args=(Formula(kind="not", args=(left,)), right)),
                    ),
                )
            )
        if inner.kind == "xor":
            left, right = inner.args
            return _to_nnf(
                Formula(
                    kind="or",
                    args=(
                        Formula(kind="and", args=(left, right)),
                        Formula(
                            kind="and",
                            args=(
                                Formula(kind="not", args=(left,)),
                                Formula(kind="not", args=(right,)),
                            ),
                        ),
                    ),
                )
            )
        if inner.kind == "eq":
            return Formula(kind="neq", term_args=inner.term_args)
        if inner.kind == "neq":
            return Formula(kind="eq", term_args=inner.term_args)
        return Formula(kind="not", args=(_to_nnf(inner),))
    if kind in {"and", "or"}:
        return Formula(kind=kind, args=tuple(_to_nnf(arg) for arg in formula.args))
    if kind == "imp":
        left, right = formula.args
        return _to_nnf(Formula(kind="or", args=(Formula(kind="not", args=(left,)), right)))
    if kind == "iff":
        left, right = formula.args
        return _to_nnf(
            Formula(
                kind="and",
                args=(
                    Formula(kind="imp", args=(left, right)),
                    Formula(kind="imp", args=(right, left)),
                ),
            )
        )
    if kind == "xor":
        left, right = formula.args
        return _to_nnf(
            Formula(
                kind="or",
                args=(
                    Formula(kind="and", args=(left, Formula(kind="not", args=(right,)))),
                    Formula(kind="and", args=(Formula(kind="not", args=(left,)), right)),
                ),
            )
        )
    if kind in {"forall", "exists"}:
        return Formula(kind=kind, quant_vars=formula.quant_vars, args=(_to_nnf(formula.args[0]),))
    return formula


def _serialize_formula(formula: Formula, var_map: dict[str, str], supply: list[int]) -> str:
    kind = formula.kind
    if kind == "atom":
        if not formula.term_args:
            return formula.atom_name or ""
        args = ",".join(_serialize_term(term, var_map, supply) for term in formula.term_args)
        return f"{formula.atom_name}({args})"
    if kind in {"eq", "neq"}:
        left, right = formula.term_args
        left_s = _serialize_term(left, var_map, supply)
        right_s = _serialize_term(right, var_map, supply)
        if left_s > right_s:
            left_s, right_s = right_s, left_s
        op = "=" if kind == "eq" else "!="
        return f"{left_s}{op}{right_s}"
    if kind == "not":
        return f"~{_serialize_formula(formula.args[0], var_map, supply)}"
    if kind in {"and", "or"}:
        flat = _flatten(kind, formula.args)
        parts = [_serialize_formula(item, var_map, supply) for item in flat]
        parts.sort()
        op = "&" if kind == "and" else "|"
        return op.join(parts)
    if kind in {"forall", "exists"}:
        vars_sorted = sorted(formula.quant_vars)
        inner_env = var_map.copy()
        canonical_vars: list[str] = []
        for var in vars_sorted:
            canonical = f"V{supply[0]}"
            supply[0] += 1
            inner_env[var] = canonical
            canonical_vars.append(canonical)
        body = _serialize_formula(formula.args[0], inner_env, supply)
        quant = "!" if kind == "forall" else "?"
        return f"{quant}[{','.join(canonical_vars)}]:{body}"
    raise ValueError(f"Unsupported formula kind: {kind}")


def canonicalize_tptp_formula(formula: str) -> str:
    parsed = parse_tptp_formula(formula)
    nnf = _to_nnf(parsed)
    return _serialize_formula(nnf, {}, [0])


def clause_signature(formula: str) -> str:
    return _hash_text(canonicalize_tptp_formula(formula))


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    bracket_depth = 0
    in_quote = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_quote:
                if i + 1 < len(text) and text[i + 1] == "'":
                    buf.append(ch)
                    buf.append("'")
                    i += 2
                    continue
                in_quote = False
            else:
                in_quote = True
        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth -= 1
            elif ch == "," and depth == 0 and bracket_depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                i += 1
                continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def _extract_statements(text: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quote = False
    capture = False

    i = 0
    while i < len(text):
        if not capture and text.startswith(("fof(", "cnf(", "tff(", "thf(", "tpi(", "tcf("), i):
            capture = True
            buf = []
            depth = 0
            in_quote = False
        ch = text[i]
        if capture:
            if ch == "'":
                if in_quote:
                    if i + 1 < len(text) and text[i + 1] == "'":
                        buf.append(ch)
                        buf.append("'")
                        i += 2
                        continue
                    in_quote = False
                else:
                    in_quote = True
            buf.append(ch)
            if not in_quote:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "." and depth == 0:
                    statements.append("".join(buf).strip())
                    buf = []
                    capture = False
                    depth = 0
                    in_quote = False
        i += 1
    return statements


def _parse_parent_list(field: str) -> list[str]:
    field = field.strip()
    if not (field.startswith("[") and field.endswith("]")):
        return []
    content = field[1:-1].strip()
    if not content:
        return []
    parents: list[str] = []
    for item in _split_top_level(content):
        item = item.strip()
        if not item:
            continue
        if item.startswith("inference(") or item.startswith("introduced("):
            _, nested = _parse_source(item)
            parents.extend(nested)
            continue
        parents.append(item)
    return parents


def _parse_source(field: str) -> tuple[str, list[str]]:
    field = field.strip()
    if field.startswith("inference("):
        inner = field[len("inference(") :].rstrip(")")
        parts = _split_top_level(inner)
        rule = parts[0].strip() if parts else "inference"
        parents: list[str] = []
        if len(parts) >= 3:
            parents = _parse_parent_list(parts[2])
        return rule, parents
    if field.startswith("introduced("):
        inner = field[len("introduced(") :].rstrip(")")
        parts = _split_top_level(inner)
        rule = parts[0].strip() if parts else "introduced"
        parents: list[str] = []
        if len(parts) >= 3:
            parents = _parse_parent_list(parts[2])
        return f"introduced:{rule}", parents
    if field.startswith(("file(", "theory(")):
        return "input", []
    return "input", []


def _parse_statement(statement: str) -> TstpStep | None:
    stmt = statement.strip()
    if not stmt.endswith("."):
        return None
    stmt = stmt[:-1].strip()
    if not (
        stmt.startswith("fof(")
        or stmt.startswith("cnf(")
        or stmt.startswith("tff(")
        or stmt.startswith("thf(")
        or stmt.startswith("tpi(")
        or stmt.startswith("tcf(")
    ):
        return None
    if "(" not in stmt or ")" not in stmt:
        return None
    inner = stmt[stmt.find("(") + 1 : stmt.rfind(")")]
    fields = _split_top_level(inner)
    if len(fields) < 3:
        return None
    name = fields[0]
    role = fields[1]
    formula = fields[2]
    rule = "input"
    parents: list[str] = []
    if len(fields) >= 4:
        rule, parents = _parse_source(fields[3])
    parents = [parent for parent in parents if parent not in PSEUDO_PARENTS]
    return TstpStep(name=name, role=role, formula=formula, rule=rule, parents=parents)


def parse_tstp(text: str) -> list[TstpStep]:
    statements = _extract_statements(text)
    steps: list[TstpStep] = []
    for statement in statements:
        step = _parse_statement(statement)
        if step is not None:
            steps.append(step)
    return steps


def _resolve_missing_parents(steps: list[TstpStep]) -> list[TstpStep]:
    node_names = {step.name for step in steps}
    input_by_formula: dict[str, list[str]] = {}
    for step in steps:
        if step.role in BASE_ROLES:
            key = canonicalize_tptp_formula(step.formula)
            input_by_formula.setdefault(key, []).append(step.name)

    resolved: list[TstpStep] = []
    for step in steps:
        parents: list[str] = []
        missing: list[str] = []
        for parent in step.parents:
            if parent in node_names:
                parents.append(parent)
                continue
            if parent in PSEUDO_PARENTS or _is_ephemeral_parent(parent):
                continue
            missing.append(parent)
        if missing and step.rule in PREPROCESS_RULES:
            key = canonicalize_tptp_formula(step.formula)
            matches = input_by_formula.get(key, [])
            candidates = [name for name in matches if name != step.name]
            if len(candidates) == 1 and candidates[0] not in parents:
                parents.append(candidates[0])
                missing = []
            elif matches:
                missing = []
        parents.extend(missing)
        resolved.append(
            TstpStep(
                name=step.name,
                role=step.role,
                formula=step.formula,
                rule=step.rule,
                parents=parents,
            )
        )
    return resolved


def _validate_parents(steps: list[TstpStep]) -> None:
    node_names = {step.name for step in steps}
    missing: dict[str, list[str]] = {}
    for step in steps:
        for parent in step.parents:
            if parent in PSEUDO_PARENTS:
                continue
            if _is_ephemeral_parent(parent):
                continue
            if parent not in node_names:
                missing.setdefault(step.name, []).append(parent)
    if missing:
        sample = list(missing.items())[:5]
        details = "; ".join(f"{name}: {parents}" for name, parents in sample)
        raise ValueError(f"Missing parent steps in TSTP: {details}")


def _assign_depths(steps: list[TstpStep]) -> dict[str, int]:
    parents_map: dict[str, list[str]] = {step.name: step.parents for step in steps}
    depths: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(name: str) -> int:
        if name in depths:
            return depths[name]
        if name in visiting:
            raise ValueError(f"Cycle detected in TSTP proof graph at {name}")
        visiting.add(name)
        parents = parents_map.get(name, [])
        if not parents:
            depths[name] = 0
        else:
            depths[name] = 1 + max(visit(parent) for parent in parents)
        visiting.remove(name)
        return depths[name]

    for step in steps:
        visit(step.name)
    return depths


def steps_to_graph(steps: Iterable[TstpStep]) -> ProofObjectGraph:
    step_list = _resolve_missing_parents(list(steps))
    _validate_parents(step_list)
    depths = _assign_depths(step_list)
    nodes: list[ProofObjectNode] = []
    edges: list[ProofObjectEdge] = []

    for step in step_list:
        nodes.append(
            ProofObjectNode(
                node_id=step.name,
                goal_sig=_hash_text(step.formula),
                goal_type=step.formula,
                depth=depths.get(step.name, 0),
                attrs={"role": step.role},
            )
        )

    order = 0
    for step in step_list:
        for parent in step.parents:
            order += 1
            edges.append(
                ProofObjectEdge(
                    source=parent,
                    target=step.name,
                    rule=step.rule,
                    order=order,
                )
            )

    return ProofObjectGraph(nodes=nodes, edges=edges)
