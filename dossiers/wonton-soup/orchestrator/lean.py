# ruff: noqa: E402
import asyncio
import gc
import json
import logging
import os
import shutil
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, NoReturn, cast

from dotenv import load_dotenv

from orchestrator import lean_basin as _lean_basin
from orchestrator import lean_checkpoints as _lean_checkpoints
from orchestrator import lean_metadata
from orchestrator import lean_reporting as _lean_reporting
from orchestrator import lean_runner as _lean_runner
from orchestrator.lean_inputs import EASY_TACTICS, create_provider, load_corpus
from orchestrator.lean_metadata import (
    distributed_settings_snapshot as _distributed_settings_snapshot,
)
from orchestrator.lean_metadata import write_run_config as _write_run_config
from orchestrator.lean_options import BUDGET_PRESETS
from orchestrator.lean_progress import CorpusProgress
from orchestrator.lean_progress import ProgressCallback as _ProgressCallback
from prover.mcts import ExpansionPolicy, coerce_expansion_policy
from run_capabilities import default_run_capabilities, normalize_run_capabilities
from runtime_paths import (
    configured_remote_log_archives_root as configured_remote_logs_root,
)
from runtime_paths import (
    resolve_logs_root as _resolve_runtime_logs_root,
)
from runtime_paths import (
    sync_logs_from_remote,
    sync_logs_to_remote,
)

DOSSIER_NAME = "wonton-soup"
DOSSIER_ROOT = Path(__file__).resolve().parents[1]


def resolve_logs_dir() -> Path:
    return _resolve_runtime_logs_root()


def _lean_repl_dir() -> Path:
    from leantree.core.project import LeanProject

    return LeanProject._get_default_repl_path()


def _lean_repl_exe_path() -> Path:
    return _lean_repl_dir() / ".lake" / "build" / "bin" / "repl"


def _mathlib_cache_root(project_path: Path) -> Path:
    return (
        project_path
        / ".lake"
        / "packages"
        / "mathlib"
        / ".lake"
        / "build"
        / "lib"
        / "lean"
        / "Mathlib"
    )


def _has_olean_files(root: Path) -> bool:
    try:
        next(root.rglob("*.olean"))
    except StopIteration:
        return False
    return True


def _print_wonton_flake_hint() -> None:
    print("Run this from dossiers/wonton-soup inside the pinned Wonton environment:")
    print("  uv run python setup_lean.py")


def _assert_lean_project_ready(project_path: str | Path) -> Path:
    path = Path(project_path).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: Lean project not found: {path}")
        _print_wonton_flake_hint()
        raise SystemExit(1)

    repl_path = _lean_repl_exe_path()
    if not repl_path.exists():
        print(f"ERROR: Lean REPL executable not found: {repl_path}")
        print(f"Build it from the installed leantree REPL directory: {_lean_repl_dir()}")
        print("  lake build")
        raise SystemExit(1)

    mathlib_root = _mathlib_cache_root(path)
    if not mathlib_root.exists() or not _has_olean_files(mathlib_root):
        print(f"ERROR: Lean project cache is cold or missing: {mathlib_root}")
        print("Warm the Lean project before running theorem batches:")
        _print_wonton_flake_hint()
        print("If the project already exists, you can also refresh it manually:")
        print("  cd lean_project")
        print("  lake exe cache get")
        print("  lake build")
        raise SystemExit(1)

    return path


def _has_ymd_prefix(value: str) -> bool:
    # Expected: YYYY-MM-DD-... or prefix-YYYY-MM-DD-...
    if len(value) < 11:
        return False
    # Check if starts with YYYY-MM-DD-
    if value[4] == "-" and value[7] == "-" and value[10] == "-":
        y = value[0:4]
        m = value[5:7]
        d = value[8:10]
        if y.isdigit() and m.isdigit() and d.isdigit():
            return True
    # Check if contains -YYYY-MM-DD- anywhere in the string
    for i in range(len(value) - 10):
        if value[i + 4] == "-" and value[i + 7] == "-" and value[i + 10] == "-":
            y = value[i : i + 4]
            m = value[i + 5 : i + 7]
            d = value[i + 8 : i + 10]
            if y.isdigit() and m.isdigit() and d.isdigit():
                return True
    return False


def _prefix_run_id_with_ymd(run_id: str) -> str:
    head, sep, tail = run_id.partition("/")
    if _has_ymd_prefix(head):
        return run_id
    date = datetime.now().strftime("%Y-%m-%d")
    return f"{date}-{head}{sep}{tail}" if sep else f"{date}-{head}"


load_dotenv()

from leantree.repl_adapter.error_metadata import build_error_record
from leantree.repl_adapter.interaction import LeanInteractionException, LeanProcessException

from analysis.trajectory import TrajectoryComparison
from corpus.lean.theorems import Intervention, Theorem
from corpus.selection import select_items
from prover import (
    ExplorationHistory,
    ExprDAG,
    GoalCache,
    LeanAdapter,
    MCTSTraceWriter,
    MCTSTree,
    ProofAssemblyTrace,
    ProofGraph,
)
from prover.goal_signature import GoalSignatureConfig
from prover.providers import TacticProvider

