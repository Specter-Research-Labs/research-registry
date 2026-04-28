from __future__ import annotations

import asyncio
from typing import Any, cast

from leantree.core.lean import LeanGoal

from prover.providers.bfs_prover import BFSProverTacticProvider


def test_bfs_batches_concurrent_requests() -> None:
    provider = BFSProverTacticProvider()
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

    async def _run() -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        return await asyncio.gather(
            provider.suggest_tactics_with_probs_async(
                goal_a, mvar_id="mA", adapter=cast(Any, None), n=5
            ),
            provider.suggest_tactics_with_probs_async(
                goal_b, mvar_id="mB", adapter=cast(Any, None), n=5
            ),
        )

    result_a, result_b = asyncio.run(_run())

    assert len(calls) == 2
    prompts_called = {prompt for prompt, _ in calls}
    assert prompts_called == {"⊢ A = A:::", "⊢ B = B:::"}
    assert all(n == 5 for _, n in calls)
    assert len(result_a) > 0
    assert len(result_b) > 0


def test_bfs_extract_tactic_from_echoed_output() -> None:
    text = "h : x = y + 2\n⊢ x - 1 = y + 1:::simp [h]"
    tactic = BFSProverTacticProvider._extract_tactic_from_text(text)
    assert tactic == "simp [h]"
