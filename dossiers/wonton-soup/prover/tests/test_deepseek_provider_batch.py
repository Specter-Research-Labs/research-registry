from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import mlx_lm
import mlx_lm.sample_utils as sample_utils
import pytest
from leantree.core.lean import LeanGoal

from prover.providers.deepseek import DeepSeekTacticProvider, _decode_bytelevel_artifacts


def test_deepseek_batches_concurrent_requests(tmp_path: Path) -> None:
    model_dir = tmp_path / "dummy-mlx-model"
    model_dir.mkdir()
    provider = DeepSeekTacticProvider(model_path=str(model_dir))
    provider._loaded = True
    provider._model = object()
    provider._tokenizer = object()

    calls: list[tuple[str, int]] = []

    def _fake_generate(prompt: str, n: int) -> list[tuple[str, float]]:
        calls.append((prompt, n))
        return [(f"tactic_for_{hash(prompt) % 100}", 1.0)]

    provider._generate_tactics = _fake_generate  # type: ignore[method-assign]

    goal_a = SimpleNamespace(hypotheses=[], type="A = A")
    goal_b = SimpleNamespace(hypotheses=[], type="B = B")

    async def _run() -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        return await asyncio.gather(
            provider.suggest_tactics_with_probs_async(goal_a, mvar_id="mA", adapter=None, n=5),
            provider.suggest_tactics_with_probs_async(goal_b, mvar_id="mB", adapter=None, n=5),
        )

    result_a, result_b = asyncio.run(_run())

    assert len(calls) == 2
    prompts_called = {c[0] for c in calls}
    assert len(prompts_called) == 2
    assert all(n == 5 for _, n in calls)
    assert len(result_a) > 0
    assert len(result_b) > 0


def test_deepseek_prompt_includes_recent_steps(tmp_path: Path) -> None:
    model_dir = tmp_path / "dummy-mlx-model"
    model_dir.mkdir()
    provider = DeepSeekTacticProvider(model_path=str(model_dir), proof_before_steps=2)
    goal = LeanGoal.from_string("⊢ A = A")
    adapter = SimpleNamespace(
        assembly_trace=SimpleNamespace(
            theorem="theorem demo_thm (a : Nat) : a = a := by\n  sorry",
            steps=[
                SimpleNamespace(tactic="intro a"),
                SimpleNamespace(tactic="simpa"),
                SimpleNamespace(tactic="rfl"),
            ],
        )
    )

    prompt = provider._format_prompt(
        goal,
        provider._extract_theorem_context(adapter),
        provider._extract_proof_before(adapter),
    )

    assert "theorem demo_thm (a : Nat) : a = a := by" in prompt
    assert "  simpa\n  rfl" in prompt
    assert "intro a" not in prompt


def test_deepseek_generate_tactics_uses_batch_generate(
    monkeypatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "dummy-mlx-model"
    model_dir.mkdir()
    provider = DeepSeekTacticProvider(model_path=str(model_dir), num_samples=4)
    provider._loaded = True
    provider._model = object()

    class _Tokenizer:
        def encode(self, text: str) -> list[int]:
            return list(range(len(text)))

    provider._tokenizer = _Tokenizer()

    calls: list[dict[str, object]] = []

    def _fake_make_sampler(*, temp: float, top_p: float):
        calls.append({"temp": temp, "top_p": top_p})
        return "sampler"

    def _fake_batch_generate(model, tokenizer, prompts, max_tokens, sampler, verbose):
        calls.append(
            {
                "model": model,
                "tokenizer": tokenizer,
                "prompt_count": len(prompts),
                "max_tokens": max_tokens,
                "sampler": sampler,
                "verbose": verbose,
            }
        )
        return SimpleNamespace(
            texts=[
                "simp[/TAC]",
                "simp[/TAC]",
                "rw [h][/TAC]",
                "",
            ]
        )

    monkeypatch.setattr(sample_utils, "make_sampler", _fake_make_sampler)
    monkeypatch.setattr(mlx_lm, "batch_generate", _fake_batch_generate)

    tactics = provider._generate_tactics("prompt", 4)

    assert calls[0] == {"temp": 0.6, "top_p": 0.9}
    assert calls[1]["prompt_count"] == 4
    assert calls[1]["max_tokens"] == provider.MAX_NEW_TOKENS
    assert calls[1]["sampler"] == "sampler"
    assert tactics == [("simp", 1.0), ("rw [h]", 0.75)]


def test_deepseek_extracts_bytelevel_batch_output(tmp_path: Path) -> None:
    model_dir = tmp_path / "dummy-mlx-model"
    model_dir.mkdir()
    provider = DeepSeekTacticProvider(model_path=str(model_dir))

    assert provider._extract_tactic_from_generated("trivialĊ[/TAC]</s>noise") == "trivial"
    assert (
        provider._extract_tactic_from_generated("simpĠonlyĠ[Nat.cast_succ]Ċ[/TAC]")
        == "simp only [Nat.cast_succ]"
    )
    assert _decode_bytelevel_artifacts("exactĠ(2Ġ:ĠâĦĿ)") == "exact (2 : ℝ)"


def test_deepseek_uses_raw_tokenizer_for_prompt_encoding(tmp_path: Path) -> None:
    model_dir = tmp_path / "dummy-mlx-model"
    model_dir.mkdir()
    provider = DeepSeekTacticProvider(model_path=str(model_dir))

    class _Encoding:
        ids = [32013, 185, 123]

    class _PromptTokenizer:
        def encode(self, prompt: str, *, add_special_tokens: bool):
            assert prompt == "prompt"
            assert add_special_tokens is True
            return _Encoding()

    class _FallbackTokenizer:
        def encode(self, prompt: str) -> list[int]:
            return [999]

    provider._prompt_tokenizer = _PromptTokenizer()
    provider._tokenizer = _FallbackTokenizer()

    assert provider._encode_prompt("prompt") == [32013, 185, 123]


def test_deepseek_rejects_stale_rope_parameters(tmp_path: Path) -> None:
    model_dir = tmp_path / "stale-mlx-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        '{"rope_parameters": {"type": "linear", "factor": 4.0, "rope_theta": 100000}}'
    )

    with pytest.raises(RuntimeError, match="rope_parameters"):
        DeepSeekTacticProvider._validate_mlx_model_config(str(model_dir))