TacticRanker = Callable[[list[tuple[str, float]], int, Any], list[tuple[str, float]]]
TacticRankerAgent = Callable[
    [list[tuple[str, float]], int, Any, int],
    list[tuple[str, float]],
]
TieBreaker = Callable[[list[tuple[str, Any]], int], tuple[str, Any]]
TieBreakerAgent = Callable[[list[tuple[str, Any]], int, int], tuple[str, Any]]
TacticRankerFactory = Callable[[Theorem, int], TacticRanker | None]
TacticRankerAgentFactory = Callable[[Theorem, int], TacticRankerAgent | None]
TieBreakerFactory = Callable[[Theorem, int], TieBreaker | None]
TieBreakerAgentFactory = Callable[[Theorem, int], TieBreakerAgent | None]


@dataclass
class RunResult:
    solved: bool
    stats: dict
    graph: ProofGraph
    history: ExplorationHistory
    proof_term: ExprDAG | None = None
    assembly_trace: ProofAssemblyTrace | None = None
    mcts_tree: MCTSTree | None = None


@dataclass
class InterventionResult:
    intervention: Intervention
    wild_type: RunResult
    intervention_run: RunResult
    ged: float | None
    ged_normalized: float | None = None
    trajectory_comparison: TrajectoryComparison | None = None


@dataclass
class TheoremResult:
    theorem: Theorem
    wild_type: RunResult
    interventions: list[InterventionResult] = field(default_factory=list)
    search_seed: int | None = None


_build_run_capabilities = lean_metadata.build_run_capabilities


@dataclass
class CrashedTheorem:
    theorem_name: str
    error: str
    error_kind: str | None = None
    error_summary: str | None = None
    repl_messages: list[dict[str, Any]] | None = None

    @classmethod
    def from_error(cls, theorem_name: str, error: str | Exception) -> "CrashedTheorem":
        record = build_error_record(error)
        error_kind = record.get("error_kind")
        error_summary = record.get("error_summary")
        repl_messages = record.get("repl_messages")
        return cls(
            theorem_name=theorem_name,
            error=record["error"],
            error_kind=error_kind if isinstance(error_kind, str) and error_kind else None,
            error_summary=(
                error_summary if isinstance(error_summary, str) and error_summary else None
            ),
            repl_messages=(
                repl_messages if isinstance(repl_messages, list) and repl_messages else None
            ),
        )

    def display_error(self) -> str:
        return self.error_summary or self.error

    def serialize(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.theorem_name,
            "error": self.error,
        }
        if self.error_kind:
            payload["error_kind"] = self.error_kind
        if self.error_summary:
            payload["error_summary"] = self.error_summary
        if self.repl_messages:
            payload["repl_messages"] = self.repl_messages
        return payload


ProgressCallback = _ProgressCallback

def handle_lean_exception(
    e: LeanInteractionException | LeanProcessException,
    theorem_name: str,
) -> CrashedTheorem:
    logger = logging.getLogger(__name__)
    crash = CrashedTheorem.from_error(theorem_name, e)
    if isinstance(e, LeanInteractionException):
        logger.warning(f"Theorem {theorem_name} has syntax/type error: {crash.display_error()}")
    else:
        logger.error(f"REPL crashed on {theorem_name}: {crash.display_error()}")
    return crash

@contextmanager
def _open_mcts_trace_writer(
    *,
    enabled: bool,
    log_dir: Path | None,
    theorem_name: str,
    filename: str,
) -> Iterator[MCTSTraceWriter | None]:
    if not enabled:
        yield None
        return
    if log_dir is None:
        raise ValueError("log_dir is required when trace_mcts is enabled")

    final_path = log_dir / theorem_name / filename
    final_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path = final_path
    if _io_spooling_enabled():
        trace_path = _io_spool_path(
            log_dir=log_dir,
            relpath=Path(theorem_name) / filename,
        )
        trace_path.parent.mkdir(parents=True, exist_ok=True)

    trace = MCTSTraceWriter(trace_path)
    try:
        yield trace
    finally:
        trace.close()
        if trace_path != final_path:
            _materialize_spooled_file(
                spool_path=trace_path,
                final_path=final_path,
                logger=logging.getLogger(__name__),
            )


_write_run_result_artifacts = _lean_reporting._write_run_result_artifacts
save_results = _lean_reporting.save_results


def _io_spooling_enabled() -> bool:
    remote_logs = configured_remote_logs_root()
    if remote_logs is None:
        return False
    # Spooling is only useful when we write directly to the remote log root.
    return resolve_logs_dir().resolve() == remote_logs.resolve()


def _io_spool_root() -> Path:
    # Use the repo-level tmp/ (gitignored) rather than dossier-local tmp/ to avoid
    # leaving unignored runtime artifacts under dossiers/.
    repo_root = DOSSIER_ROOT.parents[1]
    return (repo_root / "tmp" / "io-spool" / DOSSIER_NAME).resolve()


def _io_spool_run_root(*, log_dir: Path) -> Path:
    # Include PID to avoid collisions across concurrent runs using the same log_dir name.
    run_key = f"{log_dir.name}.pid={os.getpid()}"
    return _io_spool_root() / run_key


def _io_spool_path(*, log_dir: Path, relpath: str | Path) -> Path:
    rel = Path(relpath)
    if rel.is_absolute():
        raise ValueError(f"Spool relpath must not be absolute: {rel}")
    return _io_spool_run_root(log_dir=log_dir) / rel


