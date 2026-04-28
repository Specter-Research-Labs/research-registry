from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.logs import iter_provider_runs, read_json, read_json_gz
from analysis.proof_graph_ir import (
    ProofGraphIR,
    RelativeGraphFeatures,
    apply_relative_ranks,
    build_proof_graph_ir,
    graph_kind_distribution,
)
from atp.coq.terms import proof_graph_from_dag
from prover.expr import ExprDAG
from prover.proof import ProofGraph

HEX_ESCAPE_RE = re.compile(r"x([0-9a-fA-F]{2})")
CAMEL_SPLIT_RE = re.compile(r"([a-z0-9])([A-Z])")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_']*")

TOKEN_ALIASES = {
    "andb": "and",
    "orb": "or",
    "negb": "not",
    "implb": "imp",
    "plus": "add",
    "sum": "add",
    "minus": "sub",
    "times": "mul",
    "prod": "mul",
    "inverse": "inv",
    "commutative": "comm",
    "associative": "assoc",
    "symmetric": "sym",
    "symmetricity": "sym",
    "reflexive": "refl",
    "equiv": "eq",
    "equal": "eq",
    "equals": "eq",
    "injection": "injective",
    "surjection": "surjective",
}

TOKEN_STOPWORDS = {
    "theorem",
    "lemma",
    "corollary",
    "proposition",
    "fact",
    "remark",
    "example",
    "proof",
    "inst",
    "type",
    "fun",
    "by",
    "sorry",
    "forall",
    "exists",
}

CONNECTIVE_PATTERNS = {
    "iff": (r"<->", r"↔", r"\biff\b"),
    "imp": (r"->", r"→", r"=>", r"\bimplies\b"),
    "and": (r"/\\", r"∧", r"\band\b", r"\bandb\b"),
    "or": (r"\\/", r"∨", r"\bor\b", r"\borb\b"),
    "not": (r"¬", r"\bnot\b", r"~", r"\bnegb\b"),
    "eq": (r"=",),
    "neq": (r"<>", r"≠", r"!="),
    "forall": (r"\bforall\b", r"∀"),
    "exists": (r"\bexists\b", r"∃"),
    "add": (r"\+",),
    "sub": (r"(?<!-)-(?!>)",),
    "mul": (r"\*",),
    "div": (r"/",),
}

GRAPH_SOURCE_WILD_TYPE = "wild_type_graph"
GRAPH_SOURCE_PROOF_TERM = "proof_term_graph"
GRAPH_SOURCE_TRACE = "search_trace_graph"
VALID_PROOF_AGGREGATION = frozenset({"single", "best_of", "consensus"})
VALID_LEXICAL_ABLATION = frozenset({"none", "drop_tokens", "graph_only"})


@dataclass(frozen=True)
class TheoremTextMeta:
    display_name: str | None
    statement: str | None


@dataclass(frozen=True)
class NameObfuscationConfig:
    mode: str = "none"
    salt: str = "cross-assistant-obfuscation-v1"


@dataclass(frozen=True)
class LexicalAblationConfig:
    mode: str = "none"


@dataclass(frozen=True)
class GraphSignature:
    provider: str | None
    theorem: str
    variant: str
    proof_id: str
    solved: bool
    node_count: int
    edge_count: int
    max_depth: int
    shape_hash: str
    family_freq: dict[str, float]
    lexical_tokens: frozenset[str]
    connective_profile: dict[str, float]
    has_statement_text: bool
    graph_kind: str
    proof_ir: ProofGraphIR
    relative_graph_features: RelativeGraphFeatures


@dataclass(frozen=True)
class PairDistance:
    proof_id_a: str
    proof_id_b: str
    theorem_a: str
    theorem_b: str
    variant_a: str
    variant_b: str
    distance: float
    graph_distance: float
    lexical_distance: float
    connective_distance: float
    lexical_overlap: float
    graph_kind_a: str
    graph_kind_b: str
    cross_kind: bool


@dataclass(frozen=True)
class TheoremPairDistance:
    theorem_a: str
    theorem_b: str
    distance: float
    representative_pair: PairDistance
    proof_count_a: int
    proof_count_b: int
    nearest_neighbor_stats: dict[str, float] | None


def _load_summary(run_dir: Path) -> dict[str, Any]:
    summary_gz = run_dir / "summary.json.gz"
    summary_json = run_dir / "summary.json"
    if summary_gz.exists():
        data = read_json_gz(summary_gz)
    elif summary_json.exists():
        data = read_json(summary_json)
    else:
        raise FileNotFoundError(f"No summary.json(.gz) found under {run_dir}")
    if not isinstance(data, dict):
        raise ValueError("summary.json(.gz) must contain a JSON object")
    return data


