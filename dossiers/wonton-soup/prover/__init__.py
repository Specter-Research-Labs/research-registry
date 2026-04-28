__all__ = [
    "ProofAssemblyTrace",
    "compute_complexity",
    "metrics_to_dict",
    "ExprDAG",
    "PartialProofTerm",
    "GoalCache",
    "ExplorationHistory",
    "TacticOutcome",
    "FilteredTacticProvider",
    "LeanAdapter",
    "MCTSTraceWriter",
    "MCTSTree",
    "mcts_search",
    "ProofGraph",
    "canonical_edge_match",
    "canonical_node_match",
]


def __getattr__(name: str):
    if name == "ProofAssemblyTrace":
        from prover.assembly import ProofAssemblyTrace

        return ProofAssemblyTrace
    if name in {"compute_complexity", "metrics_to_dict"}:
        from prover.complexity import compute_complexity, metrics_to_dict

        return compute_complexity if name == "compute_complexity" else metrics_to_dict
    if name in {"ExprDAG", "PartialProofTerm"}:
        from prover.expr import ExprDAG, PartialProofTerm

        return ExprDAG if name == "ExprDAG" else PartialProofTerm
    if name == "GoalCache":
        from prover.goal_cache import GoalCache

        return GoalCache
    if name in {"ExplorationHistory", "TacticOutcome"}:
        from prover.history import ExplorationHistory, TacticOutcome

        return ExplorationHistory if name == "ExplorationHistory" else TacticOutcome
    if name == "FilteredTacticProvider":
        from prover.intervention import FilteredTacticProvider

        return FilteredTacticProvider
    if name == "LeanAdapter":
        from prover.adapters.lean import LeanAdapter

        return LeanAdapter
    if name in {"MCTSTraceWriter", "MCTSTree", "mcts_search"}:
        from prover.mcts import MCTSTraceWriter, MCTSTree, mcts_search

        if name == "MCTSTraceWriter":
            return MCTSTraceWriter
        if name == "MCTSTree":
            return MCTSTree
        return mcts_search
    if name in {"ProofGraph", "canonical_edge_match", "canonical_node_match"}:
        from prover.proof import ProofGraph, canonical_edge_match, canonical_node_match

        if name == "ProofGraph":
            return ProofGraph
        if name == "canonical_edge_match":
            return canonical_edge_match
        return canonical_node_match
    raise AttributeError(f"module {__name__} has no attribute {name}")
