import asyncio
from types import SimpleNamespace

from prover.adapters.lean import LeanAdapter
from prover.assembly import ProofAssemblyTrace


class _Result:
    def __init__(self, value=None, error: Exception | None = None):
        self.value = value
        self.error = error

    def is_success(self) -> bool:
        return self.error is None


class _Branch:
    def __init__(self) -> None:
        self._goals: list[str] = ["g_root"]
        self._last_response: dict = {"stepVerification": "OK", "goalInfos": [], "goals": []}
        self.applied_tactics: list[str] = []

    @property
    def state(self):
        return SimpleNamespace(goals=[SimpleNamespace(type=goal) for goal in self._goals])

    @property
    def is_solved(self) -> bool:
        return len(self._goals) == 0

    async def try_apply_tactic_no_branching_async(self, tactic: str) -> _Result:
        self.applied_tactics.append(tactic)
        if tactic.startswith("rotate_left "):
            count = int(tactic.split(" ", 1)[1])
            if count < 0 or count >= len(self._goals):
                return _Result(error=ValueError(f"bad rotate: {count}"))
            self._goals = self._goals[count:] + self._goals[:count]
            self._last_response = {"stepVerification": "OK", "goalInfos": [], "goals": []}
            return _Result(value=self)

        if tactic == "split" and self._goals == ["g_root"]:
            self._goals = ["g_left", "g_right"]
            self._last_response = {"stepVerification": "OK", "goalInfos": [], "goals": []}
            return _Result(value=self)

        if tactic == "close_right" and self._goals and self._goals[0] == "g_right":
            self._goals = self._goals[1:]
            self._last_response = {"stepVerification": "OK", "goalInfos": [], "goals": []}
            return _Result(value=self)

        if tactic == "close_left" and self._goals and self._goals[0] == "g_left":
            self._goals = self._goals[1:]
            self._last_response = {
                "stepVerification": "OK",
                "goalInfos": [],
                "goals": [],
                "proofTerm": {
                    "rootId": "r",
                    "nodes": [["r", {"kind": "const", "name": "True.intro"}]],
                },
            }
            return _Result(value=self)

        return _Result(error=ValueError(f"unexpected tactic: {tactic}; goals={self._goals}"))

    def get_proof_term_json(self) -> dict | None:
        if not self.is_solved:
            return None
        return self._last_response.get("proofTerm")


class _Env:
    def __init__(self, branch: _Branch):
        self._branch = branch

    async def proof_from_sorry_async(self, theorem: str) -> _Branch:
        if "theorem" not in theorem:
            raise ValueError("invalid theorem payload")
        return self._branch


def test_reconstruct_proof_term_aligns_goal_with_rotate() -> None:
    branch = _Branch()
    adapter = LeanAdapter(project=None, env=_Env(branch))
    trace = ProofAssemblyTrace(
        theorem="theorem t : True := by\n  sorry",
        root_mvar_id="root",
    )
    trace.add_step(
        tactic="split",
        mvar_id="root",
        partial_term_before=None,
        partial_term_after=None,
        goals_before=["root"],
        goals_after=["left", "right"],
    )
    adapter.assembly_trace = trace

    solution_path = [
        {"goal": "g_root", "tactic": "split"},
        {"goal": "g_right", "tactic": "close_right"},
        {"goal": "g_left", "tactic": "close_left"},
    ]

    proof_term = asyncio.run(adapter.reconstruct_proof_term(solution_path=solution_path))

    assert proof_term is not None
    assert branch.applied_tactics == ["split", "rotate_left 1", "close_right", "close_left"]


def test_replay_solution_path_returns_applied_tactics() -> None:
    branch = _Branch()
    adapter = LeanAdapter(project=None, env=_Env(branch))

    replay = asyncio.run(
        adapter.replay_solution_path(
            theorem_with_sorry="theorem t : True := by\n  sorry",
            solution_path=[
                {"goal": "g_root", "tactic": "split"},
                {"goal": "g_right", "tactic": "close_right"},
                {"goal": "g_left", "tactic": "close_left"},
            ],
        )
    )

    assert replay.success is True
    assert replay.error is None
    assert replay.proof_term is not None
    assert replay.applied_tactics == ["split", "rotate_left 1", "close_right", "close_left"]