def _materialize_spooled_file(
    *,
    spool_path: Path,
    final_path: Path,
    logger: logging.Logger,
) -> None:
    if not spool_path.exists():
        return
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    try:
        size = spool_path.stat().st_size
        start = time.monotonic()
        shutil.copyfile(spool_path, tmp_path)
        tmp_path.replace(final_path)
        spool_path.unlink(missing_ok=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "Materialized spooled file: %s bytes to %s in %.1fms",
            size,
            final_path,
            elapsed_ms,
        )
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        logger.warning(
            (
                "Failed to materialize spooled file; leaving spool in place. "
                "spool=%s final=%s err=%s:%s"
            ),
            spool_path,
            final_path,
            type(exc).__name__,
            exc,
        )


def _sync_run_dir_to_remote(
    *,
    local_log_dir: Path,
    logger: logging.Logger,
    reason: str,
) -> None:
    start = time.monotonic()
    report = sync_logs_to_remote(local_log_dir, require_src=False)
    if report is None:
        return
    elapsed = time.monotonic() - start
    logger.info(
        (
            "Synced logs to remote: src=%s dst=%s copied=%s skipped=%s bytes=%s "
            "reason=%s elapsed=%.2fs"
        ),
        report.src_root,
        report.dst_root,
        report.copied_files,
        report.skipped_files,
        report.copied_bytes,
        reason,
        elapsed,
    )


class _BufferedFileHandler(logging.Handler):
    def __init__(
        self,
        path: Path,
        *,
        flush_every: int = 256,
        flush_interval_s: float = 1.0,
    ) -> None:
        super().__init__()
        self.path = path
        self._flush_every = flush_every if flush_every > 0 else 0
        self._flush_interval_s = max(0.0, float(flush_interval_s))
        self._records_since_flush = 0
        self._last_flush = time.monotonic()
        self._handle = path.open("w", encoding="utf-8", buffering=1024 * 1024)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._handle.write(msg + "\n")
        self._records_since_flush += 1
        if self._flush_every and (self._records_since_flush % self._flush_every == 0):
            self._handle.flush()
            self._last_flush = time.monotonic()
            return
        if (
            self._flush_interval_s
            and (time.monotonic() - self._last_flush) >= self._flush_interval_s
        ):
            self._handle.flush()
            self._last_flush = time.monotonic()

    def close(self) -> None:
        try:
            self._handle.flush()
        except Exception:
            pass
        try:
            self._handle.close()
        finally:
            super().close()


def _format_budget_tiers(budget_tiers: list[int]) -> str:
    tiers = ",".join(str(b) for b in budget_tiers)
    total = sum(budget_tiers)
    return f"{tiers} (total {total})"


def _cleanup_torch_memory() -> None:
    gc.collect()
    try:
        import torch
    except Exception:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json_atomic(path: Path, payload: Any, *, indent: int = 2) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=indent)
    tmp_path.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def _normalize_run_status_payload(status: dict[str, Any]) -> dict[str, Any]:
    payload = dict(status)
    raw_capabilities = payload.get("capabilities")
    if isinstance(raw_capabilities, dict):
        payload["capabilities"] = normalize_run_capabilities(raw_capabilities)
    elif raw_capabilities is None:
        payload["capabilities"] = default_run_capabilities()
    return payload


def _write_run_status(log_dir: Path, status: dict[str, Any]) -> None:
    _write_json_atomic(log_dir / "run_status.json", _normalize_run_status_payload(status))


def _write_latest_run(
    run_dir: Path, providers: list[str], provider: str | None, multi_provider: bool
) -> None:
    logs_dir = resolve_logs_dir()
    try:
        rel = run_dir.relative_to(logs_dir).as_posix()
    except ValueError:
        rel = run_dir.name
    payload = {
        "run_dir": rel,
        "updated_at": _timestamp(),
        "providers": providers,
        "provider": provider,
        "multi_provider": multi_provider,
    }
    latest_run_path = logs_dir / "latest_run.json"
    _write_json_atomic(latest_run_path, payload)
    if not latest_run_path.exists():
        raise RuntimeError(f"latest_run.json missing after write in {logs_dir}")


