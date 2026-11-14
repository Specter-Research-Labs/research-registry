import asyncio
import re
from types import SimpleNamespace

from leantree.repl_adapter.interaction import LeanInteractionException

from prover.adapters.lean import LeanAdapter

_WRAPPED = re.compile(r"heartbeat_limit \d+ => \((.*)\)", re.DOTALL)


class _Branch:
    def __init__(self) -> None:
        self._goals: list[str] = ["g_root"]
        self._proof_term: dict | None = None
        self.applied_tactics: list[str] = []

    @property
    def state(self):
        return SimpleNamespace(goals=[SimpleNamespace(type=goal) for goal in self._goals])

    @property
    def is_solved(self) -> bool:
        return len(self._goals) == 0

    async def _delete_masked_goals_async(self) -> None:
        return None

    async def apply_tactic_no_branching_async(self, wrapped: str, timeout: int) -> "_Branch":
        match = _WRAPPED.fullmatch(wrapped)
        assert match is not None, wrapped
        tactic = match.group(1)
        self.applied_tactics.append(tactic)
        if tactic.startswith("rotate_left "):
            count = int(tactic.split(" ", 1)[1])
            self._goals = self._goals[count:] + self._goals[:count]
            return self
        if tactic == "split" and self._goals == ["g_root"]:
            self._goals = ["g_left", "g_right"]
            return self
        if tactic == "close_right" and self._goals[0] == "g_right":
            self._goals = self._goals[1:]
            return self
        if tactic == "close_left" and self._goals[0] == "g_left":
            self._goals = self._goals[1:]
            self._proof_term = {
                "rootId": "r",
                "nodes": [["r", {"kind": "const", "name": "True.intro"}]],
            }
            return self
        raise LeanInteractionException(f"unexpected tactic: {tactic}; goals={self._goals}")

    def get_proof_term_json(self) -> dict | None:
        return self._proof_term if self.is_solved else None


class _Env:
    def __init__(self, branch: _Branch):
        self._branch = branch

    async def proof_from_sorry_async(self, theorem: str) -> _Branch:
        assert "theorem" in theorem
        return self._branch


def _replay(solution_path: list[dict[str, str]]):
    branch = _Branch()
    adapter = LeanAdapter(project=None, env=_Env(branch))
    replay = asyncio.run(
        adapter.replay_solution_path(
            theorem_with_sorry="theorem t : True := by\n  sorry",
            solution_path=solution_path,
        )
    )
    return replay, branch


def test_replay_aligns_each_step_with_its_goal() -> None:
    replay, branch = _replay(
        [
            {"goal": "g_root", "tactic": "split"},
            {"goal": "g_right", "tactic": "close_right"},
            {"goal": "g_left", "tactic": "close_left"},
        ]
    )

    assert replay.success is True
    assert replay.error is None
    assert replay.proof_term is not None
    assert replay.applied_tactics == ["split", "rotate_left 1", "close_right", "close_left"]
    assert branch.applied_tactics == replay.applied_tactics


def test_replay_fails_when_a_recorded_goal_is_not_open() -> None:
    replay, _ = _replay(
        [
            {"goal": "g_root", "tactic": "split"},
            {"goal": "g_missing", "tactic": "close_right"},
            {"goal": "g_left", "tactic": "close_left"},
        ]
    )

    assert replay.success is False
    assert replay.error is not None and "g_missing" in replay.error
    assert replay.applied_tactics == ["split"]


def test_replay_fails_when_the_proof_is_still_open() -> None:
    replay, _ = _replay([{"goal": "g_root", "tactic": "split"}])

    assert replay.success is False
    assert replay.applied_tactics == ["split"]
