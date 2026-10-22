import asyncio
import os
from dataclasses import dataclass

import pytest

from prover.dependencies import (
    Dependency,
    PremiseBlocked,
    check_proof,
    forbidden_hits,
    premise_name,
    proof_script,
)
from prover.goal_signature import GoalSignatureConfig
from prover.history import ExplorationHistory, TacticOutcome
from prover.intervention import FilteredTacticProvider, PegKind
from prover.mcts import mcts_search

LEAN_PROJECT = os.environ.get("WONTON_LEAN_PROJECT")
needs_lean = pytest.mark.skipif(
    LEAN_PROJECT is None, reason="set WONTON_LEAN_PROJECT to a built Lean project"
)


def test_premise_name_strips_generated_suffixes():
    assert premise_name("List.append_nil._simp_1") == "List.append_nil"
    assert premise_name("Nat.add_comm") == "Nat.add_comm"
    assert premise_name("Nat.succ.eq_1") == "Nat.succ.eq_1"


def test_forbidden_hits_match_lemma_and_its_aux_lemmas_only():
    names = {"List.append_nil._simp_1", "List.append_nil_left", "eq_self"}
    assert forbidden_hits(names, {"List.append_nil"}) == {"List.append_nil._simp_1"}


def test_proof_script_parenthesizes_multiline_tactics():
    statement = "theorem {name} (s t : Set ℕ) : s ∩ t = t ∩ s := by\n  sorry"
    script = proof_script(statement, ["classical\n  ext x\n  simp", "rotate_left 1", "rfl"])
    assert script == (
        "theorem {name} (s t : Set ℕ) : s ∩ t = t ∩ s := by\n"
        "  (classical\n"
        "     ext x\n"
        "     simp\n"
        "  )\n"
        "  rotate_left 1\n"
        "  rfl"
    )


def test_proof_script_requires_trailing_sorry():
    with pytest.raises(ValueError):
        proof_script("theorem t : True := by\n  trivial", ["trivial"])


def test_dependency_roles():
    def dep(name, kind="thm", module="Mathlib.Algebra.Group.Basic", instance=False, prop=True):
        return Dependency(name=name, kind=kind, module=module, instance=instance, prop=prop)

    assert dep("mul_comm").role == "lemma"
    assert dep("List.append_nil", module="Init.Data.List.Basic").role == "lemma"
    assert dep("Nat.instMonoid", kind="def", instance=True, prop=False).role == "instance"
    assert dep("Mathlib.Tactic.Ring.add_congr", module="Mathlib.Tactic.Ring.Basic").role == "tactic"
    assert dep("congrArg", module="Init.Prelude").role == "logic"
    assert dep("propext", kind="axiom", module="Init.Core").role == "axiom"
    assert dep("List.length", kind="def", module="Init.Prelude", prop=False).role == "definition"


@dataclass
class _Goal:
    mvar_id: str
    type: str
    type_expr: dict | None = None
    hypotheses: tuple = ()


class _ListProvider:
    provider_id = "list"
    last_blocked: list = []

    def __init__(self, tactics):
        self.tactics = tactics

    async def suggest_tactics_with_probs_async(self, goal, mvar_id, adapter, n=10):
        return [(t, 1.0) for t in self.tactics][:n]

    def describe(self) -> str:
        return "list"


def test_textual_filter_blocks_qualified_name_only():
    provider = FilteredTacticProvider(
        _ListProvider(
            [
                "simp [List.append_nil]",
                "rw [List.append_nil_left]",
                "exact List.append_nil.symm",
                "simp",
            ]
        ),
        blocked_premises={"List.append_nil"},
        goal_sig_config=GoalSignatureConfig(scheme="text"),
    )
    kept = asyncio.run(
        provider.suggest_tactics_with_probs_async(_Goal("g", "P"), "g", adapter=None)
    )
    assert [t for t, _ in kept] == ["rw [List.append_nil_left]", "simp"]
    assert {b.peg_kind for b in provider.last_blocked} == {PegKind.PREMISE.value}


class _TermBlockingAdapter:
    async def initialize(self, theorem_with_sorry):
        self.goal = _Goal("root", "P")
        return ["root"]

    def get_goal(self, mvar_id):
        return self.goal

    async def preview_tactic(self, mvar_id, tactic):
        raise PremiseBlocked(tactic, ["List.append_nil"])


def test_mcts_records_term_level_premise_block():
    history = ExplorationHistory.create("theorem")
    tree = asyncio.run(
        mcts_search(
            "theorem",
            _TermBlockingAdapter(),
            _ListProvider(["simp"]),
            history=history,
            max_iterations=1,
            goal_sig_config=GoalSignatureConfig(scheme="text"),
        )
    )
    assert not tree.is_solved()
    attempts = [a for record in history.iterations for a in record.attempts]
    assert [(a.outcome, a.peg_kind, a.block_reason) for a in attempts] == [
        (TacticOutcome.BLOCKED, "premise", "term:List.append_nil")
    ]


IMPLICIT_SIMP = "theorem {name} (l : List ℕ) : (l ++ []).length = l.length := by\n  sorry"


async def _with_adapter(body):
    from prover.adapters.lean import LeanAdapter

    adapter = await LeanAdapter.create(LEAN_PROJECT)
    async with adapter:
        return await body(adapter)


@needs_lean
def test_check_proof_counts_lemma_simp_used_implicitly():
    async def body(adapter):
        return await check_proof(adapter.env, IMPLICIT_SIMP.format(name="dep_simp"), ["simp"])

    check = asyncio.run(_with_adapter(body))
    assert check.ok
    assert "List.append_nil" in check.premises()


@needs_lean
def test_check_proof_rejects_sorry():
    async def body(adapter):
        return await check_proof(adapter.env, IMPLICIT_SIMP.format(name="dep_sorry"), ["sorry"])

    check = asyncio.run(_with_adapter(body))
    assert not check.ok
    assert check.error == "proof uses sorry"


@needs_lean
def test_adapter_rejects_tactic_whose_term_uses_forbidden_premise():
    async def body(adapter):
        adapter.forbidden_constants = frozenset({"List.append_nil"})
        statement = IMPLICIT_SIMP.format(name="dep_block")
        [root] = await adapter.initialize(statement)
        with pytest.raises(PremiseBlocked):
            await adapter.preview_tactic(root, "simp")
        return await adapter.preview_tactic(
            root, "rw [List.length_append, List.length_nil, Nat.add_zero]"
        )

    preview = asyncio.run(_with_adapter(body))
    assert preview is not None
