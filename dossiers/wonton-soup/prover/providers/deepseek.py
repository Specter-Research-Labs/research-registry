from __future__ import annotations

import asyncio
import json
import math
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.request import Request, urlopen

from leantree.core.lean import LeanGoal

from prover.providers.base import TacticProvider

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter


SYSTEM_PROMPT = """/- You are proving a theorem in Lean 4.
You are given the following information:
- The file contents up to the current tactic, inside [CTX]...[/CTX]
- The current proof state, inside [STATE]...[/STATE]

Your task is to generate the next tactic in the proof.
Put the next tactic inside [TAC]...[/TAC]
-/
"""

DEFAULT_IMPORTS = "import Mathlib\nopen BigOperators Real Nat Topology"

STOP_SEQUENCES = ["[/TAC]", "\n\n\n", "---"]
DEEPSEEK_TOKENIZER_KWARGS = {
    "bos_token": "<｜begin▁of▁sentence｜>",
    "eos_token": "<｜end▁of▁sentence｜>",
    "pad_token": "<｜end▁of▁sentence｜>",
    "unk_token": "<unk>",
}
DeepSeekBackend = Literal["mlx", "transformers"]


@dataclass
class _BatchRequest:
    prompt: str
    n: int
    future: asyncio.Future[list[tuple[str, float]]]


MLX_MODEL_DIRNAME = "ntp-mathlib-deepseek-1.3b-mlx-bf16"
MLX_MODEL_DIRNAME_Q4 = "ntp-mathlib-deepseek-1.3b-mlx-4bit"