def _load_run_config(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_config.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {}
    return payload


def _variant_graph_path(theorem_dir: Path, variant: str) -> Path:
    if variant == "wild_type":
        return theorem_dir / "wild_type_graph.json"
    return theorem_dir / f"{variant}_graph.json"


def _variant_proof_term_paths(theorem_dir: Path, variant: str) -> tuple[Path, Path]:
    if variant == "wild_type":
        return (
            theorem_dir / "wild_type_proof_term.json.gz",
            theorem_dir / "wild_type_proof_term.json",
        )
    return (
        theorem_dir / f"{variant}_proof_term.json.gz",
        theorem_dir / f"{variant}_proof_term.json",
    )


def _load_graph(run_dir: Path, theorem: str, *, variant: str = "wild_type") -> ProofGraph:
    theorem_dir = run_dir / theorem
    graph_path = _variant_graph_path(theorem_dir, variant)
    if not graph_path.exists():
        raise FileNotFoundError(f"Missing graph artifact: {graph_path}")
    payload = read_json(graph_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid graph payload: {graph_path}")
    return ProofGraph.deserialize(payload)


def _normalize_graph_source(graph_source: str) -> str:
    norm = graph_source.strip().lower().replace("-", "_")
    if norm in {"wild", "wild_graph", "wild_type", "wild_type_graph"}:
        return GRAPH_SOURCE_WILD_TYPE
    if norm in {"proof_term", "proof_term_graph", "term_graph"}:
        return GRAPH_SOURCE_PROOF_TERM
    if norm in {"trace", "trace_graph", "search_trace", "search_trace_graph"}:
        return GRAPH_SOURCE_TRACE
    raise ValueError(f"unsupported graph source: {graph_source}")


def _load_proof_term_graph(
    run_dir: Path,
    theorem: str,
    *,
    variant: str = "wild_type",
) -> ProofGraph:
    theorem_dir = run_dir / theorem
    path_gz, path_json = _variant_proof_term_paths(theorem_dir, variant)
    if path_gz.exists():
        payload = read_json_gz(path_gz)
    elif path_json.exists():
        payload = read_json(path_json)
    else:
        raise FileNotFoundError(f"Missing proof-term artifact: {theorem_dir} ({variant})")
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid proof term payload: {theorem_dir}")
    dag = ExprDAG.from_json(payload)
    return proof_graph_from_dag(dag)


def _load_signature_graph(
    run_dir: Path,
    theorem: str,
    *,
    graph_source: str,
    variant: str = "wild_type",
) -> ProofGraph:
    source = _normalize_graph_source(graph_source)
    if source == GRAPH_SOURCE_WILD_TYPE:
        return _load_graph(run_dir, theorem, variant=variant)
    if source == GRAPH_SOURCE_PROOF_TERM:
        return _load_proof_term_graph(run_dir, theorem, variant=variant)
    if source == GRAPH_SOURCE_TRACE:
        theorem_dir = run_dir / theorem
        if variant == "wild_type":
            path = theorem_dir / "wild_type_search_trace_graph.json"
        else:
            path = theorem_dir / f"{variant}_search_trace_graph.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing trace graph artifact: {path}")
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid trace graph payload: {path}")
        return ProofGraph.deserialize(payload)
    raise ValueError(f"unsupported graph source: {graph_source}")


def _decode_name(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        code = int(match.group(1), 16)
        if 32 <= code <= 126:
            return chr(code)
        return " "

    return HEX_ESCAPE_RE.sub(repl, text)


def _normalize_token(token: str) -> str | None:
    token = token.lower().strip("_'")
    if not token or token in TOKEN_STOPWORDS:
        return None
    token = TOKEN_ALIASES.get(token, token)
    if len(token) < 2:
        return None
    return token


def _normalize_obfuscation_mode(mode: str) -> str:
    norm = mode.strip().lower().replace("-", "_")
    if norm in {"none", ""}:
        return "none"
    if norm in {"names", "theorem_names", "name_only", "name_obfuscated"}:
        return "names"
    raise ValueError(f"unsupported name obfuscation mode: {mode}")


def _normalize_lexical_ablation_mode(mode: str) -> str:
    norm = mode.strip().lower().replace("-", "_")
    if norm not in VALID_LEXICAL_ABLATION:
        raise ValueError(
            "unsupported lexical ablation mode:"
            f" {mode}; expected one of {sorted(VALID_LEXICAL_ABLATION)}"
        )
    return norm


def _apply_lexical_ablation(
    *,
    lexical_tokens: frozenset[str],
    connective_profile: dict[str, float],
    config: LexicalAblationConfig,
) -> tuple[frozenset[str], dict[str, float]]:
    if config.mode == "none":
        return lexical_tokens, connective_profile
    if config.mode == "drop_tokens":
        return frozenset(), connective_profile
    if config.mode == "graph_only":
        return frozenset(), {}
    raise ValueError(f"unsupported lexical ablation mode: {config.mode}")


def normalize_proof_aggregation(mode: str) -> str:
    norm = mode.strip().lower().replace("-", "_")
    if norm not in VALID_PROOF_AGGREGATION:
        raise ValueError(
            f"unsupported proof aggregation mode: {mode}; expected one of"
            f" {sorted(VALID_PROOF_AGGREGATION)}"
        )
    return norm


def _obfuscate_name(text: str, config: NameObfuscationConfig) -> str:
    digest = hashlib.sha256(f"{config.salt}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"obf_{digest}"


def _maybe_obfuscate_name(text: str, config: NameObfuscationConfig) -> str:
    if config.mode == "none":
        return text
    if config.mode == "names":
        return _obfuscate_name(text, config)
    raise ValueError(f"unsupported name obfuscation mode: {config.mode}")


def _tokenize_text(text: str) -> list[str]:
    decoded = _decode_name(text)
    decoded = CAMEL_SPLIT_RE.sub(r"\1 \2", decoded)
    decoded = (
        decoded.replace("↔", " iff ")
        .replace("→", " imp ")
        .replace("∀", " forall ")
        .replace("∃", " exists ")
        .replace("∧", " and ")
        .replace("∨", " or ")
        .replace("¬", " not ")
    )
    out: list[str] = []
    for raw in TOKEN_RE.findall(decoded):
        tok = _normalize_token(raw)
        if tok is not None:
            out.append(tok)
    return out


def _connective_profile(texts: list[str]) -> dict[str, float]:
    if not texts:
        return {}
    blob = "\n".join(_decode_name(t).lower() for t in texts)
    counts: dict[str, int] = {}
    for key, patterns in CONNECTIVE_PATTERNS.items():
        value = 0
        for pattern in patterns:
            value += len(re.findall(pattern, blob))
        if value > 0:
            counts[key] = value
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in sorted(counts.items())}


def _run_backend_hint(run_config: dict[str, Any]) -> str | None:
    backend = run_config.get("backend")
    if isinstance(backend, str) and backend.strip():
        return backend.strip().lower()
    mode = run_config.get("mode")
    corpus = run_config.get("corpus")
    if mode == "external" and isinstance(corpus, str):
        corpus_norm = corpus.strip().lower()
        if corpus_norm.startswith("coq"):
            return "coq"
    return None


def _load_lean_text_metadata(
    run_config: dict[str, Any],
    theorem_names: set[str],
) -> dict[str, TheoremTextMeta]:
    backend = run_config.get("backend")
    if backend != "lean":
        return {}
    corpus_meta = run_config.get("corpus_meta")
    if not isinstance(corpus_meta, dict):
        return {}
    raw_items_path = corpus_meta.get("items_path")
    if not isinstance(raw_items_path, str) or not raw_items_path.strip():
        return {}
    items_path = Path(raw_items_path)
    if not items_path.exists():
        return {}

    out: dict[str, TheoremTextMeta] = {}
    with items_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON in items_path at line {line_no}: {items_path}"
                ) from exc
            if not isinstance(row, dict):
                continue
            theorem = row.get("item_id")
            if theorem not in theorem_names:
                continue
            display_name = row.get("display_name")
            payload = row.get("payload")
            statement = None
            if isinstance(payload, dict):
                statement_raw = payload.get("statement")
                if isinstance(statement_raw, str) and statement_raw.strip():
                    statement = statement_raw
            out[theorem] = TheoremTextMeta(
                display_name=display_name if isinstance(display_name, str) else None,
                statement=statement,
            )
            if len(out) >= len(theorem_names):
                break
    return out


def _variant_summary_entry(theorem_entry: dict[str, Any], variant: str) -> dict[str, Any] | None:
    if variant == "wild_type":
        wild = theorem_entry.get("wild_type")
        return wild if isinstance(wild, dict) else None
    interventions = theorem_entry.get("interventions")
    if not isinstance(interventions, list):
        return None
    for item in interventions:
        if not isinstance(item, dict):
            continue
        if item.get("name") == variant:
            return item
    return None


def _proof_term_const_names(
    theorem_entry: dict[str, Any],
    *,
    variant: str = "wild_type",
) -> list[str]:
    summary_entry = _variant_summary_entry(theorem_entry, variant)
    if not isinstance(summary_entry, dict):
        return []
    metrics = summary_entry.get("metrics")
    if not isinstance(metrics, dict):
        return []
    proof_term = metrics.get("proof_term")
    if not isinstance(proof_term, dict):
        return []
    raw = proof_term.get("const_names")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        if isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _theorem_statement_text(theorem_entry: dict[str, Any]) -> str | None:
    direct = theorem_entry.get("statement_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    wild = theorem_entry.get("wild_type")
    if not isinstance(wild, dict):
        return None
    metrics = wild.get("metrics")
    if not isinstance(metrics, dict):
        return None
    text = metrics.get("statement_text")
    if isinstance(text, str) and text.strip():
        return text
    return None


def _theorem_variants(
    theorem_entry: dict[str, Any],
    *,
    include_interventions: bool,
    solved_only: bool,
    max_proofs_per_theorem: int | None,
) -> list[tuple[str, bool]]:
    variants: list[tuple[str, bool]] = []
    wild = theorem_entry.get("wild_type")
    wild_solved = bool(isinstance(wild, dict) and wild.get("solved") is True)
    if not solved_only or wild_solved:
        variants.append(("wild_type", wild_solved))

    if include_interventions:
        interventions = theorem_entry.get("interventions")
        if isinstance(interventions, list):
            for intervention in interventions:
                if not isinstance(intervention, dict):
                    continue
                name = intervention.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                solved = intervention.get("solved") is True
                if solved_only and not solved:
                    continue
                variants.append((name, solved))

    if max_proofs_per_theorem is not None:
        if max_proofs_per_theorem <= 0:
            raise ValueError("max_proofs_per_theorem must be >= 1 when provided")
        variants = variants[:max_proofs_per_theorem]
    return variants


def load_run_signatures(
    run_dir: Path,
    *,
    solved_only: bool = False,
    name_obfuscation: NameObfuscationConfig | None = None,
    lexical_ablation: LexicalAblationConfig | None = None,
    graph_source: str = GRAPH_SOURCE_WILD_TYPE,
    include_interventions: bool = False,
    max_proofs_per_theorem: int | None = None,
    provider: str | None = None,
) -> list[GraphSignature]:
    summary = _load_summary(run_dir)
    raw = summary.get("theorems")
    if not isinstance(raw, list):
        raise ValueError("summary.theorems must be a list")

    theorem_names = {
        entry.get("name")
        for entry in raw
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    run_config = _load_run_config(run_dir)
    lean_meta = _load_lean_text_metadata(run_config, theorem_names)
    backend_hint = _run_backend_hint(run_config)
    obfuscation = name_obfuscation or NameObfuscationConfig()
    obfuscation = NameObfuscationConfig(
        mode=_normalize_obfuscation_mode(obfuscation.mode),
        salt=obfuscation.salt,
    )
    ablation = lexical_ablation or LexicalAblationConfig()
    ablation = LexicalAblationConfig(mode=_normalize_lexical_ablation_mode(ablation.mode))
    normalized_graph_source = _normalize_graph_source(graph_source)

    rows: list[dict[str, Any]] = []
    raw_ir: list[ProofGraphIR] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        theorem = entry.get("name")
        if not isinstance(theorem, str) or not theorem:
            continue
        variants = _theorem_variants(
            entry,
            include_interventions=include_interventions,
            solved_only=solved_only,
            max_proofs_per_theorem=max_proofs_per_theorem,
        )
        for variant, solved in variants:
            try:
                graph = _load_signature_graph(
                    run_dir,
                    theorem,
                    graph_source=normalized_graph_source,
                    variant=variant,
                )
            except (FileNotFoundError, ValueError):
                continue

            theorem_text = _maybe_obfuscate_name(theorem, obfuscation)
            lexical_texts: list[str] = [theorem_text]
            connective_texts: list[str] = [theorem_text]
            meta = lean_meta.get(theorem)
            has_statement_text = False
            if meta is not None:
                if meta.display_name:
                    display_name = _maybe_obfuscate_name(meta.display_name, obfuscation)
                    lexical_texts.append(display_name)
                    connective_texts.append(display_name)
                if meta.statement:
                    connective_texts.append(meta.statement)
                    has_statement_text = True
            statement_text = _theorem_statement_text(entry)
            if statement_text:
                lexical_texts.append(statement_text)
                connective_texts.append(statement_text)
                has_statement_text = True
            lexical_texts.extend(
                _maybe_obfuscate_name(value, obfuscation)
                for value in _proof_term_const_names(entry, variant=variant)
            )

            lexical_tokens: set[str] = set()
            for text in lexical_texts:
                lexical_tokens.update(_tokenize_text(text))

            graph_ir = build_proof_graph_ir(graph, backend_hint=backend_hint)
            raw_ir.append(graph_ir)
            proof_id_prefix = f"{provider}::" if provider else ""
            lexical_tokens_frozen, connective_profile = _apply_lexical_ablation(
                lexical_tokens=frozenset(lexical_tokens),
                connective_profile=_connective_profile(connective_texts),
                config=ablation,
            )

            rows.append(
                {
                    "provider": provider,
                    "theorem": theorem,
                    "variant": variant,
                    "proof_id": f"{proof_id_prefix}{theorem}::{variant}",
                    "solved": solved,
                    "lexical_tokens": lexical_tokens_frozen,
                    "connective_profile": connective_profile,
                    "has_statement_text": has_statement_text,
                }
            )

    ranked_features = apply_relative_ranks(raw_ir)
    signatures: list[GraphSignature] = []
    for row, graph_ir, relative_features in zip(rows, raw_ir, ranked_features, strict=False):
        signatures.append(
            GraphSignature(
                provider=row["provider"],
                theorem=row["theorem"],
                variant=row["variant"],
                proof_id=row["proof_id"],
                solved=bool(row["solved"]),
                node_count=graph_ir.node_count,
                edge_count=graph_ir.edge_count,
                max_depth=graph_ir.max_depth,
                shape_hash=graph_ir.shape_hash,
                family_freq=graph_ir.edge_role_profile,
                lexical_tokens=row["lexical_tokens"],
                connective_profile=row["connective_profile"],
                has_statement_text=bool(row["has_statement_text"]),
                graph_kind=graph_ir.graph_family,
                proof_ir=graph_ir,
                relative_graph_features=relative_features,
            )
        )

    signatures.sort(key=lambda s: (s.theorem, s.variant, s.proof_id))
    return signatures


def load_signature_pool(
    run_dir: Path,
    *,
    solved_only: bool = False,
    name_obfuscation: NameObfuscationConfig | None = None,
    lexical_ablation: LexicalAblationConfig | None = None,
    graph_source: str = GRAPH_SOURCE_WILD_TYPE,
    include_interventions: bool = False,
    max_proofs_per_theorem: int | None = None,
) -> list[GraphSignature]:
    signatures: list[GraphSignature] = []
    provider_runs = iter_provider_runs(run_dir)
    for provider_run in provider_runs:
        signatures.extend(
            load_run_signatures(
                provider_run.run_dir,
                solved_only=solved_only,
                name_obfuscation=name_obfuscation,
                lexical_ablation=lexical_ablation,
                graph_source=graph_source,
                include_interventions=include_interventions,
                max_proofs_per_theorem=max_proofs_per_theorem,
                provider=provider_run.provider,
            )
        )
    signatures.sort(key=lambda s: (s.theorem, s.variant, s.proof_id))
    return signatures


def _family_l1(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a.keys()) | set(b.keys())
    if not keys:
        return 0.0
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / 2.0


def _jaccard_distance(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    if union <= 0:
        return 0.0
    return 1.0 - (inter / union)


def _graph_distance(a: GraphSignature, b: GraphSignature) -> float:
    ir_a = a.proof_ir
    ir_b = b.proof_ir
    rel_a = a.relative_graph_features
    rel_b = b.relative_graph_features
    rank_distance = (
        0.30 * abs(rel_a.node_rank - rel_b.node_rank)
        + 0.15 * abs(rel_a.edge_rank - rel_b.edge_rank)
        + 0.20 * abs(rel_a.depth_rank - rel_b.depth_rank)
        + 0.20 * abs(rel_a.branching_rank - rel_b.branching_rank)
        + 0.15 * abs(rel_a.leaf_rank - rel_b.leaf_rank)
    )
    operator_delta = _family_l1(ir_a.operator_profile, ir_b.operator_profile)
    motif_delta = _family_l1(ir_a.motif_profile, ir_b.motif_profile)
    action_delta = _family_l1(ir_a.action_kind_profile, ir_b.action_kind_profile)
    effect_delta = _family_l1(ir_a.effect_profile, ir_b.effect_profile)
    continuation_delta = _family_l1(ir_a.continuation_profile, ir_b.continuation_profile)
    coupling_delta = _family_l1(ir_a.coupling_profile, ir_b.coupling_profile)
    same_kind = ir_a.graph_family == ir_b.graph_family
    if not same_kind:
        return (
            0.35 * rank_distance
            + 0.15 * operator_delta
            + 0.10 * motif_delta
            + 0.10 * action_delta
            + 0.10 * effect_delta
            + 0.10 * continuation_delta
            + 0.05 * coupling_delta
            + 0.05
        )

    role_delta = _family_l1(ir_a.edge_role_profile, ir_b.edge_role_profile)
    shape_delta = 0.0 if ir_a.shape_hash == ir_b.shape_hash else 1.0
    return (
        0.25 * rank_distance
        + 0.12 * operator_delta
        + 0.08 * motif_delta
        + 0.15 * role_delta
        + 0.12 * action_delta
        + 0.10 * effect_delta
        + 0.08 * continuation_delta
        + 0.05 * coupling_delta
        + 0.05 * shape_delta
    )


def pair_distance(a: GraphSignature, b: GraphSignature) -> PairDistance:
    graph_distance = _graph_distance(a, b)
    lexical_distance = _jaccard_distance(a.lexical_tokens, b.lexical_tokens)
    connective_distance = _family_l1(a.connective_profile, b.connective_profile)

    cross_kind = a.graph_kind != b.graph_kind
    graph_weight = 0.45 if cross_kind else 0.55
    weighted: list[tuple[float, float]] = [(graph_weight, graph_distance)]
    if a.lexical_tokens or b.lexical_tokens:
        weighted.append((0.40 if cross_kind else 0.30, lexical_distance))
    if a.connective_profile or b.connective_profile:
        weighted.append((0.15 if cross_kind else 0.15, connective_distance))

    total_weight = sum(w for w, _ in weighted)
    distance = sum(w * value for w, value in weighted) / total_weight
    return PairDistance(
        proof_id_a=a.proof_id,
        proof_id_b=b.proof_id,
        theorem_a=a.theorem,
        theorem_b=b.theorem,
        variant_a=a.variant,
        variant_b=b.variant,
        distance=distance,
        graph_distance=graph_distance,
        lexical_distance=lexical_distance,
        connective_distance=connective_distance,
        lexical_overlap=1.0 - lexical_distance,
        graph_kind_a=a.graph_kind,
        graph_kind_b=b.graph_kind,
        cross_kind=cross_kind,
    )


def group_signatures_by_theorem(
    signatures: list[GraphSignature],
) -> dict[str, list[GraphSignature]]:
    out: dict[str, list[GraphSignature]] = {}
    for sig in signatures:
        out.setdefault(sig.theorem, []).append(sig)
    for theorem in out:
        out[theorem].sort(key=lambda sig: (sig.variant, sig.proof_id))
    return out


def aggregate_theorem_distance(
    sigs_a: list[GraphSignature],
    sigs_b: list[GraphSignature],
    *,
    proof_aggregation: str,
) -> TheoremPairDistance:
    if not sigs_a or not sigs_b:
        raise ValueError("aggregate_theorem_distance requires non-empty proof sets")

    pair_rows: list[PairDistance] = []
    nearest_from_a: dict[str, float] = {}
    nearest_from_b: dict[str, float] = {}
    for sig_a in sigs_a:
        for sig_b in sigs_b:
            pair = pair_distance(sig_a, sig_b)
            pair_rows.append(pair)
            current_a = nearest_from_a.get(sig_a.proof_id)
            if current_a is None or pair.distance < current_a:
                nearest_from_a[sig_a.proof_id] = pair.distance
            current_b = nearest_from_b.get(sig_b.proof_id)
            if current_b is None or pair.distance < current_b:
                nearest_from_b[sig_b.proof_id] = pair.distance
    pair_rows.sort(key=lambda row: (row.distance, row.theorem_b, row.variant_b, row.proof_id_b))
    best_pair = pair_rows[0]

    mode = normalize_proof_aggregation(proof_aggregation)
    nearest_neighbor_stats: dict[str, float] | None = None
    if mode == "single" or mode == "best_of":
        distance = best_pair.distance
    elif mode == "consensus":
        nn_a_values = sorted(nearest_from_a.values())
        nn_b_values = sorted(nearest_from_b.values())
        if not nn_a_values or not nn_b_values:
            distance = best_pair.distance
        else:
            nn_values = nn_a_values + nn_b_values
            nn_values.sort()
            mid = len(nn_values) // 2
            if len(nn_values) % 2:
                distance = nn_values[mid]
            else:
                distance = (nn_values[mid - 1] + nn_values[mid]) / 2.0
            nearest_neighbor_stats = {
                "nearest_mean_a": round(sum(nn_a_values) / len(nn_a_values), 6),
                "nearest_mean_b": round(sum(nn_b_values) / len(nn_b_values), 6),
                "nearest_median": round(distance, 6),
            }
    else:
        raise ValueError(f"unsupported proof aggregation mode: {proof_aggregation}")

    return TheoremPairDistance(
        theorem_a=sigs_a[0].theorem,
        theorem_b=sigs_b[0].theorem,
        distance=distance,
        representative_pair=best_pair,
        proof_count_a=len(sigs_a),
        proof_count_b=len(sigs_b),
        nearest_neighbor_stats=nearest_neighbor_stats,
    )


def rank_theorem_candidates(
    source_theorem: str,
    source_groups: dict[str, list[GraphSignature]],
    target_groups: dict[str, list[GraphSignature]],
    *,
    proof_aggregation: str,
) -> list[TheoremPairDistance]:
    source_sigs = source_groups.get(source_theorem)
    if source_sigs is None:
        return []
    out: list[TheoremPairDistance] = []
    for target_theorem, target_sigs in target_groups.items():
        out.append(
            aggregate_theorem_distance(
                source_sigs,
                target_sigs,
                proof_aggregation=proof_aggregation,
            )
        )
    out.sort(
        key=lambda row: (
            row.distance,
            row.theorem_b,
            row.representative_pair.variant_b,
            row.representative_pair.proof_id_b,
        )
    )
    return out


def _top_k_for_a(
    a: list[GraphSignature],
    b: list[GraphSignature],
    *,
    top_k: int,
) -> dict[str, list[PairDistance]]:
    out: dict[str, list[PairDistance]] = {}
    for sig_a in a:
        pairs: list[PairDistance] = []
        for sig_b in b:
            pairs.append(pair_distance(sig_a, sig_b))
        pairs.sort(key=lambda p: (p.distance, p.theorem_b, p.variant_b, p.proof_id_b))
        out[sig_a.proof_id] = pairs[:top_k]
    return out


def _one_to_one_assignment(
    all_pairs: list[PairDistance],
    *,
    max_matches: int,
) -> list[PairDistance]:
    used_a: set[str] = set()
    used_b: set[str] = set()
    chosen: list[PairDistance] = []
    for pair in sorted(all_pairs, key=lambda p: (p.distance, p.theorem_a, p.theorem_b)):
        if pair.proof_id_a in used_a or pair.proof_id_b in used_b:
            continue
        used_a.add(pair.proof_id_a)
        used_b.add(pair.proof_id_b)
        chosen.append(pair)
        if len(chosen) >= max_matches:
            break
    return chosen


def align_runs(
    run_a_dir: Path,
    run_b_dir: Path,
    *,
    solved_only: bool = False,
    top_k: int = 3,
    one_to_one: bool = True,
    proof_aggregation: str = "single",
    max_proofs_per_theorem: int | None = None,
    name_obfuscation_mode: str = "none",
    name_obfuscation_salt: str = "cross-assistant-obfuscation-v1",
    lexical_ablation_mode: str = "none",
    graph_source_a: str = GRAPH_SOURCE_WILD_TYPE,
    graph_source_b: str = GRAPH_SOURCE_WILD_TYPE,
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be >= 1")
    obfuscation = NameObfuscationConfig(
        mode=_normalize_obfuscation_mode(name_obfuscation_mode),
        salt=name_obfuscation_salt,
    )
    lexical_ablation = LexicalAblationConfig(
        mode=_normalize_lexical_ablation_mode(lexical_ablation_mode)
    )
    normalized_aggregation = normalize_proof_aggregation(proof_aggregation)
    include_interventions = normalized_aggregation != "single"

    a = load_signature_pool(
        run_a_dir,
        solved_only=solved_only,
        name_obfuscation=obfuscation,
        lexical_ablation=lexical_ablation,
        graph_source=graph_source_a,
        include_interventions=include_interventions,
        max_proofs_per_theorem=max_proofs_per_theorem,
    )
    b = load_signature_pool(
        run_b_dir,
        solved_only=solved_only,
        name_obfuscation=obfuscation,
        lexical_ablation=lexical_ablation,
        graph_source=graph_source_b,
        include_interventions=include_interventions,
        max_proofs_per_theorem=max_proofs_per_theorem,
    )
    if not a:
        raise ValueError(f"No theorem wild-type graphs found in run A: {run_a_dir}")
    if not b:
        raise ValueError(f"No theorem wild-type graphs found in run B: {run_b_dir}")

    a_by_proof = {s.proof_id: s for s in a}
    b_by_proof = {s.proof_id: s for s in b}
    a_groups = group_signatures_by_theorem(a)
    b_groups = group_signatures_by_theorem(b)

    top_for_a: dict[str, list[TheoremPairDistance]] = {}
    for theorem_a in sorted(a_groups):
        ranked = rank_theorem_candidates(
            theorem_a,
            a_groups,
            b_groups,
            proof_aggregation=normalized_aggregation,
        )
        top_for_a[theorem_a] = ranked[:top_k]
    top_for_b: dict[str, list[TheoremPairDistance]] = {}
    for theorem_b in sorted(b_groups):
        ranked = rank_theorem_candidates(
            theorem_b,
            b_groups,
            a_groups,
            proof_aggregation=normalized_aggregation,
        )
        top_for_b[theorem_b] = ranked[:1]
    all_pairs = [pair for pairs in top_for_a.values() for pair in pairs]

    if one_to_one:
        used_a_theorems: set[str] = set()
        used_b_theorems: set[str] = set()
        chosen: list[TheoremPairDistance] = []
        for pair in sorted(all_pairs, key=lambda p: (p.distance, p.theorem_a, p.theorem_b)):
            if pair.theorem_a in used_a_theorems or pair.theorem_b in used_b_theorems:
                continue
            used_a_theorems.add(pair.theorem_a)
            used_b_theorems.add(pair.theorem_b)
            chosen.append(pair)
            if len(chosen) >= min(len(a_groups), len(b_groups)):
                break
    else:
        chosen = sorted(all_pairs, key=lambda p: (p.distance, p.theorem_a, p.theorem_b))

    match_rows: list[dict[str, Any]] = []
    reciprocal_count = 0
    shape_equal_count = 0
    cross_kind_count = 0
    kind_pair_counts: dict[str, int] = {}
    for pair in chosen:
        rep = pair.representative_pair
        sig_a = a_by_proof[rep.proof_id_a]
        sig_b = b_by_proof[rep.proof_id_b]
        reciprocal = False
        top_b = top_for_b.get(pair.theorem_b, [])
        if top_b and top_b[0].theorem_b == pair.theorem_a:
            reciprocal = True
            reciprocal_count += 1
        if rep.cross_kind:
            cross_kind_count += 1
        if sig_a.shape_hash == sig_b.shape_hash:
            shape_equal_count += 1
        kind_key = f"{sig_a.graph_kind}->{sig_b.graph_kind}"
        kind_pair_counts[kind_key] = kind_pair_counts.get(kind_key, 0) + 1

        match_rows.append(
            {
                "theorem_a": pair.theorem_a,
                "theorem_b": pair.theorem_b,
                "distance": round(pair.distance, 6),
                "proof_aggregation": normalized_aggregation,
                "proof_support": {
                    "a": pair.proof_count_a,
                    "b": pair.proof_count_b,
                },
                "distance_components": {
                    "graph": round(rep.graph_distance, 6),
                    "lexical": round(rep.lexical_distance, 6),
                    "connective": round(rep.connective_distance, 6),
                },
                "lexical_overlap": round(rep.lexical_overlap, 6),
                "graph_kind_a": rep.graph_kind_a,
                "graph_kind_b": rep.graph_kind_b,
                "cross_kind": rep.cross_kind,
                "reciprocal_top1": reciprocal,
                "representative_pair": {
                    "proof_id_a": rep.proof_id_a,
                    "proof_id_b": rep.proof_id_b,
                    "variant_a": rep.variant_a,
                    "variant_b": rep.variant_b,
                },
                "nearest_neighbor_stats": pair.nearest_neighbor_stats,
                "a": {
                    "provider": sig_a.provider,
                    "variant": sig_a.variant,
                    "solved": sig_a.solved,
                    "node_count": sig_a.node_count,
                    "edge_count": sig_a.edge_count,
                    "max_depth": sig_a.max_depth,
                    "shape_hash": sig_a.shape_hash,
                    "graph_kind": sig_a.graph_kind,
                    "ir_ranks": {
                        "node": round(sig_a.relative_graph_features.node_rank, 6),
                        "edge": round(sig_a.relative_graph_features.edge_rank, 6),
                        "depth": round(sig_a.relative_graph_features.depth_rank, 6),
                        "leaf": round(sig_a.relative_graph_features.leaf_rank, 6),
                        "branching": round(
                            sig_a.relative_graph_features.branching_rank,
                            6,
                        ),
                    },
                    "lexical_token_count": len(sig_a.lexical_tokens),
                    "has_statement_text": sig_a.has_statement_text,
                },
                "b": {
                    "provider": sig_b.provider,
                    "variant": sig_b.variant,
                    "solved": sig_b.solved,
                    "node_count": sig_b.node_count,
                    "edge_count": sig_b.edge_count,
                    "max_depth": sig_b.max_depth,
                    "shape_hash": sig_b.shape_hash,
                    "graph_kind": sig_b.graph_kind,
                    "ir_ranks": {
                        "node": round(sig_b.relative_graph_features.node_rank, 6),
                        "edge": round(sig_b.relative_graph_features.edge_rank, 6),
                        "depth": round(sig_b.relative_graph_features.depth_rank, 6),
                        "leaf": round(sig_b.relative_graph_features.leaf_rank, 6),
                        "branching": round(
                            sig_b.relative_graph_features.branching_rank,
                            6,
                        ),
                    },
                    "lexical_token_count": len(sig_b.lexical_tokens),
                    "has_statement_text": sig_b.has_statement_text,
                },
            }
        )

    candidate_rows: list[dict[str, Any]] = []
    for theorem_a, candidates in sorted(top_for_a.items()):
        candidate_rows.append(
            {
                "theorem_a": theorem_a,
                "candidates": [
                    {
                        "theorem_b": cand.theorem_b,
                        "distance": round(cand.distance, 6),
                        "proof_support": {
                            "a": cand.proof_count_a,
                            "b": cand.proof_count_b,
                        },
                        "distance_components": {
                            "graph": round(cand.representative_pair.graph_distance, 6),
                            "lexical": round(cand.representative_pair.lexical_distance, 6),
                            "connective": round(cand.representative_pair.connective_distance, 6),
                        },
                        "graph_kind_b": cand.representative_pair.graph_kind_b,
                        "cross_kind": cand.representative_pair.cross_kind,
                        "lexical_overlap": round(cand.representative_pair.lexical_overlap, 6),
                        "representative_pair": {
                            "proof_id_a": cand.representative_pair.proof_id_a,
                            "proof_id_b": cand.representative_pair.proof_id_b,
                            "variant_a": cand.representative_pair.variant_a,
                            "variant_b": cand.representative_pair.variant_b,
                        },
                        "nearest_neighbor_stats": cand.nearest_neighbor_stats,
                    }
                    for cand in candidates
                ],
            }
        )

    if chosen:
        mean_distance = sum(p.distance for p in chosen) / len(chosen)
        mean_graph_distance = (
            sum(p.representative_pair.graph_distance for p in chosen) / len(chosen)
        )
        mean_lexical_distance = (
            sum(p.representative_pair.lexical_distance for p in chosen) / len(chosen)
        )
        mean_connective_distance = (
            sum(p.representative_pair.connective_distance for p in chosen) / len(chosen)
        )
        mean_lexical_overlap = (
            sum(p.representative_pair.lexical_overlap for p in chosen) / len(chosen)
        )
    else:
        mean_distance = None
        mean_graph_distance = None
        mean_lexical_distance = None
        mean_connective_distance = None
        mean_lexical_overlap = None

    top1_targets = [cands[0].theorem_b for cands in top_for_a.values() if cands]
    top1_unique_rate = (len(set(top1_targets)) / len(top1_targets)) if top1_targets else None

    run_a_statement_coverage = sum(1 for sig in a if sig.has_statement_text) / len(a)
    run_b_statement_coverage = sum(1 for sig in b if sig.has_statement_text) / len(b)
    run_a_lexical_coverage = sum(1 for sig in a if sig.lexical_tokens) / len(a)
    run_b_lexical_coverage = sum(1 for sig in b if sig.lexical_tokens) / len(b)
    run_a_kind_dist = graph_kind_distribution(sig.proof_ir for sig in a)
    run_b_kind_dist = graph_kind_distribution(sig.proof_ir for sig in b)

    return {
        "schema_version": 5,
        "run_a": str(run_a_dir.resolve()),
        "run_b": str(run_b_dir.resolve()),
        "solved_only": solved_only,
        "one_to_one": one_to_one,
        "top_k": top_k,
        "proof_aggregation": normalized_aggregation,
        "max_proofs_per_theorem": max_proofs_per_theorem,
        "graph_sources": {
            "run_a": _normalize_graph_source(graph_source_a),
            "run_b": _normalize_graph_source(graph_source_b),
        },
        "name_obfuscation": {
            "mode": obfuscation.mode,
            "salt": obfuscation.salt,
        },
        "lexical_ablation": {
            "mode": lexical_ablation.mode,
        },
        "run_a_theorems": len(a_groups),
        "run_b_theorems": len(b_groups),
        "run_a_proofs": len(a),
        "run_b_proofs": len(b),
        "matches": match_rows,
        "candidates_by_theorem_a": candidate_rows,
        "summary": {
            "matches": len(match_rows),
            "mean_distance": round(mean_distance, 6) if mean_distance is not None else None,
            "mean_graph_distance": (
                round(mean_graph_distance, 6) if mean_graph_distance is not None else None
            ),
            "mean_lexical_distance": (
                round(mean_lexical_distance, 6) if mean_lexical_distance is not None else None
            ),
            "mean_connective_distance": (
                round(mean_connective_distance, 6)
                if mean_connective_distance is not None
                else None
            ),
            "mean_lexical_overlap": (
                round(mean_lexical_overlap, 6) if mean_lexical_overlap is not None else None
            ),
            "reciprocal_top1_rate": (
                round(reciprocal_count / len(match_rows), 6) if match_rows else None
            ),
            "shape_hash_equal_rate": (
                round(shape_equal_count / len(match_rows), 6) if match_rows else None
            ),
            "cross_kind_rate": (
                round(cross_kind_count / len(match_rows), 6) if match_rows else None
            ),
            "kind_pair_distribution": {
                key: kind_pair_counts[key] for key in sorted(kind_pair_counts.keys())
            },
            "top1_unique_rate": (
                round(top1_unique_rate, 6) if top1_unique_rate is not None else None
            ),
            "run_a_statement_coverage": round(run_a_statement_coverage, 6),
            "run_b_statement_coverage": round(run_b_statement_coverage, 6),
            "run_a_lexical_coverage": round(run_a_lexical_coverage, 6),
            "run_b_lexical_coverage": round(run_b_lexical_coverage, 6),
            "run_a_graph_kind_distribution": run_a_kind_dist,
            "run_b_graph_kind_distribution": run_b_kind_dist,
        },
    }
