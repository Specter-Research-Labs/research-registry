from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb

from analysis.logs import read_json, read_json_gz, sha256_file
from prover.proof import (
    GRAPH_FAMILY_EXTERNAL_PROOF,
    GRAPH_FAMILY_SEARCH_TRACE,
    normalize_graph_family,
)
from prover.providers.base import tactic_family

_GRAPH_KINDS = {"graph", "proof_graph", "search_trace_graph"}
_MCTS_TREE_KINDS = {"mcts_tree"}

_CLASSIFIERS: list[tuple[str, str]] = [
    ("_search_trace_graph.json.gz", "search_trace_graph"),
    ("_search_trace_graph.json", "search_trace_graph"),
    ("_proof_graph.json.gz", "proof_graph"),
    ("_proof_graph.json", "proof_graph"),
    ("_graph.json.gz", "graph"),
    ("_graph.json", "graph"),
    ("_mcts_trace.jsonl.gz", "mcts_trace"),
    ("_mcts_trace.jsonl", "mcts_trace"),
    ("_mcts_tree.json.gz", "mcts_tree"),
    ("_mcts_tree.json", "mcts_tree"),
    ("_history.json.gz", "history"),
    ("_history.json", "history"),
    ("_assembly.json.gz", "assembly"),
    ("_assembly.json", "assembly"),
    ("_process_trace.json.gz", "process_trace"),
    ("_process_trace.json", "process_trace"),
    ("_proof_term.json.gz", "proof_term"),
    ("_proof_term.json", "proof_term"),
    ("_comparison.json.gz", "comparison"),
    ("_comparison.json", "comparison"),
    ("_metrics.json.gz", "metrics"),
    ("_metrics.json", "metrics"),
]


@dataclass(frozen=True)
class ArtifactCandidate:
    theorem: str
    variant: str | None
    artifact_kind: str
    rel_path: str
    abs_path: Path


@dataclass(frozen=True)
class ArtifactExtractReport:
    runs_scanned: int
    artifacts_indexed: int
    graph_files: int
    graph_nodes: int
    graph_edges: int
    trace_files: int
    trace_rows: int
    errors: list[str]


def _is_jsonish(name: str) -> bool:
    return name.endswith((".json", ".json.gz", ".jsonl", ".jsonl.gz"))


def _classify_theorem_artifact(path: Path) -> tuple[str, str | None] | None:
    name = path.name
    if name in {"basin_analysis.json", "basin_analysis.json.gz"}:
        return "basin_analysis", None
    for suffix, kind in _CLASSIFIERS:
        if not name.endswith(suffix):
            continue
        variant = name[: -len(suffix)]
        return kind, variant or None
    if _is_jsonish(name):
        return "other_json", None
    return None


def _iter_theorem_artifacts(run_dir: Path) -> Iterable[ArtifactCandidate]:
    for theorem_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        theorem = theorem_dir.name
        if theorem.startswith(".") or theorem.startswith("provider="):
            continue
        for path in sorted(p for p in theorem_dir.rglob("*") if p.is_file()):
            if any(part.startswith(".") for part in path.relative_to(theorem_dir).parts):
                continue
            classified = _classify_theorem_artifact(path)
            if classified is None:
                continue
            artifact_kind, variant = classified
            rel_path = path.relative_to(run_dir).as_posix()
            yield ArtifactCandidate(
                theorem=theorem,
                variant=variant,
                artifact_kind=artifact_kind,
                rel_path=rel_path,
                abs_path=path,
            )


def _graph_kind(candidate: ArtifactCandidate, payload: dict[str, Any]) -> str:
    raw_family = payload.get("graph_family")
    if isinstance(raw_family, str) and raw_family.strip():
        return normalize_graph_family(raw_family.strip())
    raw = payload.get("graph_kind")
    if isinstance(raw, str) and raw.strip():
        return normalize_graph_family(raw.strip())
    if candidate.artifact_kind == "proof_graph":
        return GRAPH_FAMILY_EXTERNAL_PROOF
    if candidate.artifact_kind == "search_trace_graph":
        return GRAPH_FAMILY_SEARCH_TRACE
    return GRAPH_FAMILY_SEARCH_TRACE


def _read_json_auto(path: Path) -> Any:
    if path.name.endswith(".gz"):
        return read_json_gz(path)
    return read_json(path)


