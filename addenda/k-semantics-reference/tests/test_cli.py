import json
from pathlib import Path

from cli import main

FIXTURES = Path(__file__).with_name("fixtures")


def _compute_payload(name: str) -> dict:
    return {
        "name": name,
        "trials": [
            {"agent_cost": 10.0, "agent_solved": True, "blind_cost": 100.0, "blind_solved": True},
            {"agent_cost": 20.0, "agent_solved": True, "blind_cost": 200.0, "blind_solved": True},
        ],
        "problem_space": {
            "S": "toy states",
            "O": ["step_a", "step_b"],
            "C": ["no invalid transitions"],
            "E": "maximize progress",
            "H": 1000.0,
            "H_unit": "step",
            "w": {"default": 2.0, "by_operator": {"step_b": 3.0}, "unit": "joule"},
            "S_init": "start",
            "S_goal": "goal",
        },
        "agent_policy_spec": {
            "name": "agent",
            "operator_semantics": "toy-step",
        },
        "blind_policy_spec": {
            "name": "blind",
            "operator_semantics": "toy-step",
        },
    }


def test_compute_cli_accepts_structured_problem_space(tmp_path, capsys):
    path = tmp_path / "compute.json"
    path.write_text(json.dumps(_compute_payload("toy-case")), encoding="utf-8")

    main(["compute", "--input", str(path)])
    out = json.loads(capsys.readouterr().out)

    assert out["name"] == "toy-case"
    assert out["problem_space"]["w"]["default"] == 2.0
    assert out["problem_space"]["w"]["by_operator"] == {"step_b": 3.0}
    assert out["problem_space"]["w"]["unit"] == "joule"
    assert out["K"]["restricted_mean_at_stop"] == 1.0


def test_sweep_and_report_render_markdown(tmp_path, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        "\n".join(json.dumps(_compute_payload(name)) for name in ("case-a", "case-b")) + "\n",
        encoding="utf-8",
    )

    sweep_output = tmp_path / "sweep.jsonl"
    main(["sweep", "--input", str(cases), "--format", "jsonl", "--output", str(sweep_output)])
    sweep_rows = sweep_output.read_text(encoding="utf-8").strip().splitlines()
    assert len(sweep_rows) == 2

    capsys.readouterr()
    main(["report", "--input", str(sweep_output), "--format", "markdown"])
    rendered = capsys.readouterr().out
    expected = (FIXTURES / "report_markdown_golden.md").read_text(encoding="utf-8")
    assert rendered == expected


def test_benchmark_cli_emits_summary_rows(capsys):
    main(
        [
            "benchmark",
            "--case",
            "sorting-small",
            "--case",
            "bitstring-small",
            "--repeats",
            "1",
            "--warmup",
            "0",
            "--format",
            "jsonl",
        ]
    )
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [row["name"] for row in rows] == ["sorting-small", "bitstring-small"]
    for row in rows:
        assert row["mean_wall_sec"] >= 0.0
        assert row["min_wall_sec"] >= 0.0
        assert row["max_wall_sec"] >= row["min_wall_sec"]
        assert row["repeats"] == 1
        assert row["seed"] == 0
        assert row["exact_supported"] is True
        assert "K_restricted_mean_at_stop" in row


def test_paper_demo_cli_notes_are_attached(capsys):
    main(["demo", "paper-amoeba"])
    amoeba = json.loads(capsys.readouterr().out)
    assert amoeba["cli"]["assumptions"]
    assert amoeba["cli"]["units"]["tau_agent"] == "s"

    main(["demo", "paper-planarian"])
    planarian = json.loads(capsys.readouterr().out)
    assert planarian["cli"]["assumptions"]
    assert planarian["cli"]["units"]["tau_agent"] == "days"
