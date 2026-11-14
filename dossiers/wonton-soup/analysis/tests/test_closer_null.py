from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from analysis.closer_null import recovers, run_attempt

THEOREM = "Nat_x2eadd_x5fcomm"


@dataclass
class FakeAdapter:
    """Goals are strings; a tactic maps a goal to its child goals, or is rejected when absent."""

    rules: dict[tuple[str, str], list[str]]
    root: str
    states: dict[str, str] = field(default_factory=dict)
    checked: list[list[dict[str, str]]] = field(default_factory=list)
    declared: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.env = SimpleNamespace(
            checkpoint=lambda: frozenset(self.declared),
            rollback_to=lambda saved: setattr(self, "declared", set(saved)),
        )

    async def initialize(self, statement: str) -> list[str]:
        assert statement not in self.declared, "attempts must roll back their declaration"
        self.declared.add(statement)
        self.states = {"s0": self.root}
        return ["s0"]

    def get_goal(self, state: str):
        return SimpleNamespace(type=self.states[state])

    async def preview_tactic(self, state: str, tactic: str):
        children = self.rules.get((self.states[state], tactic))
        if children is None:
            return None
        ids = [f"{state}.{i}" for i in range(len(children))]
        return SimpleNamespace(child_mvar_ids=ids, children=dict(zip(ids, children)))

    def commit_tactic(self, preview) -> list[str]:
        self.states.update(preview.children)
        return preview.child_mvar_ids

    async def kernel_check(self, statement, path, *, library_name, blocked_premises):
        self.checked.append(path)
        tactics = [step["tactic"] for step in path]
        return SimpleNamespace(
            status="checked", error=None, tactics=tactics, premises=["Nat.add_comm"]
        ), None


def _run(adapter, prefix, closer):
    return asyncio.run(run_attempt(adapter, "theorem x : P := by\n  sorry", prefix, closer))


def test_attempt_statuses_and_checked_path() -> None:
    adapter = FakeAdapter(
        rules={
            ("a b : Nat ⊢ P", "omega"): [],
            ("⊢ ∀ a b, P", "intros"): ["a b : Nat ⊢ P"],
            ("⊢ ∀ a b, P", "constructor"): ["g1", "g2"],
        },
        root="⊢ ∀ a b, P",
    )
    assert _run(adapter, (), "omega") == {"status": "rejected"}
    assert _run(adapter, (), "constructor") == {"status": "open_goals", "open_goals": 2}
    assert _run(adapter, ("intros",), "ring") == {"status": "rejected"}
    row = _run(adapter, ("intros",), "omega")
    assert row["status"] == "checked" and row["tactics"] == ["intros", "omega"]
    assert adapter.checked == [
        [
            {"tactic": "intros", "goal": "⊢ ∀ a b, P"},
            {"tactic": "omega", "goal": "a b : Nat ⊢ P"},
        ]
    ]
    adapter.rules[("⊢ ∀ a b, P", "intros")] = ["g1", "g2"]
    assert _run(adapter, ("intros",), "omega") == {"status": "prefix_goals", "open_goals": 2}


def test_recovers_respects_block_easy_and_self_citation() -> None:
    attempts = [
        {"status": "checked", "tactics": ["intros", "omega"], "premises": []},
        {"status": "checked", "tactics": ["linarith"], "premises": ["Nat.add_comm"]},
        {"status": "rejected"},
    ]
    none: frozenset[str] = frozenset()
    assert recovers(attempts, THEOREM, frozenset({"linarith"}), matched=False, nonself=False)
    assert not recovers(attempts, THEOREM, frozenset({"linarith"}), matched=True, nonself=False)
    assert recovers(attempts, THEOREM, none, matched=True, nonself=False)
    assert not recovers(attempts, THEOREM, none, matched=True, nonself=True)
    assert not recovers(
        attempts, THEOREM, frozenset({"intros", "linarith"}), matched=False, nonself=False
    )