class RunStatusWriter:
    def __init__(
        self,
        *,
        log_dir: Path,
        initial_status: dict[str, Any],
        materialize_interval_s: float = 2.0,
    ) -> None:
        self.log_dir = log_dir
        self._payload = dict(initial_status)
        self._lock = threading.Lock()
        self._last_progress_write = 0.0
        self._spool_path: Path | None = None
        self._last_materialize = 0.0
        self._materialize_interval_s = materialize_interval_s
        self._spool_writes = 0
        self._materialize_writes = 0
        if _io_spooling_enabled():
            self._spool_path = _io_spool_path(log_dir=log_dir, relpath="run_status.json")
            self._spool_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def payload(self) -> dict[str, Any]:
        return self._payload

    def io_debug_payload(self) -> dict[str, Any] | None:
        if self._spool_path is None:
            return None
        return {
            "status_local_writes": self._spool_writes,
            "status_materialize_writes": self._materialize_writes,
            "status_materialize_interval_s": self._materialize_interval_s,
        }

    def write_initial(self) -> None:
        with self._lock:
            self._write_locked(force_materialize=True)

    def write_progress(self, progress: dict[str, Any], *, force: bool = False) -> None:
        now_wall = time.time()
        if not force and now_wall - self._last_progress_write < 0.5:
            return
        self._last_progress_write = now_wall
        with self._lock:
            self._payload["progress"] = progress
            self._write_locked(force_materialize=force)

    def finalize(
        self,
        *,
        status_value: str,
        partial_results: bool,
        capabilities: dict[str, Any],
        error: str | Exception | None = None,
        traceback_text: str | None = None,
    ) -> None:
        with self._lock:
            self._payload["capabilities"] = capabilities
            self._payload.update(
                {
                    "status": status_value,
                    "completed_at": _timestamp(),
                    "partial_results": partial_results,
                }
            )
            if error is not None:
                if isinstance(traceback_text, str) and traceback_text:
                    self._payload["traceback"] = traceback_text
                record = build_error_record(error)
                self._payload["error"] = record["error"]
                error_kind = record.get("error_kind")
                if isinstance(error_kind, str) and error_kind:
                    self._payload["error_kind"] = error_kind
                error_summary = record.get("error_summary")
                if isinstance(error_summary, str) and error_summary:
                    self._payload["error_summary"] = error_summary
            self._write_locked(force_materialize=True)

    def _write_locked(self, *, force_materialize: bool) -> None:
        payload = _normalize_run_status_payload(self._payload)
        final_path = self.log_dir / "run_status.json"
        if self._spool_path is None:
            _write_json_atomic(final_path, payload)
            return
        _write_json_atomic(self._spool_path, payload)
        self._spool_writes += 1
        now_mono = time.monotonic()
        if force_materialize or (
            now_mono - self._last_materialize
        ) >= self._materialize_interval_s:
            self._last_materialize = now_mono
            self._materialize_writes += 1
            _materialize_spooled_file(
                spool_path=self._spool_path,
                final_path=final_path,
                logger=logging.getLogger("orchestrator.lean"),
            )


@dataclass
class RunLifecycle:
    log_dir: Path
    logger: logging.Logger
    trace_mcts: bool
    no_sync: bool
    results: list[TheoremResult]
    status_writer: RunStatusWriter
    failed: bool = False
    error: Exception | None = None
    error_trace: str | None = None

    def record_failure(self, error: Exception) -> None:
        if self.failed:
            return
        self.failed = True
        self.error = error
        self.error_trace = traceback.format_exc()

    def finalize(
        self,
        *,
        status_value: str,
        partial_results: bool,
        sync_reason: str,
        has_goal_cache: bool | None = None,
        error: str | Exception | None = None,
        traceback_text: str | None = None,
    ) -> None:
        self.status_writer.finalize(
            status_value=status_value,
            partial_results=partial_results,
            capabilities=_build_run_capabilities(
                self.results,
                has_goal_cache=(
                    _lean_checkpoints._goal_cache_exists(self.log_dir)
                    if has_goal_cache is None
                    else has_goal_cache
                ),
                has_mcts_trace=self.trace_mcts,
            ),
            error=error,
            traceback_text=traceback_text,
        )
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        if not self.no_sync:
            _sync_run_dir_to_remote(
                local_log_dir=self.log_dir,
                logger=self.logger,
                reason=sync_reason,
            )


def _select_theorems_for_run(
    theorem_corpus: list[Theorem],
    *,
    theorem_name: str | None,
    corpus_label: str,
    logger: logging.Logger,
    resume: bool,
    log_dir: Path,
    corpus: str,
    offset: int,
    limit: int | None,
    sample: int | None,
    seed: int | None,
) -> tuple[list[Theorem], str | None, str, int | None]:
    if theorem_name is not None:
        matching = [theorem for theorem in theorem_corpus if theorem.name == theorem_name]
        if not matching:
            error = f"Theorem '{theorem_name}' not found in corpus '{corpus_label}'"
            print(error)
            available = ", ".join(theorem.name for theorem in theorem_corpus[:10])
            suffix = "..." if len(theorem_corpus) > 10 else ""
            if available:
                print(f"Available: {available}{suffix}")
            return [], error, "head", None
        logger.info("Running single theorem: %s", theorem_name)
        return matching, None, "theorem", None

    if resume:
        resumed_selection = _lean_checkpoints._resume_selected_theorems(
            theorem_corpus,
            log_dir=log_dir,
            corpus=corpus,
        )
        if resumed_selection is not None:
            selected_theorems, selection_seed = resumed_selection
            logger.info(
                "Resume-selected %s theorems from existing run_config.json",
                len(selected_theorems),
            )
            return selected_theorems, None, "resume_saved_selection", selection_seed

    selected_theorems, selection_meta = select_items(
        theorem_corpus,
        lambda theorem: theorem.name,
        offset=offset,
        limit=limit,
        sample=sample,
        seed=seed,
    )
    if selection_meta.method == "hash_sample":
        assert selection_meta.seed is not None
        logger.info(
            "Hash-selected %s theorems (seed=%s, offset=%s, sample=%s)",
            len(selected_theorems),
            selection_meta.seed,
            offset,
            sample,
        )
    elif selection_meta.method == "head":
        if offset > 0:
            logger.info("Skipped first %s theorems", offset)
        if limit is not None:
            logger.info("Limited to %s theorems", len(selected_theorems))
    return selected_theorems, None, selection_meta.method, selection_meta.seed


