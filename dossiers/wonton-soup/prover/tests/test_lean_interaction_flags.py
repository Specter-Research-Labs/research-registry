import asyncio
from types import MethodType

from leantree.repl_adapter.interaction import LeanProcessException, LeanProofBranch


class _Env:
    def __init__(self) -> None:
        self.last_data: dict | None = None
        self.last_method: str | None = None

    async def _send_to_repl_async(self, data: dict) -> dict:
        self.last_method = "_send_to_repl_async"
        self.last_data = data
        return {
            "proofState": 2,
            "goalInfos": [],
            "mctxAfter": {"rootGoals": [], "goals": {}},
            "stepVerification": "OK",
            "goals": [],
        }

    async def inspect_proof_state_async(
        self,
        proof_state: int,
        *,
        include_proof_term: bool = False,
        include_partial_proof_term: bool = False,
        include_step_verification: bool = False,
        include_proof_action_summary: bool = False,
    ) -> dict:
        self.last_method = "inspect_proof_state_async"
        self.last_data = {
            "proofState": proof_state,
            "includeProofTerm": include_proof_term,
            "includePartialProofTerm": include_partial_proof_term,
            "includeStepVerification": include_step_verification,
            "includeProofActionSummary": include_proof_action_summary,
        }
        return {
            "proofState": proof_state + 1,
            "goalInfos": [],
            "mctxAfter": {"rootGoals": [], "goals": {}},
            "stepVerification": "OK",
            "goals": [],
            "proofTerm": {
                "rootId": "r",
                "nodes": [["r", {"kind": "const", "name": "True.intro"}]],
            },
        }


def test_send_tactic_async_forwards_proofstep_flags() -> None:
    env = _Env()
    branch = LeanProofBranch(env, 1, [])

    asyncio.run(
        branch._send_tactic_async(
            "linarith",
            include_proof_term=True,
            include_partial_proof_term=True,
            include_step_verification=True,
            include_proof_action_summary=True,
        )
    )

    assert env.last_data == {
        "tactic": "linarith",
        "proofState": 1,
        "includeProofTerm": True,
        "includePartialProofTerm": True,
        "includeStepVerification": True,
        "includeProofActionSummary": True,
        "timeout": 1000,
    }


def test_inspect_async_forwards_inspection_flags() -> None:
    env = _Env()
    branch = LeanProofBranch(env, 3, [])

    response = asyncio.run(
        branch.inspect_async(
            include_proof_term=True,
            include_partial_proof_term=True,
            include_step_verification=True,
            include_proof_action_summary=True,
        )
    )

    assert env.last_method == "inspect_proof_state_async"
    assert env.last_data == {
        "proofState": 3,
        "includeProofTerm": True,
        "includePartialProofTerm": True,
        "includeStepVerification": True,
        "includeProofActionSummary": True,
    }
    assert response["proofTerm"]["rootId"] == "r"


def test_try_apply_tactic_no_branching_contains_lean_process_crashes() -> None:
    branch = LeanProofBranch(_Env(), 1, ["goal"])

    async def _boom(
        self,
        tactic: str,
        timeout: int | None = 1000,
        *,
        include_proof_term: bool = False,
    ):
        raise LeanProcessException("boom")

    branch.apply_tactic_no_branching_async = MethodType(_boom, branch)

    result = asyncio.run(branch.try_apply_tactic_no_branching_async("linarith"))

    assert not result.is_success()
    assert isinstance(result.error, LeanProcessException)
