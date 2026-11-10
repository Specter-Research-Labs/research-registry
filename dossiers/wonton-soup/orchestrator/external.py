from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from leantree.repl_adapter.error_metadata import build_error_record

from atp.coq.process_trace import CoqProcessTrace, process_trace_to_graph, replay_theorem_block
from atp.coq.runner import CoqConfig, _exec_sentences
from atp.coq.sentences import split_coq_sentences
from atp.coq.serapi import SerapiSession, extract_constr_sexpr, extract_feedback_strings
from atp.coq.source import CoqTheoremBlock, collect_theorem_blocks, index_theorem_blocks
from atp.coq.stdlib import module_to_path
from atp.coq.terms import coq_constr_to_dag, proof_graph_from_dag
from atp.log_writer import ExternalProof, ExternalRunWriter, ExternalTheoremResult
from corpus.artifacts import timestamp, write_json_atomic
from corpus.selection import select_items
from prover.proof import ProofGraph
from runtime_paths import sync_logs_to_remote

ExternalProgressCallback = Callable[[dict[str, Any]], None]
_MISSING = object()


def _sync_run_dir_to_remote(log_dir: Path, *, reason: str) -> None:
    report = sync_logs_to_remote(log_dir, require_src=False)
    if report is None:
        return
    logging.getLogger(__name__).info(
        (
            "Synced external logs to remote: src=%s dst=%s copied=%s skipped=%s "
            "bytes=%s reason=%s"
        ),
        report.src_root,
        report.dst_root,
        report.copied_files,
        report.skipped_files,
        report.copied_bytes,
        reason,
    )


def _patch_run_status(log_dir: Path, progress: dict[str, Any]) -> None:
    status_path = log_dir / "run_status.json"
    if not status_path.exists():
        return
    try:
        data = json.loads(status_path.read_text())
    except Exception:
        return
    if not isinstance(data, dict):
        return
    data["progress"] = progress
    write_json_atomic(status_path, data)


def _write_latest_run(run_dir: Path, provider: str) -> None:
    from orchestrator import lean as _lean_runtime

    _lean_runtime._write_latest_run(run_dir, [provider], provider, False)


def _selection_payload(
    *,
    selection_meta: Any,
    offset: int,
    sample: int | None,
    selected_items: list[str],
    selected_key: str,
    limit: Any = _MISSING,
) -> dict[str, Any]:
    payload = {
        "method": selection_meta.method,
        "offset": offset,
        "sample": sample,
        "seed": selection_meta.seed,
        "selected_count": len(selected_items),
        selected_key: selected_items,
    }
    if limit is not _MISSING:
        payload["limit"] = limit
    return payload


def _start_external_run(
    *,
    log_dir: Path,
    run_config: dict[str, Any],
    goal_sig_scheme: str,
    provider: str,
) -> ExternalRunWriter:
    writer = ExternalRunWriter(log_dir, run_config, goal_sig_scheme=goal_sig_scheme)
    writer.write_run_status(status="running", started_at=timestamp())
    _write_latest_run(log_dir, provider=provider)
    return writer


ItemProcessor = Callable[[Any], tuple[ExternalProof, str | None]]

RECENT_BUFFER_SIZE = 48


