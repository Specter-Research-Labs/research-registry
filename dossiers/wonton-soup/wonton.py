#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import os
import shlex
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, NoReturn

import duckdb
import typer

from analysis.logs import relpath_under
from orchestrator import lean_options as _lean_options
from runtime_env import assert_wonton_python_runtime
from runtime_paths import (
    resolve_artifacts_root,
    resolve_corpora_root,
    resolve_logs_root,
    resolve_synthetic_bureau_root,
    sync_artifacts_to_remote,
    sync_corpora_to_remote,
    sync_logs_to_remote,
)

DOSSIER_NAME = "wonton-soup"
DOSSIER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = DOSSIER_ROOT.parents[1]

app = typer.Typer(add_completion=False, no_args_is_help=True)
lean_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Lean workflows")
app.add_typer(lean_app, name="lean")
corpus_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Corpus pipeline")
app.add_typer(corpus_app, name="corpus")
lake_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Cross-run lake tooling")
app.add_typer(lake_app, name="lake")
lake_job_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Jobs (materialize datasets)"
)
lake_app.add_typer(lake_job_app, name="job")

_lean_typer_option = _lean_options.typer_option


class Backend(str, Enum):
    lean = "lean"
    coq = "coq"


class CoqMode(str, Enum):
    file = "file"
    stdlib = "stdlib"


def resolve_logs_dir() -> Path:
    return resolve_logs_root()


def _default_log_dir(label: str) -> Path:
    logs_dir = resolve_logs_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return logs_dir / f"corpus-{timestamp}-{label}"


