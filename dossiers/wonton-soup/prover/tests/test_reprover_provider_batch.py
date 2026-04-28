from __future__ import annotations

import asyncio
from types import SimpleNamespace

from prover.providers.reprover import ReProverTacticProvider


class _FakeModel:
    def __init__(self) -> None:
        self.batch_calls: list[tuple[list[str], int]] = []

    def generate_tactics_batch(
        self,
        states: list[str],
        num_return: int = 10,
        max_length: int = 256,
    ) -> list[list[tuple[str, float]]]:
        _ = max_length
        self.batch_calls.append((list(states), num_return))
        return [[(f"{state} :: tactic", 1.0)] for state in states]


def test_reprover_batches_concurrent_requests() -> None:
    provider = ReProverTacticProvider()
    model = _FakeModel()
    provider._loaded = True
    provider.model = model

    goal_a = SimpleNamespace(hypotheses=[], type="A = A")
    goal_b = SimpleNamespace(hypotheses=[], type="B = B")

    async def _run() -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        return await asyncio.gather(
            provider.suggest_tactics_with_probs_async(goal_a, mvar_id="mA", adapter=None, n=5),
            provider.suggest_tactics_with_probs_async(goal_b, mvar_id="mB", adapter=None, n=5),
        )

    result_a, result_b = asyncio.run(_run())

    assert len(model.batch_calls) == 1
    batched_states, num_return = model.batch_calls[0]
    assert set(batched_states) == {"⊢ A = A", "⊢ B = B"}
    assert num_return == 5
    assert result_a == [("⊢ A = A :: tactic", 1.0)]
    assert result_b == [("⊢ B = B :: tactic", 1.0)]