def _prepare_pending_theorems(
    *,
    indexed_theorems: list[tuple[int, Theorem]],
    basin_seeds: int | None,
    basin_blind: bool,
    resume: bool,
    log_dir: Path,
    logger: logging.Logger,
    progress: CorpusProgress,
    init_phase: str,
    results: list[TheoremResult],
) -> list[tuple[int, Theorem]]:
    resumed_count = 0
    if basin_seeds is not None:
        if resume:
            pending_theorems, resumed_count, resumed_solves = (
                _lean_basin.prefilter_resumed_theorems(
                    indexed_theorems,
                    log_dir=log_dir,
                    seeds=list(range(basin_seeds)),
                    include_blind=basin_blind,
                )
            )
        else:
            pending_theorems = indexed_theorems
            resumed_solves = 0
        progress.start_basin_mode(basin_seeds)
        resume_message = (
            "Resume prefilter: skipping "
            f"{resumed_count} completed theorems "
            f"({resumed_solves} solved seeds total)"
        )
        no_pending_message = "Resume prefilter found no pending basin theorems"
    elif resume:
        pending_theorems, resumed_checkpoint_results = (
            _lean_checkpoints._resume_checkpointed_theorems(
                indexed_theorems,
                log_dir=log_dir,
                logger=logger,
            )
        )
        results.extend(resumed_checkpoint_results)
        resumed_count = len(resumed_checkpoint_results)
        resume_message = f"Resume prefilter: skipping {resumed_count} completed theorems"
    else:
        pending_theorems = indexed_theorems
        resume_message = "Resume prefilter: skipping 0 completed theorems"
    if basin_seeds is None:
        no_pending_message = "Resume prefilter: all selected theorems already have checkpoints"
    progress.completed_theorems = resumed_count
    progress.start()
    progress.start_initializing(init_phase)
    if resumed_count:
        logger.info(resume_message)
        progress._write_progress_status(force=True)
    if not pending_theorems:
        logger.info(no_pending_message)
    return pending_theorems


async def _run_worker_phase_with_progress_stop(
    *,
    pending_theorems: list[tuple[int, Theorem]],
    progress: CorpusProgress,
    worker_phase_kwargs: dict[str, Any],
    state_lock: asyncio.Lock,
    worker_label: str,
    fatal_message: str,
    failure_message: str,
    run_item: Callable[[LeanAdapter, TacticProvider, int, Theorem, int], Awaitable[None]],
    pool_label: str | None = None,
) -> None:
    if not pending_theorems:
        progress.stop()
        return
    try:
        await _lean_runner.run_worker_phase(
            entries=pending_theorems,
            **worker_phase_kwargs,
            state_lock=state_lock,
            pool_label=pool_label,
            worker_label=worker_label,
            fatal_message=fatal_message,
            failure_message=failure_message,
            run_item=run_item,
        )
    finally:
        progress.stop()


def _finalize_failed_run(
    lifecycle: RunLifecycle,
    *,
    partial_results: bool,
    sync_reason: str,
    has_goal_cache: bool | None = None,
) -> NoReturn:
    error = lifecycle.error
    if error is None:
        raise RuntimeError("RunLifecycle missing error for failed run finalization")
    lifecycle.finalize(
        status_value="failed",
        error=error,
        partial_results=partial_results,
        sync_reason=sync_reason,
        traceback_text=lifecycle.error_trace,
        has_goal_cache=has_goal_cache,
    )
    raise error