def _truncate_middle(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    keep = max(0, max_len - 3)
    left = keep // 2
    right = keep - left
    return value[:left] + "..." + value[-right:]


def _sparkline(values: list[float], width: int = 24) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    if len(values) > width:
        values = values[-width:]
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return blocks[0] * len(values)
    out = []
    for value in values:
        idx = int((value - lo) / (hi - lo) * (len(blocks) - 1))
        out.append(blocks[max(0, min(idx, len(blocks) - 1))])
    return "".join(out)


def _rich_progress_bar(completed: int, total: int, width: int = 28):
    from rich.text import Text

    text = Text()
    if total <= 0:
        text.append("░" * width, style="dim")
        return text
    filled = int(width * (completed / total))
    filled = max(0, min(filled, width))
    text.append("█" * filled, style="green")
    text.append("░" * (width - filled), style="dim")
    return text


def _rich_stacked_bar(width: int, counts: list[tuple[int, str]]):
    from rich.text import Text

    text = Text()
    nums = [max(0, int(n)) for n, _ in counts]
    total = sum(nums)
    if total <= 0:
        text.append("░" * width, style="dim")
        return text
    raw = [n / total * width for n in nums]
    seg = [int(v) for v in raw]
    rem = width - sum(seg)
    fracs = sorted([(raw[i] - seg[i], i) for i in range(len(seg))], reverse=True)
    for _, i in fracs[: max(0, rem)]:
        seg[i] += 1
    for (_, style), count in zip(counts, seg, strict=True):
        if count > 0:
            text.append("█" * count, style=style)
    return text


def _emit_agent_event(payload: dict[str, Any]) -> None:
    print(json.dumps(payload), flush=True)


def _compact_agent_payload(**payload: Any) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _emit_backend_agent_start(backend: str, log_dir: Path | str, **payload: Any) -> None:
    _emit_agent_event(
        _compact_agent_payload(event="start", backend=backend, log_dir=str(log_dir), **payload)
    )


def _emit_agent_status_event(
    event: str,
    *,
    status: str,
    errors: list[str] | None = None,
    **payload: Any,
) -> None:
    _emit_agent_event(
        _compact_agent_payload(
            event=event,
            status=status,
            errors=[] if errors is None else errors,
            **payload,
        )
    )


def _emit_backend_agent_end(
    backend: str,
    log_dir: Path | str,
    *,
    status: str,
    errors: list[str] | None = None,
    **payload: Any,
) -> None:
    _emit_agent_status_event(
        "end", status=status, errors=errors, backend=backend, log_dir=str(log_dir), **payload
    )


def _emit_backend_completion(
    backend: str,
    log_dir: Path,
    *,
    agent: bool,
    run_id: str | None = None,
    summary_path: str | None = None,
    postprocess_command: str | None = None,
    run_kind: str | None = None,
    extra_lines: Iterable[str] = (),
) -> None:
    if agent:
        _emit_backend_agent_end(
            backend,
            log_dir,
            status="completed",
            run_id=run_id,
            summary_path=summary_path,
            postprocess_command=postprocess_command,
            run_kind=run_kind,
        )
        return
    print(f"Logs: {log_dir}")
    for line in extra_lines:
        print(line)


def _run_backend_with_reporting(
    *,
    backend: str,
    log_dir: Path,
    agent: bool,
    run_fn: Callable[[], Any],
    start_payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    summary_path: str | None = None,
    postprocess_command: str | None = None,
    run_kind: str | None = None,
    extra_lines: Iterable[str] = (),
) -> None:
    if agent:
        _emit_backend_agent_start(backend, log_dir, **(start_payload or {}))
    try:
        run_fn()
    except Exception as exc:
        if agent:
            _emit_backend_agent_end(
                backend,
                log_dir,
                status="failed",
                errors=[str(exc)],
                run_id=run_id,
                run_kind=run_kind,
            )
        raise
    _emit_backend_completion(
        backend,
        log_dir,
        agent=agent,
        run_id=run_id,
        summary_path=summary_path,
        postprocess_command=postprocess_command,
        run_kind=run_kind,
        extra_lines=extra_lines,
    )


def _emit_status_or_lines(
    event: str,
    *,
    agent: bool,
    status: str = "completed",
    errors: list[str] | None = None,
    lines: Iterable[str] = (),
    **payload: Any,
) -> None:
    if agent:
        _emit_agent_status_event(event, status=status, errors=errors, **payload)
        return
    for line in lines:
        print(line)


def _is_set(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    return True


def _load_theorems(args) -> list[str]:
    theorems: list[str] = []
    if args.theorem:
        theorems.extend(args.theorem)
    if args.theorem_file:
        path = Path(args.theorem_file)
        if not path.exists():
            raise SystemExit(f"Theorem file not found: {path}")
        for line in path.read_text().splitlines():
            name = line.strip()
            if name:
                theorems.append(name)
    return theorems


def _die(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _print_sync_report(label: str, report) -> None:
    typer.echo(
        (
            f"{label}: {report.src_root} -> {report.dst_root} "
            f"(copied={report.copied_files}, skipped={report.skipped_files}, "
            f"bytes={report.copied_bytes})"
        )
    )


def _provider_label(provider: object) -> str:
    return f"provider={provider}" if isinstance(provider, str) and provider else "provider=single"


def _resolve_artifact_output_root(out_dir: str | None, suffix: str) -> Path:
    from analysis.logs import resolve_artifacts_dir

    return Path(out_dir) if out_dir else (resolve_artifacts_dir() / suffix)


def _emit_provider_results(
    results: Iterable[Any],
    format_result: Callable[[Any], str],
) -> None:
    for result in results:
        typer.echo(f"{_provider_label(getattr(result, 'provider', None))}: {format_result(result)}")


def _coerce_typer_option(value: Any, default: Any) -> Any:
    if isinstance(value, typer.models.OptionInfo):
        return default
    return value


def _emit_text_report(
    output_text: str,
    report: Any,
    *,
    output: str | None,
    label: str,
) -> None:
    typer.echo(output_text)
    if output is None:
        return
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(f"\nWrote {label}: {output_path}")


@contextmanager
def _open_lake_db(db: str | None) -> Iterator[tuple[duckdb.DuckDBPyConnection, Path]]:
    from analysis.lake.db import connect as lake_connect
    from analysis.lake.db import ensure_schema, resolve_lake_paths

    db_path = Path(os.path.expanduser(db)).resolve() if db else resolve_lake_paths().db_path
    conn = lake_connect(db_path)
    try:
        ensure_schema(conn)
        yield conn, db_path
    finally:
        conn.close()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _auto_sync_paths(paths: list[Path], *, reason: str) -> None:
    sync_roots = [
        ("logs", resolve_logs_dir().resolve(), sync_logs_to_remote),
        ("artifacts", resolve_artifacts_root().resolve(), sync_artifacts_to_remote),
        ("corpora", resolve_corpora_root().resolve(), sync_corpora_to_remote),
    ]
    seen: set[tuple[str, str]] = set()

    for path in paths:
        resolved = path.resolve()
        for name, root, push in sync_roots:
            if not _is_under(resolved, root):
                continue
            key = (name, str(resolved))
            if key in seen:
                break
            seen.add(key)
            report = push(resolved, require_src=False)
            if report is not None and report.copied_files > 0:
                _print_sync_report(f"auto-sync {name} ({reason})", report)
            break


def _validate_sampling_args(args, *, allow_limit_with_sample: bool) -> None:
    if args.sample is None:
        return
    if args.seed is None:
        _die("--seed is required when --sample is set")
    if not allow_limit_with_sample and args.limit is not None:
        _die("Use --sample or --limit, not both")


def _validate_lean_flag_conflicts(args) -> None:
    if args.wild_only and args.with_interventions:
        _die("--wild-only and --with-interventions are mutually exclusive")
    if args.trace_mcts and args.no_trace_mcts:
        _die("--trace-mcts and --no-trace-mcts are mutually exclusive")


def _validate_backend_args(args) -> None:
    if args.backend == Backend.lean:
        _die("`run --backend lean` is unsupported")
    if _is_set(args.limit):
        _die("--limit is not valid for --backend coq")
    _validate_sampling_args(args, allow_limit_with_sample=True)


def _validate_lean_args(args) -> None:
    _validate_sampling_args(args, allow_limit_with_sample=False)
    _validate_lean_flag_conflicts(args)


def _has_ymd_prefix(value: str) -> bool:
    # Expected: YYYY-MM-DD-...
    if len(value) < 11:
        return False
    if value[4] != "-" or value[7] != "-" or value[10] != "-":
        return False
    y = value[0:4]
    m = value[5:7]
    d = value[8:10]
    return y.isdigit() and m.isdigit() and d.isdigit()


def _prefix_run_id_with_ymd(run_id: str) -> str:
    head, sep, tail = run_id.partition("/")
    if _has_ymd_prefix(head):
        return run_id
    date = datetime.now().strftime("%Y-%m-%d")
    return f"{date}-{head}{sep}{tail}" if sep else f"{date}-{head}"


def _build_run_id(run_id: str | None) -> str:
    if run_id:
        # Keep corpus ids stable (many tools treat "corpus-..." specially), but
        # date-prefix user-supplied ids for chronological sorting under logs/.
        if run_id.startswith("corpus-"):
            return run_id
        return _prefix_run_id_with_ymd(run_id)
    return f"corpus-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"


def _lean_postprocess_command(run_dir: Path) -> str:
    return (
        f"uv run python {shlex.quote(str(DOSSIER_ROOT / 'wonton.py'))} "
        f"postprocess --run-dir {shlex.quote(str(run_dir))}"
    )


def _run_lean(args) -> None:
    from orchestrator import lean as lean_run

    if args.lean_project:
        os.environ["LEAN_PROJECT_PATH"] = args.lean_project

    if args.theorem and len(args.theorem) > 1:
        _die("--theorem can only be used once for --backend lean")
    args.theorem = args.theorem[0] if args.theorem else None

    # Typer exposes independent booleans instead of argparse's tri-state flags.
    # Normalize them before handing off to the shared Lean executor.
    args.wild_only = (
        True
        if args.wild_only
        else False if getattr(args, "with_interventions", False) else None
    )
    args.trace_mcts = True if args.trace_mcts else False if args.no_trace_mcts else None
    args.goal_sig = args.goal_sig or "ast"
    args.plain = bool(args.plain or args.agent)

    lean_run.run_from_args(args)


def _run_lean_backend(args) -> None:
    run_id = _build_run_id(args.run_id)
    args.run_id = run_id
    log_dir = (resolve_logs_dir() / run_id).resolve()
    basin_mode = args.basin_seeds is not None
    run_kind = "basin" if basin_mode else "run"
    summary_path = None if basin_mode else str(log_dir / "summary.json.gz")
    postprocess_cmd = None if basin_mode else _lean_postprocess_command(log_dir)
    extra_lines = (
        [
            "Basin mode output: per-theorem basin_analysis.json only "
            "(no summary.json.gz/report.md)."
        ]
        if basin_mode
        else [
            "Postprocess (heavy metrics):",
            f"  {postprocess_cmd}",
            "Fills: ged_search_graph_soft, goal_novelty, solution_path_soft_distance; "
            "writes: root_goal_similarity.json, external_statement_similarity.json, "
            "postprocess_metrics.json",
        ]
    )
    _run_backend_with_reporting(
        backend="lean",
        log_dir=log_dir,
        agent=bool(args.agent),
        run_fn=lambda: _run_lean(args),
        start_payload={
            "provider": args.provider,
            "providers": args.providers,
            "run_id": run_id,
            "run_kind": run_kind,
        },
        run_id=run_id,
        summary_path=summary_path,
        postprocess_command=postprocess_cmd,
        run_kind=run_kind,
        extra_lines=extra_lines,
    )


def _run_external_corpus(
    args,
    *,
    log_dir: Path,
    run_batch: Callable[[Callable[[dict[str, Any]], None] | None], None],
) -> Path:
    progress_cb, close_ui = _build_external_progress_ui(not args.agent and not args.plain)
    try:
        run_batch(progress_cb)
    finally:
        if close_ui is not None:
            close_ui()
    return log_dir


def _build_external_progress_ui(
    enabled: bool,
) -> tuple[Callable[[dict[str, Any]], None] | None, Callable[[], None] | None]:
    if not enabled:
        return None, None

    import time
    from collections import deque

    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "--"
        total = max(int(seconds), 0)
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        if minutes > 0:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    class _ExternalProgressUI:
        def __init__(self) -> None:
            self.console = Console()
            self.live: Live | None = None
            self.backend = "external"
            self.provider = ""
            self.corpus = ""
            self.log_dir = ""
            self.root: str | None = None
            self.domains: list[str] = []
            self.source: str | None = None
            self.imports_count: int | None = None
            self.timeout_sec: int | None = None
            self.total = 0
            self.stage: str | None = None
            self.current_name: str | None = None
            self.completed = 0
            self.solved = 0
            self.unsolved = 0
            self.crashed = 0
            self.timeouts = 0
            self.status_counts: dict[str, int] = {}
            self.started_at = time.time()
            self.item_started_at: float | None = None
            self.durations: deque[float] = deque(maxlen=48)
            self.status_strip: deque[tuple[str, str]] = deque(maxlen=42)

        def start(self) -> None:
            self.live = Live(self._render(), console=self.console, refresh_per_second=8)
            self.live.start()

        def stop(self) -> None:
            if self.live is not None:
                self.live.stop()
                self.live = None

        def _eta(self) -> float | None:
            if self.total <= 0 or self.completed <= 0:
                return None
            avg = sum(self.durations) / len(self.durations) if self.durations else None
            if avg is None or avg <= 0:
                return None
            remaining = max(self.total - self.completed, 0)
            return remaining * avg

        def _render(self) -> Panel:
            left = Text()
            right = Text()

            title = f"  {self.backend.upper()} | provider: {self.provider} | corpus: {self.corpus}"

            left.append("  ")
            left.append(str(self.completed), style="bold")
            left.append("/")
            left.append(str(self.total) if self.total else "?", style="bold")
            left.append("  ")
            left.append_text(_rich_progress_bar(self.completed, self.total))
            left.append("\n", style="white")

            if self.current_name:
                left.append("  > ", style="dim")
                left.append(_truncate_middle(self.current_name, 72), style="bold cyan")
                left.append("\n")

            if self.stage:
                left.append("  stage: ", style="dim")
                left.append(self.stage, style="white")
                left.append("\n")

            if self.root:
                left.append("  root: ", style="dim")
                left.append(_truncate_middle(self.root, 78), style="white")
                left.append("\n")
            if self.domains:
                left.append("  domains: ", style="dim")
                left.append(_truncate_middle(", ".join(self.domains), 78), style="white")
                left.append("\n")
            if self.source:
                left.append("  source: ", style="dim")
                left.append(_truncate_middle(self.source, 78), style="white")
                left.append("\n")
            if self.imports_count is not None:
                left.append("  imports: ", style="dim")
                left.append(str(self.imports_count), style="white")
                left.append("\n")

            elapsed = time.time() - self.started_at
            eta = self._eta()
            right.append(f"  time: {_format_duration(elapsed)}", style="white")
            if eta is not None:
                right.append(f" | eta~ {_format_duration(eta)}", style="white")
            right.append("\n")

            if self.timeout_sec is not None:
                right.append(f"  timeout: {self.timeout_sec}s\n", style="dim")

            right.append("  solved: ", style="dim")
            right.append(str(self.solved), style="green")
            right.append("  unsolved: ", style="dim")
            right.append(str(self.unsolved), style="yellow")
            right.append("  crashed: ", style="dim")
            right.append(str(self.crashed), style="red")
            if self.timeouts:
                right.append("  timeouts: ", style="dim")
                right.append(str(self.timeouts), style="magenta")
            right.append("\n")

            right.append("  outcomes: ", style="dim")
            right.append_text(
                _rich_stacked_bar(
                    28,
                    [
                        (self.solved, "green"),
                        (self.unsolved, "yellow"),
                        (max(0, min(self.timeouts, self.crashed)), "magenta"),
                        (max(0, self.crashed - max(0, min(self.timeouts, self.crashed))), "red"),
                    ],
                )
            )
            right.append("\n")

            if self.durations:
                vals = list(self.durations)
                right.append("  rate: ", style="dim")
                items_per_sec = 1.0 / (sum(vals) / len(vals)) if sum(vals) > 0 else 0.0
                right.append(f"{items_per_sec:.2f} item/s", style="white")
                right.append("  ")
                right.append(_sparkline(vals, width=24), style="cyan")
                right.append("\n")

            if self.status_counts:
                top = sorted(self.status_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
                parts = [f"{k}×{v}" for k, v in top]
                right.append("  status: ", style="dim")
                right.append(_truncate_middle(" | ".join(parts), 78), style="white")
                right.append("\n")

            if self.status_strip:
                strip = Text("  ")
                for ch, style in self.status_strip:
                    strip.append(ch, style=style)
                right.append_text(strip)
                right.append("\n")

            right.append(f"  logs: {_truncate_middle(self.log_dir, 80)}\n", style="dim")

            grid = Table.grid(expand=True)
            grid.add_column(ratio=3)
            grid.add_column(ratio=2)
            grid.add_row(left, right)
            return Panel(grid, title=title, border_style="blue", padding=(0, 1))

        def handle(self, event: dict[str, Any]) -> None:
            kind = event.get("event")
            if kind == "start":
                self.backend = str(event.get("backend", self.backend))
                self.provider = str(event.get("provider", self.provider))
                self.corpus = str(event.get("corpus", self.corpus))
                self.log_dir = str(event.get("log_dir", self.log_dir))
                self.root = event.get("root") if isinstance(event.get("root"), str) else None
                domains = event.get("domains")
                self.domains = domains if isinstance(domains, list) else []
                source = event.get("source")
                self.source = source if isinstance(source, str) else None
                imports_count = event.get("imports_count")
                self.imports_count = imports_count if isinstance(imports_count, int) else None
                self.timeout_sec = event.get("timeout_sec")
                self.total = int(event.get("total") or 0)
                if self.live is None:
                    self.start()
                elif self.live:
                    self.live.update(self._render())
                return
            if kind == "stage":
                self.stage = str(event.get("stage") or "") + (
                    f": {event.get('detail')}" if event.get("detail") else ""
                )
                if self.live:
                    self.live.update(self._render())
                return
            if kind == "item_start":
                self.current_name = str(event.get("name") or "")
                self.item_started_at = time.time()
                if self.live:
                    self.live.update(self._render())
                return
            if kind == "item_end":
                self.completed = int(event.get("idx") or self.completed)
                solved = bool(event.get("solved"))
                err = event.get("error")
                status = event.get("status")
                if self.item_started_at is not None:
                    self.durations.append(max(time.time() - self.item_started_at, 0.0))
                if err:
                    self.crashed += 1
                    err_s = str(err)
                    if "timed out" in err_s:
                        self.timeouts += 1
                        self.status_strip.append(("!", "magenta"))
                    else:
                        self.status_strip.append(("x", "red"))
                else:
                    if solved:
                        self.solved += 1
                        self.status_strip.append(("█", "green"))
                    else:
                        self.unsolved += 1
                        self.status_strip.append(("░", "yellow"))
                if isinstance(status, str) and status:
                    self.status_counts[status] = self.status_counts.get(status, 0) + 1
                if self.live:
                    self.live.update(self._render())
                return
            if kind == "end":
                if self.live:
                    self.live.update(self._render())
                return

    ui = _ExternalProgressUI()

    def progress_cb(event: dict[str, Any]) -> None:
        ui.handle(event)

    def close() -> None:
        ui.stop()

    return progress_cb, close


def _coq_backend_label(coq_mode: CoqMode | None) -> str:
    return "coq-stdlib" if coq_mode == CoqMode.stdlib else "coq"


def _run_coq(args) -> Path:
    from atp.coq.runner import CoqConfig
    from atp.coq.serapi import SerapiConfig
    from atp.coq.stdlib import (
        DEFAULT_STDLIB_MODULES,
        build_import_sentences,
        collect_stdlib_theorems,
        find_coq_stdlib_root,
    )
    from orchestrator.external import run_coq_extraction, run_coq_import_extraction

    coq_mode = args.coq_mode or CoqMode.file
    serapi_binary = args.serapi_binary or "sertop"
    doc_name = args.doc_name or "coqdoc"
    coqc_binary = args.coqc_binary or "coqc"
    limit_per_module = args.limit_per_module if args.limit_per_module is not None else 25
    log_dir = Path(args.log_dir) if args.log_dir else _default_log_dir(_coq_backend_label(coq_mode))
    serapi = (
        SerapiConfig(binary=serapi_binary)
        if args.serapi_args is None
        else SerapiConfig(binary=serapi_binary, extra_args=args.serapi_args)
    )
    config = CoqConfig(serapi=serapi, doc_name=doc_name)

    if coq_mode == CoqMode.stdlib:
        modules = args.modules if args.modules else DEFAULT_STDLIB_MODULES
        if not modules:
            _die("No Coq stdlib modules provided")

        if args.stdlib_root:
            stdlib_root = Path(args.stdlib_root)
        else:
            stdlib_root = find_coq_stdlib_root(coqc_binary)
        if not stdlib_root.exists():
            _die(f"Coq stdlib root not found: {stdlib_root}")

        theorems = collect_stdlib_theorems(
            modules,
            stdlib_root,
            limit_per_module=limit_per_module,
            limit_total=args.limit_total,
        )
        if not theorems:
            _die("No Coq theorems found for selected modules")

        imports = build_import_sentences(modules)
        corpus_meta = {
            "stdlib_root": str(stdlib_root),
            "modules": modules,
            "limit_per_module": args.limit_per_module,
            "limit_total": args.limit_total,
        }

        def _run_batch(progress_cb: Callable[[dict[str, Any]], None] | None) -> None:
            run_coq_import_extraction(
                imports,
                log_dir,
                theorems,
                offset=args.offset or 0,
                sample=args.sample,
                seed=args.seed,
                config=config,
                corpus_meta=corpus_meta,
                progress=progress_cb,
            )

        return _run_external_corpus(args, log_dir=log_dir, run_batch=_run_batch)

    if not args.source:
        _die("--source is required for --backend coq when --coq-mode file")
    theorems = _load_theorems(args)
    if not theorems:
        _die("No theorems provided (use --theorem or --theorem-file)")

    def _run_batch(progress_cb: Callable[[dict[str, Any]], None] | None) -> None:
        run_coq_extraction(
            Path(args.source),
            log_dir,
            theorems,
            offset=args.offset or 0,
            sample=args.sample,
            seed=args.seed,
            config=config,
            progress=progress_cb,
        )

    return _run_external_corpus(args, log_dir=log_dir, run_batch=_run_batch)


_EXTERNAL_COMMAND_RUN_DEFAULTS: dict[str, Any] = {
    "agent": False,
    "limit": None,
    "theorem": None,
    "offset": None,
    "sample": None,
    "seed": None,
    "log_dir": None,
    "source": None,
    "theorem_file": None,
    "serapi_binary": None,
    "serapi_args": None,
    "doc_name": None,
    "coq_mode": None,
    "modules": None,
    "limit_per_module": None,
    "limit_total": None,
    "stdlib_root": None,
    "coqc_binary": None,
}


class ExternalInvocation:
    def __init__(self, *, backend: Backend, **kwargs: Any) -> None:
        self.backend = backend
        for name, default in _EXTERNAL_COMMAND_RUN_DEFAULTS.items():
            setattr(self, name, kwargs.get(name, default))

    @classmethod
    def from_values(cls, *, backend: Backend, values: dict[str, Any]) -> "ExternalInvocation":
        return cls(
            backend=backend,
            **{
                name: _coerce_typer_option(values.get(name), default)
                for name, default in _EXTERNAL_COMMAND_RUN_DEFAULTS.items()
            },
        )


def _external_alias_kwargs(backend: Backend, values: dict[str, Any]) -> dict[str, Any]:
    return {"backend": backend} | {
        name: _coerce_typer_option(values.get(name), default)
        for name, default in _EXTERNAL_COMMAND_RUN_DEFAULTS.items()
    }


def _run_external_invocation(args: ExternalInvocation) -> None:
    _validate_backend_args(args)

    if args.log_dir is None:
        args.log_dir = str(_default_log_dir(_coq_backend_label(args.coq_mode)))
    log_dir_path = Path(args.log_dir)
    _run_backend_with_reporting(
        backend=args.backend.value,
        log_dir=log_dir_path,
        agent=bool(args.agent),
        run_fn=lambda: _run_coq(args),
        summary_path=str(log_dir_path / "summary.json.gz"),
    )


@app.command()
def run(
    backend: Backend = typer.Option(..., "--backend", help="Backend to run"),
    agent: bool = typer.Option(False, "--agent", help="Agent-optimized output"),
    limit: int | None = typer.Option(None, "-n", "--limit", help="Max theorems"),
    theorem: list[str] | None = typer.Option(None, "-t", "--theorem", help="Theorem name"),
    offset: int | None = typer.Option(None, "--offset"),
    sample: int | None = typer.Option(None, "--sample"),
    seed: int | None = typer.Option(None, "--seed"),
    log_dir: str | None = typer.Option(None, "--log-dir"),
    source: str | None = typer.Option(None, "--source"),
    theorem_file: str | None = typer.Option(None, "--theorem-file"),
    serapi_binary: str | None = typer.Option(None, "--serapi-binary"),
    serapi_args: list[str] | None = typer.Option(None, "--serapi-args"),
    doc_name: str | None = typer.Option(None, "--doc-name"),
    coq_mode: CoqMode | None = typer.Option(None, "--coq-mode"),
    modules: list[str] | None = typer.Option(None, "--modules"),
    limit_per_module: int | None = typer.Option(None, "--limit-per-module"),
    limit_total: int | None = typer.Option(None, "--limit-total"),
    stdlib_root: str | None = typer.Option(None, "--stdlib-root"),
    coqc_binary: str | None = typer.Option(None, "--coqc-binary"),
) -> None:
    _run_external_invocation(ExternalInvocation.from_values(backend=backend, values=locals()))


@app.command()
def postprocess(
    run_dir: str | None = typer.Option(
        None,
        "--run-dir",
        help="Process a single run directory (single-provider or multi-provider root)",
    ),
    logs_dir: list[str] | None = typer.Option(
        None,
        "--logs-dir",
        help="Logs directory root to scan (repeatable). Default: canonical local Wonton logs root",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only report which runs would be processed",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Maximum number of pending runs to process",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--fail-fast",
        help="Continue processing other runs after one fails",
    ),
    agent: bool = typer.Option(False, "--agent", help="Agent-optimized output"),
) -> None:
    """Compute heavy metrics for runs. Batch mode by default; --run-dir for a single run."""

    from analysis.logs import write_json_atomic
    from analysis.postprocess_batch import (
        discover_postprocess_run_states,
        inspect_postprocess_run_state,
        postprocess_unprocessed_runs,
    )
    from analysis.postprocess_metrics import PostprocessParams, postprocess_run

    params = PostprocessParams()

    if run_dir is not None:
        target = Path(os.path.expanduser(run_dir)).resolve()
        if not target.exists():
            _die(f"Run dir not found: {target}")

        if dry_run:
            state = inspect_postprocess_run_state(
                target,
                params=params,
                include_partial=True,
            )
            _emit_status_or_lines(
                "postprocess_end",
                agent=agent,
                log_dir=str(target),
                dry_run=True,
                eligible=state.eligible,
                pending=state.needs_processing,
                reason=state.reason,
                lines=(
                    "Postprocess dry-run",
                    f"Run: {target}",
                    f"Eligible: {state.eligible}",
                    f"Pending: {state.needs_processing}",
                    f"Reason: {state.reason}",
                ),
            )
            return

        report = postprocess_run(target, params=params)
        report_path = target / "postprocess_metrics.json"
        write_json_atomic(report_path, report)
        summary = report.get("metrics") if isinstance(report, dict) else None

        lines = [f"Postprocess report: {report_path}"]
        if isinstance(summary, dict):
            computed = summary.get("computed")
            skipped = summary.get("skipped")
            if isinstance(computed, int) and isinstance(skipped, int):
                lines.append(f"Postprocess metrics: computed {computed}, skipped {skipped}")
        _emit_status_or_lines(
            "postprocess_end",
            agent=agent,
            log_dir=str(target),
            report_path=str(report_path),
            metrics_summary=summary,
            lines=lines,
        )
        return

    roots = [Path(os.path.expanduser(path)).resolve() for path in (logs_dir or [])]
    if not roots:
        roots = [resolve_logs_dir()]

    if dry_run:
        states = discover_postprocess_run_states(
            roots, params=params, include_partial=True
        )
        eligible = [state for state in states if state.eligible]
        pending = [state for state in eligible if state.needs_processing]
        if limit is not None:
            pending = pending[: max(0, limit)]
        _emit_status_or_lines(
            "postprocess_batch_end",
            agent=agent,
            discovered=len(states),
            eligible=len(eligible),
            pending=len(pending),
            processed=0,
            succeeded=0,
            failed=0,
            skipped=len(states),
            dry_run=True,
            lines=[
                "Postprocess dry-run",
                f"Discovered: {len(states)}",
                f"Eligible: {len(eligible)}",
                f"Pending: {len(pending)}",
                *(f"  {state.run_dir} ({state.reason})" for state in pending),
            ],
        )
        return

    batch_report = postprocess_unprocessed_runs(
        logs_dirs=roots,
        params=params,
        include_partial=True,
        limit=limit,
        continue_on_error=continue_on_error,
    )

    lines = [
        "Postprocess batch summary",
        f"Discovered: {batch_report.discovered}",
        f"Eligible: {batch_report.eligible}",
        f"Pending: {batch_report.pending}",
        f"Processed: {batch_report.processed}",
        f"Succeeded: {batch_report.succeeded}",
        f"Failed: {batch_report.failed}",
        f"Skipped: {batch_report.skipped}",
    ]
    if batch_report.failures:
        lines.append("Failures:")
        lines.extend(
            f"  {failure.get('run_dir')}: {failure.get('error')}"
            for failure in batch_report.failures
        )
    _emit_status_or_lines(
        "postprocess_batch_end",
        agent=agent,
        status="failed" if batch_report.failed else "completed",
        discovered=batch_report.discovered,
        eligible=batch_report.eligible,
        pending=batch_report.pending,
        processed=batch_report.processed,
        succeeded=batch_report.succeeded,
        failed=batch_report.failed,
        skipped=batch_report.skipped,
        failures=batch_report.failures,
        lines=lines,
    )

    if batch_report.failed > 0:
        raise typer.Exit(code=1)


@app.command("verify-run-local")
def verify_run_local_command(
    run_dir: str = typer.Option(
        ...,
        "--run-dir",
        help="Single-provider run dir or multi-provider root to verify",
    ),
    theorem: list[str] | None = typer.Option(
        None,
        "-t",
        "--theorem",
        help="Verify only these theorem names (repeatable)",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Maximum solved theorems to verify per provider",
    ),
    lean_project: str | None = typer.Option(
        None,
        "--lean-project",
        help="Override Lean project path recorded in run_config.json",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing theorem-level verification artifacts",
    ),
) -> None:
    from analysis.verify_run_local import VERIFY_LOCAL_SUMMARY_NAME, verify_run_local

    target = Path(os.path.expanduser(run_dir)).resolve()
    if not target.exists():
        _die(f"Run dir not found: {target}")

    reports = verify_run_local(
        target,
        theorem_names=theorem,
        limit=limit,
        lean_project=Path(lean_project).expanduser().resolve() if lean_project else None,
        force=force,
    )
    for report in reports:
        counts = report.get("counts") if isinstance(report, dict) else None
        run_dir_value = report.get("run_dir") if isinstance(report, dict) else None
        provider = report.get("provider") if isinstance(report, dict) else None
        if not isinstance(counts, dict) or not isinstance(run_dir_value, str):
            raise ValueError("verify-run-local produced an invalid report payload")
        label = _provider_label(provider)
        typer.echo(
            f"{label}: "
            f"verified={counts.get('verified', 0)}/{counts.get('eligible', 0)} "
            f"candidate_failed={counts.get('candidate_failed', 0)} "
            f"replay_failed={counts.get('replay_failed', 0)} "
            f"input_failed={counts.get('input_failed', 0)} "
            f"skipped_existing={counts.get('skipped_existing', 0)} "
            f"skipped_unsolved={counts.get('skipped_unsolved', 0)} "
            f"-> {Path(run_dir_value) / VERIFY_LOCAL_SUMMARY_NAME}"
        )


@app.command()
def coq(
    source: str | None = typer.Option(None, "--source"),
    theorem: list[str] | None = typer.Option(None, "-t", "--theorem"),
    theorem_file: str | None = typer.Option(None, "--theorem-file"),
    offset: int | None = typer.Option(None, "--offset"),
    sample: int | None = typer.Option(None, "--sample"),
    seed: int | None = typer.Option(None, "--seed"),
    serapi_binary: str = typer.Option("sertop", "--serapi-binary"),
    serapi_args: list[str] | None = typer.Option(None, "--serapi-args"),
    doc_name: str = typer.Option("coqdoc", "--doc-name"),
    coq_mode: CoqMode = typer.Option(CoqMode.file, "--coq-mode"),
    modules: list[str] | None = typer.Option(None, "--modules"),
    limit_per_module: int = typer.Option(25, "--limit-per-module"),
    limit_total: int | None = typer.Option(None, "--limit-total"),
    stdlib_root: str | None = typer.Option(None, "--stdlib-root"),
    coqc_binary: str = typer.Option("coqc", "--coqc-binary"),
    log_dir: str | None = typer.Option(None, "--log-dir"),
    agent: bool = typer.Option(False, "--agent"),
) -> None:
    run(**_external_alias_kwargs(Backend.coq, locals()))


_LEAN_COMMAND_OPTION_NAMES = (
    "agent",
    *_lean_options.LEAN_SHARED_OPTION_NAMES,
    "wild_only",
    "with_interventions",
    "trace_mcts",
    "no_trace_mcts",
    "basin_seeds",
    "basin_blind",
)

_LEAN_COMMAND_PARAM_NAMES = (*_LEAN_COMMAND_OPTION_NAMES, "no_sync")


class LeanInvocation:
    def __init__(self, **kwargs: Any) -> None:
        for name in _LEAN_COMMAND_PARAM_NAMES:
            setattr(self, name, kwargs[name])

    @classmethod
    def from_kwargs(cls, kwargs: dict[str, Any]) -> "LeanInvocation":
        return cls(**{name: kwargs[name] for name in _LEAN_COMMAND_PARAM_NAMES})


def _build_lean_command_signature() -> inspect.Signature:
    return inspect.Signature(
        [
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=True if name == "no_sync" else _lean_options.option_default(name),
            )
            for name in _LEAN_COMMAND_PARAM_NAMES
        ]
    )


def _run_lean_command(**kwargs: Any) -> None:
    _run_lean_backend(LeanInvocation.from_kwargs(kwargs))


_run_lean_command.__signature__ = _build_lean_command_signature()


def _collect_lean_command_kwargs(
    values: dict[str, Any],
    **overrides: Any,
) -> dict[str, Any]:
    return (
        {
            name: _coerce_typer_option(values.get(name), _lean_options.option_default(name))
            for name in _LEAN_COMMAND_OPTION_NAMES
        }
        | {"no_sync": not bool(values.get("sync", False))}
        | overrides
    )


def _build_lean_run_variant(values: dict[str, Any]) -> dict[str, Any]:
    return _collect_lean_command_kwargs(values, basin_seeds=None, basin_blind=False)


def _build_lean_basin_variant(values: dict[str, Any]) -> dict[str, Any]:
    return _collect_lean_command_kwargs(
        values,
        wild_only=False,
        with_interventions=False,
        basin_seeds=values["seeds"],
        basin_blind=values["blind"],
        analysis=False,
    )


def _build_lean_suite_variants(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    suite_root = values.get("run_id") or "lean-suite"
    common_kwargs = _collect_lean_command_kwargs(values)
    seeds = values["seeds"]
    blind = values["blind"]
    analysis = values["analysis"]
    return {
        "run": common_kwargs
        | {
            "run_id": f"{suite_root}/run",
            "resume": False,
            "basin_seeds": None,
            "basin_blind": False,
            "analysis": analysis,
        },
        "basin": common_kwargs
        | {
            "wild_only": False,
            "with_interventions": False,
            "run_id": f"{suite_root}/basin-{seeds}",
            "resume": False,
            "basin_seeds": seeds,
            "basin_blind": blind,
            "analysis": False,
        },
    }


def _run_lean_variants(
    variants: dict[str, dict[str, Any]],
    *,
    summarize: bool = False,
) -> None:
    resolved_run_dirs: dict[str, Path] = {}
    for name, kwargs in variants.items():
        _run_lean_command(**kwargs)
        run_id = kwargs.get("run_id")
        if isinstance(run_id, str) and run_id:
            resolved_run_dirs[name] = resolve_logs_dir() / _build_run_id(run_id)
    if summarize and variants:
        typer.echo("Suite completed:")
        for name in variants:
            log_dir = resolved_run_dirs.get(name)
            if log_dir is not None:
                typer.echo(f"  {name}: {log_dir}")


def _emit_built_corpus(
    built: Any,
    *,
    sync: bool,
    sync_reason: str,
    extra_lines: list[str] | None = None,
) -> None:
    typer.echo(f"Built: {built.ref()}")
    typer.echo(f"Dir: {built.build_dir}")
    for line in extra_lines or []:
        typer.echo(line)
    if sync:
        _auto_sync_paths([built.build_dir], reason=sync_reason)


def _build_and_emit_corpus(
    build_fn: Callable[..., Any],
    *,
    sync: bool,
    sync_reason: str,
    extra_lines: list[str] | None = None,
    extra_lines_factory: Callable[[Any], list[str]] | None = None,
    **build_kwargs: Any,
) -> None:
    built = build_fn(**build_kwargs)
    _emit_built_corpus(
        built,
        sync=sync,
        sync_reason=sync_reason,
        extra_lines=extra_lines_factory(built) if extra_lines_factory is not None else extra_lines,
    )


def _lean_1000_plus_manifest_lines(build_dir: Path) -> list[str]:
    manifest_payload = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
    build_config = (
        manifest_payload.get("build_config") if isinstance(manifest_payload, dict) else None
    )
    if not isinstance(build_config, dict):
        return []

    lines: list[str] = []
    requested = build_config.get("identifier_requested_count")
    resolved = build_config.get("identifier_resolved_count")
    unresolved = build_config.get("identifier_unresolved_count")
    if isinstance(requested, int) and isinstance(resolved, int) and isinstance(unresolved, int):
        lines.append(
            f"Identifiers: requested={requested}, resolved={resolved}, unresolved={unresolved}"
        )
    preview = build_config.get("identifier_unresolved_preview")
    if isinstance(preview, list):
        unresolved_preview = [name for name in preview if isinstance(name, str) and name]
        if unresolved_preview:
            lines.append("Unresolved preview: " + ", ".join(unresolved_preview))
    return lines


def _emit_validation_result(
    *,
    headline: str,
    validation_path: Path,
    derived_dir: Path | None,
    derived_label: str,
    sync: bool,
    sync_reason: str,
) -> None:
    typer.echo(headline)
    typer.echo(f"Wrote: {validation_path}")
    if derived_dir is not None:
        typer.echo(f"{derived_label}: {derived_dir}")
    if sync:
        sync_paths = [validation_path]
        if derived_dir is not None:
            sync_paths.append(derived_dir)
        _auto_sync_paths(sync_paths, reason=sync_reason)


def _emit_capability_sweep_result(
    result: Any,
    *,
    sync: bool,
    sync_reason: str,
    include_sweep_root: bool = False,
) -> None:
    typer.echo(
        f"Reachable: {result.reachable_count}/{result.total_count} ({result.reachable_rate:.1%})"
    )
    if include_sweep_root:
        typer.echo(f"Sweep root: {result.sweep_root}")
    typer.echo(f"Wrote: {result.capability_path}")
    typer.echo(f"Derived feasible dir: {result.derived_feasible_dir}")
    if sync:
        sync_paths = [result.capability_path, result.derived_feasible_dir]
        if include_sweep_root:
            sync_paths.insert(0, result.sweep_root)
        _auto_sync_paths(sync_paths, reason=sync_reason)


@lean_app.command("run")
def lean_run(
    agent: bool = typer.Option(False, "--agent", help="Agent-optimized output"),
    mode: str | None = _lean_typer_option("mode"),
    corpus: str | None = _lean_typer_option("corpus"),
    provider: str | None = _lean_typer_option("provider"),
    providers: str | None = _lean_typer_option("providers"),
    all_providers: bool = _lean_typer_option("all_providers"),
    budget: str | None = _lean_typer_option("budget"),
    limit: int | None = _lean_typer_option("limit"),
    theorem: list[str] | None = _lean_typer_option("theorem"),
    lean_project: str | None = _lean_typer_option("lean_project"),
    wild_only: bool = typer.Option(False, "--wild-only", help="Skip interventions"),
    with_interventions: bool = typer.Option(
        False, "--with-interventions", help="Run intervention comparisons"
    ),
    trace_mcts: bool = typer.Option(False, "--trace-mcts", help="Enable MCTS tracing"),
    no_trace_mcts: bool = typer.Option(False, "--no-trace-mcts", help="Disable MCTS tracing"),
    mcts_mode: str | None = _lean_typer_option("mcts_mode"),
    mcts_expansion_policy: str | None = _lean_typer_option("mcts_expansion_policy"),
    mcts_agents: int | None = _lean_typer_option("mcts_agents"),
    mcts_inflight: int | None = _lean_typer_option("mcts_inflight"),
    mcts_block_fraction: float | None = _lean_typer_option("mcts_block_fraction"),
    mcts_block_duration: int | None = _lean_typer_option("mcts_block_duration"),
    mcts_block_seed: int | None = _lean_typer_option("mcts_block_seed"),
    mcts_block_immovable_fraction: float | None = _lean_typer_option(
        "mcts_block_immovable_fraction"
    ),
    mcts_unfreeze_after: int | None = _lean_typer_option("mcts_unfreeze_after"),
    mcts_unfreeze_prob: float | None = _lean_typer_option("mcts_unfreeze_prob"),
    mcts_reroute_blocked: bool = _lean_typer_option("mcts_reroute_blocked"),
    mcts_reroute_max: int | None = _lean_typer_option("mcts_reroute_max"),
    mcts_delay_prob: float | None = _lean_typer_option("mcts_delay_prob"),
    mcts_delay_duration: int | None = _lean_typer_option("mcts_delay_duration"),
    mcts_delay_seed: int | None = _lean_typer_option("mcts_delay_seed"),
    mcts_virtual_loss: int | None = _lean_typer_option("mcts_virtual_loss"),
    mcts_depth_bias: float | None = _lean_typer_option("mcts_depth_bias"),
    mcts_path_bias: float | None = _lean_typer_option("mcts_path_bias"),
    mcts_history_cache: bool = _lean_typer_option("mcts_history_cache"),
    mcts_deterministic_inference: bool = _lean_typer_option("mcts_deterministic_inference"),
    allow_easy: bool = _lean_typer_option("allow_easy"),
    debug: bool = _lean_typer_option("debug"),
    plain: bool = _lean_typer_option("plain"),
    sampling: bool = _lean_typer_option("sampling"),
    deepseek_num_samples: int | None = _lean_typer_option("deepseek_num_samples"),
    deepseek_model_path: str | None = _lean_typer_option("deepseek_model_path"),
    deepseek_backend: str = _lean_typer_option("deepseek_backend"),
    bfs_num_samples: int | None = _lean_typer_option("bfs_num_samples"),
    internlm_num_samples: int | None = _lean_typer_option("internlm_num_samples"),
    device: str | None = _lean_typer_option("device"),
    workers: int | None = _lean_typer_option("workers"),
    offset: int | None = _lean_typer_option("offset"),
    sample: int | None = _lean_typer_option("sample"),
    seed: int | None = _lean_typer_option("seed"),
    search_seed: int | None = _lean_typer_option("search_seed"),
    goal_sig: str | None = _lean_typer_option("goal_sig"),
    run_id: str | None = _lean_typer_option("run_id"),
    resume: bool = _lean_typer_option("resume"),
    analysis: bool = _lean_typer_option("analysis"),
    no_solution_artifacts: bool = _lean_typer_option("no_solution_artifacts"),
    baseline_solved_only: bool = _lean_typer_option("baseline_solved_only"),
    intervention_name: list[str] | None = _lean_typer_option("intervention_name"),
    extra_intervention: list[str] | None = _lean_typer_option("extra_intervention"),
    tactic_ranker: str | None = _lean_typer_option("tactic_ranker"),
    tactic_ranker_model: str | None = _lean_typer_option("tactic_ranker_model"),
    tactic_ranker_alpha: float | None = _lean_typer_option("tactic_ranker_alpha"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    _run_lean_variants({"run": _build_lean_run_variant(locals())})


@lean_app.command("basin")
def lean_basin(
    seeds: int = typer.Option(..., "--seeds", min=1, help="Number of basin seeds"),
    blind: bool = typer.Option(False, "--blind", help="Run blind baseline per seed"),
    agent: bool = typer.Option(False, "--agent", help="Agent-optimized output"),
    mode: str | None = _lean_typer_option("mode"),
    corpus: str | None = _lean_typer_option("corpus"),
    provider: str | None = _lean_typer_option("provider"),
    providers: str | None = _lean_typer_option("providers"),
    all_providers: bool = _lean_typer_option("all_providers"),
    budget: str | None = _lean_typer_option("budget"),
    limit: int | None = _lean_typer_option("limit"),
    theorem: list[str] | None = _lean_typer_option("theorem"),
    lean_project: str | None = _lean_typer_option("lean_project"),
    trace_mcts: bool = typer.Option(False, "--trace-mcts", help="Enable MCTS tracing"),
    no_trace_mcts: bool = typer.Option(False, "--no-trace-mcts", help="Disable MCTS tracing"),
    mcts_mode: str | None = _lean_typer_option("mcts_mode"),
    mcts_expansion_policy: str | None = _lean_typer_option("mcts_expansion_policy"),
    mcts_agents: int | None = _lean_typer_option("mcts_agents"),
    mcts_inflight: int | None = _lean_typer_option("mcts_inflight"),
    mcts_block_fraction: float | None = _lean_typer_option("mcts_block_fraction"),
    mcts_block_duration: int | None = _lean_typer_option("mcts_block_duration"),
    mcts_block_seed: int | None = _lean_typer_option("mcts_block_seed"),
    mcts_block_immovable_fraction: float | None = _lean_typer_option(
        "mcts_block_immovable_fraction"
    ),
    mcts_unfreeze_after: int | None = _lean_typer_option("mcts_unfreeze_after"),
    mcts_unfreeze_prob: float | None = _lean_typer_option("mcts_unfreeze_prob"),
    mcts_reroute_blocked: bool = _lean_typer_option("mcts_reroute_blocked"),
    mcts_reroute_max: int | None = _lean_typer_option("mcts_reroute_max"),
    mcts_delay_prob: float | None = _lean_typer_option("mcts_delay_prob"),
    mcts_delay_duration: int | None = _lean_typer_option("mcts_delay_duration"),
    mcts_delay_seed: int | None = _lean_typer_option("mcts_delay_seed"),
    mcts_virtual_loss: int | None = _lean_typer_option("mcts_virtual_loss"),
    mcts_depth_bias: float | None = _lean_typer_option("mcts_depth_bias"),
    mcts_path_bias: float | None = _lean_typer_option("mcts_path_bias"),
    mcts_history_cache: bool = _lean_typer_option("mcts_history_cache"),
    mcts_deterministic_inference: bool = _lean_typer_option("mcts_deterministic_inference"),
    allow_easy: bool = _lean_typer_option("allow_easy"),
    debug: bool = _lean_typer_option("debug"),
    plain: bool = _lean_typer_option("plain"),
    sampling: bool = _lean_typer_option("sampling"),
    deepseek_num_samples: int | None = _lean_typer_option("deepseek_num_samples"),
    deepseek_model_path: str | None = _lean_typer_option("deepseek_model_path"),
    deepseek_backend: str = _lean_typer_option("deepseek_backend"),
    bfs_num_samples: int | None = _lean_typer_option("bfs_num_samples"),
    internlm_num_samples: int | None = _lean_typer_option("internlm_num_samples"),
    device: str | None = _lean_typer_option("device"),
    workers: int | None = _lean_typer_option("workers"),
    offset: int | None = _lean_typer_option("offset"),
    sample: int | None = _lean_typer_option("sample"),
    seed: int | None = _lean_typer_option("seed"),
    search_seed: int | None = _lean_typer_option("search_seed"),
    goal_sig: str | None = _lean_typer_option("goal_sig"),
    run_id: str | None = _lean_typer_option("run_id"),
    resume: bool = _lean_typer_option("resume"),
    no_solution_artifacts: bool = _lean_typer_option("no_solution_artifacts"),
    intervention_name: list[str] | None = _lean_typer_option("intervention_name"),
    extra_intervention: list[str] | None = _lean_typer_option("extra_intervention"),
    tactic_ranker: str | None = _lean_typer_option("tactic_ranker"),
    tactic_ranker_model: str | None = _lean_typer_option("tactic_ranker_model"),
    tactic_ranker_alpha: float | None = _lean_typer_option("tactic_ranker_alpha"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    _run_lean_variants({"basin": _build_lean_basin_variant(locals())})


@lean_app.command("suite")
def lean_suite(
    seeds: int = typer.Option(..., "--seeds", min=1, help="Number of basin seeds"),
    blind: bool = typer.Option(False, "--blind", help="Run blind baseline per seed"),
    agent: bool = typer.Option(False, "--agent", help="Agent-optimized output"),
    mode: str | None = _lean_typer_option("mode"),
    corpus: str | None = _lean_typer_option("corpus"),
    provider: str | None = _lean_typer_option("provider"),
    providers: str | None = _lean_typer_option("providers"),
    all_providers: bool = _lean_typer_option("all_providers"),
    budget: str | None = _lean_typer_option("budget"),
    limit: int | None = _lean_typer_option("limit"),
    theorem: list[str] | None = _lean_typer_option("theorem"),
    lean_project: str | None = _lean_typer_option("lean_project"),
    wild_only: bool = typer.Option(False, "--wild-only", help="Skip interventions"),
    with_interventions: bool = typer.Option(
        False, "--with-interventions", help="Run intervention comparisons"
    ),
    trace_mcts: bool = typer.Option(False, "--trace-mcts", help="Enable MCTS tracing"),
    no_trace_mcts: bool = typer.Option(False, "--no-trace-mcts", help="Disable MCTS tracing"),
    mcts_mode: str | None = _lean_typer_option("mcts_mode"),
    mcts_expansion_policy: str | None = _lean_typer_option("mcts_expansion_policy"),
    mcts_agents: int | None = _lean_typer_option("mcts_agents"),
    mcts_inflight: int | None = _lean_typer_option("mcts_inflight"),
    mcts_block_fraction: float | None = _lean_typer_option("mcts_block_fraction"),
    mcts_block_duration: int | None = _lean_typer_option("mcts_block_duration"),
    mcts_block_seed: int | None = _lean_typer_option("mcts_block_seed"),
    mcts_block_immovable_fraction: float | None = _lean_typer_option(
        "mcts_block_immovable_fraction"
    ),
    mcts_unfreeze_after: int | None = _lean_typer_option("mcts_unfreeze_after"),
    mcts_unfreeze_prob: float | None = _lean_typer_option("mcts_unfreeze_prob"),
    mcts_reroute_blocked: bool = _lean_typer_option("mcts_reroute_blocked"),
    mcts_reroute_max: int | None = _lean_typer_option("mcts_reroute_max"),
    mcts_delay_prob: float | None = _lean_typer_option("mcts_delay_prob"),
    mcts_delay_duration: int | None = _lean_typer_option("mcts_delay_duration"),
    mcts_delay_seed: int | None = _lean_typer_option("mcts_delay_seed"),
    mcts_virtual_loss: int | None = _lean_typer_option("mcts_virtual_loss"),
    mcts_depth_bias: float | None = _lean_typer_option("mcts_depth_bias"),
    mcts_path_bias: float | None = _lean_typer_option("mcts_path_bias"),
    mcts_history_cache: bool = _lean_typer_option("mcts_history_cache"),
    mcts_deterministic_inference: bool = _lean_typer_option("mcts_deterministic_inference"),
    allow_easy: bool = _lean_typer_option("allow_easy"),
    debug: bool = _lean_typer_option("debug"),
    plain: bool = _lean_typer_option("plain"),
    sampling: bool = _lean_typer_option("sampling"),
    deepseek_num_samples: int | None = _lean_typer_option("deepseek_num_samples"),
    deepseek_model_path: str | None = _lean_typer_option("deepseek_model_path"),
    deepseek_backend: str = _lean_typer_option("deepseek_backend"),
    bfs_num_samples: int | None = _lean_typer_option("bfs_num_samples"),
    internlm_num_samples: int | None = _lean_typer_option("internlm_num_samples"),
    device: str | None = _lean_typer_option("device"),
    workers: int | None = _lean_typer_option("workers"),
    offset: int | None = _lean_typer_option("offset"),
    sample: int | None = _lean_typer_option("sample"),
    seed: int | None = _lean_typer_option("seed"),
    search_seed: int | None = _lean_typer_option("search_seed"),
    goal_sig: str | None = _lean_typer_option("goal_sig"),
    run_id: str | None = _lean_typer_option("run_id"),
    analysis: bool = _lean_typer_option("analysis"),
    no_solution_artifacts: bool = _lean_typer_option("no_solution_artifacts"),
    baseline_solved_only: bool = _lean_typer_option("baseline_solved_only"),
    intervention_name: list[str] | None = _lean_typer_option("intervention_name"),
    extra_intervention: list[str] | None = _lean_typer_option("extra_intervention"),
    tactic_ranker: str | None = _lean_typer_option("tactic_ranker"),
    tactic_ranker_model: str | None = _lean_typer_option("tactic_ranker_model"),
    tactic_ranker_alpha: float | None = _lean_typer_option("tactic_ranker_alpha"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    _run_lean_variants(_build_lean_suite_variants(locals()), summarize=not agent)


@corpus_app.command("build-lean-mathlib")
def corpus_build_lean_mathlib(
    corpus_id: str = typer.Option("mathlib4", "--corpus-id"),
    lean_project: str = typer.Option(str(DOSSIER_ROOT / "lean_project"), "--lean-project"),
    limit: int | None = typer.Option(None, "--limit"),
    elementary_only: bool = typer.Option(True, "--elementary-only/--no-elementary-only"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_mathlib

    _build_and_emit_corpus(
        build_lean_mathlib,
        sync=sync,
        sync_reason="corpus-build-lean-mathlib",
        corpus_id=corpus_id,
        lean_project=Path(lean_project),
        limit=limit,
        elementary_only=elementary_only,
    )


@corpus_app.command("build-lean-minif2f")
def corpus_build_lean_minif2f(
    corpus_id: str = typer.Option("miniF2F-lean4", "--corpus-id"),
    rev: str = typer.Option(..., "--rev", help="Pinned git commit SHA"),
    repo_url: str = typer.Option("https://github.com/yangky11/miniF2F-lean4", "--repo-url"),
    split: list[str] = typer.Option(["Test", "Valid"], "--split"),
    limit: int | None = typer.Option(None, "--limit"),
    repo_path: str | None = typer.Option(
        None, "--repo-path", help="Use an existing local checkout"
    ),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_minif2f

    _build_and_emit_corpus(
        build_lean_minif2f,
        sync=sync,
        sync_reason="corpus-build-lean-minif2f",
        corpus_id=corpus_id,
        rev=rev,
        repo_url=repo_url,
        splits=split,
        limit=limit,
        repo_path=Path(repo_path) if repo_path else None,
    )


@corpus_app.command("build-lean-1000-plus")
def corpus_build_lean_1000_plus(
    corpus_id: str = typer.Option("1000-plus-lean", "--corpus-id"),
    rev: str = typer.Option(..., "--rev", help="Pinned git commit SHA"),
    repo_url: str = typer.Option(
        "https://github.com/1000-plus/1000-plus.github.io",
        "--repo-url",
    ),
    lean_project: str = typer.Option(str(DOSSIER_ROOT / "lean_project"), "--lean-project"),
    limit: int | None = typer.Option(None, "--limit"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_1000_plus

    _build_and_emit_corpus(
        build_lean_1000_plus,
        sync=sync,
        sync_reason="corpus-build-lean-1000-plus",
        extra_lines_factory=lambda built: _lean_1000_plus_manifest_lines(built.build_dir),
        corpus_id=corpus_id,
        rev=rev,
        repo_url=repo_url,
        lean_project=Path(lean_project),
        limit=limit,
    )


@corpus_app.command("build-lean-coq-paired-micro")
def corpus_build_lean_coq_paired_micro(
    corpus_id: str = typer.Option("coq-paired-micro-v1", "--corpus-id"),
    pairs_path: str = typer.Option(
        str(DOSSIER_ROOT / "analysis" / "benchmarks" / "lean_coq_logic_micro_v1.json"),
        "--pairs-path",
    ),
    limit: int | None = typer.Option(None, "--limit"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_coq_paired_micro

    _build_and_emit_corpus(
        build_lean_coq_paired_micro,
        sync=sync,
        sync_reason="corpus-build-lean-coq-paired-micro",
        corpus_id=corpus_id,
        pairs_path=Path(pairs_path),
        limit=limit,
    )


@corpus_app.command("build-lean-subset")
def corpus_build_lean_subset(
    corpus_id: str = typer.Option(..., "--corpus-id"),
    source_ref: str = typer.Option(..., "--source-ref"),
    theorems_path: str = typer.Option(..., "--theorems-path"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_subset

    _build_and_emit_corpus(
        build_lean_subset,
        sync=sync,
        sync_reason="corpus-build-lean-subset",
        corpus_id=corpus_id,
        source_ref=source_ref,
        theorems_path=Path(theorems_path),
    )


@corpus_app.command("build-lean-deepseek-prover-v1")
def corpus_build_lean_deepseek_prover_v1(
    corpus_id: str = typer.Option("deepseek-prover-v1", "--corpus-id"),
    revision: str = typer.Option(..., "--revision", help="Pinned HuggingFace revision (required)"),
    split: str = typer.Option("train", "--split"),
    limit: int | None = typer.Option(None, "--limit"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.build import build_lean_huggingface_deepseek_prover_v1

    _build_and_emit_corpus(
        build_lean_huggingface_deepseek_prover_v1,
        sync=sync,
        sync_reason="corpus-build-deepseek-prover-v1",
        corpus_id=corpus_id,
        revision=revision,
        split=split,
        limit=limit,
    )


@corpus_app.command("validate")
def corpus_validate(
    corpus_ref: str = typer.Option(..., "--ref"),
    lean_project: str | None = typer.Option(None, "--lean-project"),
    min_valid_rate: float = typer.Option(0.9, "--min-valid-rate"),
    allow_low_validity: bool = typer.Option(False, "--allow-low-validity"),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.validate import validate_and_derive_valid

    summary = validate_and_derive_valid(
        corpus_ref=corpus_ref,
        lean_project=Path(lean_project) if lean_project else None,
        min_valid_rate=min_valid_rate,
        allow_low_validity=allow_low_validity,
    )
    _emit_validation_result(
        headline=(
            f"Validated {summary.backend} {summary.corpus_ref}: "
            f"{summary.valid_count}/{summary.validated_count} valid ({summary.valid_rate:.1%})"
        ),
        validation_path=summary.validation_path,
        derived_dir=summary.derived_valid_dir,
        derived_label="Derived valid dir",
        sync=sync,
        sync_reason="corpus-validate",
    )

@corpus_app.command("sweep-lean-capability")
def corpus_sweep_lean_capability(
    corpus_ref: str = typer.Option(..., "--ref"),
    sweep_root: str | None = typer.Option(
        None,
        "--sweep-root",
        help=(
            "Resume or reuse an existing sweep root "
            "(must be under SPECTER_LOG_ROOT/wonton-soup/logs)"
        ),
    ),
    providers: list[str] | None = typer.Option(None, "--provider"),
    include_heuristic: bool = typer.Option(False, "--include-heuristic"),
    mcts_mode: list[str] | None = typer.Option(None, "--mcts-mode"),
    distributed_agents: int | None = typer.Option(None, "--distributed-agents"),
    distributed_inflight: int | None = typer.Option(None, "--distributed-inflight"),
    basin_seeds: int = typer.Option(5, "--basin-seeds"),
    budget: str = typer.Option("deep", "--budget", help="Budget preset (quick|standard|deep)"),
    deepseek_num_samples: int | None = typer.Option(
        None,
        "--deepseek-samples",
        help="Override DeepSeek sample count (default: provider default)",
    ),
    bfs_num_samples: int | None = typer.Option(
        None,
        "--bfs-samples",
        help="Override BFS sample count (default: provider default)",
    ),
    internlm_num_samples: int | None = typer.Option(
        None,
        "--internlm-samples",
        help="Override InternLM sample count (default: provider default)",
    ),
    offset: int = typer.Option(0, "--offset"),
    sample: int | None = typer.Option(None, "--sample"),
    seed: int | None = typer.Option(None, "--seed"),
    reachable_threshold: float = typer.Option(0.2, "--reachable-threshold"),
    min_feasible_rate: float = typer.Option(0.05, "--min-feasible-rate"),
    allow_low_feasible: bool = typer.Option(False, "--allow-low-feasible"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
    resume: bool = typer.Option(
        False,
        "--resume",
        help=(
            "Resume incomplete runs under --sweep-root (skips existing basin_analysis.json outputs)"
        ),
    ),
    sync: bool = typer.Option(False, "--sync/--no-sync", help="Sync outputs to remote"),
) -> None:
    from corpus.pipeline.capability import run_lean_capability_sweep

    if sample is not None and seed is None:
        raise typer.BadParameter("--seed is required when using --sample")

    result = run_lean_capability_sweep(
        corpus_ref=corpus_ref,
        sweep_root=sweep_root,
        providers=providers,
        include_heuristic=include_heuristic,
        mcts_modes=mcts_mode,
        distributed_agents=distributed_agents,
        distributed_inflight=distributed_inflight,
        basin_seeds=basin_seeds,
        budget=budget,
        deepseek_num_samples=deepseek_num_samples,
        bfs_num_samples=bfs_num_samples,
        internlm_num_samples=internlm_num_samples,
        offset=offset,
        sample=sample,
        seed=seed,
        reachable_threshold=reachable_threshold,
        min_feasible_rate=min_feasible_rate,
        allow_low_feasible=allow_low_feasible,
        allow_partial=allow_partial,
        resume=resume,
    )
    _emit_capability_sweep_result(
        result,
        sync=sync,
        sync_reason="corpus-sweep-lean-capability",
        include_sweep_root=True,
    )


@corpus_app.command("list")
def corpus_list(
    backend: list[str] | None = typer.Option(None, "--backend", help="Filter by backend"),
    corpus_id: list[str] | None = typer.Option(None, "--corpus-id", help="Filter by corpus id"),
    verbose: bool = typer.Option(False, "--verbose", help="Print build ids and problems"),
) -> None:
    from corpus.artifacts import list_corpora, resolve_corpora_root

    root = resolve_corpora_root()
    entries = list_corpora(root)
    if backend:
        allowed = {b.strip() for b in backend if b.strip()}
        entries = [e for e in entries if e.backend in allowed]
    if corpus_id:
        allowed = {c.strip() for c in corpus_id if c.strip()}
        entries = [e for e in entries if e.corpus_id in allowed]

    typer.echo(f"corpora_root: {root}")
    if not entries:
        typer.echo("(no corpora found)")
        return

    for e in entries:
        ref = f"{e.backend}:{e.corpus_id}"
        current = e.current_build_id or "-"
        items = str(e.items_total) if e.items_total is not None else "-"
        derived = "-"
        if e.derived_current:
            parts: list[str] = []
            for name in sorted(e.derived_current):
                did = e.derived_current[name]
                parts.append(f"{name}@{did}" if did else name)
            derived = ",".join(parts)
        warn = " !" if e.problems else ""
        typer.echo(
            f"{ref}{warn}  CURRENT={current}  builds={len(e.build_ids)}  "
            f"items={items}  derived={derived}"
        )
        if verbose and e.build_ids:
            typer.echo(f"  build_ids: {','.join(e.build_ids)}")
        if verbose and e.problems:
            for p in e.problems:
                typer.echo(f"  problem: {p}", err=True)


@app.command()
def analyze(
    run_dir: str | None = typer.Option(None, "--run-dir"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    from analysis import find_latest_corpus, generate_report, load_corpus_run

    logs_dir = resolve_logs_dir()
    generated_dir = resolve_synthetic_bureau_root()

    if run_dir:
        log_dir = Path(run_dir)
    else:
        log_dir = find_latest_corpus(logs_dir)

    if log_dir is None:
        _die(f"No corpus run found in {logs_dir}")
    assert log_dir is not None
    if not log_dir.exists():
        _die(f"Corpus run not found: {log_dir}")

    typer.echo(f"Analyzing: {log_dir.name}")

    run = load_corpus_run(log_dir)
    report = generate_report(run)

    generated_dir.mkdir(parents=True, exist_ok=True)
    output_path = generated_dir / f"{datetime.now().strftime('%Y-%m-%d')}-convergence-analysis.md"

    with open(output_path, "w") as f:
        f.write(report)

    typer.echo(f"Analysis written to: {output_path}")

    if verbose:
        typer.echo("\n" + report)


@app.command("export-learning")
def export_learning(
    run_dir: str = typer.Option(..., "--run-dir", help="Corpus run directory under logs/"),
    out_dir: str | None = typer.Option(
        None,
        "--out-dir",
        help="Output root (default: canonical local Wonton artifacts root)",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing outputs"),
) -> None:
    from analysis.export_learning_dataset import export_learning_dataset

    run_path = Path(run_dir)
    out_root = _resolve_artifact_output_root(out_dir, "learning")
    results = export_learning_dataset(run_path, out_root, overwrite=overwrite)
    _emit_provider_results(
        results,
        lambda result: f"rows={result.rows_written} -> {result.dataset_path}",
    )


@app.command("train-family-prior")
def train_family_prior(
    run_dir: str = typer.Option(..., "--run-dir", help="Corpus run directory under logs/"),
    out_dir: str | None = typer.Option(
        None,
        "--out-dir",
        help="Output root (default: canonical local Wonton artifacts root)",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing outputs"),
    epochs: int = typer.Option(25, "--epochs"),
    lr: float = typer.Option(0.2, "--lr"),
    l2: float = typer.Option(1e-3, "--l2"),
    max_weight: int = typer.Option(50, "--max-weight"),
) -> None:
    from analysis.train_family_prior import train_family_prior_from_run

    run_path = Path(run_dir)
    out_root = _resolve_artifact_output_root(out_dir, "learning")
    results = train_family_prior_from_run(
        run_path,
        out_root,
        overwrite=overwrite,
        epochs=epochs,
        lr=lr,
        l2=l2,
        max_weight=max_weight,
    )
    _emit_provider_results(
        results,
        lambda result: f"examples={result.examples} -> {result.model_path}",
    )


@app.command("transition-analysis")
def transition_analysis(
    run_dir: str = typer.Option(..., "--run-dir", help="Corpus run directory under logs/"),
    out_dir: str | None = typer.Option(
        None,
        "--out-dir",
        help="Output root (default: canonical local Wonton artifacts root)",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing outputs"),
) -> None:
    from analysis.transition_analysis import transition_analysis as run_transition_analysis

    run_path = Path(run_dir)
    out_root = _resolve_artifact_output_root(out_dir, "transition_analysis")
    results = run_transition_analysis(run_path, out_root, overwrite=overwrite)
    _emit_provider_results(results, lambda result: f"wrote under {result.out_dir}")


@lake_app.command()
def reconcile(
    logs_dir: list[str] | None = typer.Option(
        None,
        "--logs-dir",
        help="Logs directory to reconcile (repeatable). Default: canonical local Wonton logs root",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DuckDB path (default: canonical local Wonton lake)",
    ),
    prune: bool = typer.Option(
        False,
        "--prune",
        help="Delete DB rows for runs no longer on filesystem",
    ),
) -> None:
    """Index runs, extract facts, and optionally prune stale entries."""

    from analysis.lake.reconcile import reconcile as run_reconcile

    logs_dirs = [Path(resolve_logs_dir() if logs_dir is None else d) for d in (logs_dir or [])]
    if not logs_dirs:
        logs_dirs = [resolve_logs_dir()]
    logs_dirs = [Path(os.path.expanduser(str(p))).resolve() for p in logs_dirs]

    with _open_lake_db(db) as (conn, db_path):
        report = run_reconcile(conn, logs_dirs=logs_dirs, prune=prune)

    print(f"Lake DB: {db_path}")
    print(f"Indexed: {report.index.runs_indexed} runs, {report.index.files_indexed} files")
    print(
        f"Extracted: {report.extract.runs_extracted} runs, "
        f"{report.extract.wild_rows} wild, {report.extract.intervention_rows} interventions"
    )
    if report.artifacts.artifacts_indexed > 0:
        print(
            f"Artifacts: {report.artifacts.artifacts_indexed} indexed, "
            f"{report.artifacts.graph_files} graph files "
            f"({report.artifacts.graph_nodes} nodes, {report.artifacts.graph_edges} edges), "
            f"{report.artifacts.trace_files} traces "
            f"({report.artifacts.trace_rows} summarized)"
        )
    if report.basin.basin_run_rows > 0:
        print(
            f"Basin: {report.basin.basin_run_rows} theorems, "
            f"{report.basin.basin_seed_rows} seeds, "
            f"{report.basin.basin_structure_rows} structures"
        )
    if report.stale_run_keys:
        if prune:
            print(f"Pruned: {report.pruned} stale runs")
        else:
            print(f"Stale runs (use --prune to remove): {len(report.stale_run_keys)}")
    all_errors = (
        report.index.errors
        + report.extract.errors
        + report.artifacts.errors
        + report.basin.errors
    )
    if all_errors:
        print("Errors:")
        for err in all_errors[:20]:
            print(f"  {err}")


@lake_app.command("export-parquet")
def lake_export_parquet(
    out_dir: str = typer.Option(..., "--out-dir", help="Output directory for parquet files"),
    profile: str = typer.Option("full", "--profile", help="Export profile: full or dashboard"),
    release_id: str = typer.Option(
        "",
        "--release-id",
        help="Release identifier written into the manifest",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DuckDB path (default: canonical local Wonton lake)",
    ),
) -> None:
    """Export lake tables as parquet files."""

    from analysis.lake.export_parquet import export_parquet

    out_path = Path(os.path.expanduser(out_dir)).resolve()

    with _open_lake_db(db) as (conn, db_path):
        report = export_parquet(conn, profile=profile, out_dir=out_path, release_id=release_id)

    print(f"Profile: {report['profile']}")
    print(f"Output: {report['out_dir']}")
    print(f"Selected runs: {report['selected_runs']}")
    print(f"Tables: {len(report['tables'])}")
    for t in report["tables"]:
        print(f"  {t['name']}: {t['file']}")


@lake_app.command("score-k")
def lake_score_k(
    ref_id: str = typer.Option(..., "--ref-id"),
    logs_dir: str | None = typer.Option(
        None,
        "--logs-dir",
        help="Logs directory root (default: ./logs or $SPECTER_LOG_ROOT)",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--fail-fast",
        help="Continue scoring other runs when one run errors",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DuckDB path (default: canonical local Wonton lake)",
    ),
) -> None:
    """Score K-style search efficiency using a cross-run reference model."""

    from analysis.lake.db import run_dir_where_clause
    from analysis.lake.score_k import inspect_score_k_run, score_k_for_run

    root = Path(os.path.expanduser(logs_dir)).resolve() if logs_dir else resolve_logs_dir()

    discovered = 0
    eligible = 0
    ineligible = 0
    processed = 0
    failed = 0
    scored = 0
    skipped = 0
    ineligible_reasons: dict[str, int] = {}
    failures: list[str] = []
    with _open_lake_db(db) as (conn, db_path):
        clause, params = run_dir_where_clause(root=root)
        run_rows = conn.execute(
            f"SELECT run_key, run_dir FROM runs WHERE {clause} ORDER BY run_dir",
            params,
        ).fetchall()
        discovered = len(run_rows)
        for run_key, run_dir_raw in run_rows:
            if not isinstance(run_key, str) or not isinstance(run_dir_raw, str):
                continue
            run_dir = Path(run_dir_raw).resolve()
            rel = relpath_under(root, run_dir)
            state = inspect_score_k_run(run_dir)
            if not state.eligible:
                ineligible += 1
                reason = state.reason or "ineligible"
                ineligible_reasons[reason] = ineligible_reasons.get(reason, 0) + 1
                continue
            eligible += 1
            try:
                rep = score_k_for_run(conn, run_key=run_key, run_dir=run_dir, ref_id=ref_id)
            except Exception as exc:
                failed += 1
                failures.append(f"{rel}: {type(exc).__name__}: {exc}")
                if not continue_on_error:
                    raise
                continue
            processed += 1
            scored += rep.scored
            skipped += rep.skipped

    print(f"Lake DB: {db_path}")
    print(f"Reference id: {ref_id}")
    print(f"Discovered: {discovered}")
    print(f"Eligible: {eligible}")
    print(f"Ineligible: {ineligible}")
    print(f"Processed: {processed}")
    print(f"Failed: {failed}")
    print(f"Scored: {scored}")
    print(f"Skipped: {skipped}")
    if ineligible_reasons:
        print("Ineligible reasons:")
        for reason in sorted(ineligible_reasons):
            print(f"  {reason}: {ineligible_reasons[reason]}")
    if failures:
        print("Failures:")
        for msg in failures[:20]:
            print(f"  {msg}")


@lake_job_app.command("run")
def lake_job_run(
    config: str = typer.Option(..., "--config", help="Job config JSON path"),
    logs_dir: str | None = typer.Option(
        None,
        "--logs-dir",
        help="Logs directory root (default: ./logs or $SPECTER_LOG_ROOT)",
    ),
    out_dir: str | None = typer.Option(
        None,
        "--out-dir",
        help="Output directory (default: canonical local Wonton lake jobs root)",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DuckDB path (default: canonical local Wonton lake)",
    ),
) -> None:
    """Run a lake job: select runs, optionally build references, materialize datasets."""

    from analysis.lake.job import load_job_config, run_job

    job = load_job_config(Path(config).resolve())
    root = Path(os.path.expanduser(logs_dir)).resolve() if logs_dir else None
    out_path = Path(os.path.expanduser(out_dir)).resolve() if out_dir else None

    with _open_lake_db(db) as (conn, db_path):
        report = run_job(conn, job=job, logs_root=root, out_dir=out_path)

    print(f"Lake DB: {db_path}")
    print(f"Job run id: {report.job_run_id}")
    print(f"Out: {report.out_dir}")
    print(f"Selected runs: {report.selected_runs}")
    if report.ref_id:
        print(f"Reference id: {report.ref_id}")
    print("Datasets:")
    for ds in report.datasets_written:
        name = ds.get("name")
        path = ds.get("path")
        fmt = ds.get("format")
        rows = ds.get("rows")
        suffix = f" rows={rows}" if isinstance(rows, int) else ""
        print(f"  {name}: {fmt} -> {path}{suffix}")


@lake_job_app.command("presets")
def lake_job_presets(
    dir: str | None = typer.Option(
        None,
        "--dir",
        help=(
            "Directory containing preset job JSONs (default: analysis/lake/presets)"
        ),
    ),
) -> None:
    """List preset lake jobs shipped with the dossier."""

    preset_dir = (
        Path(os.path.expanduser(dir)).resolve()
        if dir
        else (DOSSIER_ROOT / "analysis" / "lake" / "presets").resolve()
    )
    if not preset_dir.exists():
        _die(f"Preset dir not found: {preset_dir}")
    paths = sorted([p for p in preset_dir.iterdir() if p.is_file() and p.suffix == ".json"])
    if not paths:
        _die(f"No presets found in: {preset_dir}")
    for p in paths:
        print(p)


@app.command("list")
def list_runs() -> None:
    logs_dir = resolve_logs_dir()

    # Rich table (falls back to plain text when not a TTY).
    import gzip
    import json

    from rich.console import Console
    from rich.table import Table

    from analysis.lake.index import discover_run_dirs
    from analysis.logs import relpath_under

    discovered = discover_run_dirs(logs_dir.resolve())
    rows: list[dict[str, str]] = []

    for provider_run in discovered:
        d = provider_run.run_dir
        run_config_path = d / "run_config.json"
        run_status_path = d / "run_status.json"
        rel_run_dir = relpath_under(logs_dir, d)
        run_id = rel_run_dir
        status = "unknown"
        backend = "?"
        provider = provider_run.provider or "?"
        corpus = "?"
        created = ""
        partial = ""
        solved_str = ""

        run_config = None
        if run_config_path.exists():
            try:
                run_config = json.loads(run_config_path.read_text())
                run_id = str(run_config.get("run_id") or run_id)
                provider = str(run_config.get("provider") or provider)
                corpus = str(run_config.get("corpus") or corpus)
                created = str(run_config.get("created_at") or "")
            except Exception:
                run_config = None
        if run_status_path.exists():
            try:
                run_status = json.loads(run_status_path.read_text())
                status = str(run_status.get("status") or status)
                scheme = str(run_status.get("goal_id_scheme") or "")
                if scheme == "checkpoint":
                    backend = "lean"
                elif scheme == "external":
                    backend = "external"
                else:
                    backend = "?"
                partial = "yes" if run_status.get("partial_results") else "no"
            except Exception:
                pass

        summary_gz = d / "summary.json.gz"
        if summary_gz.exists():
            try:
                with gzip.open(summary_gz, "rt") as f:
                    data = json.load(f)
                theorems = data.get("theorems") or []
                total = len(theorems)
                solved = 0
                for t in theorems:
                    wild = t.get("wild_type") or {}
                    if wild.get("solved"):
                        solved += 1
                solved_str = f"{solved}/{total}" if total else ""
            except Exception:
                solved_str = ""

        rows.append(
            {
                "run_id": run_id,
                "status": status,
                "backend": backend,
                "provider": provider,
                "corpus": corpus,
                "created": created,
                "solved": solved_str,
                "partial": partial,
                "rel_run_dir": rel_run_dir,
            }
        )

    rows.sort(key=lambda row: (row["created"], row["rel_run_dir"]), reverse=True)

    if not rows:
        typer.echo("No runs found.")
        return

    console = Console()
    table = Table(title=f"Recent Runs ({min(len(rows), 10)}/{len(rows)})")
    table.add_column("run_id", style="bold")
    table.add_column("status")
    table.add_column("backend")
    table.add_column("provider")
    table.add_column("corpus")
    table.add_column("created")
    table.add_column("solved", justify="right")
    table.add_column("partial", justify="center")

    for row in rows[:10]:
        table.add_row(
            row["run_id"],
            row["status"],
            row["backend"],
            row["provider"],
            row["corpus"],
            row["created"].replace("T", " ")[:19] if row["created"] else "",
            row["solved"],
            row["partial"],
        )

    console.print(table)

    if len(rows) > 10:
        typer.echo(f"\n  ... and {len(rows) - 10} more")


@app.command()
def compare(
    run_a: str = typer.Option(..., "--run-a"),
    run_b: str = typer.Option(..., "--run-b"),
    hash_mode: str = typer.Option("all", "--hash-mode"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    import json

    from analysis.summary import load_corpus_run
    from atp.compare_hash import hash_goal_sig, hash_shape
    from prover.proof import ProofGraph

    run_a_dir = Path(run_a)
    run_b_dir = Path(run_b)
    run_a_data = load_corpus_run(run_a_dir)
    run_b_data = load_corpus_run(run_b_dir)

    a_map = {t.name: t for t in run_a_data.theorems}
    b_map = {t.name: t for t in run_b_data.theorems}

    lines = []
    mismatches = []
    compared = 0

    def _load_wild_graph(run_dir: Path, theorem_name: str) -> ProofGraph:
        graph_path = run_dir / theorem_name / "wild_type_graph.json"
        if not graph_path.exists():
            raise FileNotFoundError(f"Missing wild_type_graph.json: {graph_path}")
        data = json.loads(graph_path.read_text())
        return ProofGraph.deserialize(data)

    for name in a_map:
        if name not in b_map:
            continue
        compared += 1

        a_graph = _load_wild_graph(run_a_dir, name)
        b_graph = _load_wild_graph(run_b_dir, name)

        if hash_mode in {"all", "goal-sig"}:
            a_hash = hash_goal_sig(a_graph)
            b_hash = hash_goal_sig(b_graph)
            if a_hash != b_hash:
                mismatches.append((name, "goal-sig", a_hash, b_hash))

        if hash_mode in {"all", "shape"}:
            a_hash = hash_shape(a_graph)
            b_hash = hash_shape(b_graph)
            if a_hash != b_hash:
                mismatches.append((name, "shape", a_hash, b_hash))

    lines.append(f"Compared {compared} shared theorems")
    lines.append(f"Mismatches: {len(mismatches)}")
    lines.append("")

    if mismatches:
        max_show = 25
        for name, kind, a_hash, b_hash in mismatches[:max_show]:
            lines.append(f"{name} ({kind})")
            lines.append(f"  A: {a_hash}")
            lines.append(f"  B: {b_hash}")
        if len(mismatches) > max_show:
            lines.append(f"... and {len(mismatches) - max_show} more")
        lines.append("")

    output_text = "\n".join(lines)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text)
        typer.echo(f"Wrote comparison to: {output_path}")
    else:
        typer.echo(output_text)


@app.command("compare-cross-assistant")
def compare_cross_assistant(
    run_a: str = typer.Option(..., "--run-a"),
    run_b: str = typer.Option(..., "--run-b"),
    solved_only: bool = typer.Option(False, "--solved-only"),
    top_k: int = typer.Option(3, "--top-k"),
    one_to_one: bool = typer.Option(True, "--one-to-one/--allow-many-to-one"),
    proof_aggregation: str = typer.Option(
        "single",
        "--proof-aggregation",
        help="Theorem-level proof aggregation: single | best_of | consensus",
    ),
    max_proofs_per_theorem: int | None = typer.Option(
        None,
        "--max-proofs-per-theorem",
        help="Optional cap on loaded proofs per theorem when aggregation != single",
    ),
    graph_source_a: str = typer.Option("wild_type_graph", "--graph-source-a"),
    graph_source_b: str = typer.Option("wild_type_graph", "--graph-source-b"),
    name_obfuscation: str = typer.Option("none", "--name-obfuscation"),
    name_obfuscation_salt: str = typer.Option(
        "cross-assistant-obfuscation-v1",
        "--name-obfuscation-salt",
    ),
    lexical_ablation: str = typer.Option(
        "none",
        "--lexical-ablation",
        help="Lexical ablation mode: none | drop_tokens | graph_only",
    ),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    from analysis.cross_assistant_alignment import align_runs

    report = align_runs(
        Path(run_a),
        Path(run_b),
        solved_only=solved_only,
        top_k=top_k,
        one_to_one=one_to_one,
        proof_aggregation=proof_aggregation,
        max_proofs_per_theorem=max_proofs_per_theorem,
        graph_source_a=graph_source_a,
        graph_source_b=graph_source_b,
        name_obfuscation_mode=name_obfuscation,
        name_obfuscation_salt=name_obfuscation_salt,
        lexical_ablation_mode=lexical_ablation,
    )

    summary = report.get("summary") if isinstance(report, dict) else None
    matches = report.get("matches", []) if isinstance(report, dict) else []
    def _summary_value(key: str) -> Any:
        if not isinstance(summary, dict):
            return None
        return summary.get(key)

    lines = [
        "Mode: diagnostic (use benchmark-cross-assistant for gated evaluation)",
        f"Run A theorems: {report.get('run_a_theorems')}",
        f"Run B theorems: {report.get('run_b_theorems')}",
        f"Run A proofs: {report.get('run_a_proofs')}",
        f"Run B proofs: {report.get('run_b_proofs')}",
        f"Graph source A: {report.get('graph_sources', {}).get('run_a')}",
        f"Graph source B: {report.get('graph_sources', {}).get('run_b')}",
        f"Proof aggregation: {report.get('proof_aggregation')}",
        f"Max proofs per theorem: {report.get('max_proofs_per_theorem')}",
        f"Lexical ablation mode: {report.get('lexical_ablation', {}).get('mode')}",
        f"Matches: {_summary_value('matches') or 0}",
        f"Mean distance: {_summary_value('mean_distance')}",
        f"Mean graph distance: {_summary_value('mean_graph_distance')}",
        f"Mean lexical distance: {_summary_value('mean_lexical_distance')}",
        f"Mean connective distance: {_summary_value('mean_connective_distance')}",
        f"Mean lexical overlap: {_summary_value('mean_lexical_overlap')}",
        (
            "Reciprocal top1 rate: "
            f"{_summary_value('reciprocal_top1_rate')}"
        ),
        f"Shape hash equal rate: {_summary_value('shape_hash_equal_rate')}",
        f"Cross-kind rate: {_summary_value('cross_kind_rate')}",
        f"Top1 unique rate: {_summary_value('top1_unique_rate')}",
        f"Run A statement coverage: {_summary_value('run_a_statement_coverage')}",
        f"Run B statement coverage: {_summary_value('run_b_statement_coverage')}",
        f"Run A lexical coverage: {_summary_value('run_a_lexical_coverage')}",
        f"Run B lexical coverage: {_summary_value('run_b_lexical_coverage')}",
        "",
    ]

    max_show = 25
    if isinstance(matches, list):
        for row in matches[:max_show]:
            if not isinstance(row, dict):
                continue
            theorem_a = row.get("theorem_a")
            theorem_b = row.get("theorem_b")
            distance = row.get("distance")
            reciprocal = row.get("reciprocal_top1")
            lines.append(
                f"{theorem_a} -> {theorem_b} | distance={distance} | reciprocal_top1={reciprocal}"
            )
        if len(matches) > max_show:
            lines.append(f"... and {len(matches) - max_show} more")

    _emit_text_report(
        "\n".join(lines),
        report,
        output=output,
        label="cross-assistant alignment report",
    )


@app.command("inspect-proof-ir")
def inspect_proof_ir(
    run_dir: str = typer.Option(..., "--run-dir"),
    theorem: str = typer.Option(..., "--theorem"),
    variant: str = typer.Option("wild_type", "--variant"),
    provider: str | None = typer.Option(None, "--provider"),
    graph_source: str = typer.Option("wild_type_graph", "--graph-source"),
    name_obfuscation: str = typer.Option("none", "--name-obfuscation"),
    name_obfuscation_salt: str = typer.Option(
        "cross-assistant-obfuscation-v1",
        "--name-obfuscation-salt",
    ),
    lexical_ablation: str = typer.Option(
        "none",
        "--lexical-ablation",
        help="Lexical ablation mode: none | drop_tokens | graph_only",
    ),
    compare_run_dir: str | None = typer.Option(None, "--compare-run-dir"),
    compare_theorem: str | None = typer.Option(None, "--compare-theorem"),
    compare_variant: str = typer.Option("wild_type", "--compare-variant"),
    compare_provider: str | None = typer.Option(None, "--compare-provider"),
    compare_graph_source: str | None = typer.Option(None, "--compare-graph-source"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    from analysis.cross_assistant_alignment import LexicalAblationConfig, NameObfuscationConfig
    from analysis.inspect_proof_ir import inspect_theorem_ir, inspect_theorem_ir_pair

    variant = _coerce_typer_option(variant, "wild_type")
    provider = _coerce_typer_option(provider, None)
    graph_source = _coerce_typer_option(graph_source, "wild_type_graph")
    name_obfuscation = _coerce_typer_option(name_obfuscation, "none")
    name_obfuscation_salt = _coerce_typer_option(
        name_obfuscation_salt,
        "cross-assistant-obfuscation-v1",
    )
    lexical_ablation = _coerce_typer_option(lexical_ablation, "none")
    compare_run_dir = _coerce_typer_option(compare_run_dir, None)
    compare_theorem = _coerce_typer_option(compare_theorem, None)
    compare_variant = _coerce_typer_option(compare_variant, "wild_type")
    compare_provider = _coerce_typer_option(compare_provider, None)
    compare_graph_source = _coerce_typer_option(compare_graph_source, None)
    output = _coerce_typer_option(output, None)

    if compare_run_dir and not compare_theorem:
        raise typer.BadParameter("--compare-theorem is required when --compare-run-dir is set")
    if compare_theorem and compare_run_dir is None:
        compare_run_dir = run_dir
    compare_target_run = compare_run_dir or run_dir
    compare_source = compare_graph_source or graph_source
    obfuscation = NameObfuscationConfig(
        mode=name_obfuscation,
        salt=name_obfuscation_salt,
    )
    ablation = LexicalAblationConfig(mode=lexical_ablation)

    def _format_profile(profile: dict[str, Any]) -> str:
        if not isinstance(profile, dict) or not profile:
            return "(empty)"
        parts = [f"{key}={value:.3f}" for key, value in sorted(profile.items())]
        return ", ".join(parts)

    if compare_theorem:
        report = inspect_theorem_ir_pair(
            Path(run_dir),
            theorem_a=theorem,
            variant_a=variant,
            provider_a=provider,
            graph_source_a=graph_source,
            run_b_dir=Path(compare_target_run),
            theorem_b=compare_theorem,
            variant_b=compare_variant,
            provider_b=compare_provider,
            graph_source_b=compare_source,
            name_obfuscation=obfuscation,
            lexical_ablation=ablation,
        )
        left = report["left"]
        right = report["right"]
        distance = report["distance"]
        lines = [
            f"Left theorem: {left['theorem']} ({left['variant']})",
            f"Right theorem: {right['theorem']} ({right['variant']})",
            f"Left graph family: {left['graph']['family']}",
            f"Right graph family: {right['graph']['family']}",
            f"Distance total: {distance['total']}",
            f"Distance graph: {distance['graph']}",
            f"Distance lexical: {distance['lexical']}",
            f"Distance connective: {distance['connective']}",
            f"Lexical overlap: {distance['lexical_overlap']}",
            f"Cross kind: {distance['cross_kind']}",
            "",
            "Left continuation profile: "
            f"{_format_profile(left['proof_ir']['continuation_profile'])}",
            "Right continuation profile: "
            f"{_format_profile(right['proof_ir']['continuation_profile'])}",
            "Left coupling profile: "
            f"{_format_profile(left['proof_ir']['coupling_profile'])}",
            "Right coupling profile: "
            f"{_format_profile(right['proof_ir']['coupling_profile'])}",
        ]
    else:
        inspected = inspect_theorem_ir(
            Path(run_dir),
            theorem=theorem,
            variant=variant,
            provider=provider,
            graph_source=graph_source,
            name_obfuscation=obfuscation,
            lexical_ablation=ablation,
        )
        report = inspected.payload
        actions = report["actions"]
        lines = [
            f"Theorem: {report['theorem']} ({report['variant']})",
            f"Provider: {report.get('provider')}",
            f"Graph source: {report['graph_source']}",
            f"Graph family: {report['graph']['family']}",
            (
                "Graph counts: "
                f"nodes={report['graph']['node_count']} edges={report['graph']['edge_count']}"
                f" depth={report['graph']['max_depth']}"
            ),
            f"Lexical tokens: {report['lexical']['token_count']}",
            f"Edge role profile: {_format_profile(report['proof_ir']['edge_role_profile'])}",
            f"Operator profile: {_format_profile(report['proof_ir']['operator_profile'])}",
            f"Continuation profile: {_format_profile(report['proof_ir']['continuation_profile'])}",
            f"Coupling profile: {_format_profile(report['proof_ir']['coupling_profile'])}",
            f"Action count: {len(actions)}",
            "",
            "Actions:",
        ]
        max_actions = 12
        for action in actions[:max_actions]:
            effect_flags = ",".join(action["effect_flags"]) or "-"
            lines.append(
                "  "
                f"{action['index']}. {action['operator_kind']} / {action['motif_kind']} "
                f"| kind={action['action_kind']} "
                f"| branch_arity={action['branch_arity']} "
                f"| continuation={action['continuation_kind']} "
                f"| coupling={action['goal_coupling']} "
                f"| effects={effect_flags}"
            )
        if len(actions) > max_actions:
            lines.append(f"  ... and {len(actions) - max_actions} more actions")

    _emit_text_report(
        "\n".join(lines),
        report,
        output=output,
        label="proof IR inspection report",
    )


@app.command("benchmark-cross-assistant")
def benchmark_cross_assistant(
    run_lean: str = typer.Option(..., "--run-lean"),
    run_coq: str = typer.Option(..., "--run-coq"),
    pairs: str = typer.Option(
        str(DOSSIER_ROOT / "analysis" / "benchmarks" / "lean_coq_logic_micro_v1.json"),
        "--pairs",
    ),
    solved_only: bool = typer.Option(False, "--solved-only"),
    graph_source_lean: str = typer.Option("wild_type_graph", "--graph-source-lean"),
    graph_source_coq: str = typer.Option("wild_type_graph", "--graph-source-coq"),
    name_obfuscation: str = typer.Option("none", "--name-obfuscation"),
    name_obfuscation_salt: str = typer.Option(
        "cross-assistant-obfuscation-v1",
        "--name-obfuscation-salt",
    ),
    lexical_ablation: str = typer.Option(
        "none",
        "--lexical-ablation",
        help="Lexical ablation mode: none | drop_tokens | graph_only",
    ),
    gate_claim: str = typer.Option(
        "all",
        "--gate-claim",
        help="Which gate claim to enforce: all | global | cross_kind | same_kind",
    ),
    gate_axis: str = typer.Option(
        "all",
        "--gate-axis",
        help="Which gate axis to enforce: all | coverage | quality",
    ),
    proof_aggregation: str = typer.Option(
        "single",
        "--proof-aggregation",
        help="Theorem-level proof aggregation: single | best_of | consensus",
    ),
    max_proofs_per_theorem: int | None = typer.Option(
        None,
        "--max-proofs-per-theorem",
        help="Optional cap on loaded proofs per theorem when aggregation != single",
    ),
    k: list[int] | None = typer.Option(None, "--k"),
    output: str | None = typer.Option(None, "--output"),
    fail_on_gate: bool = typer.Option(True, "--fail-on-gate/--no-fail-on-gate"),
) -> None:
    from analysis.cross_assistant_paired_benchmark import evaluate_paired_benchmark

    report = evaluate_paired_benchmark(
        run_lean_dir=Path(run_lean),
        run_coq_dir=Path(run_coq),
        pairs_path=Path(pairs),
        solved_only=solved_only,
        ks=k,
        graph_source_lean=graph_source_lean,
        graph_source_coq=graph_source_coq,
        name_obfuscation_mode=name_obfuscation,
        name_obfuscation_salt=name_obfuscation_salt,
        lexical_ablation_mode=lexical_ablation,
        gate_claim=gate_claim,
        gate_axis=gate_axis,
        proof_aggregation=proof_aggregation,
        max_proofs_per_theorem=max_proofs_per_theorem,
    )
    summary = report.get("summary", {})
    gate = report.get("gate", {})
    summary_by_kind = summary.get("by_kind", {})

    lines = [
        "Mode: paired benchmark (primary cross-assistant gate)",
        f"Run Lean theorems: {report.get('run_lean')}",
        f"Run Coq theorems: {report.get('run_coq')}",
        f"Graph source Lean: {report.get('graph_sources', {}).get('run_lean')}",
        f"Graph source Coq: {report.get('graph_sources', {}).get('run_coq')}",
        f"Name obfuscation mode: {report.get('name_obfuscation', {}).get('mode')}",
        f"Lexical ablation mode: {report.get('lexical_ablation', {}).get('mode')}",
        f"Gate claim: {gate.get('claim')}",
        f"Gate axis: {gate.get('axis')}",
        f"Proof aggregation: {report.get('proof_aggregation')}",
        f"Max proofs per theorem: {report.get('max_proofs_per_theorem')}",
        f"Pairs total: {summary.get('pairs_total')}",
        f"Pairs evaluated: {summary.get('pairs_evaluated')}",
        f"Pairs missing: {summary.get('pairs_missing')}",
        f"Eval rate: {summary.get('eval_rate')}",
        f"MRR: {summary.get('mrr')}",
        f"Mean rank: {summary.get('mean_rank')}",
        f"Median rank: {summary.get('median_rank')}",
        f"Recall@1: {summary.get('recall_at_1')}",
        f"Recall@3: {summary.get('recall_at_3')}",
        f"Recall@5: {summary.get('recall_at_5')}",
        f"Recall@10: {summary.get('recall_at_10')}",
        f"Gate passed: {gate.get('passed')}",
    ]
    if isinstance(summary_by_kind, dict):
        for kind in sorted(summary_by_kind.keys()):
            bucket = summary_by_kind.get(kind)
            if not isinstance(bucket, dict):
                continue
            lines.extend(
                [
                    f"{kind} pairs: {bucket.get('pairs_evaluated')}",
                    f"{kind} MRR: {bucket.get('mrr')}",
                    f"{kind} Recall@1: {bucket.get('recall_at_1')}",
                    f"{kind} Recall@10: {bucket.get('recall_at_10')}",
                ]
            )
    failures = gate.get("failures")
    if isinstance(failures, list) and failures:
        lines.append("Gate failures:")
        for failure in failures:
            lines.append(f"  - {failure}")

    _emit_text_report(
        "\n".join(lines),
        report,
        output=output,
        label="paired benchmark report",
    )

    if fail_on_gate and gate.get("passed") is False:
        raise typer.Exit(code=1)


@app.command("analysis")
def analysis(
    mode: str = typer.Argument("edit", help="edit, run, or export"),
    output: str = typer.Option(
        "analysis/notebooks/deep_analysis.html", "--output", "-o",
    ),
) -> None:
    """Open the deep analysis Marimo notebook against the lake DB."""
    import subprocess

    notebook = DOSSIER_ROOT / "analysis" / "notebooks" / "deep_analysis.py"
    if not notebook.exists():
        raise typer.BadParameter(f"Notebook not found: {notebook}")

    from analysis.lake.db import resolve_lake_paths

    lake_db = resolve_lake_paths().db_path
    if not lake_db.exists():
        _die(f"Lake DB not found: {lake_db} (set SPECTER_ARTIFACT_ROOT or run `lake reconcile`)")

    env = {**os.environ, "LAKE_DB_PATH": str(lake_db)}

    if mode == "edit":
        print(f"Opening notebook (lake: {lake_db})")
        subprocess.run(["marimo", "edit", str(notebook)], env=env, check=True)
    elif mode == "run":
        print(f"Running notebook headless (lake: {lake_db})")
        subprocess.run(["marimo", "run", str(notebook)], env=env, check=True)
    elif mode == "export":
        out = DOSSIER_ROOT / output
        print(f"Exporting to {out} (lake: {lake_db})")
        subprocess.run(
            ["marimo", "export", "html", str(notebook), "-o", str(out)],
            env=env,
            check=True,
        )
    else:
        raise typer.BadParameter(f"Unknown mode: {mode}. Use edit, run, or export.")


if __name__ == "__main__":
    assert_wonton_python_runtime(dossier_root=DOSSIER_ROOT, command_name="wonton.py")
    app()
