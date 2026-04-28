from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from leantree.core.lean import LeanGoal

from prover.providers.base import TacticProvider
from prover.providers.reprover_client import PremiseRetriever, ReProverModel

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter


@dataclass
class _BatchRequest:
    state: str
    n: int
    future: asyncio.Future[list[tuple[str, float]]]


class ReProverTacticProvider(TacticProvider):
    def __init__(
        self,
        device: str | None = None,
        cache_size: int = 100,
        use_retrieval: bool = False,
        use_sampling: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9,
        num_runs: int = 1,
    ):
        self.model = ReProverModel(
            device=device,
            use_sampling=use_sampling,
            temperature=temperature,
            top_p=top_p,
        )
        self.retriever = PremiseRetriever(device=device) if use_retrieval else None
        self._loaded = False
        self._cache: OrderedDict[str, list[tuple[str, float]]] = OrderedDict()
        self._cache_size = cache_size
        self._use_sampling = use_sampling
        self._temperature = temperature
        self._top_p = top_p
        self._num_runs = num_runs
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_latency_ms: float | None = None
        self.avg_latency_ms: float | None = None
        self._batch_lock: asyncio.Lock | None = None
        self._batch_queue: list[_BatchRequest] = []
        self._batch_task: asyncio.Task[None] | None = None
        self._batch_max_size = 8

    def _ensure_loaded(self):
        if not self._loaded:
            self.model.load()
            if self.retriever is not None:
                self.retriever.load()
            self._loaded = True

    def set_seed(self, seed: int) -> None:
        self._ensure_loaded()
        self.model.set_seed(seed)

    def clear_cache(self) -> None:
        self._cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0

    def _cache_get(self, state: str) -> list[tuple[str, float]] | None:
        cached = self._cache.get(state)
        if cached is None:
            return None
        self._cache.move_to_end(state)
        return cached

    def _cache_put(self, state: str, tactics: list[tuple[str, float]]) -> None:
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[state] = tactics

    def _supports_batch_generation(self) -> bool:
        return self.retriever is None and (not self._use_sampling) and self._num_runs == 1

    async def _enqueue_batch_request(
        self,
        state: str,
        n: int,
    ) -> list[tuple[str, float]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[tuple[str, float]]] = loop.create_future()
        if self._batch_lock is None:
            self._batch_lock = asyncio.Lock()
        async with self._batch_lock:
            self._batch_queue.append(_BatchRequest(state=state, n=n, future=future))
            if self._batch_task is None or self._batch_task.done():
                self._batch_task = loop.create_task(self._drain_batch_queue())
        return await future

    async def _drain_batch_queue(self) -> None:
        # Give concurrent workers in the same event-loop tick a chance to join this batch.
        await asyncio.sleep(0)
        while True:
            lock = self._batch_lock
            if lock is None:
                return
            async with lock:
                if not self._batch_queue:
                    self._batch_task = None
                    return
                batch = self._batch_queue[: self._batch_max_size]
                del self._batch_queue[: self._batch_max_size]
            self._resolve_batch(batch)

    def _resolve_batch(self, batch: list[_BatchRequest]) -> None:
        try:
            max_n = max((req.n for req in batch), default=1)
            unique_states: list[str] = []
            for req in batch:
                if req.state in unique_states:
                    continue
                if self._cache_get(req.state) is not None:
                    continue
                unique_states.append(req.state)

            if unique_states:
                generated = self.model.generate_tactics_batch(unique_states, num_return=max_n)
                for state, tactics in zip(unique_states, generated):
                    self._cache_put(state, tactics)

            for req in batch:
                if req.future.done():
                    continue
                cached = self._cache_get(req.state)
                req.future.set_result(cached[: req.n] if cached is not None else [])
        except Exception as exc:
            for req in batch:
                if req.future.done():
                    continue
                req.future.set_exception(exc)

    def _format_state(self, goal: LeanGoal) -> str:
        lines = []
        for hyp in goal.hypotheses:
            lines.append(f"{hyp.user_name} : {self._normalize_type(hyp.type)}")
        lines.append(f"⊢ {self._normalize_type(goal.type)}")
        return "\n".join(lines)

    def _normalize_type(self, t: str) -> str:
        t = t.replace("ℕ", "Nat").replace("ℤ", "Int").replace("ℚ", "Rat")
        return t.replace("ℝ", "Real").replace("ℂ", "Complex")

    def _record_stats(self, start_time: float, cache_hit: bool) -> None:
        elapsed_ms = (time.time() - start_time) * 1000
        self.last_latency_ms = elapsed_ms
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        if self.avg_latency_ms is None:
            self.avg_latency_ms = elapsed_ms
        else:
            self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (elapsed_ms * 0.1)

    async def suggest_tactics_with_probs_async(
        self, goal: LeanGoal, mvar_id: str, adapter: LeanAdapter, n: int = 10
    ) -> list[tuple[str, float]]:
        self._ensure_loaded()

        start_time = time.time()
        state = self._format_state(goal)

        cached = self._cache_get(state)
        if cached is not None:
            self._record_stats(start_time, cache_hit=True)
            return cached[:n]

        if self._supports_batch_generation():
            tactics = await self._enqueue_batch_request(state, n)
        elif self.retriever is not None and self.retriever.premise_embeddings is not None:
            premises = self.retriever.retrieve(state, k=100)
            tactics = self.model.generate_tactics_with_premises(state, premises, num_return=n)
        elif self._num_runs > 1 and self._use_sampling:
            tactics = self.model.generate_tactics_multi_run(
                state, num_return=n, num_runs=self._num_runs
            )
        else:
            tactics = self.model.generate_tactics(state, num_return=n)
            self._cache_put(state, tactics)

        self._record_stats(start_time, cache_hit=False)
        return tactics[:n]

    def load_premises(self, premises: list[tuple[str, str]]):
        if self.retriever is None:
            raise RuntimeError("Retriever not enabled. Set use_retrieval=True.")
        self._ensure_loaded()
        self.retriever.load_premises(premises)

    def describe(self) -> str:
        retrieval = "+retrieval" if self.retriever is not None else ""
        sampling = ""
        if self._use_sampling:
            sampling = f"+sampling(t={self._temperature},p={self._top_p})"
            if self._num_runs > 1:
                sampling += f"+runs={self._num_runs}"
        return f"ReProverTacticProvider(leandojo-lean4-tacgen-byt5-small{retrieval}{sampling})"