async def run_corpus(
    project_path: str,
    budget_tiers: list[int] | None = None,
    budget_label: str | None = None,
    provider_name: str = "reprover",
    device: str | None = None,
    use_sampling: bool = False,
    debug: bool = False,
    skip_interventions: bool = False,
    skip_interventions_after_wild_failure: bool = False,
    block_easy: bool = False,
    corpus: str = "research",
    limit: int | None = None,
    offset: int = 0,
    sample: int | None = None,
    seed: int | None = None,
    search_seed: int | None = None,
    run_id: str | None = None,
    num_workers: int = 1,
    theorem_name: str | None = None,
    intervention_names: list[str] | None = None,
    extra_interventions: list[Intervention] | None = None,
    plain: bool = False,
    basin_seeds: int | None = None,
    basin_blind: bool = False,
    goal_sig_scheme: str = "ast",
    run_analysis: bool = False,
    trace_mcts: bool = False,
    collect_solution_artifacts: bool = True,
    postprocess_metrics: bool = True,
    mcts_mode: str = "centralized",
    expansion_policy: ExpansionPolicy | str = ExpansionPolicy.ALL_SUCCESSES,
    distributed_settings: dict[str, Any] | None = None,
    provider_label: str | None = None,
    mode: str | None = None,
    mode_defaults: dict | None = None,
    cli_args: dict | None = None,
    write_latest_run: bool = True,
    tactic_ranker: TacticRanker | None = None,
    tactic_ranker_agent: TacticRankerAgent | None = None,
    tie_breaker: TieBreaker | None = None,
    tie_breaker_agent: TieBreakerAgent | None = None,
    tactic_ranker_factory: TacticRankerFactory | None = None,
    tactic_ranker_agent_factory: TacticRankerAgentFactory | None = None,
    tie_breaker_factory: TieBreakerFactory | None = None,
    tie_breaker_agent_factory: TieBreakerAgentFactory | None = None,
    deepseek_num_samples: int | None = None,
    deepseek_model_path: str | None = None,
    deepseek_backend: str = "mlx",
    bfs_num_samples: int | None = None,
    internlm_num_samples: int | None = None,
    resume: bool = False,
    no_sync: bool = False,
) -> list[TheoremResult]:
    if budget_tiers is None:
        budget_tiers = BUDGET_PRESETS["standard"]
    if search_seed is not None and search_seed < 0:
        raise ValueError("search_seed must be >= 0")
    if basin_blind and basin_seeds is None:
        raise ValueError("basin_blind requires basin_seeds")
    if basin_blind and mcts_mode != "centralized":
        raise ValueError("basin_blind currently requires centralized MCTS")
    if basin_seeds is not None and search_seed is not None:
        raise ValueError("search_seed is not supported with basin_seeds")
    if skip_interventions and intervention_names:
        raise ValueError("intervention_names require interventions to be enabled")
    if skip_interventions and extra_interventions:
        raise ValueError("extra_interventions require interventions to be enabled")
    expansion_policy = coerce_expansion_policy(expansion_policy)
    expansion_policy_value = expansion_policy.value
    logs_dir = resolve_logs_dir()
    if run_id:
        if not run_id.startswith("corpus-"):
            run_id = _prefix_run_id_with_ymd(run_id)
        log_dir = logs_dir / run_id
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        log_dir = logs_dir / f"corpus-{timestamp}"
    log_dir.mkdir(parents=True, exist_ok=True)
    hydrated_from_remote = sync_logs_from_remote(log_dir, require_src=False) if resume else None

    corpus_log_final = log_dir / "corpus.log"
    # Buffer log writes to avoid per-record flush overhead on slower volumes.
    log_handler: logging.Handler = _BufferedFileHandler(corpus_log_final)

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[log_handler],
        force=True,
    )
    logger = logging.getLogger(__name__)
    resolved_run_id = run_id or log_dir.name
    if hydrated_from_remote is not None:
        logger.info(
            (
                "Hydrated local run dir from remote for resume: src=%s dst=%s copied=%s "
                "skipped=%s bytes=%s"
            ),
            hydrated_from_remote.src_root,
            hydrated_from_remote.dst_root,
            hydrated_from_remote.copied_files,
            hydrated_from_remote.skipped_files,
            hydrated_from_remote.copied_bytes,
        )
    results: list[TheoremResult] = []
    crashed: list[CrashedTheorem] = []
    theorem_corpus, corpus_meta, corpus_artifact_ref = load_corpus(corpus)
    corpus_label = cast(str, corpus_meta.get("name", corpus))

    goal_sig_config = GoalSignatureConfig(
        scheme=goal_sig_scheme,
    )
    provider_factory = partial(
        create_provider,
        provider_name,
        device,
        use_sampling,
        goal_sig_config,
        block_easy,
        deepseek_num_samples=deepseek_num_samples,
        deepseek_model_path=deepseek_model_path,
        deepseek_backend=deepseek_backend,
        bfs_num_samples=bfs_num_samples,
        internlm_num_samples=internlm_num_samples,
    )
    base_provider = provider_factory()

    provider_label = provider_label or provider_name
    if block_easy:
        provider_label = f"{provider_label}+block_easy"

    for resolved, factory, label in (
        (tactic_ranker, tactic_ranker_factory, "tactic_ranker"),
        (tactic_ranker_agent, tactic_ranker_agent_factory, "tactic_ranker_agent"),
        (tie_breaker, tie_breaker_factory, "tie_breaker"),
        (tie_breaker_agent, tie_breaker_agent_factory, "tie_breaker_agent"),
    ):
        if resolved is not None and factory is not None:
            raise ValueError(f"{label}_factory cannot be set with {label}")

    theorem_corpus, selection_error, selection_method, selection_seed = _select_theorems_for_run(
        theorem_corpus,
        theorem_name=theorem_name,
        corpus_label=corpus_label,
        logger=logger,
        resume=resume,
        log_dir=log_dir,
        corpus=corpus,
        offset=offset,
        limit=limit,
        sample=sample,
        seed=seed,
    )

    distributed_snapshot = _distributed_settings_snapshot(distributed_settings)
    blocked_tactics = sorted(EASY_TACTICS) if block_easy else []
    requested_interventions = list(intervention_names or [])
    extra_intervention_payloads = [
        {
            "name": intervention.name,
            "blocked": sorted(intervention.blocked),
            "is_control": intervention.is_control,
        }
        for intervention in (extra_interventions or [])
    ]
    run_config = lean_metadata.build_run_config(
        resolved_run_id=resolved_run_id,
        logs_dir=logs_dir,
        log_dir=log_dir,
        provider_name=provider_name,
        provider_label=provider_label,
        provider=base_provider,
        mode=mode,
        corpus_label=corpus_label,
        corpus_spec=corpus,
        budget_label=budget_label,
        budget_tiers=budget_tiers,
        limit=limit,
        offset=offset,
        sample=sample,
        selection_seed=selection_seed,
        search_seed=search_seed,
        skip_interventions=skip_interventions,
        skip_interventions_after_wild_failure=skip_interventions_after_wild_failure,
        trace_mcts=trace_mcts,
        collect_solution_artifacts=collect_solution_artifacts,
        postprocess_metrics=postprocess_metrics,
        run_analysis=run_analysis,
        device=device,
        num_workers=num_workers,
        goal_sig_scheme=goal_sig_scheme,
        cli_args=cli_args,
        block_easy=block_easy,
        use_sampling=use_sampling,
        theorem_name=theorem_name,
        debug=debug,
        plain=plain,
        basin_seeds=basin_seeds,
        basin_blind=basin_blind,
        mode_defaults=mode_defaults,
        project_path=project_path,
        corpus_artifact_ref=corpus_artifact_ref,
        corpus_meta=corpus_meta,
        mcts_mode=mcts_mode,
        expansion_policy=expansion_policy_value,
        distributed_snapshot=distributed_snapshot,
        selection_method=selection_method,
        selected_theorems=[t.name for t in theorem_corpus],
        selection_error=selection_error,
        blocked_tactics=blocked_tactics,
        requested_interventions=requested_interventions,
        extra_intervention_payloads=extra_intervention_payloads,
    )
    _write_run_config(log_dir, run_config)
    if write_latest_run:
        _write_latest_run(log_dir, [provider_name], provider_name, False)
    run_status = {
        "status": "running",
        "started_at": _timestamp(),
        "completed_at": None,
        "goal_id_scheme": "checkpoint",
        "partial_results": False,
        "capabilities": default_run_capabilities(),
    }
    status_writer = RunStatusWriter(log_dir=log_dir, initial_status=run_status)
    lifecycle = RunLifecycle(
        log_dir=log_dir,
        logger=logger,
        trace_mcts=trace_mcts,
        no_sync=no_sync,
        results=results,
        status_writer=status_writer,
    )
    status_writer.write_initial()
    if selection_error is not None:
        lifecycle.finalize(
            status_value="failed",
            error=selection_error,
            partial_results=False,
            sync_reason="selection-error",
            has_goal_cache=False,
        )
        return []

    total_budget = sum(budget_tiers)
    logger.info(
        f"Starting corpus run with {len(theorem_corpus)} theorems ({corpus_label}), "
        f"budget_tiers={budget_tiers} (total={total_budget}), workers={num_workers}"
    )

    logger.info(f"Base provider: {base_provider.describe()}")
    goal_cache = (
        _lean_checkpoints._load_resume_goal_cache(log_dir, goal_sig_config, logger=logger)
        if resume
        else GoalCache(goal_sig_config)
    )
    progress = CorpusProgress(
        len(theorem_corpus),
        corpus_label,
        provider_label,
        base_provider.describe(),
        run_id=resolved_run_id,
        log_dir=log_dir,
        mode=mode,
        budget_label=budget_label,
        budget_tiers=budget_tiers,
        seed=selection_seed,
        workers=num_workers,
        mcts_mode=mcts_mode,
        distributed_settings=distributed_snapshot,
        trace_mcts=trace_mcts,
        provider=base_provider,
        goal_cache=goal_cache,
        status_writer=status_writer,
        show_debug=debug,
        plain=plain,
    )
    init_phase = "lean_repl_imports" if num_workers == 1 else f"lean_repl_imports x{num_workers}"
    indexed_theorems = list(enumerate(theorem_corpus, 1))
    worker_phase_kwargs = {
        "num_workers": num_workers,
        "project_path": project_path,
        "logger": logger,
        "base_provider": base_provider,
        "provider_factory": provider_factory,
        "progress": progress,
        "crashed": crashed,
        "record_lean_exception": handle_lean_exception,
        "crash_from_error": CrashedTheorem.from_error,
        "record_failure": lifecycle.record_failure,
    }
    pending_theorems = _prepare_pending_theorems(
        indexed_theorems=indexed_theorems,
        basin_seeds=basin_seeds,
        basin_blind=basin_blind,
        resume=resume,
        log_dir=log_dir,
        logger=logger,
        progress=progress,
        init_phase=init_phase,
        results=results,
    )

    if basin_seeds is not None:
        seeds = list(range(basin_seeds))
        if run_analysis:
            logger.warning("Post-analysis is skipped in basin mode")
        blind_suffix = " + blind baseline" if basin_blind else ""
        logger.info(
            f"Basin analysis mode: running each theorem with {basin_seeds} seeds{blind_suffix}"
        )

        async def run_basin_theorem_with_resume(
            adapter: LeanAdapter,
            provider: TacticProvider,
            idx: int,
            theorem: Theorem,
            worker_idx: int,
        ) -> None:
            worker_id = None if num_workers == 1 else worker_idx
            theorem_dir = log_dir / theorem.name
            logger.info(f"Basin analysis [{idx}/{len(theorem_corpus)}]: {theorem.name}")
            progress.start_basin_theorem(theorem.name, idx, worker_id=worker_id)
            try:
                basin_result = await _lean_basin.run_basin_analysis(
                    adapter=adapter,
                    theorem=theorem,
                    base_provider=provider,
                    budget_tiers=budget_tiers,
                    seeds=seeds,
                    include_blind=basin_blind,
                    mcts_mode=mcts_mode,
                    expansion_policy=expansion_policy,
                    distributed_settings=distributed_settings,
                    goal_cache=goal_cache,
                    goal_sig_config=goal_sig_config,
                    progress=progress,
                    progress_worker_id=worker_id,
                )
                theorem_dir.mkdir(parents=True, exist_ok=True)
                with open(theorem_dir / "basin_analysis.json", "w") as f:
                    json.dump(basin_result.serialize(), f, indent=2)
                logger.info(
                    f"  solve_rate={basin_result.solve_rate:.2f}, "
                    f"unique_structures={basin_result.unique_structures}, "
                    f"dominant_freq={basin_result.dominant_structure_frequency:.2f}"
                )
            finally:
                progress.end_basin_theorem(worker_id=worker_id)

        await _run_worker_phase_with_progress_stop(
            pending_theorems=pending_theorems,
            progress=progress,
            worker_phase_kwargs=worker_phase_kwargs,
            state_lock=asyncio.Lock(),
            pool_label="basin",
            worker_label="basin worker",
            fatal_message="Fatal error during basin analysis; aborting run",
            failure_message="Fatal error during basin startup or worker recovery",
            run_item=run_basin_theorem_with_resume,
        )

        if not pending_theorems:
            lifecycle.finalize(
                status_value="completed",
                partial_results=False,
                sync_reason="basin-completed",
            )
            return results

        if crashed:
            logger.warning(f"{len(crashed)} theorems crashed during basin analysis")
        if lifecycle.failed and lifecycle.error is not None:
            _finalize_failed_run(
                lifecycle,
                partial_results=bool(progress.completed_theorems or crashed),
                sync_reason="basin-failed",
            )
        lifecycle.finalize(
            status_value="completed",
            partial_results=False,
            sync_reason="basin-completed",
        )
        return results

    counter = [0]
    results_lock = asyncio.Lock()

    async def run_theorem_queue_item(
        adapter: LeanAdapter,
        provider: TacticProvider,
        idx: int,
        theorem: Theorem,
        worker_idx: int,
    ) -> None:
        del worker_idx
        try:
            def resolve_for_theorem(factory: Any, fallback: Any) -> Any:
                return factory(theorem, idx) if factory is not None else fallback

            result = await _lean_runner.run_theorem(
                adapter,
                theorem,
                provider,
                budget_tiers,
                counter,
                skip_interventions,
                skip_interventions_after_wild_failure,
                goal_cache,
                goal_sig_config,
                mcts_mode,
                expansion_policy,
                distributed_settings,
                progress,
                log_dir,
                idx,
                trace_mcts,
                search_seed=search_seed,
                intervention_names=intervention_names,
                extra_interventions=extra_interventions,
                tactic_ranker=resolve_for_theorem(tactic_ranker_factory, tactic_ranker),
                tactic_ranker_agent=resolve_for_theorem(
                    tactic_ranker_agent_factory,
                    tactic_ranker_agent,
                ),
                tie_breaker=resolve_for_theorem(tie_breaker_factory, tie_breaker),
                tie_breaker_agent=resolve_for_theorem(
                    tie_breaker_agent_factory,
                    tie_breaker_agent,
                ),
                collect_solution_artifacts=collect_solution_artifacts,
            )
            if result is not None:
                async with results_lock:
                    _lean_checkpoints._write_theorem_result_checkpoint(log_dir, result)
                    results.append(result)
        finally:
            progress.finish_theorem(theorem.name)

    await _run_worker_phase_with_progress_stop(
        pending_theorems=pending_theorems,
        progress=progress,
        worker_phase_kwargs=worker_phase_kwargs,
        state_lock=results_lock,
        worker_label="worker",
        fatal_message="Fatal error during theorem run; aborting run",
        failure_message="Fatal error during Lean startup or worker recovery",
        run_item=run_theorem_queue_item,
    )

    if lifecycle.failed and lifecycle.error is not None and not (
        progress.completed_theorems > 0 or bool(results or crashed)
    ):
        _finalize_failed_run(
            lifecycle,
            partial_results=False,
            sync_reason="run-failed",
            has_goal_cache=False,
        )

    return _lean_reporting.complete_corpus_run(
        lifecycle=lifecycle,
        progress=progress,
        results=results,
        crashed=crashed,
        theorem_corpus=theorem_corpus,
        goal_cache=goal_cache,
        goal_sig_config=goal_sig_config,
        provider_label=provider_label,
        corpus=corpus,
        budget_tiers=budget_tiers,
        skip_interventions=skip_interventions,
        run_analysis=run_analysis,
        postprocess_metrics=postprocess_metrics,
    )


def run_from_args(args: Any, *, parser_error: Callable[[str], NoReturn] | None = None) -> None:
    from orchestrator.lean_cli import run_from_args as _run_from_args

    _run_from_args(args, parser_error=parser_error)


def main(argv: list[str] | None = None) -> None:
    from orchestrator.lean_cli import main as _main

    _main(argv)


if __name__ == "__main__":
    main()