def _parse_graph_nodes(
    *,
    payload: dict[str, Any],
) -> list[tuple[str, str | None, bool | None, dict[str, Any] | None]]:
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("graph.nodes must be a list")
    dedup: dict[str, tuple[str | None, bool | None, dict[str, Any] | None]] = {}
    for node in raw_nodes:
        node_id: str | None = None
        attrs: dict[str, Any] | None = None
        if isinstance(node, dict):
            node_id_raw = node.get("id")
            if isinstance(node_id_raw, str) and node_id_raw:
                node_id = node_id_raw
                attrs = {k: v for k, v in node.items() if k != "id"}
        elif (
            isinstance(node, list)
            and len(node) == 2
            and isinstance(node[0], str)
            and isinstance(node[1], dict)
        ):
            node_id = node[0]
            attrs = dict(node[1])
        if node_id is None:
            raise ValueError(f"graph node missing id: {node!r}")
        attrs_obj = attrs or {}
        goal_sig = attrs_obj.get("goal_sig")
        in_proof = attrs_obj.get("in_proof")
        dedup[node_id] = (
            goal_sig if isinstance(goal_sig, str) else None,
            in_proof if isinstance(in_proof, bool) else None,
            attrs or None,
        )
    rows: list[tuple[str, str | None, bool | None, dict[str, Any] | None]] = []
    for node_id in sorted(dedup.keys()):
        goal_sig, in_proof, attrs = dedup[node_id]
        rows.append((node_id, goal_sig, in_proof, attrs))
    return rows


def _parse_graph_edges(
    *,
    payload: dict[str, Any],
) -> list[tuple[int, str, str, str | None, str | None, bool | None, dict[str, Any] | None]]:
    raw_edges = payload.get("edges")
    if not isinstance(raw_edges, list):
        raise ValueError("graph.edges must be a list")
    rows: list[
        tuple[int, str, str, str | None, str | None, bool | None, dict[str, Any] | None]
    ] = []
    for idx, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            raise ValueError(f"graph edge must be object: {edge!r}")
        src = edge.get("source")
        if not isinstance(src, str) or not src:
            src = edge.get("src")
        dst = edge.get("target")
        if not isinstance(dst, str) or not dst:
            dst = edge.get("dst")
        if not isinstance(src, str) or not src or not isinstance(dst, str) or not dst:
            raise ValueError(f"graph edge missing source/target: {edge!r}")

        attrs = {
            k: v
            for k, v in edge.items()
            if k not in {"source", "target", "src", "dst"}
        }
        tactic = attrs.get("tactic")
        if not isinstance(tactic, str) or not tactic.strip():
            tactic = attrs.get("tactic_norm")
        if not isinstance(tactic, str) or not tactic.strip():
            tactic = attrs.get("action_norm")
        tactic_out = tactic if isinstance(tactic, str) and tactic.strip() else None

        fam = attrs.get("tactic_family")
        if not isinstance(fam, str) or not fam.strip():
            fam = attrs.get("action_family")
        family_out = fam if isinstance(fam, str) and fam.strip() else None
        if family_out is None and tactic_out is not None:
            family_out = tactic_family(tactic_out)

        in_proof = attrs.get("in_proof")
        rows.append(
            (
                idx,
                src,
                dst,
                tactic_out,
                family_out,
                in_proof if isinstance(in_proof, bool) else None,
                attrs or None,
            )
        )
    return rows


def _parse_mcts_tree(
    *,
    payload: dict[str, Any],
) -> tuple[
    list[tuple[str, str | None, str | None, int, int, int, bool, bool, int | None]],
    list[tuple[str, str, str, int]],
]:
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, dict):
        raise ValueError("mcts_tree.nodes must be a dict")

    node_rows: list[
        tuple[str, str | None, str | None, int, int, int, bool, bool, int | None]
    ] = []
    edge_rows: list[tuple[str, str, str, int]] = []

    for mvar_id, node in raw_nodes.items():
        if not isinstance(node, dict):
            raise ValueError(f"mcts_tree node must be object: {mvar_id}")
        node_rows.append((
            mvar_id,
            node.get("goal_type") if isinstance(node.get("goal_type"), str) else None,
            node.get("goal_sig") if isinstance(node.get("goal_sig"), str) else None,
            int(node.get("depth", 0)),
            int(node.get("visit_count", 0)),
            int(node.get("success_count", 0)),
            bool(node.get("is_terminal", False)),
            bool(node.get("is_dead", False)),
            int(node["expansion_order"])
            if isinstance(node.get("expansion_order"), int)
            else None,
        ))

        children = node.get("children", {})
        if isinstance(children, dict):
            edge_order = 0
            for tactic, child_ids in children.items():
                if not isinstance(child_ids, list):
                    child_ids = [child_ids]
                for child_id in child_ids:
                    if isinstance(child_id, str):
                        edge_rows.append((mvar_id, child_id, tactic, edge_order))
                        edge_order += 1

    node_rows.sort(key=lambda r: (r[3], r[0]))
    return node_rows, edge_rows


