import asyncio
import os
import random
import subprocess
import sys
from contextlib import contextmanager

from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory, TacticOutcome
from prover.mcts import mcts_search
from prover.providers.base import TacticProvider
from prover.tests import LEAN_PROJECT, needs_lean

IMPLICIT_SIMP = "theorem {name} (l : List ℕ) : (l ++ []).length = l.length := by\n  sorry"

# ring_nf on this goal runs until the per-tactic heartbeat budget is spent, so its
# outcome is decided by the limit, which is what a host-load test has to exercise.
HEAVY = (
    "theorem heavy (a b c d e : ℕ) :\n"
    "    (a + b + c + d + e) ^ 6 = (e + d + c + b + a) ^ 6 ∧ a + 0 = a := by\n  sorry"
)
HEAVY_TACTICS = [
    "ring_nf",
    "constructor",
    "rw [show a + b + c + d + e = e + d + c + b + a by omega]",
    "simp",
]


class _ListProvider(TacticProvider):
    provider_id = "list"
    last_blocked: list = []

    def __init__(self, tactics):
        self.tactics = tactics

    async def suggest_tactics_with_probs_async(self, goal, mvar_id, adapter, n=10):
        return [(t, 1.0) for t in self.tactics][:n]

    def set_seed(self, seed: int) -> None:
        pass

    def describe(self) -> str:
        return "list"


async def _search(statement: str, tactics: list[str], max_iterations: int, after):
    from prover.adapters.lean import LeanAdapter

    assert LEAN_PROJECT is not None
    adapter = await LeanAdapter.create(LEAN_PROJECT)
    async with adapter:
        history = ExplorationHistory.create("t")
        tree = await mcts_search(
            statement,
            adapter,
            _ListProvider(tactics),
            history=history,
            max_iterations=max_iterations,
            goal_sig_config=GoalSignatureConfig(scheme="text"),
            rng=random.Random(0),
        )
        return await after(adapter, tree, history)


def _check(statement: str, *, library_name: str | None, blocked: frozenset[str]):
    async def after(adapter, tree, _history):
        assert tree.is_solved()
        path = tree.extract_winning_tactics()
        assert path is not None
        check, _ = await adapter.kernel_check(
            statement, path, library_name=library_name, blocked_premises=blocked
        )
        return check

    return asyncio.run(_search(statement, ["simp"], 4, after))


@needs_lean
def test_kernel_check_records_premises_term_hash_and_self_citation():
    check = _check(
        IMPLICIT_SIMP.format(name="kc_ok"), library_name="List.append_nil", blocked=frozenset()
    )
    assert check.status == "checked"
    assert check.tactics == ("simp",)
    assert check.term_hash is not None
    assert "List.append_nil" in check.premises
    assert check.self_citation is True


@needs_lean
def test_kernel_check_rejects_proof_that_uses_a_blocked_premise():
    check = _check(
        IMPLICIT_SIMP.format(name="kc_blocked"),
        library_name=None,
        blocked=frozenset({"List.append_nil"}),
    )
    assert check.status == "blocked_premise"
    assert check.blocked_hits
    assert check.self_citation is None


def _trace(history: ExplorationHistory) -> dict:
    data = history.serialize()
    for record in data["iterations"]:
        for attempt in record["attempts"]:
            del attempt["timestamp_ms"]
    return data


def _heavy_trace() -> tuple[bool, dict]:
    async def after(_adapter, tree, history):
        return tree.is_solved(), _trace(history)

    return asyncio.run(_search(HEAVY, HEAVY_TACTICS, 8, after))


@contextmanager
def _cpu_load():
    cpus = os.cpu_count()
    assert cpus is not None
    burners = [
        subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(2 * cpus)
    ]
    try:
        yield
    finally:
        for burner in burners:
            burner.kill()
            burner.wait()


@needs_lean
def test_same_seed_gives_same_trace_under_cpu_load():
    quiet = _heavy_trace()
    with _cpu_load():
        loaded = _heavy_trace()
    assert quiet == loaded
    solved, trace = quiet
    assert solved
    heavy_ring_nf = [
        a["outcome"]
        for r in trace["iterations"]
        for a in r["attempts"]
        if a["tactic"] == "ring_nf" and "^ 6" in a["goal_type"]
    ]
    assert heavy_ring_nf and set(heavy_ring_nf) == {TacticOutcome.FAILURE.value}
