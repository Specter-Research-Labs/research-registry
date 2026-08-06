from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from prover.expr import ExprDAG, PartialProofTerm


@dataclass
class AssemblyStep:
    tactic: str
    mvar_id: str
    partial_term_before: PartialProofTerm | None
    partial_term_after: PartialProofTerm | None
    goals_closed: list[str] = field(default_factory=list)
    goals_opened: list[str] = field(default_factory=list)
    action_metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> "AssemblyStep":
        partial_before = data.get("partialTermBefore")
        partial_after = data.get("partialTermAfter")
        action_metadata = data.get("actionMetadata")
        return cls(
            tactic=str(data["tactic"]),
            mvar_id=str(data["mvarId"]),
            partial_term_before=PartialProofTerm.from_json(partial_before)
            if isinstance(partial_before, dict)
            else None,
            partial_term_after=PartialProofTerm.from_json(partial_after)
            if isinstance(partial_after, dict)
            else None,
            goals_closed=[str(item) for item in data.get("goalsClosed", [])],
            goals_opened=[str(item) for item in data.get("goalsOpened", [])],
            action_metadata=deepcopy(action_metadata) if isinstance(action_metadata, dict) else {},
        )

    def serialize(self) -> dict:
        return {
            "tactic": self.tactic,
            "mvarId": self.mvar_id,
            "partialTermBefore": self.partial_term_before.serialize()
            if self.partial_term_before
            else None,
            "partialTermAfter": self.partial_term_after.serialize()
            if self.partial_term_after
            else None,
            "goalsClosed": self.goals_closed,
            "goalsOpened": self.goals_opened,
            "actionMetadata": deepcopy(self.action_metadata),
        }

    @classmethod
    def from_json(cls, data: dict) -> "AssemblyStep":
        before = data.get("partialTermBefore")
        after = data.get("partialTermAfter")
        action_metadata = data.get("actionMetadata")
        return cls(
            tactic=str(data["tactic"]),
            mvar_id=str(data["mvarId"]),
            partial_term_before=PartialProofTerm.from_json(before)
            if isinstance(before, dict)
            else None,
            partial_term_after=PartialProofTerm.from_json(after)
            if isinstance(after, dict)
            else None,
            goals_closed=[str(goal) for goal in data.get("goalsClosed", [])],
            goals_opened=[str(goal) for goal in data.get("goalsOpened", [])],
            action_metadata=dict(action_metadata) if isinstance(action_metadata, dict) else {},
        )


@dataclass
class ProofAssemblyTrace:
    theorem: str
    root_mvar_id: str
    steps: list[AssemblyStep] = field(default_factory=list)
    final_term: ExprDAG | None = None

    @classmethod
    def from_json(cls, data: dict) -> "ProofAssemblyTrace":
        final_term = data.get("finalTerm")
        return cls(
            theorem=str(data["theorem"]),
            root_mvar_id=str(data["rootMvarId"]),
            steps=[
                AssemblyStep.from_json(step)
                for step in data.get("steps", [])
                if isinstance(step, dict)
            ],
            final_term=ExprDAG.from_json(final_term) if isinstance(final_term, dict) else None,
        )

    def add_step(
        self,
        tactic: str,
        mvar_id: str,
        partial_term_before: PartialProofTerm | None,
        partial_term_after: PartialProofTerm | None,
        goals_before: list[str],
        goals_after: list[str],
        action_metadata: dict[str, object] | None = None,
    ) -> None:
        goals_closed = [g for g in goals_before if g not in goals_after]
        goals_opened = [g for g in goals_after if g not in goals_before]

        self.steps.append(
            AssemblyStep(
                tactic=tactic,
                mvar_id=mvar_id,
                partial_term_before=partial_term_before,
                partial_term_after=partial_term_after,
                goals_closed=goals_closed,
                goals_opened=goals_opened,
                action_metadata=deepcopy(action_metadata) if action_metadata else {},
            )
        )

    def is_complete(self) -> bool:
        return self.final_term is not None

    def serialize(self) -> dict:
        return {
            "theorem": self.theorem,
            "rootMvarId": self.root_mvar_id,
            "steps": [s.serialize() for s in self.steps],
            "finalTerm": self.final_term.serialize() if self.final_term else None,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ProofAssemblyTrace":
        final_term = data.get("finalTerm")
        return cls(
            theorem=str(data["theorem"]),
            root_mvar_id=str(data["rootMvarId"]),
            steps=[
                AssemblyStep.from_json(step)
                for step in data.get("steps", [])
                if isinstance(step, dict)
            ],
            final_term=ExprDAG.from_json(final_term) if isinstance(final_term, dict) else None,
        )
