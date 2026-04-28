from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from analysis.attractors import cluster_proof_structures
from atp.sexp import tokenize_sexpr
from atp.tptp.parser import Formula, Term, parse_tptp_formula
from corpus.external.smtlib import list_smtlib_problems
from corpus.external.tptp import list_tptp_problems
from prover.tree_edit_distance import OrderedTree, tree_edit_distance

DISTANCE_THRESHOLD = 0.25
SAMPLE_SEED = "external_statement_similarity:v1"


def _tree_size(tree: OrderedTree) -> int:
    size = 0
    stack = [tree]
    while stack:
        node = stack.pop()
        size += 1
        stack.extend(node.children)
    return size


def _normalized_distance(a: OrderedTree, b: OrderedTree, size_a: int, size_b: int) -> float:
    denom = size_a + size_b
    return tree_edit_distance(a, b) / denom if denom else 0.0


def _select_sample(names: list[str], sample_size: int) -> tuple[list[str], dict[str, Any]]:
    if sample_size <= 0:
        return [], {"sample_strategy": "empty"}
    if sample_size >= len(names):
        return sorted(names), {"sample_strategy": "all"}
    ranked: list[tuple[str, str]] = []
    for name in names:
        digest = hashlib.sha256((SAMPLE_SEED + name).encode("utf-8")).hexdigest()
        ranked.append((digest, name))
    ranked.sort()
    sample = sorted(name for _, name in ranked[:sample_size])
    return sample, {"sample_strategy": "sha256", "sample_seed": SAMPLE_SEED}


def _resolve_mode(mode: str, n: int, *, max_theorems_full: int, max_knn_theorems: int) -> str:
    if mode == "auto":
        if n <= max_theorems_full:
            return "full"
        if n <= max_knn_theorems:
            return "knn"
        return "sample"
    if mode not in {"full", "knn", "sample"}:
        raise ValueError(f"unknown statement_similarity mode: {mode}")
    return mode


def _tree_hash(tree: OrderedTree) -> bytes:
    memo: dict[int, bytes] = {}
    stack: list[tuple[OrderedTree, int]] = [(tree, 0)]
    while stack:
        node, state = stack.pop()
        node_id = id(node)
        if state == 0:
            if node_id in memo:
                continue
            stack.append((node, 1))
            for child in node.children:
                stack.append((child, 0))
            continue
        h = hashlib.sha256()
        h.update(node.label.encode("utf-8"))
        h.update(b"\x00")
        for child in node.children:
            h.update(memo[id(child)])
            h.update(b"\x00")
        memo[node_id] = h.digest()
    return memo[id(tree)]


def _sort_children_commutative(children: list[OrderedTree]) -> list[OrderedTree]:
    keyed = [(_tree_hash(c), c) for c in children]
    keyed.sort(key=lambda item: item[0])
    return [c for _, c in keyed]


def _term_to_tree(term: Term) -> OrderedTree:
    if term.is_var:
        return OrderedTree("var", ())
    if not term.args:
        return OrderedTree(term.name, ())
    children = [_term_to_tree(t) for t in term.args]
    return OrderedTree(term.name, tuple(children))


def _formula_to_tree(formula: Formula) -> OrderedTree:
    kind = formula.kind
    if kind == "atom":
        args = tuple(_term_to_tree(t) for t in formula.term_args)
        name = formula.atom_name or "atom"
        return OrderedTree(name, args)
    if kind in {"eq", "neq"}:
        children = [_term_to_tree(t) for t in formula.term_args]
        if kind == "eq":
            children = _sort_children_commutative(children)
        return OrderedTree(kind, tuple(children))
    if kind in {"and", "or", "iff", "xor"}:
        children = [_formula_to_tree(c) for c in formula.args]
        children = _sort_children_commutative(children)
        return OrderedTree(kind, tuple(children))
    if kind in {"not", "imp", "forall", "exists"}:
        children = [_formula_to_tree(c) for c in formula.args]
        if kind in {"forall", "exists"} and formula.quant_vars:
            # Normalize away variable names but keep arity.
            children = [OrderedTree(f"{kind}_vars:{len(formula.quant_vars)}", ())] + children
        return OrderedTree(kind, tuple(children))
    children = [_formula_to_tree(c) for c in formula.args]
    return OrderedTree(kind, tuple(children))


_TPTP_STMT_RE = re.compile(r"^(fof|cnf)\s*\(", re.IGNORECASE)


