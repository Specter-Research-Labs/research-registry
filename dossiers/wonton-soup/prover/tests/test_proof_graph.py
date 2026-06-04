from prover.proof import ProofGraph


def test_extract_solution_path_handles_cycles_without_repeated_descendant_scans() -> None:
    graph = ProofGraph()
    graph.graph.add_node("root", goal_type="root")
    graph.graph.add_node("loop_a", goal_type="loop_a")
    graph.graph.add_node("loop_b", goal_type="loop_b")
    graph.graph.add_node("terminal", goal_type="terminal", is_terminal=True, terminal_tactic="done")
    graph.graph.add_edge("root", "loop_a", tactic="intro")
    graph.graph.add_edge("loop_a", "loop_b", tactic="cases h")
    graph.graph.add_edge("loop_b", "loop_a", tactic="cycle")
    graph.graph.add_edge("loop_b", "terminal", tactic="exact h")

    assert graph.extract_solution_path() == [
        {"goal": "root", "tactic": "intro", "mvar_id": "root"},
        {"goal": "loop_a", "tactic": "cases h", "mvar_id": "loop_a"},
        {"goal": "loop_b", "tactic": "exact h", "mvar_id": "loop_b"},
        {"goal": "terminal", "tactic": "done", "mvar_id": "terminal"},
    ]


def test_extract_solution_path_ignores_unreachable_terminal_branches() -> None:
    graph = ProofGraph()
    graph.graph.add_node("root", goal_type="root")
    graph.graph.add_node("dead", goal_type="dead")
    graph.graph.add_node("other_root", goal_type="other_root")
    graph.graph.add_node("terminal", goal_type="terminal", is_terminal=True, terminal_tactic="done")
    graph.graph.add_edge("root", "dead", tactic="bad")
    graph.graph.add_edge("other_root", "terminal", tactic="good")

    assert graph.extract_solution_path() == [
        {"goal": "other_root", "tactic": "good", "mvar_id": "other_root"},
        {"goal": "terminal", "tactic": "done", "mvar_id": "terminal"},
    ]
