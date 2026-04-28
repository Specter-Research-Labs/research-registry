from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

import psutil
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from prover import GoalCache
from prover.providers import TacticProvider

if TYPE_CHECKING:
    from orchestrator.lean import RunStatusWriter

ProgressCallback = Callable[[int, int, int, int, int, str | None, str | None], bool]


class CorpusProgress:
    CORPUS_ETA_WINDOW = 5
    CORPUS_ETA_MIN_SAMPLES = 3
    DEGENERATE_ABORT_THRESHOLD = 5

    @staticmethod
    def _lean_helpers():
        from orchestrator import lean as lean_mod

        return lean_mod

    def _timestamp(self) -> str:
        return self._lean_helpers()._timestamp()

    def __init__(
        self,
        total_theorems: int,
        corpus_name: str,
        provider_label: str,
        provider_desc: str,
        *,
        run_id: str | None = None,
        log_dir: Path | None = None,
        mode: str | None = None,
        budget_label: str | None = None,
        budget_tiers: list[int] | None = None,
        seed: int | None = None,
        workers: int | None = None,
        mcts_mode: str | None = None,
        distributed_settings: dict[str, Any] | None = None,
        trace_mcts: bool = False,
        provider: TacticProvider | None = None,
        goal_cache: GoalCache | None = None,
        status_writer: RunStatusWriter | None = None,
        show_debug: bool = False,
        plain: bool = False,
    ):
        self.total_theorems = total_theorems
        self.corpus_name = corpus_name
        self.provider_label = provider_label
        self.provider_desc = provider_desc
        self.run_id = run_id
        self.log_dir = log_dir
        self.mode = mode
        self.budget_label = budget_label
        self.budget_tiers = budget_tiers or []
        self.seed = seed
        self.workers = workers
        self.mcts_mode = mcts_mode
        self.distributed_settings = distributed_settings
        self.trace_mcts = trace_mcts
        self.provider = provider
        self.goal_cache = goal_cache
        self._status_writer = status_writer
        self.show_debug = show_debug
        self.plain = plain
        self.console = Console() if not plain else None
        self.live: Live | None = None
        self.start_time = time.time()
        self.theorem_start_time: float | None = None
        self.theorem_start_times: dict[str, float] = {}
        self.completed_theorems = 0
        self.theorem_durations: deque[float] = deque(maxlen=self.CORPUS_ETA_WINDOW)

        self.current_theorem = ""
        self.current_theorem_idx = 0
        self.current_tier = 0
        self.total_tiers = 0
        self.current_budget = 0
        self.current_iter = 0
        self.current_nodes = 0
        self.current_leaves = 0
        self.current_depth = 0
        self.current_phase = "wild"
        self.current_stage_label: str | None = None
        self.current_stage_step: int | None = None
        self.current_stage_total: int | None = None
        self.current_stage_note: str | None = None

        self.wild_solved = 0
        self.wild_failed = 0
        self.wild_aborted = 0
        self.interventions_solved = 0
        self.interventions_total = 0

        self.unique_tactics: set[str] = set()
        self.tactic_counts: dict[str, int] = {}
        self.seen_goals: dict[str, int] = {}
        self.repeat_count = 0
        self.linearity = 0.0
        self.degenerate_iters = 0
        self.last_update_time: float | None = None
        self.last_update_iter: int | None = None
        self.iters_per_sec: float | None = None
        self.iters_per_sec_hist: deque[float] = deque(maxlen=36)
        self.nodes_per_sec: float | None = None
        self.nodes_per_sec_hist: deque[float] = deque(maxlen=36)
        self._last_nodes: int | None = None
        self._last_nodes_time: float | None = None
        self.ram_bytes = 0
        self.peak_ram_bytes = 0
        self.gpu_mem_bytes: int | None = None
        self.gpu_reserved_bytes: int | None = None
        self._torch = None
        self._gpu_backend: str | None = None
        self.provider_cache_hits: int | None = None
        self.provider_cache_misses: int | None = None
        self.provider_last_latency_ms: float | None = None
        self.provider_avg_latency_ms: float | None = None
        self.repl_restarts = 0
        self.last_repl_error: str | None = None
        self._process = psutil.Process(os.getpid())

        self.basin_mode = False
        self.basin_theorem = ""
        self.basin_theorem_idx = 0
        self.basin_total_seeds = 0
        self.basin_completed_seeds = 0
        self.basin_seeds_solved = 0
        self.basin_unique_structures: set[str] = set()
        self.basin_current_seed: int | None = None
        self.basin_workers_state: dict[int, dict[str, Any]] = {}

        self.recent_wild: deque[str] = deque(maxlen=48)

    def start_initializing(self, stage: str) -> None:
        self.current_theorem = ""
        self.current_theorem_idx = 0
        self._reset_search_state()
        self.current_phase = f"startup:{stage}"
        self._set_stage_progress()
        self._update_memory()
        self._update_provider_stats()
        if self.plain:
            print(f"Startup: {stage}")
        elif self.live:
            self.live.update(self._render())
        self._write_progress_status(force=True)

    def _reset_search_state(
        self,
        *,
        total_tiers: int = 0,
        current_budget: int = 0,
    ) -> None:
        self.current_tier = 0
        self.total_tiers = total_tiers
        self.current_iter = 0
        self.current_budget = current_budget
        self.current_nodes = 0
        self.current_leaves = 0
        self.current_depth = 0

    def _set_stage_progress(
        self,
        *,
        stage_label: str | None = None,
        stage_step: int | None = None,
        stage_total: int | None = None,
        stage_note: str | None = None,
    ) -> None:
        self.current_stage_label = stage_label
        self.current_stage_step = stage_step
        self.current_stage_total = stage_total
        self.current_stage_note = stage_note

    def _make_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        if total == 0:
            return "░" * width
        filled = int(width * current / total)
        return "█" * filled + "░" * (width - filled)

    def _truncate_middle(self, value: str, max_len: int) -> str:
        if len(value) <= max_len:
            return value
        keep = max(0, max_len - 3)
        left = keep // 2
        right = keep - left
        return value[:left] + "..." + value[-right:]

    def _sparkline(self, values: list[float], width: int = 22) -> str:
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
        for v in values:
            idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
            out.append(blocks[max(0, min(idx, len(blocks) - 1))])
        return "".join(out)

    def _format_elapsed(self) -> str:
        return self._format_duration(time.time() - self.start_time)

    def _format_duration(self, seconds: float | None) -> str:
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

    def _format_bytes(self, value: int | None) -> str:
        if value is None:
            return "--"
        size = float(value)
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)}B"
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}{units[-1]}"

    def _update_speed(self, iteration: int) -> None:
        now = time.time()
        if self.last_update_time is None or self.last_update_iter is None:
            self.last_update_time = now
            self.last_update_iter = iteration
            return
        delta_iter = iteration - self.last_update_iter
        delta_time = now - self.last_update_time
        self.last_update_time = now
        self.last_update_iter = iteration
        if delta_time <= 0 or delta_iter <= 0:
            return
        inst = delta_iter / delta_time
        if self.iters_per_sec is None:
            self.iters_per_sec = inst
        else:
            self.iters_per_sec = (self.iters_per_sec * 0.7) + (inst * 0.3)
        if self.iters_per_sec is not None:
            self.iters_per_sec_hist.append(self.iters_per_sec)

    def _update_memory(self) -> None:
        rss = self._process.memory_info().rss
        self.ram_bytes = rss
        if rss > self.peak_ram_bytes:
            self.peak_ram_bytes = rss

        if self._gpu_backend is None:
            try:
                import torch
            except ImportError:
                self._gpu_backend = "none"
            else:
                self._torch = torch
                if hasattr(torch, "cuda") and torch.cuda.is_available():
                    self._gpu_backend = "cuda"
                elif (
                    hasattr(torch, "backends")
                    and hasattr(torch.backends, "mps")
                    and torch.backends.mps.is_available()
                ):
                    self._gpu_backend = "mps"
                else:
                    self._gpu_backend = "none"

        if self._gpu_backend == "cuda" and self._torch is not None:
            self.gpu_mem_bytes = self._torch.cuda.memory_allocated()
            self.gpu_reserved_bytes = self._torch.cuda.memory_reserved()
        elif self._gpu_backend == "mps" and self._torch is not None:
            if hasattr(self._torch.mps, "current_allocated_memory"):
                self.gpu_mem_bytes = self._torch.mps.current_allocated_memory()
            else:
                self.gpu_mem_bytes = None
            self.gpu_reserved_bytes = None
        elif self._gpu_backend == "none":
            self.gpu_mem_bytes = None
            self.gpu_reserved_bytes = None

    def _update_provider_stats(self) -> None:
        provider = self.provider
        if provider is None:
            return
        while hasattr(provider, "base"):
            base = getattr(provider, "base")
            if base is None:
                break
            provider = base
        self.provider_cache_hits = getattr(provider, "cache_hits", None)
        self.provider_cache_misses = getattr(provider, "cache_misses", None)
        self.provider_last_latency_ms = getattr(provider, "last_latency_ms", None)
        self.provider_avg_latency_ms = getattr(provider, "avg_latency_ms", None)

    def _progress_snapshot(self) -> dict[str, Any]:
        if self.basin_mode:
            active_workers = self._basin_active_states()
            basin_payload: dict[str, Any] = {
                "theorem": self.basin_theorem,
                "theorem_idx": self.basin_theorem_idx,
                "seeds_total": self.basin_total_seeds,
                "seeds_completed": self.basin_completed_seeds,
                "seeds_solved": self.basin_seeds_solved,
                "unique_structures": len(self.basin_unique_structures),
                "current_seed": self.basin_current_seed,
            }
            if active_workers:
                basin_payload["workers_active"] = len(active_workers)
            if len(active_workers) > 1:
                basin_payload["workers"] = [
                    {
                        "worker_id": state.get("worker_id"),
                        "theorem": state.get("theorem"),
                        "theorem_idx": state.get("theorem_idx"),
                        "seeds_completed": state.get("completed_seeds"),
                        "seeds_solved": state.get("solved_seeds"),
                        "unique_structures": len(
                            cast(set[str], state.get("unique_structures", set()))
                        ),
                        "current_seed": state.get("current_seed"),
                    }
                    for state in active_workers[:4]
                ]
            return {
                "backend": "lean",
                "mode": "basin",
                "corpus": self.corpus_name,
                "provider": self.provider_label,
                "total": self.total_theorems,
                "completed": self.completed_theorems,
                "basin": basin_payload,
                "updated_at": self._timestamp(),
            }
        leaf_ratio = (self.current_leaves / self.current_nodes) if self.current_nodes > 0 else None
        low_diversity = len(self.unique_tactics) < 3 and self.current_iter > 50
        linear = self.linearity > 0.9
        cycling = self.repeat_count > 10
        flags: list[str] = []
        if low_diversity:
            flags.append("div")
        if linear:
            flags.append("lin")
        if cycling:
            flags.append("cycle")
        debug_payload: dict[str, Any] | None = None
        if self.show_debug:
            items = sorted(
                self.tactic_counts.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )[:5]
            hottest = sorted(self.seen_goals.items(), key=lambda kv: -kv[1])[:3]
            debug_payload = {
                "top_tactics": [{"name": k, "count": v} for k, v in items],
                "goal_churn": {
                    "unique": len(self.seen_goals),
                    "repeats": self.repeat_count,
                    "hot": [{"sig": k, "count": v} for k, v in hottest if v > 1],
                },
            }
            if self._status_writer is not None:
                io_spool = self._status_writer.io_debug_payload()
                if io_spool is not None:
                    debug_payload["io_spool"] = io_spool
        return {
            "backend": "lean",
            "mode": "corpus",
            "corpus": self.corpus_name,
            "provider": self.provider_label,
            "total": self.total_theorems,
            "completed": self.completed_theorems,
            "recent": list(self.recent_wild),
            "current": {
                "theorem": self.current_theorem,
                "theorem_idx": self.current_theorem_idx,
                "phase": self.current_phase,
                "tier": self.current_tier,
                "tiers_total": self.total_tiers,
                "iter": self.current_iter,
                "budget": self.current_budget,
                "nodes": self.current_nodes,
                "leaves": self.current_leaves,
                "depth": self.current_depth,
                "stage_label": self.current_stage_label,
                "stage_step": self.current_stage_step,
                "stage_total": self.current_stage_total,
                "stage_note": self.current_stage_note,
            },
            "wild": {
                "solved": self.wild_solved,
                "failed": self.wild_failed,
                "aborted": self.wild_aborted,
            },
            "interventions": {
                "solved": self.interventions_solved,
                "total": self.interventions_total,
            },
            "speed": {
                "iters_per_sec": self.iters_per_sec,
                "nodes_per_sec": self.nodes_per_sec,
            },
            "speed_hist": {
                "iters_per_sec": list(self.iters_per_sec_hist),
                "nodes_per_sec": list(self.nodes_per_sec_hist),
            },
            "health": {
                "unique_tactics": len(self.unique_tactics),
                "repeat_count": self.repeat_count,
                "linearity": self.linearity,
                "degenerate_iters": self.degenerate_iters,
                "leaf_ratio": leaf_ratio,
                "flags": flags,
            },
            "provider_stats": {
                "cache_hits": self.provider_cache_hits,
                "cache_misses": self.provider_cache_misses,
                "last_latency_ms": self.provider_last_latency_ms,
                "avg_latency_ms": self.provider_avg_latency_ms,
            },
            "debug": debug_payload,
            "repl": {
                "restarts": self.repl_restarts,
                "last_error": self.last_repl_error,
            },
            "memory": {
                "ram_bytes": self.ram_bytes,
                "peak_ram_bytes": self.peak_ram_bytes,
                "gpu_mem_bytes": self.gpu_mem_bytes,
                "gpu_reserved_bytes": self.gpu_reserved_bytes,
            },
            "config": {
                "run_id": self.run_id,
                "log_dir": str(self.log_dir) if self.log_dir is not None else None,
                "mode_profile": self.mode,
                "budget_label": self.budget_label,
                "budget_tiers": self.budget_tiers,
                "seed": self.seed,
                "workers": self.workers,
                "mcts_mode": self.mcts_mode,
                "distributed": self.distributed_settings,
                "trace_mcts": self.trace_mcts,
                "debug": self.show_debug,
                "plain": self.plain,
            },
            "updated_at": self._timestamp(),
        }

    def _write_progress_status(self, *, force: bool = False) -> None:
        if self._status_writer is None:
            return
        self._status_writer.write_progress(self._progress_snapshot(), force=force)

    def _estimate_tier_eta(self) -> float | None:
        if self.iters_per_sec is None or self.iters_per_sec <= 0 or self.current_budget <= 0:
            return None
        remaining = max(self.current_budget - self.current_iter, 0)
        return remaining / self.iters_per_sec

    def _estimate_corpus_eta(self) -> float | None:
        if len(self.theorem_durations) < self.CORPUS_ETA_MIN_SAMPLES:
            return None
        remaining = max(self.total_theorems - self.completed_theorems, 0)
        if remaining == 0:
            return 0.0
        avg = sum(self.theorem_durations) / len(self.theorem_durations)
        return avg * remaining

    def _format_speed_line(self) -> str | None:
        parts = []
        if self.iters_per_sec is not None:
            parts.append(f"{self.iters_per_sec:.1f} it/s")
        if self.nodes_per_sec is not None:
            parts.append(f"{self.nodes_per_sec:.0f} node/s")
        if len(self.iters_per_sec_hist) >= 6:
            parts.append(f"trend {self._sparkline(list(self.iters_per_sec_hist))}")
        tier_eta = self._estimate_tier_eta()
        if tier_eta is not None:
            parts.append(f"tier eta~ {self._format_duration(tier_eta)}")
        if not parts:
            return None
        return "speed: " + " | ".join(parts)

    def _format_time_line(self) -> str | None:
        parts = []
        if self.theorem_start_time is not None:
            elapsed = time.time() - self.theorem_start_time
            parts.append(f"theorem {self._format_duration(elapsed)}")
        corpus_eta = self._estimate_corpus_eta()
        if corpus_eta is not None:
            parts.append(f"corpus eta~ {self._format_duration(corpus_eta)}")
        if not parts:
            return None
        return "time: " + " | ".join(parts)

    def _format_memory_line(self) -> str | None:
        if self.ram_bytes <= 0 and self.gpu_mem_bytes is None:
            return None
        parts = []
        if self.ram_bytes > 0:
            ram = f"RAM {self._format_bytes(self.ram_bytes)}"
            if self.peak_ram_bytes > 0:
                ram += f" (peak {self._format_bytes(self.peak_ram_bytes)})"
            parts.append(ram)
        if self.gpu_mem_bytes is not None and self.gpu_mem_bytes > 0:
            gpu = f"GPU {self._format_bytes(self.gpu_mem_bytes)}"
            if self.gpu_reserved_bytes is not None and self.gpu_reserved_bytes > 0:
                gpu += f" (res {self._format_bytes(self.gpu_reserved_bytes)})"
            parts.append(gpu)
        return "memory: " + " | ".join(parts)

    def _format_provider_line(self) -> str | None:
        parts = []
        cache_hits = self.provider_cache_hits
        cache_misses = self.provider_cache_misses
        if cache_hits is not None and cache_misses is not None:
            total = cache_hits + cache_misses
            if total > 0:
                hit_rate = cache_hits / total
                if self.show_debug:
                    parts.append(f"cache hit {hit_rate:.0%} ({cache_hits}/{total})")
                else:
                    parts.append(f"cache hit {hit_rate:.0%}")
        if self.provider_avg_latency_ms is not None:
            latency = f"lat {self.provider_avg_latency_ms:.0f}ms avg"
            if self.provider_last_latency_ms is not None:
                latency += f" (last {self.provider_last_latency_ms:.0f}ms)"
            parts.append(latency)
        if not parts:
            return None
        return f"provider: {self.provider_label} | " + " | ".join(parts)

    def _format_run_line(self) -> str | None:
        if self.run_id is None and self.log_dir is None:
            return None
        parts = []
        if self.run_id is not None:
            parts.append(f"id {self.run_id}")
        if self.log_dir is not None:
            log_label = str(self.log_dir) if self.show_debug else self.log_dir.name
            parts.append(f"logs {log_label}")
        return "run: " + " | ".join(parts) if parts else None

    def _format_config_line(self) -> str | None:
        parts: list[str] = []
        if self.mode:
            parts.append(f"mode {self.mode}")
        if self.budget_label:
            parts.append(f"budget {self.budget_label}")
        elif self.budget_tiers:
            parts.append(f"tiers {self.budget_tiers}")
        if self.seed is not None:
            parts.append(f"seed {self.seed}")
        if self.workers is not None and self.workers > 0:
            parts.append(f"workers {self.workers}")
        if self.mcts_mode:
            parts.append(f"mcts {self.mcts_mode}")
            if self.mcts_mode == "distributed" and self.distributed_settings:
                agents = self.distributed_settings.get("agents")
                inflight = self.distributed_settings.get("inflight")
                if agents is not None:
                    parts.append(f"agents {agents}")
                if inflight is not None:
                    parts.append(f"inflight {inflight}")
        if self.trace_mcts:
            parts.append("trace on")
        return "config: " + " | ".join(parts) if parts else None

    def _format_top_tactics(self, n: int = 5) -> str | None:
        if not self.tactic_counts:
            return None
        items = sorted(self.tactic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
        parts = []
        for name, count in items:
            label = self._truncate_middle(name, 22)
            parts.append(f"{label}×{count}")
        return "top tactics: " + " | ".join(parts) if parts else None

    def _format_goal_churn(self) -> str | None:
        if not self.seen_goals:
            return None
        unique = len(self.seen_goals)
        repeats = self.repeat_count
        # Show the hottest cycles; goal sigs are already hashed/truncated upstream.
        hottest = sorted(self.seen_goals.items(), key=lambda kv: -kv[1])[:3]
        hot_parts = []
        for sig, count in hottest:
            if count <= 1:
                continue
            hot_parts.append(f"{self._truncate_middle(sig, 18)}×{count}")
        hot = (" | hot " + ", ".join(hot_parts)) if hot_parts else ""
        return f"goals: {unique} unique | repeats {repeats}{hot}"

    def _format_debug_line(self) -> str | None:
        if not self.show_debug:
            return None
        parts = []
        if self.goal_cache is not None:
            parts.append(
                f"goal_cache {len(self.goal_cache.entries)} sigs / "
                f"{len(self.goal_cache.mvar_to_sig)} mvars"
            )
        if not parts:
            return None
        return "debug: " + " | ".join(parts)

    def _append_run_context(self, lines: Text) -> None:
        run_line = self._format_run_line()
        if run_line:
            lines.append(f"    {run_line}\n", style="dim")

        config_line = self._format_config_line()
        if config_line:
            lines.append(f"    {config_line}\n", style="dim")

    def _append_runtime_context(self, lines: Text, *, include_speed: bool = False) -> None:
        if include_speed:
            speed_line = self._format_speed_line()
            if speed_line:
                lines.append(f"    {speed_line}\n", style="white")

        time_line = self._format_time_line()
        if time_line:
            lines.append(f"    {time_line}\n", style="white")

        memory_line = self._format_memory_line()
        if memory_line:
            lines.append(f"    {memory_line}\n", style="white")

        provider_line = self._format_provider_line()
        if provider_line:
            lines.append(f"    {provider_line}\n", style="white")

        if self.repl_restarts > 0:
            repl_line = f"repl: restarts {self.repl_restarts}"
            if self.last_repl_error:
                repl_line += f" | last {self.last_repl_error}"
            lines.append(f"    {repl_line}\n", style="white")

        debug_line = self._format_debug_line()
        if debug_line:
            lines.append(f"    {debug_line}\n", style="dim")

    def _render(self) -> Panel:
        if self.basin_mode:
            return self._render_basin()
        return self._render_normal()

    def _render_basin(self) -> Panel:
        lines = Text()
        active_workers = self._basin_active_states()

        lines.append(f"  > {self.basin_theorem}", style="bold cyan")
        lines.append(f"  [{self.basin_theorem_idx}/{self.total_theorems}]\n", style="dim")
        self._append_run_context(lines)

        lines.append(
            f"    mode: basin analysis ({self.basin_total_seeds} seeds)\n",
            style="white",
        )
        if len(active_workers) > 1:
            lines.append(f"    workers active: {len(active_workers)}\n", style="white")

        bar = self._make_progress_bar(
            self.basin_completed_seeds,
            self.basin_total_seeds,
        )
        lines.append(
            f"    seeds: {bar} {self.basin_completed_seeds}/{self.basin_total_seeds}\n",
            style="white",
        )

        if self.basin_current_seed is not None:
            lines.append(f"    current seed: {self.basin_current_seed}\n", style="dim")

        solve_rate = (
            self.basin_seeds_solved / self.basin_completed_seeds
            if self.basin_completed_seeds > 0
            else 0.0
        )
        if solve_rate >= 0.5:
            rate_style = "green"
        elif solve_rate >= 0.2:
            rate_style = "yellow"
        else:
            rate_style = "red"
        lines.append("    solve rate: ", style="white")
        lines.append(f"{solve_rate:.0%}", style=rate_style)
        lines.append(
            f" ({self.basin_seeds_solved}/{self.basin_completed_seeds})\n",
            style="dim",
        )

        lines.append(f"    unique structures: {len(self.basin_unique_structures)}\n", style="white")

        if len(active_workers) > 1:
            for state in active_workers[1:4]:
                worker_id = state.get("worker_id")
                theorem = self._truncate_middle(cast(str, state.get("theorem", "")), 34)
                theorem_idx = state.get("theorem_idx")
                completed = state.get("completed_seeds")
                current_seed = state.get("current_seed")
                extra = f", seed {current_seed}" if current_seed is not None else ""
                lines.append(
                    f"    worker {worker_id}: [{theorem_idx}/{self.total_theorems}] "
                    f"{theorem} ({completed}/{self.basin_total_seeds}{extra})\n",
                    style="dim",
                )
        self._append_runtime_context(lines)

        lines.append("\n  -----------------------------------------\n", style="dim")

        lines.append(
            f"  Theorems: {self.completed_theorems}/{self.total_theorems}\n",
            style="white",
        )
        lines.append(f"  Elapsed: {self._format_elapsed()}\n", style="dim")

        header = (
            f"  Basin Analysis: {self.corpus_name} ({self.total_theorems} theorems) | "
            f"Provider: {self.provider_label}"
        )
        if self.run_id:
            header += f" | {self.run_id}"
        return Panel(lines, title=header, border_style="magenta", padding=(0, 1))

    def _render_normal(self) -> Panel:
        lines = Text()

        lines.append(f"  > {self.current_theorem}", style="bold cyan")
        lines.append(f"  [{self.current_theorem_idx}/{self.total_theorems}]\n", style="dim")
        self._append_run_context(lines)

        if self.current_phase == "wild":
            phase_label = "wild type"
        else:
            phase_label = self.current_phase

        lines.append(f"    phase: {phase_label}\n", style="white")

        if (
            self.current_stage_label
            and isinstance(self.current_stage_step, int)
            and isinstance(self.current_stage_total, int)
            and self.current_stage_total > 0
        ):
            stage_bar = self._make_progress_bar(
                self.current_stage_step,
                self.current_stage_total,
            )
            lines.append(
                f"    {self.current_stage_label}: "
                f"{stage_bar} {self.current_stage_step}/{self.current_stage_total}\n",
                style="white",
            )
        if self.current_stage_note:
            lines.append(f"    note: {self.current_stage_note}\n", style="dim")

        if self.total_tiers > 0:
            lines.append(
                f"    tier: {self.current_tier}/{self.total_tiers} "
                f"(budget {self.current_budget})\n",
                style="white",
            )

        bar = self._make_progress_bar(self.current_iter, self.current_budget)
        lines.append(
            f"    search: {bar} {self.current_iter}/{self.current_budget}\n",
            style="white",
        )
        lines.append(
            f"    tree: {self.current_nodes} nodes, {self.current_leaves} leaves, "
            f"depth {self.current_depth}",
            style="white",
        )
        if self.current_nodes > 0:
            leaf_ratio = self.current_leaves / self.current_nodes
            lines.append(f" | leaf {leaf_ratio:.0%}", style="dim")
        lines.append("\n")

        if self.current_iter >= 10:
            health_parts = []

            tactic_count = len(self.unique_tactics)
            if tactic_count < 3 and self.current_iter > 50:
                health_parts.append((f"low diversity ({tactic_count} tactics)", "red"))
            else:
                health_parts.append(
                    (
                        f"unique tactics: {tactic_count}",
                        "green" if tactic_count >= 5 else "yellow",
                    )
                )

            linearity_label = f"tree linearity (depth/nodes): {self.linearity:.0%}"
            if self.linearity > 0.9:
                health_parts.append((linearity_label, "red"))
            elif self.linearity > 0.7:
                health_parts.append((linearity_label, "yellow"))
            else:
                health_parts.append((linearity_label, "green"))

            if self.repeat_count > 10:
                health_parts.append((f"goal repeats: {self.repeat_count}", "red"))
            elif self.repeat_count > 3:
                health_parts.append((f"goal repeats: {self.repeat_count}", "yellow"))

            if self.degenerate_iters > 0:
                health_parts.append(
                    (
                        f"degenerate {self.degenerate_iters}/"
                        f"{self.DEGENERATE_ABORT_THRESHOLD} (auto-abort)",
                        "red",
                    )
                )
            # Make the degeneracy trigger interpretable.
            low_diversity = len(self.unique_tactics) < 3 and self.current_iter > 50
            linear = self.linearity > 0.9
            cycling = self.repeat_count > 10
            flags = []
            if low_diversity:
                flags.append("div")
            if linear:
                flags.append("lin")
            if cycling:
                flags.append("cycle")
            if flags:
                health_parts.append((f"flags: {','.join(flags)}", "dim"))

            lines.append("    health: ", style="dim")
            for i, (text, style) in enumerate(health_parts):
                if i > 0:
                    lines.append(" | ", style="dim")
                lines.append(text, style=style)
            lines.append("\n")

        self._append_runtime_context(lines, include_speed=True)

        if self.show_debug:
            top_tactics = self._format_top_tactics()
            if top_tactics:
                lines.append(f"    {top_tactics}\n", style="dim")
            goal_churn = self._format_goal_churn()
            if goal_churn:
                lines.append(f"    {goal_churn}\n", style="dim")

        lines.append("\n  -----------------------------------------\n", style="dim")

        wild_total = self.wild_solved + self.wild_failed + self.wild_aborted
        strip = Text("  Wild: ", style="white")
        if self.recent_wild:
            for outcome in list(self.recent_wild):
                if outcome == "solved":
                    strip.append("█", style="green")
                elif outcome == "aborted":
                    strip.append("!", style="magenta")
                else:
                    strip.append("░", style="yellow")
        else:
            strip.append("(no results yet)", style="dim")
        strip.append(f"  {self.wild_solved}/{wild_total}", style="dim")
        if self.wild_aborted > 0:
            strip.append(f" ({self.wild_aborted} aborted)", style="magenta")
        lines.append(strip)
        lines.append("\n")

        if self.interventions_total > 0:
            lines.append(
                f"  Interventions: {self.interventions_solved}/{self.interventions_total} solved\n",
                style="white",
            )

        lines.append(f"  Elapsed: {self._format_elapsed()}\n", style="dim")

        header = (
            f"  Corpus: {self.corpus_name} ({self.total_theorems} theorems) | "
            f"Provider: {self.provider_label}"
        )
        if self.run_id:
            header += f" | {self.run_id}"
        return Panel(lines, title=header, border_style="blue", padding=(0, 1))

    def _refresh(self, *, force_status: bool = False) -> None:
        self._update_memory()
        self._update_provider_stats()
        if self.live:
            self.live.update(self._render())
        self._write_progress_status(force=force_status)

    def start(self):
        if self.plain:
            print(f"Starting corpus: {self.corpus_name} ({self.total_theorems} theorems)")
            print(f"Provider: {self.provider_label} | {self.provider_desc}")
        else:
            self._update_memory()
            self._update_provider_stats()
            self.live = Live(self._render(), console=self.console, refresh_per_second=4)
            self.live.start()
        self._refresh(force_status=True)

    def stop(self):
        if self.live:
            self.live.stop()
        if not self.plain and self.console is not None and self.log_dir is not None:
            wild_total = self.wild_solved + self.wild_failed + self.wild_aborted
            self.console.print(
                f"[dim]Logs:[/dim] {self.log_dir}  "
                f"[dim]| Wild:[/dim] {self.wild_solved}/{wild_total} solved"
            )
        self._write_progress_status(force=True)

    def start_theorem(self, name: str, idx: int, num_tiers: int):
        self.current_theorem = name
        self.current_theorem_idx = idx
        self._reset_search_state(total_tiers=num_tiers)
        self.current_phase = "wild"
        self._set_stage_progress()
        start_time = time.time()
        self.theorem_start_time = start_time
        self.theorem_start_times[name] = start_time
        self.unique_tactics = set()
        self.tactic_counts = {}
        self.seen_goals = {}
        self.repeat_count = 0
        self.linearity = 0.0
        self.degenerate_iters = 0
        self._last_nodes = None
        self._last_nodes_time = None
        self.nodes_per_sec = None
        self.nodes_per_sec_hist.clear()
        if self.plain:
            print(f"\n[{idx}/{self.total_theorems}] {name}")
            print("  phase: wild type")
        self._refresh(force_status=True)

    def start_tier(self, tier_idx: int, budget: int):
        self.current_tier = tier_idx + 1
        self.current_budget = budget
        self.current_iter = 0
        self.last_update_time = None
        self.last_update_iter = None
        self.iters_per_sec = None
        self.iters_per_sec_hist.clear()
        self.nodes_per_sec = None
        self.nodes_per_sec_hist.clear()
        self._last_nodes = None
        self._last_nodes_time = None
        if self.plain:
            print(f"  tier {tier_idx + 1}/{self.total_tiers} (budget={budget})")
        self._refresh(force_status=True)

    def start_intervention(self, name: str):
        self.current_phase = name
        self.current_tier = 0
        self.current_iter = 0
        self._set_stage_progress()
        self.interventions_total += 1
        if self.plain:
            print(f"  phase: {name}")
        self._refresh(force_status=True)

    def set_phase_progress(
        self,
        phase: str,
        *,
        theorem: str = "",
        theorem_idx: int = 0,
        stage_label: str | None = None,
        stage_step: int | None = None,
        stage_total: int | None = None,
        stage_note: str | None = None,
    ) -> None:
        self.current_phase = phase
        self.current_theorem = theorem
        self.current_theorem_idx = theorem_idx
        self._reset_search_state()
        self._set_stage_progress(
            stage_label=stage_label,
            stage_step=stage_step,
            stage_total=stage_total,
            stage_note=stage_note,
        )
        self._refresh(force_status=True)

    def update_search(
        self,
        iteration: int,
        max_iter: int,
        nodes: int,
        leaves: int,
        depth: int,
        tactic: str | None = None,
        goal_sig: str | None = None,
    ):
        self.current_iter = iteration
        self.current_budget = max_iter
        self.current_nodes = nodes
        self.current_leaves = leaves
        self.current_depth = depth
        self._update_speed(iteration)
        now = time.time()
        if self._last_nodes is not None and self._last_nodes_time is not None:
            dn = nodes - self._last_nodes
            dt = now - self._last_nodes_time
            if dt > 0 and dn >= 0:
                inst_nodes = dn / dt
                if self.nodes_per_sec is None:
                    self.nodes_per_sec = inst_nodes
                else:
                    self.nodes_per_sec = (self.nodes_per_sec * 0.7) + (inst_nodes * 0.3)
                if self.nodes_per_sec is not None:
                    self.nodes_per_sec_hist.append(self.nodes_per_sec)
        self._last_nodes = nodes
        self._last_nodes_time = now

        if tactic:
            self.unique_tactics.add(tactic)
            self.tactic_counts[tactic] = self.tactic_counts.get(tactic, 0) + 1
        if goal_sig:
            self.seen_goals[goal_sig] = self.seen_goals.get(goal_sig, 0) + 1
            if self.seen_goals[goal_sig] > 1:
                self.repeat_count += 1

        self.linearity = depth / nodes if nodes > 0 else 0.0

        if self._is_degenerate():
            self.degenerate_iters += 1
        else:
            self.degenerate_iters = 0

        if self.plain and (iteration == 0 or iteration == max_iter or iteration % 10 == 0):
            print(
                f"    iter {iteration}/{max_iter}: {nodes} nodes, depth {depth}, "
                f"{len(self.unique_tactics)} tactics"
            )
        self._refresh()

    def _is_degenerate(self) -> bool:
        if self.current_iter < 50:
            return False
        low_diversity = len(self.unique_tactics) < 3
        linear = self.linearity > 0.9
        cycling = self.repeat_count > 10
        return low_diversity and linear and cycling

    def should_abort(self) -> bool:
        return self.degenerate_iters >= self.DEGENERATE_ABORT_THRESHOLD

    def end_theorem(self, solved: bool, aborted: bool = False):
        if self.current_phase == "wild":
            if solved:
                self.wild_solved += 1
                self.recent_wild.append("solved")
            elif aborted:
                self.wild_aborted += 1
                self.recent_wild.append("aborted")
            else:
                self.wild_failed += 1
                self.recent_wild.append("failed")
        else:
            if solved:
                self.interventions_solved += 1
        if self.plain:
            if solved:
                print(f"  -> SOLVED (depth {self.current_depth})")
            elif aborted:
                print("  -> ABORTED")
            else:
                print("  -> FAILED")
        self._refresh(force_status=True)

    def finish_theorem(self, theorem_name: str | None = None):
        start_time = None
        if theorem_name is not None:
            start_time = self.theorem_start_times.pop(theorem_name, None)
        if start_time is None:
            start_time = self.theorem_start_time
        if start_time is None:
            return
        duration = max(time.time() - start_time, 0.0)
        self.theorem_durations.append(duration)
        self.completed_theorems += 1
        if theorem_name is None or theorem_name == self.current_theorem:
            self.theorem_start_time = None
        self._refresh(force_status=True)

    def record_repl_restart(self, error: str | None = None):
        self.repl_restarts += 1
        if error:
            cleaned = " ".join(error.split())
            self.last_repl_error = cleaned[:120]
        self._refresh(force_status=True)

    def _basin_worker_key(self, worker_id: int | None) -> int:
        return -1 if worker_id is None else worker_id

    def _ensure_basin_worker_state(self, worker_id: int | None) -> dict[str, Any]:
        key = self._basin_worker_key(worker_id)
        state = self.basin_workers_state.get(key)
        if state is None:
            state = {
                "worker_id": worker_id,
                "theorem": "",
                "theorem_idx": 0,
                "completed_seeds": 0,
                "solved_seeds": 0,
                "unique_structures": set(),
                "current_seed": None,
                "start_time": None,
            }
            self.basin_workers_state[key] = state
        return state

    def _basin_active_states(self) -> list[dict[str, Any]]:
        states = [
            state
            for state in self.basin_workers_state.values()
            if isinstance(state.get("theorem"), str) and state.get("theorem")
        ]
        return sorted(
            states,
            key=lambda state: (
                int(state.get("theorem_idx") or 0),
                int(state.get("worker_id") or 0),
            ),
        )

    def _sync_basin_primary(self) -> None:
        active = self._basin_active_states()
        if not active:
            self.basin_theorem = ""
            self.basin_theorem_idx = 0
            self.basin_completed_seeds = 0
            self.basin_seeds_solved = 0
            self.basin_unique_structures = set()
            self.basin_current_seed = None
            self.theorem_start_time = None
            return

        primary = active[0]
        self.basin_theorem = cast(str, primary["theorem"])
        self.basin_theorem_idx = int(primary["theorem_idx"])
        self.basin_completed_seeds = int(primary["completed_seeds"])
        self.basin_seeds_solved = int(primary["solved_seeds"])
        self.basin_unique_structures = set(cast(set[str], primary["unique_structures"]))
        self.basin_current_seed = cast(int | None, primary["current_seed"])
        self.theorem_start_time = cast(float | None, primary["start_time"])

    def _set_basin_progress(
        self,
        *,
        completed_seeds: int,
        solved_seeds: int,
        unique_structures: set[str],
        current_seed: int | None,
        worker_id: int | None = None,
    ) -> None:
        state = self._ensure_basin_worker_state(worker_id)
        state["completed_seeds"] = completed_seeds
        state["solved_seeds"] = solved_seeds
        state["unique_structures"] = set(unique_structures)
        state["current_seed"] = current_seed
        self._sync_basin_primary()

    def start_basin_mode(self, total_seeds: int):
        self.basin_mode = True
        self.basin_total_seeds = total_seeds
        self.basin_completed_seeds = 0
        self.basin_seeds_solved = 0
        self.basin_unique_structures = set()
        self.basin_current_seed = None
        self.basin_workers_state = {}
        self._write_progress_status(force=True)

    def start_basin_theorem(self, name: str, idx: int, worker_id: int | None = None):
        start_time = time.time()
        state = self._ensure_basin_worker_state(worker_id)
        state["theorem"] = name
        state["theorem_idx"] = idx
        state["completed_seeds"] = 0
        state["solved_seeds"] = 0
        state["unique_structures"] = set()
        state["current_seed"] = None
        state["start_time"] = start_time
        self._sync_basin_primary()
        self.theorem_start_times[name] = start_time
        if self.plain:
            worker_label = f" [worker {worker_id}]" if worker_id is not None else ""
            print(f"\n[{idx}/{self.total_theorems}] {name} (basin analysis{worker_label})")
        self._refresh(force_status=True)

    def update_basin_seed(
        self,
        seed: int,
        solved: bool,
        structure_hash: str | None,
        worker_id: int | None = None,
    ):
        state = self._ensure_basin_worker_state(worker_id)
        completed_seeds = int(state["completed_seeds"]) + 1
        solved_seeds = int(state["solved_seeds"]) + (1 if solved else 0)
        unique_structures = set(cast(set[str], state["unique_structures"]))
        if structure_hash:
            unique_structures.add(structure_hash)
        self._set_basin_progress(
            completed_seeds=completed_seeds,
            solved_seeds=solved_seeds,
            unique_structures=unique_structures,
            current_seed=seed,
            worker_id=worker_id,
        )
        if self.plain:
            status = "solved" if solved else "failed"
            worker_label = f" [worker {worker_id}]" if worker_id is not None else ""
            print(
                f"  seed {seed}{worker_label}: {status} | {solved_seeds}/"
                f"{completed_seeds} solved | {len(unique_structures)} structures"
            )
        self._refresh(force_status=True)

    def end_basin_theorem(self, worker_id: int | None = None):
        key = self._basin_worker_key(worker_id)
        state = self.basin_workers_state.pop(key, None)
        theorem_name = (
            cast(str | None, state.get("theorem")) if state is not None else self.basin_theorem
        )
        theorem_start = (
            cast(float | None, state.get("start_time"))
            if state is not None
            else self.theorem_start_time
        )
        completed_seeds = (
            int(state["completed_seeds"]) if state is not None else self.basin_completed_seeds
        )
        solved_seeds = int(state["solved_seeds"]) if state is not None else self.basin_seeds_solved
        unique_structures = (
            set(cast(set[str], state["unique_structures"]))
            if state is not None
            else set(self.basin_unique_structures)
        )

        if theorem_start is not None:
            duration = max(time.time() - theorem_start, 0.0)
            self.theorem_durations.append(duration)
        if theorem_name:
            self.theorem_start_times.pop(theorem_name, None)
        self.completed_theorems += 1
        self._sync_basin_primary()
        solve_rate = (solved_seeds / completed_seeds) if completed_seeds > 0 else 0.0
        if self.plain:
            worker_label = f" [worker {worker_id}]" if worker_id is not None else ""
            print(
                f"  ->{worker_label} {solved_seeds}/{completed_seeds} "
                f"solved ({solve_rate:.0%}), {len(unique_structures)} unique structures"
            )
        self._refresh(force_status=True)

    def make_callback(self) -> ProgressCallback:
        def callback(
            iteration: int,
            max_iter: int,
            nodes: int,
            leaves: int,
            depth: int,
            tactic: str | None,
            goal_sig: str | None,
        ) -> bool:
            self.update_search(iteration, max_iter, nodes, leaves, depth, tactic, goal_sig)
            return self.should_abort()

        return callback

    def print_summary(self):
        if not self.plain:
            return
        print("\n" + "-" * 40)
        wild_total = self.wild_solved + self.wild_failed + self.wild_aborted
        print(f"Wild: {self.wild_solved}/{wild_total} solved", end="")
        if self.wild_aborted > 0:
            print(f", {self.wild_aborted} aborted", end="")
        print()
        if self.interventions_total > 0:
            print(f"Interventions: {self.interventions_solved}/{self.interventions_total} solved")