def _escape_vernac(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _extract_statement_from_check_message(message: str, theorem: str) -> str | None:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return None

    theorem_re = re.escape(theorem)
    joined = " ".join(lines)
    match = re.match(rf"^{theorem_re}\s*:\s*(.+)$", joined)
    if match:
        stmt = match.group(1).strip()
        return stmt or None

    if lines[0] == theorem and len(lines) >= 2:
        second = lines[1]
        if second.startswith(":"):
            stmt = second[1:].strip()
            return stmt or None
    return None


def _query_coq_statement_text(session: SerapiSession, theorem: str) -> str | None:
    responses = session.send(f'(Query () (Vernac "Check {_escape_vernac(theorem)}."))')
    for message in extract_feedback_strings(responses):
        statement = _extract_statement_from_check_message(message, theorem)
        if statement:
            return statement
    return None


def _parse_coqtop_check_output(output: str, theorem_order: list[str]) -> dict[str, str]:
    lines = output.splitlines()
    theorem_set = set(theorem_order)
    parsed: dict[str, str] = {}
    current_theorem: str | None = None
    current_parts: list[str] = []

    def flush_current() -> None:
        if current_theorem is None:
            return
        if not current_parts:
            return
        parsed[current_theorem] = " ".join(part for part in current_parts if part)

    for raw in lines:
        stripped = raw.strip()
        if stripped in theorem_set:
            flush_current()
            current_theorem = stripped
            current_parts = []
            continue
        if current_theorem is None:
            continue
        if raw.lstrip().startswith(":"):
            current_parts.append(raw.split(":", 1)[1].strip())
        elif current_parts and (raw.startswith(" ") or raw.startswith("\t")):
            current_parts.append(stripped)
        elif current_parts and stripped:
            current_parts.append(stripped)

    flush_current()
    return {theorem: parsed[theorem] for theorem in theorem_order if theorem in parsed}


def _query_coqtop_statement_map(
    *,
    prelude: str,
    theorems: list[str],
    coqtop_binary: str = "coqtop",
) -> dict[str, str]:
    if not theorems:
        return {}

    script = prelude.rstrip() + "\n"
    for theorem in theorems:
        script += f"Check {theorem}.\n"

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".v",
            encoding="utf-8",
            delete=False,
        ) as handle:
            handle.write(script)
            tmp_path = Path(handle.name)

        completed = subprocess.run(
            [coqtop_binary, "-quiet", "-batch", "-l", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logging.getLogger(__name__).warning(
            "coqtop binary not found for statement extraction fallback: %s",
            coqtop_binary,
        )
        return {}
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "coqtop statement extraction failed to start: %s",
            exc,
        )
        return {}
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        logging.getLogger(__name__).warning(
            "coqtop statement extraction failed: code=%s stderr=%s",
            completed.returncode,
            stderr[:240],
        )
        return {}
    return _parse_coqtop_check_output(completed.stdout or "", theorems)


def _coq_source_block_lookup(blocks: list[CoqTheoremBlock]) -> dict[str, CoqTheoremBlock]:
    lookup: dict[str, CoqTheoremBlock] = {}
    by_basename: dict[str, list[CoqTheoremBlock]] = {}
    for block in blocks:
        lookup[block.qualname] = block
        basename = block.qualname.rsplit(".", 1)[-1]
        by_basename.setdefault(basename, []).append(block)
    for basename, matches in by_basename.items():
        if len(matches) == 1:
            lookup.setdefault(basename, matches[0])
    return lookup


def _replay_coq_trace(
    block: CoqTheoremBlock,
    *,
    config: CoqConfig,
) -> tuple[CoqProcessTrace, ProofGraph] | tuple[None, None]:
    if not block.replayable:
        return None, None
    session = SerapiSession(config.serapi)
    try:
        process_trace = replay_theorem_block(
            session,
            theorem=block.qualname,
            source_path=block.source_path,
            prelude_sentences=list(block.prelude_sentences),
            block_sentences=list(block.block_sentences),
        )
    finally:
        session.close()
    return process_trace, process_trace_to_graph(process_trace)


def _base_run_config(
    log_dir: Path,
    *,
    provider: str,
    corpus: str,
    limit: int | None,
    offset: int,
    sample: int | None,
    seed: int | None,
    binary: str,
    extra_args: list[str],
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "format_version": 2, "run_id": log_dir.name, "log_dir": str(log_dir),
        "created_at": timestamp(), "provider": provider, "mode": "external",
        "corpus": corpus, "limit": limit, "offset": offset, "sample": sample,
        "seed": seed, "binary": binary, "extra_args": extra_args,
    }
    if timeout_sec is not None:
        cfg["timeout_sec"] = timeout_sec
    return cfg


def _base_progress_state(
    *, backend: str, provider: str, corpus: str, total: int, **extra: Any,
) -> dict[str, Any]:
    return {
        "backend": backend, "provider": provider, "corpus": corpus,
        "total": total, "completed": 0, "solved": 0, "unsolved": 0,
        "crashed": 0, "timeouts": 0, "stage": None, "current": None,
        "status_counts": {}, "recent": [], "updated_at": timestamp(),
        **extra,
    }


def _run_corpus_loop(
    items: list[tuple[str, Any]],
    processor: ItemProcessor,
    *,
    backend: str,
    log_dir: Path,
    writer: ExternalRunWriter,
    progress_state: dict[str, Any],
    start_event: dict[str, Any],
    progress: ExternalProgressCallback | None = None,
) -> None:
    _patch_run_status(log_dir, progress_state)
    if progress is not None:
        progress(start_event)

    results: list[ExternalTheoremResult] = []
    crashed: list[dict[str, Any]] = []
    recent: list[str] = progress_state.get("recent", [])
    status_counts: dict[str, int] = progress_state.get("status_counts", {})

    for idx, (name, item) in enumerate(items, 1):
        progress_state["current"] = name
        progress_state["updated_at"] = timestamp()
        _patch_run_status(log_dir, progress_state)
        if progress is not None:
            progress({"event": "item_start", "idx": idx, "total": len(items), "name": name})
        try:
            proof, status = processor(item)
            results.append(ExternalTheoremResult(name=name, wild_type=proof))
            progress_state["completed"] = idx
            if proof.solved:
                progress_state["solved"] += 1
                recent.append("solved")
            else:
                progress_state["unsolved"] += 1
                recent.append("unsolved")
            del recent[:-RECENT_BUFFER_SIZE]
            if isinstance(status, str) and status:
                status_counts[status] = status_counts.get(status, 0) + 1
            progress_state["updated_at"] = timestamp()
            _patch_run_status(log_dir, progress_state)
            if progress is not None:
                progress({
                    "event": "item_end", "idx": idx, "total": len(items),
                    "name": name, "status": status, "solved": proof.solved, "error": None,
                })
        except Exception as exc:
            error_record = build_error_record(exc)
            crashed.append({"name": name, **error_record})
            progress_state["completed"] = idx
            progress_state["crashed"] += 1
            if "timed out" in str(exc):
                progress_state["timeouts"] += 1
                recent.append("timeout")
            else:
                recent.append("crashed")
            del recent[:-RECENT_BUFFER_SIZE]
            progress_state["updated_at"] = timestamp()
            _patch_run_status(log_dir, progress_state)
            if progress is not None:
                progress({
                    "event": "item_end", "idx": idx, "total": len(items),
                    "name": name,
                    "status": None,
                    "solved": False,
                    "error": error_record.get("error_summary") or error_record["error"],
                })

    writer.write_results(results, crashed=crashed)
    writer.write_run_status(
        status="completed", completed_at=timestamp(), partial_results=bool(crashed),
    )
    progress_state["current"] = None
    progress_state["updated_at"] = timestamp()
    _patch_run_status(log_dir, progress_state)
    if progress is not None:
        progress({
            "event": "end", "backend": backend, "total": len(items),
            "solved": sum(1 for r in results if r.wild_type.solved),
            "completed": len(results) + len(crashed),
            "crashed": len(crashed), "log_dir": str(log_dir),
        })


def _run_coq_query_corpus(
    *,
    corpus: str,
    log_dir: Path,
    theorems: list[str],
    offset: int,
    sample: int | None,
    seed: int | None,
    config: CoqConfig,
    corpus_meta: dict[str, Any],
    progress_state_extra: dict[str, Any],
    start_event_extra: dict[str, Any],
    load_detail: str,
    load_sentences: list[str],
    statement_prelude: str,
    theorem_blocks: dict[str, CoqTheoremBlock],
    sync_reason: str,
    progress: ExternalProgressCallback | None = None,
) -> None:
    theorems, selection_meta = select_items(
        theorems,
        lambda theorem: theorem,
        offset=offset,
        limit=None,
        sample=sample,
        seed=seed,
    )
    if not theorems:
        raise RuntimeError("No theorems selected for Coq extraction")

    run_config = _base_run_config(
        log_dir,
        provider="coq",
        corpus=corpus,
        limit=len(theorems),
        offset=offset,
        sample=sample,
        seed=selection_meta.seed,
        binary=config.serapi.binary,
        extra_args=list(config.serapi.extra_args) if config.serapi.extra_args else [],
    )
    run_config["corpus_meta"] = {
        **corpus_meta,
        "selected_count": len(theorems),
    }
    run_config["theorem_selection"] = _selection_payload(
        selection_meta=selection_meta,
        offset=offset,
        sample=sample,
        selected_items=list(theorems),
        selected_key="selected_theorems",
    )
    writer = _start_external_run(
        log_dir=log_dir,
        run_config=run_config,
        goal_sig_scheme="coq-constr",
        provider="coq",
    )

    progress_state = _base_progress_state(
        backend="coq",
        provider=config.serapi.binary,
        corpus=corpus,
        total=len(theorems),
        **progress_state_extra,
    )
    coqtop_statement_map = _query_coqtop_statement_map(
        prelude=statement_prelude,
        theorems=[str(theorem) for theorem in theorems],
    )

    session = SerapiSession(config.serapi)
    try:
        if progress is not None:
            progress({"event": "stage", "stage": "load", "detail": load_detail})
        progress_state["stage"] = f"load: {load_detail}"
        progress_state["updated_at"] = timestamp()
        _patch_run_status(log_dir, progress_state)
        _exec_sentences(session, load_sentences)

        def process(theorem: Any) -> tuple[ExternalProof, str | None]:
            theorem_name = str(theorem)
            responses = session.send(f'(Query () (Definition "{theorem_name}"))')
            constr = extract_constr_sexpr(responses)
            if constr is None:
                raise RuntimeError(f"No Coq constr found for {theorem_name}")
            dag = coq_constr_to_dag(constr)
            graph = proof_graph_from_dag(dag)
            theorem_block = theorem_blocks.get(theorem_name)
            process_trace = None
            trace_graph = None
            trace_source = None
            trace_completeness = None
            if theorem_block is not None:
                process_trace, trace_graph = _replay_coq_trace(theorem_block, config=config)
                if process_trace is not None:
                    trace_source = process_trace.trace_source
                    trace_completeness = process_trace.trace_completeness
            metrics_overrides: dict[str, Any] = {}
            statement_text = coqtop_statement_map.get(theorem_name)
            statement_source = "coqtop_check_batch" if statement_text else None
            if not statement_text:
                statement_text = _query_coq_statement_text(session, theorem_name)
                if statement_text:
                    statement_source = "serapi_check"
            if statement_text:
                metrics_overrides["statement_text"] = statement_text
                metrics_overrides["statement_source"] = statement_source
            proof = ExternalProof(
                graph=graph,
                solved=True,
                proof_term=dag,
                iterations=None,
                metrics_overrides=metrics_overrides,
                trace_graph=trace_graph,
                process_trace=process_trace,
                trace_source=trace_source,
                trace_completeness=trace_completeness,
            )
            return proof, "ok"

        _run_corpus_loop(
            [(theorem, theorem) for theorem in theorems],
            process,
            backend="coq",
            log_dir=log_dir,
            writer=writer,
            progress_state=progress_state,
            start_event={
                "event": "start",
                "backend": "coq",
                "provider": config.serapi.binary,
                "corpus": corpus,
                "total": len(theorems),
                "log_dir": str(log_dir),
                **start_event_extra,
            },
            progress=progress,
        )
    finally:
        session.close()
        _sync_run_dir_to_remote(log_dir, reason=sync_reason)


def run_coq_extraction(
    source: Path,
    log_dir: Path,
    theorems: list[str],
    *,
    offset: int = 0,
    sample: int | None = None,
    seed: int | None = None,
    config: CoqConfig | None = None,
    progress: ExternalProgressCallback | None = None,
) -> None:
    if config is None:
        config = CoqConfig()
    if not source.exists():
        raise FileNotFoundError(f"Coq source file not found: {source}")
    source_text = source.read_text(encoding="utf-8")
    _run_coq_query_corpus(
        corpus="coq",
        log_dir=log_dir,
        theorems=theorems,
        offset=offset,
        sample=sample,
        seed=seed,
        config=config,
        corpus_meta={"source": str(source)},
        progress_state_extra={"source": str(source)},
        start_event_extra={"source": str(source)},
        load_detail="exec sentences",
        load_sentences=split_coq_sentences(source_text),
        statement_prelude=source_text,
        theorem_blocks=_coq_source_block_lookup(
            collect_theorem_blocks(source_text, source_path=str(source))
        ),
        sync_reason="external-coq-file",
        progress=progress,
    )


def run_coq_import_extraction(
    imports: list[str],
    log_dir: Path,
    theorems: list[str],
    *,
    offset: int = 0,
    sample: int | None = None,
    seed: int | None = None,
    config: CoqConfig | None = None,
    corpus_meta: dict[str, Any] | None = None,
    progress: ExternalProgressCallback | None = None,
) -> None:
    if config is None:
        config = CoqConfig()
    if not imports:
        raise RuntimeError("No imports provided for Coq extraction")
    imports_prelude = "\n".join(imports).strip() + "\n"
    theorem_blocks: dict[str, CoqTheoremBlock] = {}
    stdlib_root = corpus_meta.get("stdlib_root") if isinstance(corpus_meta, dict) else None
    modules = corpus_meta.get("modules") if isinstance(corpus_meta, dict) else None
    if isinstance(stdlib_root, str) and isinstance(modules, list):
        module_paths = [module_to_path(Path(stdlib_root), str(module)) for module in modules]
        theorem_blocks = _coq_source_block_lookup(list(index_theorem_blocks(module_paths).values()))
    _run_coq_query_corpus(
        corpus="coq-stdlib",
        log_dir=log_dir,
        theorems=theorems,
        offset=offset,
        sample=sample,
        seed=seed,
        config=config,
        corpus_meta={"imports": imports, **(corpus_meta or {})},
        progress_state_extra={"imports_count": len(imports)},
        start_event_extra={"imports_count": len(imports)},
        load_detail="exec imports",
        load_sentences=imports,
        statement_prelude=imports_prelude,
        theorem_blocks=theorem_blocks,
        sync_reason="external-coq-imports",
        progress=progress,
    )