def _open_jsonl(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _summarize_mcts_trace(path: Path) -> dict[str, Any]:
    line_count = 0
    bad_json_lines = 0
    event_count = 0
    iteration_event_count = 0
    tactic_attempt_event_count = 0
    max_iteration: int | None = None
    unique_mvars: set[str] = set()
    candidate_total = 0
    candidate_max = 0
    event_counts: dict[str, int] = {}

    with _open_jsonl(path) as f:
        for raw_line in f:
            line_count += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad_json_lines += 1
                continue
            if not isinstance(record, dict):
                continue

            event = record.get("event")
            if not isinstance(event, str) or not event:
                event = "_unknown"
            event_count += 1
            event_counts[event] = event_counts.get(event, 0) + 1

            if event == "iteration":
                iteration_event_count += 1
                it = record.get("iteration")
                if isinstance(it, int) and not isinstance(it, bool):
                    max_iteration = it if max_iteration is None else max(max_iteration, it)
                node = record.get("node")
                if isinstance(node, dict):
                    mvar = node.get("mvar_id")
                    if isinstance(mvar, str) and mvar:
                        unique_mvars.add(mvar)
                tactics = record.get("tactics")
                if isinstance(tactics, list):
                    n = sum(1 for item in tactics if isinstance(item, dict))
                    candidate_total += n
                    candidate_max = max(candidate_max, n)
            elif event == "tactic_attempt":
                tactic_attempt_event_count += 1
                mvar = record.get("mvar_id")
                if isinstance(mvar, str) and mvar:
                    unique_mvars.add(mvar)

    return {
        "line_count": line_count,
        "bad_json_lines": bad_json_lines,
        "event_count": event_count,
        "iteration_event_count": iteration_event_count,
        "tactic_attempt_event_count": tactic_attempt_event_count,
        "max_iteration": max_iteration,
        "unique_mvar_count": len(unique_mvars),
        "candidate_total": candidate_total,
        "candidate_max": candidate_max,
        "event_counts": event_counts,
    }


def _get_extract_state(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_key: str,
    rel_path: str,
    extractor: str,
) -> tuple[str, bool] | None:
    row = conn.execute(
        """
        SELECT sha256, parse_ok
        FROM artifact_extract_state
        WHERE run_key = ? AND rel_path = ? AND extractor = ?
        """,
        [run_key, rel_path, extractor],
    ).fetchone()
    if row is None:
        return None
    sha, parse_ok = row
    if not isinstance(sha, str) or not isinstance(parse_ok, bool):
        return None
    return sha, parse_ok


def _set_extract_state(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_key: str,
    rel_path: str,
    extractor: str,
    sha256: str,
    parse_ok: bool,
) -> None:
    conn.execute(
        "DELETE FROM artifact_extract_state WHERE run_key = ? AND rel_path = ? AND extractor = ?",
        [run_key, rel_path, extractor],
    )
    conn.execute(
        """
        INSERT INTO artifact_extract_state(run_key, rel_path, extractor, sha256, parse_ok)
        VALUES (?, ?, ?, ?, ?)
        """,
        [run_key, rel_path, extractor, sha256, parse_ok],
    )


def _cleanup_stale_extractor_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_key: str,
    extractor: str,
    current_paths: set[str],
) -> None:
    rows = conn.execute(
        """
        SELECT rel_path
        FROM artifact_extract_state
        WHERE run_key = ? AND extractor = ?
        """,
        [run_key, extractor],
    ).fetchall()
    stale = [rel for (rel,) in rows if isinstance(rel, str) and rel not in current_paths]
    for rel_path in stale:
        conn.execute(
            (
                "DELETE FROM artifact_extract_state "
                "WHERE run_key = ? AND rel_path = ? AND extractor = ?"
            ),
            [run_key, rel_path, extractor],
        )
        if extractor == "graph":
            conn.execute(
                "DELETE FROM graph_nodes WHERE run_key = ? AND rel_path = ?",
                [run_key, rel_path],
            )
            conn.execute(
                "DELETE FROM graph_edges WHERE run_key = ? AND rel_path = ?",
                [run_key, rel_path],
            )
        elif extractor == "mcts_trace":
            conn.execute(
                "DELETE FROM mcts_trace_stats WHERE run_key = ? AND rel_path = ?",
                [run_key, rel_path],
            )
        elif extractor == "mcts_tree":
            conn.execute(
                "DELETE FROM mcts_tree_nodes WHERE run_key = ? AND rel_path = ?",
                [run_key, rel_path],
            )
            conn.execute(
                "DELETE FROM mcts_tree_edges WHERE run_key = ? AND rel_path = ?",
                [run_key, rel_path],
            )