def _iter_tptp_statements(text: str) -> Iterable[str]:
    lines = []
    for raw in text.splitlines():
        if "%" in raw:
            raw = raw.split("%", 1)[0]
        stripped = raw.strip()
        if stripped:
            lines.append(stripped)
    blob = " ".join(lines)

    i = 0
    while i < len(blob):
        m = _TPTP_STMT_RE.search(blob, i)
        if not m:
            return
        start = m.start()
        j = m.end() - 1
        depth = 0
        in_quote = False
        while j < len(blob):
            ch = blob[j]
            if ch == "'" and (j == 0 or blob[j - 1] != "\\"):
                in_quote = not in_quote
            if not in_quote:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(depth - 1, 0)
                    if depth == 0:
                        k = j + 1
                        while k < len(blob) and blob[k].isspace():
                            k += 1
                        if k < len(blob) and blob[k] == ".":
                            yield blob[start : k + 1]
                            i = k + 1
                            break
            j += 1
        else:
            return


def _split_top_level_commas(payload: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_quote = False
    buf: list[str] = []
    for ch in payload:
        if ch == "'" and (not buf or buf[-1] != "\\"):
            in_quote = not in_quote
        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(depth - 1, 0)
            elif ch == "," and depth == 0:
                part = "".join(buf).strip()
                parts.append(part)
                buf = []
                continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_tptp_problem_tree(path: Path) -> tuple[OrderedTree | None, int]:
    text = path.read_text(errors="replace")
    formulas: list[Formula] = []
    conjectures: list[Formula] = []
    parse_failures = 0
    for stmt in _iter_tptp_statements(text):
        head = stmt.split("(", 1)[0].strip().lower()
        inner = stmt[len(head) + 1 :].strip()
        if inner.endswith(")."):
            inner = inner[:-2]
        args = _split_top_level_commas(inner)
        if len(args) < 3:
            continue
        role = args[1].strip().lower()
        formula_txt = args[2].strip()
        try:
            f = parse_tptp_formula(formula_txt)
        except Exception:
            parse_failures += 1
            continue
        formulas.append(f)
        if role in {"conjecture", "negated_conjecture"}:
            conjectures.append(f)
    chosen = conjectures if conjectures else formulas
    if not chosen:
        return None, parse_failures
    children = [_formula_to_tree(f) for f in chosen]
    return OrderedTree("tptp_problem", tuple(children)), parse_failures


def _parse_many_sexprs(text: str) -> list[Any]:
    tokens = tokenize_sexpr(text)
    out: list[Any] = []
    stack: list[list[Any]] = []
    for tok in tokens:
        if tok == "(":
            stack.append([])
            continue
        if tok == ")":
            if not stack:
                raise ValueError("unbalanced parentheses")
            expr = stack.pop()
            if stack:
                stack[-1].append(expr)
            else:
                out.append(expr)
            continue
        if stack:
            stack[-1].append(tok)
        else:
            out.append(tok)
    if stack:
        raise ValueError("unbalanced parentheses")
    return out


_COMMUTATIVE_SMT = {"and", "or", "+", "*", "=", "xor"}


def _smt_expr_to_tree(expr: Any) -> OrderedTree:
    if not isinstance(expr, list):
        s = str(expr)
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return OrderedTree("lit", ())
        if s.startswith("\"") and s.endswith("\""):
            return OrderedTree("lit", ())
        return OrderedTree(s, ())

    if not expr:
        return OrderedTree("empty", ())

    head = expr[0]
    label = str(head)
    children = [_smt_expr_to_tree(x) for x in expr[1:]]
    if label in _COMMUTATIVE_SMT:
        children = _sort_children_commutative(children)
    return OrderedTree(label, tuple(children))


def _extract_smtlib_problem_tree(path: Path) -> tuple[OrderedTree | None, int]:
    text = path.read_text(errors="replace")
    try:
        forms = _parse_many_sexprs(text)
    except Exception:
        return None, 0
    asserts: list[OrderedTree] = []
    for form in forms:
        if not isinstance(form, list) or not form:
            continue
        head = form[0]
        if head == "assert" and len(form) >= 2:
            asserts.append(_smt_expr_to_tree(form[1]))
    if not asserts:
        return None, 0
    return OrderedTree("smtlib_problem", tuple(asserts)), 0


def compute_external_statement_similarity(
    *,
    corpus: str,
    root: Path,
    selected_names: list[str],
    mode: str = "auto",
    max_theorems_full: int = 400,
    max_knn_theorems: int = 2000,
    knn_k: int = 12,
    knn_sample_size: int = 200,
    sample_size: int = 400,
) -> dict[str, Any]:
    if corpus not in {"tptp", "smtlib"}:
        raise ValueError(f"unsupported corpus for statement similarity: {corpus}")

    trees, invalid, partial = _extract_external_problem_trees(corpus, root, selected_names)
    report = _compute_similarity_report(
        corpus=corpus,
        root=root,
        trees=trees,
        invalid=invalid,
        mode=mode,
        max_theorems_full=max_theorems_full,
        max_knn_theorems=max_knn_theorems,
        knn_k=knn_k,
        knn_sample_size=knn_sample_size,
        sample_size=sample_size,
    )
    if partial and report.get("valid") is True:
        examples = list(sorted(partial.items()))[:5]
        notes = report.get("validity_notes")
        if isinstance(notes, list):
            notes.append(
                f"partial_parse_problems={len(partial)}; "
                f"total_parse_failures={sum(partial.values())}; examples={examples}"
            )
    return report


def compute_tptp_statement_similarity_from_logs(
    run_dir: Path,
    *,
    selected_names: list[str],
    mode: str = "auto",
    max_theorems_full: int = 400,
    max_knn_theorems: int = 2000,
    knn_k: int = 12,
    knn_sample_size: int = 200,
    sample_size: int = 400,
) -> dict[str, Any]:
    """Fallback for moved logs: derive TPTP statement trees from logged wild_type_graph.json."""

    trees: dict[str, OrderedTree] = {}
    invalid: dict[str, str] = {}
    partial: dict[str, int] = {}
    for name in selected_names:
        graph_path = run_dir / name / "wild_type_graph.json"
        if not graph_path.exists():
            invalid[name] = "missing_wild_type_graph"
            continue
        try:
            payload = json.loads(graph_path.read_text())
        except Exception:
            invalid[name] = "invalid_wild_type_graph_json"
            continue
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            invalid[name] = "invalid_wild_type_graph_nodes"
            continue

        formulas: list[Formula] = []
        conjectures: list[Formula] = []
        parse_failures = 0
        for node in nodes:
            if not isinstance(node, dict):
                continue
            role = node.get("role")
            formula_txt = node.get("goal_type")
            if not isinstance(formula_txt, str) or not formula_txt.strip():
                continue
            try:
                f = parse_tptp_formula(formula_txt.strip())
            except Exception:
                parse_failures += 1
                continue
            formulas.append(f)
            if role in {"conjecture", "negated_conjecture"}:
                conjectures.append(f)
        chosen = conjectures if conjectures else formulas
        if not chosen:
            invalid[name] = "no_parsable_formulas"
            continue
        if parse_failures:
            partial[name] = parse_failures
        trees[name] = OrderedTree("tptp_problem", tuple(_formula_to_tree(f) for f in chosen))

    report = _compute_similarity_report(
        corpus="tptp",
        root=None,
        trees=trees,
        invalid=invalid,
        mode=mode,
        max_theorems_full=max_theorems_full,
        max_knn_theorems=max_knn_theorems,
        knn_k=knn_k,
        knn_sample_size=knn_sample_size,
        sample_size=sample_size,
    )
    if partial and report.get("valid") is True:
        examples = list(sorted(partial.items()))[:5]
        notes = report.get("validity_notes")
        if isinstance(notes, list):
            notes.append(
                f"partial_parse_theorems={len(partial)}; "
                f"total_parse_failures={sum(partial.values())}; examples={examples}"
            )
    report["source"] = "logged_wild_type_graph"
    return report


def _extract_external_problem_trees(
    corpus: str,
    root: Path,
    selected_names: list[str],
) -> tuple[dict[str, OrderedTree], dict[str, str], dict[str, int]]:
    name_to_path: dict[str, Path] = {}
    if corpus == "tptp":
        for p in list_tptp_problems(root, domains=None, limit=None):
            name_to_path[p.name] = p.path
    else:
        for p in list_smtlib_problems(root, limit=None):
            name_to_path[p.name] = p.path

    trees: dict[str, OrderedTree] = {}
    invalid: dict[str, str] = {}
    partial_parse_failures: dict[str, int] = {}
    for name in selected_names:
        path = name_to_path.get(name)
        if path is None:
            invalid[name] = "missing_path"
            continue
        tree, failures = (
            _extract_tptp_problem_tree(path)
            if corpus == "tptp"
            else _extract_smtlib_problem_tree(path)
        )
        if tree is None:
            invalid[name] = "parse_failed"
            continue
        if failures:
            partial_parse_failures[name] = failures
        trees[name] = tree
    return trees, invalid, partial_parse_failures


def _compute_similarity_report(
    *,
    corpus: str,
    root: Path | None,
    trees: dict[str, OrderedTree],
    invalid: dict[str, str],
    mode: str,
    max_theorems_full: int,
    max_knn_theorems: int,
    knn_k: int,
    knn_sample_size: int,
    sample_size: int,
) -> dict[str, Any]:
    names = sorted(trees.keys())
    if not names:
        return {
            "schema_version": 1,
            "valid": False,
            "validity_notes": ["no parsable problem statements found"],
            "corpus": corpus,
        }

    mode_used = _resolve_mode(
        mode,
        len(names),
        max_theorems_full=max_theorems_full,
        max_knn_theorems=max_knn_theorems,
    )
    tree_sizes = {name: _tree_size(t) for name, t in trees.items()}

    sample_meta: dict[str, Any] = {}
    sample_names: list[str] = []
    if mode_used in {"knn", "sample"}:
        eff = knn_sample_size if mode_used == "knn" else sample_size
        if eff < 1:
            raise ValueError("sample size must be >= 1")
        sample_names, sample_meta = _select_sample(names, eff)

    names_for_matrix = sample_names if mode_used == "sample" else names
    matrix: dict[str, dict[str, float | None]]
    if mode_used in {"full", "sample"}:
        matrix = {n: {} for n in names_for_matrix}
        for i, a in enumerate(names_for_matrix):
            matrix[a][a] = 0.0
            for j in range(i + 1, len(names_for_matrix)):
                b = names_for_matrix[j]
                value = _normalized_distance(trees[a], trees[b], tree_sizes[a], tree_sizes[b])
                matrix[a][b] = value
                matrix[b][a] = value
    else:
        if knn_k < 1:
            raise ValueError("knn_k must be >= 1")
        matrix = {n: {} for n in names}
        for n in names:
            matrix[n][n] = 0.0
        for name in names:
            neighbors: list[tuple[float, str]] = []
            for sample in sample_names:
                if sample == name:
                    continue
                value = _normalized_distance(
                    trees[name], trees[sample], tree_sizes[name], tree_sizes[sample]
                )
                neighbors.append((value, sample))
            neighbors.sort(key=lambda item: (item[0], item[1]))
            for value, sample in neighbors[:knn_k]:
                matrix[name][sample] = value
                matrix[sample][name] = value

    clusters = cluster_proof_structures(
        matrix,
        distance_threshold=DISTANCE_THRESHOLD,
        theorem_name="external_statement_similarity",
        missing_distance=1.0,
    ).serialize()

    notes: list[str] = []
    if invalid:
        examples = list(sorted(invalid.items()))[:5]
        notes.append(f"excluded_problems={len(invalid)}; examples={examples}")
    if mode_used != "full":
        note = f"matrix_mode={mode_used}; problem_count={len(names)}"
        if mode_used == "knn":
            note = f"{note}; knn_k={knn_k}; knn_sample_size={len(sample_names)}"
        if mode_used == "sample":
            note = f"{note}; sample_size={len(sample_names)}"
        notes.append(note)

    report: dict[str, Any] = {
        "schema_version": 1,
        "valid": True,
        "validity_notes": notes,
        "corpus": corpus,
        "root": str(root) if root is not None else None,
        "distance_metric": "normalized_ordered_ted",
        "distance_threshold": DISTANCE_THRESHOLD,
        "matrix_mode": mode_used,
        "matrix_kind": "dense" if mode_used in {"full", "sample"} else "sparse",
        "problem_count_total": len(names),
        "problems": names_for_matrix,
        "distance_matrix": matrix,
        "clusters": clusters,
    }
    if mode_used in {"knn", "sample"}:
        report.update({"sample_size": len(sample_names), "sample_meta": sample_meta})
    report.update(
        {
            "max_theorems_full": max_theorems_full,
            "max_knn_theorems": max_knn_theorems,
        }
    )
    if mode_used == "knn":
        report.update({"knn_k": knn_k, "knn_sample_size": knn_sample_size})
    if mode_used == "sample":
        report.update({"sample_size_target": sample_size})
    return report