def _resolve_model_path(explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit

    roots: list[tuple[str, str]] = []
    deepseek_root = os.environ.get("DEEPSEEK_ARTIFACT_ROOT")
    if deepseek_root:
        roots.append(("DEEPSEEK_ARTIFACT_ROOT", deepseek_root))
    artifact_root = os.environ.get("SPECTER_ARTIFACT_ROOT")
    if artifact_root:
        roots.append(("SPECTER_ARTIFACT_ROOT", artifact_root))

    inaccessible: list[str] = []
    for env_name, root in roots:
        for model_dirname in (MLX_MODEL_DIRNAME, MLX_MODEL_DIRNAME_Q4):
            candidate = Path(root) / "wonton-soup" / "models" / model_dirname
            try:
                if candidate.is_dir():
                    return str(candidate)
            except OSError as exc:
                inaccessible.append(f"{candidate} ({exc})")

    inaccessible_note = ""
    if inaccessible:
        inaccessible_note = " Inaccessible model paths: " + "; ".join(inaccessible) + "."
    raise FileNotFoundError(
        f"No MLX model found. Either pass model_path explicitly, or place the "
        f"converted model at "
        f"$DEEPSEEK_ARTIFACT_ROOT/wonton-soup/models/{MLX_MODEL_DIRNAME} "
        f"(or $SPECTER_ARTIFACT_ROOT/wonton-soup/models/{MLX_MODEL_DIRNAME}). "
        f"Convert with: python -m mlx_lm convert "
        f"--hf-path l3lab/ntp-mathlib-context-deepseek-coder-1.3b "
        f"--mlx-path $DEEPSEEK_ARTIFACT_ROOT/wonton-soup/models/{MLX_MODEL_DIRNAME}."
        f"{inaccessible_note}"
    )


_VLLM_DEFAULT_PORTS = [8000, 8001, 8002, 8003]


def _resolve_backend(
    explicit_model_path: str | None = None,
) -> tuple[list[str], str]:
    vllm_env = os.environ.get("VLLM_ENDPOINTS") or os.environ.get("VLLM_ENDPOINT")
    if vllm_env:
        return [e.strip() for e in vllm_env.split(",") if e.strip()], ""

    try:
        return [], _resolve_model_path(explicit_model_path)
    except FileNotFoundError:
        pass

    # MLX model not found -- probe localhost for a vLLM server on default ports
    for port in _VLLM_DEFAULT_PORTS:
        try:
            req = Request(
                f"http://localhost:{port}/v1/models",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    endpoints = [
                        f"http://localhost:{p}"
                        for p in _VLLM_DEFAULT_PORTS
                        if _probe_port(p)
                    ]
                    return endpoints, ""
        except Exception:
            continue

    raise FileNotFoundError(
        "DeepSeek backend unavailable: no local MLX model found and no vLLM "
        "server detected on localhost. Either set VLLM_ENDPOINTS, place the "
        f"MLX model at $DEEPSEEK_ARTIFACT_ROOT/wonton-soup/models/{MLX_MODEL_DIRNAME}, "
        "or start a vLLM server on port 8000."
    )


def _probe_port(port: int) -> bool:
    try:
        req = Request(
            f"http://localhost:{port}/v1/models",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


class DeepSeekTacticProvider(TacticProvider):
    MODEL_ID = "l3lab/ntp-mathlib-context-deepseek-coder-1.3b"
    MAX_INPUT_LENGTH = 2048
    MAX_NEW_TOKENS = 64
    STOP_SEQUENCES = STOP_SEQUENCES
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(
        self,
        model_path: str | None = None,
        backend: DeepSeekBackend = "mlx",
        device: str | None = None,
        cache_size: int = 100,
        num_samples: int = 10,
        proof_before_steps: int = 8,
    ):
        if backend not in ("mlx", "transformers"):
            raise ValueError(f"Unknown DeepSeek backend: {backend}")
        self._backend = backend
        if backend == "mlx":
            self._vllm_endpoints, self._model_path = _resolve_backend(model_path)
            self._device = device
        else:
            self._vllm_endpoints = []
            self._model_path = _resolve_model_path(model_path)
            self._device = device or _default_transformers_device_name()
        self._vllm_next = 0
        self._model: Any = None
        self._tokenizer: Any = None
        self._loaded = False
        self._cache: OrderedDict[str, list[tuple[str, float]]] = OrderedDict()
        self._cache_size = cache_size
        self._num_samples = num_samples
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
        if self._backend == "mlx":
            from mlx_lm import load

            self._validate_mlx_model_config(self._model_path)
            self._model, self._tokenizer = load(self._model_path)
            self._prompt_tokenizer = self._load_prompt_tokenizer(self._model_path)
        else:
            import torch
            from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast

            device = self._device or _default_transformers_device(torch)
            dtype = torch.float16 if device in {"mps", "cuda"} else torch.float32
            tokenizer_file = Path(self._model_path) / "tokenizer.json"
            if not tokenizer_file.exists():
                raise FileNotFoundError(f"DeepSeek tokenizer.json not found: {tokenizer_file}")
            self._tokenizer = PreTrainedTokenizerFast(
                tokenizer_file=str(tokenizer_file),
                **DEEPSEEK_TOKENIZER_KWARGS,
            )
            model = AutoModelForCausalLM.from_pretrained(
                self._model_path,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
            )
            self._model = cast(Any, model).to(device)
            self._model.eval()
            self._device = device
        self._loaded = True

    @staticmethod
    def _validate_mlx_model_config(model_path: str) -> None:
        config_path = Path(model_path) / "config.json"
        if not config_path.exists():
            return
        with config_path.open() as f:
            config = json.load(f)
        if (
            isinstance(config.get("rope_parameters"), dict)
            and "rope_theta" not in config
            and "rope_scaling" not in config
        ):
            raise RuntimeError(
                "DeepSeek MLX model config is incompatible with mlx_lm: it "
                "contains Hugging Face `rope_parameters` but lacks the "
                "`rope_theta`/`rope_scaling` fields that mlx_lm reads. Refresh "
                "the local model metadata from l3lab/ntp-mathlib-context-"
                "deepseek-coder-1.3b or use a repaired MLX model path."
            )

    @staticmethod
    def _load_prompt_tokenizer(model_path: str) -> Any | None:
        tokenizer_path = Path(model_path) / "tokenizer.json"
        if not tokenizer_path.exists():
            return None
        try:
            from tokenizers import Tokenizer
        except Exception:
            return None
        return Tokenizer.from_file(str(tokenizer_path))

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

    async def _enqueue_batch_request(
        self,
        prompt: str,
        n: int,
    ) -> list[tuple[str, float]]:
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

    def _format_prompt(
        self,
        goal: LeanGoal,
        theorem_context: str | None = None,
        proof_before: str = "",
    ) -> str:
        state_lines = []
        for hyp in goal.hypotheses:
            state_lines.append(f"{hyp.user_name} : {hyp.type}")
        state_lines.append(f"\u22a2 {goal.type}")
        state_str = "\n".join(state_lines)

        ctx = self._build_ctx(theorem_context, proof_before)
        return f"{self.SYSTEM_PROMPT}[CTX]\n{ctx}\n[/CTX]\n[STATE]\n{state_str}\n[/STATE]\n[TAC]\n"

    @staticmethod
    def _build_ctx(theorem_statement: str | None, proof_before: str = "") -> str:
        if theorem_statement is None:
            return DEFAULT_IMPORTS
        # Strip the sorry placeholder so CTX shows the theorem header up to
        # where the next tactic would be inserted (matches training format).
        header = theorem_statement.replace("sorry", "").rstrip()
        if not proof_before:
            return f"{DEFAULT_IMPORTS}\n\n{header}"
        return f"{DEFAULT_IMPORTS}\n\n{header}\n{proof_before}"

    def _extract_proof_before(self, adapter: Any) -> str:
        trace = getattr(adapter, "assembly_trace", None)
        steps = getattr(trace, "steps", None)
        if not isinstance(steps, list) or not steps:
            return ""
        tactics = [getattr(step, "tactic", "") for step in steps]
        if self._proof_before_steps > 0:
            tactics = tactics[-self._proof_before_steps :]
        proof_lines = []
        for tactic in tactics:
            if not isinstance(tactic, str):
                continue
            stripped = tactic.strip()
            if stripped:
                proof_lines.append(f"  {stripped}")
        return "\n".join(proof_lines)

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

    def _extract_tactic_from_generated(self, generated_only: str) -> str | None:
        text = _decode_bytelevel_artifacts(generated_only)
        stop_positions = [
            pos
            for stop in ("[/TAC]", "</s>", "<｜end of sentence｜>", "<|EOT|>", "\n\n\n", "---")
            if (pos := text.find(stop)) >= 0
        ]
        if stop_positions:
            tactic = text[: min(stop_positions)].strip()
            if tactic:
                return tactic
        first_line = text.strip().split("\n")[0].strip()
        if first_line:
            return first_line
        return None

    def _encode_prompt(self, prompt: str) -> list[int]:
        tokenizer = self._prompt_tokenizer
        if tokenizer is not None:
            return list(tokenizer.encode(prompt, add_special_tokens=True).ids)
        return list(self._tokenizer.encode(prompt))

    def _generate_tactics(self, prompt: str, n: int) -> list[tuple[str, float]]:
        if self._backend == "transformers":
            return self._generate_tactics_transformers(prompt, n)
        return self._generate_tactics_mlx(prompt, n)

    def _generate_tactics_mlx(self, prompt: str, n: int) -> list[tuple[str, float]]:
        self._ensure_loaded()
        from mlx_lm import batch_generate
        from mlx_lm.sample_utils import make_sampler

        num_to_generate = max(1, min(n, self._num_samples))
        sampler = make_sampler(temp=0.6, top_p=0.9)
        encoded_prompt = self._encode_prompt(prompt)
        if len(encoded_prompt) > self.MAX_INPUT_LENGTH:
            keep_prefix = self.MAX_INPUT_LENGTH // 2
            keep_suffix = self.MAX_INPUT_LENGTH - keep_prefix
            encoded_prompt = encoded_prompt[:keep_prefix] + encoded_prompt[-keep_suffix:]
        prompts = [list(encoded_prompt) for _ in range(num_to_generate)]
        batch = batch_generate(
            self._model,
            self._tokenizer,
            prompts=prompts,
            max_tokens=self.MAX_NEW_TOKENS,
            sampler=sampler,
            verbose=False,
        )
        seen: dict[str, float] = {}
        for text in batch.texts:
            tactic = self._extract_tactic_from_generated(text)
            if tactic and tactic not in seen:
                seen[tactic] = 1.0 - (len(seen) / num_to_generate)
        return sorted(seen.items(), key=lambda x: x[1], reverse=True)

    def _generate_tactics_transformers(self, prompt: str, n: int) -> list[tuple[str, float]]:
        self._ensure_loaded()
        import torch

        assert self._model is not None
        assert self._tokenizer is not None

        num_to_generate = max(1, min(n, self._num_samples))
        encoded = self._tokenizer(
            prompt,
            return_tensors="pt",
            max_length=self.MAX_INPUT_LENGTH,
            truncation=True,
        ).to(self._device)
        with torch.no_grad():
            outputs = self._model.generate(
                **encoded,
                max_new_tokens=self.MAX_NEW_TOKENS,
                do_sample=True,
                temperature=0.6,
                top_p=0.9,
                num_return_sequences=num_to_generate,
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        prompt_len = encoded["input_ids"].shape[-1]
        decoded = self._tokenizer.batch_decode(
            outputs.sequences[:, prompt_len:].detach().cpu(),
            skip_special_tokens=False,
        )
        sequence_scores = getattr(outputs, "sequences_scores", None)
        seen: dict[str, float] = {}

        for idx, text in enumerate(decoded):
            tactic = self._extract_tactic_from_generated(text)
            if tactic is None:
                continue
            if sequence_scores is not None:
                prob = _score_from_logit(float(sequence_scores[idx].item()))
            else:
                prob = 1.0 - (idx / max(len(decoded), 1))
            prev = seen.get(tactic)
            if prev is None or prob > prev:
                seen[tactic] = prob
        return sorted(seen.items(), key=lambda item: item[1], reverse=True)

    @staticmethod
    def _extract_theorem_context(adapter: Any) -> str | None:
        trace = getattr(adapter, "assembly_trace", None)
        if trace is not None:
            return trace.theorem
        return None

    async def suggest_tactics_with_probs_async(
        self, goal: LeanGoal, mvar_id: str, adapter: LeanAdapter, n: int = 10
    ) -> list[tuple[str, float]]:
        start_time = time.time()
        theorem_context = self._extract_theorem_context(adapter)
        proof_before = self._extract_proof_before(adapter)
        prompt = self._format_prompt(goal, theorem_context, proof_before)

        cached = self._cache_get(prompt)
        if cached is not None:
            self._record_stats(start_time, cache_hit=True)
            return cached[:n]

        tactics = await self._enqueue_batch_request(prompt, n)

        self._record_stats(start_time, cache_hit=False)
        return tactics[:n]

    def describe(self) -> str:
        return (
            "DeepSeekTacticProvider("
            f"ntp-mathlib-deepseek-1.3b,backend={self._backend},"
            f"samples={self._num_samples},"
            f"proof_before={self._proof_before_steps})"
        )


def _default_transformers_device(torch_module: Any) -> str:
    if torch_module.backends.mps.is_available():
        return "mps"
    if torch_module.cuda.is_available():
        return "cuda"
    return "cpu"


def _default_transformers_device_name() -> str:
    import torch

    return _default_transformers_device(torch)


def _score_from_logit(score: float) -> float:
    return 1.0 / (1.0 + math.exp(-score))
