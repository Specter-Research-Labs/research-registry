from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.cross_assistant_alignment import load_run_signatures
from atp.coq.process_trace import extract_goal_state, process_trace_to_graph, replay_theorem_block


def _goal_fields(name: str, ty_name: str) -> list[object]:
    return [
        ["info", [["evar", ["Ser_Evar", name]], ["name", []]]],
        ["ty", ["Const", ty_name]],
        ["hyp", []],
    ]


def _goal_response(
    *,
    focused: list[list[object]],
    background: list[list[object]] | None = None,
    shelved: list[list[object]] | None = None,
    given_up: list[list[object]] | None = None,
) -> list[object]:
    background = background or []
    shelved = shelved or []
    given_up = given_up or []
    return [
        [
            "Answer",
            "1",
            [
                "ObjList",
                [
                    [
                        "CoqGoal",
                        [
                            ["goals", focused],
                            ["stack", [[ [goal], [] ] for goal in background]],
                            ["bullet", []],
                            ["shelf", shelved],
                            ["given_up", given_up],
                        ],
                    ]
                ],
            ],
        ],
        ["Answer", "1", "Completed"],
    ]


def _message_response(message: str) -> list[object]:
    escaped = message.replace("\\", "\\\\").replace("\n", "\\n")
    return [
        [
            "Feedback",
            [["contents", ["Message", [f'str"{escaped}"']]]],
        ],
        ["Answer", "1", "Completed"],
    ]


class FakeSerapiSession:
    def __init__(self) -> None:
        self._next_state = 1

    def send(self, command: str) -> list[object]:
        if command.startswith("(Add () "):
            state_id = self._next_state
            self._next_state += 1
            return [["Answer", "1", ["Added", str(state_id)]], ["Answer", "1", "Completed"]]
        if command.startswith("(Exec "):
            return [["Answer", "1", "Completed"]]
        if command == "(Query () Goals)":
            return _goal_response(focused=[])
        if command == '(Query () (Vernac "Show Proof."))':
            return _message_response("")
        if command == "(Query ((sid 1)) Goals)":
            return _goal_response(focused=[])
        if command == '(Query ((sid 1)) (Vernac "Show Proof."))':
            return _message_response("")
        if command == "(Query ((sid 2)) Goals)":
            return _goal_response(focused=[_goal_fields("1", "goal_demo")])
        if command == '(Query ((sid 2)) (Vernac "Show Proof."))':
            return _message_response("?demo")
        if command == "(Query ((sid 3)) Goals)":
            return _goal_response(
                focused=[_goal_fields("2", "left_goal"), _goal_fields("3", "right_goal")]
            )
        if command == '(Query ((sid 3)) (Vernac "Show Proof."))':
            return _message_response("conj ?left ?right")
        if command == "(Query ((sid 4)) Goals)":
            return _goal_response(focused=[_goal_fields("3", "right_goal")])
        if command == '(Query ((sid 4)) (Vernac "Show Proof."))':
            return _message_response("conj I ?right")
        if command == "(Query ((sid 5)) Goals)":
            return _goal_response(focused=[])
        if command == '(Query ((sid 5)) (Vernac "Show Proof."))':
            return _message_response("conj I I")
        if command == "(Query ((sid 6)) Goals)":
            return _goal_response(focused=[])
        if command == '(Query ((sid 6)) (Vernac "Show Proof."))':
            return _message_response("demo = conj I I")
        raise AssertionError(f"unexpected command: {command}")


def test_extract_goal_state_parses_focused_goals() -> None:
    state = extract_goal_state(
        _goal_response(
            focused=[_goal_fields("7", "goal_one"), _goal_fields("8", "goal_two")],
        )
    )

    assert state is not None
    assert [goal.goal_id for goal in state.focused] == ["7", "8"]
    assert [goal.goal_type for goal in state.focused] == ["(Const goal_one)", "(Const goal_two)"]


def test_extract_goal_state_parses_background_shelved_and_given_up_goals() -> None:
    state = extract_goal_state(
        _goal_response(
            focused=[_goal_fields("7", "goal_one")],
            background=[_goal_fields("8", "goal_two")],
            shelved=[_goal_fields("9", "goal_three")],
            given_up=[_goal_fields("10", "goal_four")],
        )
    )

    assert state is not None
    assert [goal.goal_id for goal in state.background] == ["8"]
    assert [goal.goal_id for goal in state.shelved] == ["9"]
    assert [goal.goal_id for goal in state.given_up] == ["10"]


def test_replay_theorem_block_builds_process_steps_and_trace_graph() -> None:
    trace = replay_theorem_block(
        FakeSerapiSession(),
        theorem="demo",
        source_path="sample.v",
        prelude_sentences=["Require Import Coq.Init.Logic."],
        block_sentences=[
            "Theorem demo : True /\\ True.",
            "split.",
            "exact I.",
            "exact I.",
            "Qed.",
        ],
    )

    assert trace.trace_source == "serapi_replay"
    assert trace.trace_completeness == "script"
    assert [step.command_kind for step in trace.steps] == [
        "theorem_decl",
        "tactic",
        "tactic",
        "tactic",
        "proof_end",
    ]
    assert trace.steps[1].action_metadata["branch_arity"] == 2
    assert trace.steps[1].action_metadata["continuation_kind"] == "branch"
    assert trace.steps[3].action_metadata["continuation_kind"] == "solve"

    graph = process_trace_to_graph(trace)
    assert graph.graph.number_of_nodes() == 3
    assert graph.graph.number_of_edges() == 2
    last_state = "state:2"
    assert graph.graph.nodes[last_state]["is_terminal"] is True
    assert graph.graph.nodes[last_state]["terminal_tactic"] == "exact I."


def test_load_run_signatures_can_use_search_trace_graph_source(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    graph_payload = {
        "graph_family": "search_trace",
        "graph_backend": "coq",
        "graph_provenance": "process_replay",
        "nodes": [
            {"id": "n0", "goal_sig": "sig0", "goal_type": "g0", "depth": 0},
            {"id": "n1", "goal_sig": "sig1", "goal_type": "g1", "depth": 1},
        ],
        "edges": [
            {
                "source": "n0",
                "target": "n1",
                "tactic": "split.",
                "tactic_norm": "split",
                "edge_role": "fam:split",
                "action_kind": "tactic_step",
            }
        ],
    }
    (run_dir / "t1").mkdir(parents=True, exist_ok=True)
    (run_dir / "run_config.json").write_text(
        json.dumps({"mode": "external", "corpus": "coq-stdlib", "run_id": run_dir.name}),
        encoding="utf-8",
    )
    (run_dir / "t1" / "wild_type_search_trace_graph.json").write_text(
        json.dumps(graph_payload),
        encoding="utf-8",
    )
    with gzip.open(run_dir / "summary.json.gz", "wt") as handle:
        json.dump(
            {"theorems": [{"name": "t1", "wild_type": {"solved": True}, "interventions": []}]},
            handle,
        )

    sigs = load_run_signatures(run_dir, solved_only=False, graph_source="search_trace_graph")
    assert len(sigs) == 1
    assert sigs[0].graph_kind == "search_trace"
