from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from leantree.core.lean import LeanGoal

from prover.providers.internlm_step import InternLMStepProverTacticProvider


def test_internlm_batches_concurrent_requests() -> None:
    provider = InternLMStepProverTacticProvider()
    provider._loaded = True
    provider._model = object()
    provider._tokenizer = object()

    calls: list[tuple[str, int]] = []

    def _fake_generate(prompt: str, n: int) -> list[tuple[str, float]]:
        calls.append((prompt, n))
        return [(f"tactic_for_{hash(prompt) % 100}", 1.0)]

    provider._generate_tactics = _fake_generate  # type: ignore[method-assign]

    goal_a = LeanGoal.from_string("⊢ A = A")
    goal_b = LeanGoal.from_string("⊢ B = B")
    adapter = SimpleNamespace(assembly_trace=None)

    async def _run() -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        return await asyncio.gather(
            provider.suggest_tactics_with_probs_async(
                goal_a, mvar_id="mA", adapter=cast(Any, adapter), n=5
            ),
            provider.suggest_tactics_with_probs_async(
                goal_b, mvar_id="mB", adapter=cast(Any, adapter), n=5
            ),
        )

    result_a, result_b = asyncio.run(_run())

    assert len(calls) == 2
    assert all("STATE_BEFORE: ⊢ " in prompt for prompt, _ in calls)
    assert all("TACTIC: " in prompt for prompt, _ in calls)
    assert all(n == 5 for _, n in calls)
    assert len(result_a) > 0
    assert len(result_b) > 0


def test_internlm_prompt_includes_theorem_and_recent_steps() -> None:
    provider = InternLMStepProverTacticProvider(proof_before_steps=2)
    goal = LeanGoal.from_string("⊢ A = A")
    adapter = SimpleNamespace(
        assembly_trace=SimpleNamespace(
            theorem="theorem demo_thm (a : Nat) : a = a := by sorry",
            steps=[
                SimpleNamespace(tactic="intro a"),
                SimpleNamespace(tactic="simpa"),
                SimpleNamespace(tactic="rfl"),
            ],
        )
    )

    prompt = provider._format_prompt(goal, cast(Any, adapter))

    assert "NAME: demo_thm" in prompt
    assert "PROOF_BEFORE: simpa\nrfl" in prompt
    assert "STATE_BEFORE: ⊢ A = A" in prompt


def test_internlm_extract_tactic_from_output() -> None:
    text = "---\nTACTIC: rw [← Nat.mod_add_div x 8]"
    tactic = InternLMStepProverTacticProvider._extract_tactic_from_text(text)
    assert tactic == "rw [← Nat.mod_add_div x 8]"