def _insert_artifact_rows(
    conn: duckdb.DuckDBPyConnection,
    *,
    rows: list[tuple[str, str, str | None, str, str, str | None, int, int, str]],
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO theorem_artifacts(
          run_key, theorem, variant, artifact_kind, rel_path,
          sha256, bytes, mtime_epoch, parse_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def extract_artifact_facts(
    conn: duckdb.DuckDBPyConnection,
    *,
    root_dir: Path,
    run_rows: list[tuple[str, str]],  # (run_key, rel_run_dir)
) -> ArtifactExtractReport:
    runs_scanned = 0
    artifacts_indexed = 0
    graph_files = 0
    graph_nodes = 0
    graph_edges = 0
    trace_files = 0
    trace_rows = 0
    errors: list[str] = []

    for run_key, rel in run_rows:
        run_dir = (root_dir / rel).resolve()
        if not run_dir.exists():
            continue
        runs_scanned += 1

        graph_paths: set[str] = set()
        trace_paths: set[str] = set()
        mcts_tree_paths: set[str] = set()
        artifact_rows: list[tuple[str, str, str | None, str, str, str | None, int, int, str]] = []

        conn.begin()
        conn.execute("DELETE FROM theorem_artifacts WHERE run_key = ?", [run_key])
        conn.execute("DELETE FROM graph_extract_errors WHERE run_key = ?", [run_key])
        for cand in _iter_theorem_artifacts(run_dir):
            sha = sha256_file(cand.abs_path)
            if not isinstance(sha, str):
                continue
            st = cand.abs_path.stat()
            parse_status = "indexed"

            if cand.artifact_kind in _GRAPH_KINDS:
                graph_paths.add(cand.rel_path)
                graph_files += 1
                state = _get_extract_state(
                    conn,
                    run_key=run_key,
                    rel_path=cand.rel_path,
                    extractor="graph",
                )
                if state is not None and state[0] == sha and state[1]:
                    parse_status = "skipped_unchanged"
                else:
                    conn.execute(
                        "DELETE FROM graph_nodes WHERE run_key = ? AND rel_path = ?",
                        [run_key, cand.rel_path],
                    )
                    conn.execute(
                        "DELETE FROM graph_edges WHERE run_key = ? AND rel_path = ?",
                        [run_key, cand.rel_path],
                    )
                    try:
                        payload = _read_json_auto(cand.abs_path)
                        if not isinstance(payload, dict):
                            raise ValueError("graph payload must be object")
                        graph_kind = _graph_kind(cand, payload)
                        node_rows = _parse_graph_nodes(payload=payload)
                        edge_rows = _parse_graph_edges(payload=payload)
                        for node_id, goal_sig, in_proof, attrs in node_rows:
                            conn.execute(
                                """
                                INSERT INTO graph_nodes(
                                  run_key, theorem, variant, graph_kind, rel_path,
                                  node_id, goal_sig, in_proof, attrs_json, source_sha256
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                [
                                    run_key,
                                    cand.theorem,
                                    cand.variant,
                                    graph_kind,
                                    cand.rel_path,
                                    node_id,
                                    goal_sig,
                                    in_proof,
                                    json.dumps(attrs) if attrs is not None else None,
                                    sha,
                                ],
                            )
                        for (
                            edge_idx,
                            src,
                            dst,
                            tactic,
                            family,
                            in_proof,
                            attrs,
                        ) in edge_rows:
                            conn.execute(
                                """
                                INSERT INTO graph_edges(
                                  run_key, theorem, variant, graph_kind, rel_path,
                                  edge_idx, src_node_id, dst_node_id,
                                  tactic, tactic_family, in_proof, attrs_json, source_sha256
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                [
                                    run_key,
                                    cand.theorem,
                                    cand.variant,
                                    graph_kind,
                                    cand.rel_path,
                                    edge_idx,
                                    src,
                                    dst,
                                    tactic,
                                    family,
                                    in_proof,
                                    json.dumps(attrs) if attrs is not None else None,
                                    sha,
                                ],
                            )
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="graph",
                            sha256=sha,
                            parse_ok=True,
                        )
                        parse_status = "parsed"
                        graph_nodes += len(node_rows)
                        graph_edges += len(edge_rows)
                    except Exception as exc:
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="graph",
                            sha256=sha,
                            parse_ok=False,
                        )
                        conn.execute(
                            """
                            INSERT INTO graph_extract_errors(
                              run_key, theorem, variant, rel_path, stage, error
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            [
                                run_key,
                                cand.theorem,
                                cand.variant,
                                cand.rel_path,
                                "parse_graph",
                                f"{type(exc).__name__}: {exc}",
                            ],
                        )
                        errors.append(
                            f"{rel}: parse_graph: {cand.rel_path}: {type(exc).__name__}: {exc}"
                        )
                        parse_status = "parse_error"

            elif cand.artifact_kind == "mcts_trace":
                trace_paths.add(cand.rel_path)
                trace_files += 1
                state = _get_extract_state(
                    conn,
                    run_key=run_key,
                    rel_path=cand.rel_path,
                    extractor="mcts_trace",
                )
                if state is not None and state[0] == sha and state[1]:
                    parse_status = "trace_skipped_unchanged"
                else:
                    conn.execute(
                        "DELETE FROM mcts_trace_stats WHERE run_key = ? AND rel_path = ?",
                        [run_key, cand.rel_path],
                    )
                    try:
                        summary = _summarize_mcts_trace(cand.abs_path)
                        conn.execute(
                            """
                            INSERT INTO mcts_trace_stats(
                              run_key, theorem, variant, rel_path, source_sha256,
                              line_count, bad_json_lines, event_count, iteration_event_count,
                              tactic_attempt_event_count, max_iteration, unique_mvar_count,
                              candidate_total, candidate_max, event_counts_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                run_key,
                                cand.theorem,
                                cand.variant,
                                cand.rel_path,
                                sha,
                                int(summary["line_count"]),
                                int(summary["bad_json_lines"]),
                                int(summary["event_count"]),
                                int(summary["iteration_event_count"]),
                                int(summary["tactic_attempt_event_count"]),
                                int(summary["max_iteration"])
                                if isinstance(summary["max_iteration"], int)
                                else None,
                                int(summary["unique_mvar_count"]),
                                int(summary["candidate_total"]),
                                int(summary["candidate_max"]),
                                json.dumps(summary["event_counts"]),
                            ],
                        )
                        if iteration_rows:
                            conn.executemany(
                                """
                                INSERT OR REPLACE INTO mcts_controller_iterations(
                                  run_key, theorem, variant, rel_path,
                                  iteration, event, reason, tier, budget,
                                  selected_path_json, node_mvar_id, node_goal_sig,
                                  node_goal_sig_strict, node_goal_type,
                                  node_visit_count, node_success_count, node_depth,
                                  node_is_terminal, node_is_dead,
                                  candidate_count, attempt_count,
                                  candidates_json, attempts_json,
                                  expanded, terminal_reached, backprop_success, agent_id,
                                  tree_nodes, tree_expansions, tree_max_depth,
                                  tree_solved, tree_aborted, tree_inflight,
                                  block_json, delay_json, reroute_json,
                                  source_sha256
                                ) VALUES (
                                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                                )
                                """,
                                [
                                    (
                                        run_key,
                                        cand.theorem,
                                        cand.variant,
                                        cand.rel_path,
                                        *row,
                                        sha,
                                    )
                                    for row in iteration_rows
                                ],
                            )
                        _insert_mcts_controller_metrics(
                            conn,
                            run_key=run_key,
                            theorem=cand.theorem,
                            variant=cand.variant,
                            rel_path=cand.rel_path,
                            source_sha256=sha,
                        )
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="mcts_trace",
                            sha256=sha,
                            parse_ok=True,
                        )
                        parse_status = "trace_summarized"
                        trace_rows += 1
                    except Exception as exc:
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="mcts_trace",
                            sha256=sha,
                            parse_ok=False,
                        )
                        conn.execute(
                            "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                            [
                                run_key,
                                "read_mcts_trace",
                                f"{cand.rel_path}: {type(exc).__name__}: {exc}",
                            ],
                        )
                        errors.append(
                            f"{rel}: read_mcts_trace: {cand.rel_path}: {type(exc).__name__}: {exc}"
                        )
                        parse_status = "trace_error"

            elif cand.artifact_kind in _MCTS_TREE_KINDS:
                mcts_tree_paths.add(cand.rel_path)
                state = _get_extract_state(
                    conn,
                    run_key=run_key,
                    rel_path=cand.rel_path,
                    extractor="mcts_tree",
                )
                if state is not None and state[0] == sha and state[1]:
                    parse_status = "mcts_tree_skipped_unchanged"
                else:
                    conn.execute(
                        "DELETE FROM mcts_tree_nodes WHERE run_key = ? AND rel_path = ?",
                        [run_key, cand.rel_path],
                    )
                    conn.execute(
                        "DELETE FROM mcts_tree_edges WHERE run_key = ? AND rel_path = ?",
                        [run_key, cand.rel_path],
                    )
                    try:
                        payload = _read_json_auto(cand.abs_path)
                        if not isinstance(payload, dict):
                            raise ValueError("mcts_tree payload must be object")
                        tree_node_rows, tree_edge_rows = _parse_mcts_tree(
                            payload=payload,
                        )
                        for (
                            mvar_id,
                            goal_type,
                            goal_sig,
                            depth,
                            visit_count,
                            success_count,
                            is_terminal,
                            is_dead,
                            expansion_order,
                        ) in tree_node_rows:
                            conn.execute(
                                """
                                INSERT INTO mcts_tree_nodes(
                                  run_key, theorem, variant, rel_path,
                                  mvar_id, goal_type, goal_sig, depth,
                                  visit_count, success_count, is_terminal, is_dead,
                                  expansion_order, source_sha256
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                [
                                    run_key,
                                    cand.theorem,
                                    cand.variant,
                                    cand.rel_path,
                                    mvar_id,
                                    goal_type,
                                    goal_sig,
                                    depth,
                                    visit_count,
                                    success_count,
                                    is_terminal,
                                    is_dead,
                                    expansion_order,
                                    sha,
                                ],
                            )
                        for (
                            parent_mvar_id,
                            child_mvar_id,
                            tactic,
                            edge_order,
                        ) in tree_edge_rows:
                            conn.execute(
                                """
                                INSERT INTO mcts_tree_edges(
                                  run_key, theorem, variant, rel_path,
                                  parent_mvar_id, child_mvar_id, tactic, edge_order,
                                  source_sha256
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                [
                                    run_key,
                                    cand.theorem,
                                    cand.variant,
                                    cand.rel_path,
                                    parent_mvar_id,
                                    child_mvar_id,
                                    tactic,
                                    edge_order,
                                    sha,
                                ],
                            )
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="mcts_tree",
                            sha256=sha,
                            parse_ok=True,
                        )
                        parse_status = "mcts_tree_parsed"
                    except Exception as exc:
                        _set_extract_state(
                            conn,
                            run_key=run_key,
                            rel_path=cand.rel_path,
                            extractor="mcts_tree",
                            sha256=sha,
                            parse_ok=False,
                        )
                        errors.append(
                            f"{rel}: parse_mcts_tree: {cand.rel_path}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        parse_status = "mcts_tree_error"

            artifact_rows.append(
                (
                    run_key,
                    cand.theorem,
                    cand.variant,
                    cand.artifact_kind,
                    cand.rel_path,
                    sha,
                    int(st.st_size),
                    int(st.st_mtime),
                    parse_status,
                )
            )
            artifacts_indexed += 1

        _cleanup_stale_extractor_rows(
            conn,
            run_key=run_key,
            extractor="graph",
            current_paths=graph_paths,
        )
        _cleanup_stale_extractor_rows(
            conn,
            run_key=run_key,
            extractor="mcts_trace",
            current_paths=trace_paths,
        )
        _cleanup_stale_extractor_rows(
            conn,
            run_key=run_key,
            extractor="mcts_tree",
            current_paths=mcts_tree_paths,
        )
        _insert_artifact_rows(conn, rows=artifact_rows)
        conn.commit()

    return ArtifactExtractReport(
        runs_scanned=runs_scanned,
        artifacts_indexed=artifacts_indexed,
        graph_files=graph_files,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        trace_files=trace_files,
        trace_rows=trace_rows,
        errors=errors,
    )
