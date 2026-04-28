from __future__ import annotations

import asyncio
import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from leantree.core.lean import LeanGoal
from transformers import AutoModelForCausalLM, AutoTokenizer

from prover.providers.base import TacticProvider
from prover.providers.reprover_client import get_default_device

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter


@dataclass
class _BatchRequest:
    prompt: str
    n: int
    future: asyncio.Future[list[tuple[str, float]]]


class InternLMStepProverTacticProvider(TacticProvider):
    MODEL_ID = "internlm/internlm2_5-step-prover"
    MAX_INPUT_LENGTH = 4096
    MAX_NEW_TOKENS = 64
    DEFAULT_BEAM_LIMIT = 4
    THEOREM_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_']*)")

    def __init__(
        self,
        model_id: str = MODEL_ID,
        device: str | None = None,
        cache_size: int = 100,
        num_samples: int = 10,
        use_sampling: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9,
        proof_before_steps: int = 8,
    ):
        self._model_id = model_id
        self._device = device if device is not None else get_default_device()
        self._model: Any = None
        self._tokenizer: Any = None
        self._loaded = False
        self._cache: OrderedDict[str, list[tuple[str, float]]] = OrderedDict()
        self._cache_size = cache_size
        self._num_samples = num_samples
        self._use_sampling = use_sampling
        self._temperature = temperature
        self._top_p = top_p
        self._beam_limit = self.DEFAULT_BEAM_LIMIT
        self._proof_before_steps = proof_before_steps
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_latency_ms: float | None = None
        self.avg_latency_ms: float | None = None
        self._batch_lock: asyncio.Lock | None = None
        self._batch_queue: list[_BatchRequest] = []
        self._batch_task: asyncio.Task[None] | None = None
        self._batch_max_size = 8

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_id, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            trust_remote_code=True,
        )
        self._model = cast(Any, model).to(self._device)
        self._model.eval()
        if self._tokenizer.pad_token_id is None and self._tokenizer.eos_token_id is not None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        self._loaded = True

    def _cache_get(self, prompt: str) -> list[tuple[str, float]] | None:
        cached = self._cache.get(prompt)
        if cached is None:
            return None
        self._cache.move_to_end(prompt)
        return cached

    def _cache_put(self, prompt: str, tactics: list[tuple[str, float]]) -> None:
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[prompt] = tactics

    async def _enqueue_batch_request(self, prompt: str, n: int) -> list[tuple[str, float]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[tuple[str, float]]] = loop.create_future()
        if self._batch_lock is None:
            self._batch_lock = asyncio.Lock()
        async with self._batch_lock:
            self._batch_queue.append(_BatchRequest(prompt=prompt, n=n, future=future))
            if self._batch_task is None or self._batch_task.done():
                self._batch_task = loop.create_task(self._drain_batch_queue())
        return await future

    async def _drain_batch_queue(self) -> None:
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
            unique_prompts: list[str] = []
            for req in batch:
                if req.prompt in unique_prompts:
                    continue
                if self._cache_get(req.prompt) is not None:
                    continue
                unique_prompts.append(req.prompt)

            for prompt in unique_prompts:
                tactics = self._generate_tactics(prompt, max_n)
                self._cache_put(prompt, tactics)

            for req in batch:
                if req.future.done():
                    continue
                cached = self._cache_get(req.prompt)
                req.future.set_result(cached[: req.n] if cached is not None else [])
        except Exception as exc:
            for req in batch:
                if req.future.done():
                    continue
                req.future.set_exception(exc)

    @staticmethod
    def _normalize_type(type_str: str) -> str:
        type_str = type_str.replace("ℕ", "Nat").replace("ℤ", "Int").replace("ℚ", "Rat")
        return type_str.replace("ℝ", "Real").replace("ℂ", "Complex")

    def _format_state(self, goal: LeanGoal) -> str:
        lines = []
        for hyp in goal.hypotheses:
            lines.append(f"{hyp.user_name} : {self._normalize_type(hyp.type)}")
        lines.append(f"⊢ {self._normalize_type(goal.type)}")
        return "\n".join(lines)

    def _extract_theorem_name(self, adapter: Any) -> str:
        trace = getattr(adapter, "assembly_trace", None)
        theorem = getattr(trace, "theorem", "")
        if not isinstance(theorem, str):
            return "unknown_theorem"
        match = self.THEOREM_NAME_RE.search(theorem)
        if match is None:
            return "unknown_theorem"
        return match.group(1)

    def _extract_proof_before(self, adapter: Any) -> str:
        trace = getattr(adapter, "assembly_trace", None)
        steps = getattr(trace, "steps", None)
        if not isinstance(steps, list) or not steps:
            return ""
        tactics = [getattr(step, "tactic", "") for step in steps[-self._proof_before_steps :]]
        return "\n".join(t for t in tactics if isinstance(t, str) and t)

    def _format_prompt(self, goal: LeanGoal, adapter: Any) -> str:
        theorem_name = self._extract_theorem_name(adapter)
        proof_before = self._extract_proof_before(adapter)
        state = self._format_state(goal)
        return (
            f"---\nNAME: {theorem_name}\n\n"
            f"---\nPROOF_BEFORE: {proof_before}\n\n"
            f"---\nSTATE_BEFORE: {state}\n\n"
            "---\nTACTIC: "
        )

    @staticmethod
    def _extract_tactic_from_text(text: str) -> str | None:
        if "TACTIC:" in text:
            tail = text.rsplit("TACTIC:", 1)[1]
        else:
            tail = text
        tactic = tail.strip().split("\n", 1)[0].strip()
        if not tactic:
            return None
        if tactic.startswith("```"):
            tactic = tactic.strip("`").strip()
        return tactic if tactic else None

    @staticmethod
    def _score_from_logit(score: float) -> float:
        return 1.0 / (1.0 + math.exp(-score))

    def _generate_tactics(self, prompt: str, n: int) -> list[tuple[str, float]]:
        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None

        num_to_generate = max(1, min(n, self._num_samples))
        encoded = self._tokenizer(
            prompt,
            return_tensors="pt",
            max_length=self.MAX_INPUT_LENGTH,
            truncation=True,
        ).to(self._device)

        if self._use_sampling:
            outputs = self._model.generate(
                **encoded,
                max_new_tokens=self.MAX_NEW_TOKENS,
                do_sample=True,
                temperature=self._temperature,
                top_p=self._top_p,
                num_return_sequences=num_to_generate,
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=self._tokenizer.pad_token_id,
            )
        else:
            num_beams = min(num_to_generate, self._beam_limit)
            outputs = self._model.generate(
                **encoded,
                max_new_tokens=self.MAX_NEW_TOKENS,
                do_sample=False,
                num_beams=num_beams,
                num_return_sequences=num_beams,
                length_penalty=0.0,
                early_stopping=False,
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        decoded = self._tokenizer.batch_decode(outputs.sequences, skip_special_tokens=True)
        sequence_scores = getattr(outputs, "sequences_scores", None)
        seen: dict[str, float] = {}

        for idx, text in enumerate(decoded):
            tactic = self._extract_tactic_from_text(text)
            if tactic is None:
                continue
            if sequence_scores is not None:
                score = float(sequence_scores[idx].item())
                prob = self._score_from_logit(score)
            else:
                prob = 1.0 - (idx / max(len(decoded), 1))
            prev = seen.get(tactic)
            if prev is None or prob > prev:
                seen[tactic] = prob

        return sorted(seen.items(), key=lambda item: item[1], reverse=True)

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
        _ = mvar_id
        start_time = time.time()
        prompt = self._format_prompt(goal, adapter)

        cached = self._cache_get(prompt)
        if cached is not None:
            self._record_stats(start_time, cache_hit=True)
            return cached[:n]

        tactics = await self._enqueue_batch_request(prompt, n)
        self._record_stats(start_time, cache_hit=False)
        return tactics[:n]

    def describe(self) -> str:
        mode = "sampling" if self._use_sampling else "beam"
        model_id = self._model_id
        samples = self._num_samples
        return f"InternLMStepProverTacticProvider({model_id},{mode},samples={samples})"
