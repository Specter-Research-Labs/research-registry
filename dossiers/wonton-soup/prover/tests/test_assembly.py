from prover.assembly import AssemblyStep, ProofAssemblyTrace


def test_proof_assembly_trace_round_trips_action_metadata_without_terms() -> None:
    trace = ProofAssemblyTrace(theorem="theorem t : True := by trivial", root_mvar_id="root")
    trace.steps.append(
        AssemblyStep(
            tactic="trivial",
            mvar_id="root",
            partial_term_before=None,
            partial_term_after=None,
            goals_closed=["root"],
            action_metadata={"provider": "deepseek"},
        )
    )

    restored = ProofAssemblyTrace.from_json(trace.serialize())

    assert restored.serialize() == trace.serialize()
