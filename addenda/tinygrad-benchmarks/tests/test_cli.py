from __future__ import annotations

import json
from pathlib import Path

from tinygrad_benchmarks.cli import main


def test_cli_curate_private_and_freeze_split(tmp_path: Path) -> None:
    input_path = tmp_path / "tasks.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "repo_remote": "https://example.com/tinygrad.git",
                    "repo_commit": "1" * 40,
                    "task_statement": "Fix one",
                    "source_refs": ["issue:#1"],
                    "target_paths": ["tinygrad/a.py"],
                    "acceptance_command": ["python", "-m", "pytest", "tests/test_a.py"],
                    "timeout_seconds": 10,
                    "gold_commit": "9" * 40,
                    "historical_solution_refs": ["commit:9999"],
                    "metadata": {
                        "quality_score": 71,
                        "mined_from_commit": "a" * 40,
                    },
                },
                {
                    "repo_remote": "https://example.com/tinygrad.git",
                    "repo_commit": "2" * 40,
                    "task_statement": "Fix two",
                    "source_refs": ["issue:#2"],
                    "target_paths": ["tinygrad/b.py"],
                    "acceptance_command": ["python", "-m", "pytest", "tests/test_b.py"],
                    "timeout_seconds": 10,
                },
            ]
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "index.jsonl"
    private_path = tmp_path / "private.json"
    split_dir = tmp_path / "split"
    assert (
        main(
            [
                "curate",
                "--input",
                str(input_path),
                "--out",
                str(index_path),
                "--private-out",
                str(private_path),
            ]
        )
        == 0
    )
    assert index_path.is_file()
    assert private_path.is_file()
    public_rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    assert "gold_commit" not in public_rows[0]
    assert public_rows[0]["source_refs"] == ["history:mined"]
    assert public_rows[0]["metadata"] == {"quality_score": 71}
    private_payload = json.loads(private_path.read_text(encoding="utf-8"))
    assert private_payload["rows"][0]["gold_commit"] == "9" * 40
    assert private_payload["rows"][0]["private_source_refs"] == ["issue:#1"]
    assert private_payload["rows"][0]["private_metadata"]["mined_from_commit"] == "a" * 40
    assert (
        main(
            [
                "freeze-split",
                "--index",
                str(index_path),
                "--out-dir",
                str(split_dir),
                "--seed",
                "7",
                "--heldout-fraction",
                "0.5",
            ]
        )
        == 0
    )
    assert (split_dir / "public_dev.jsonl").is_file()
    assert (split_dir / "heldout_test.jsonl").is_file()
    assert (split_dir / "split_manifest.json").is_file()


def test_cli_export_prompts_omits_repo_provenance(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    index_path.write_text(
        json.dumps(
            {
                "repo_remote": "https://example.com/tinygrad.git",
                "repo_commit": "1" * 40,
                "task_statement": "Fix `tinygrad/a.py` so `tests/test_a.py` passes.",
                "source_refs": ["history:mined"],
                "target_paths": ["tinygrad/a.py"],
                "acceptance_command": ["python", "-m", "pytest", "tests/test_a.py"],
                "timeout_seconds": 10,
                "metadata": {"quality_score": 71},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "prompts.jsonl"
    assert (
        main(
            [
                "export-prompts",
                "--index",
                str(index_path),
                "--out",
                str(out_path),
            ]
        )
        == 0
    )
    prompt_row = json.loads(out_path.read_text(encoding="utf-8").splitlines()[0])
    assert "repo_remote" not in prompt_row
    assert "repo_commit" not in prompt_row
    assert "source_refs" not in prompt_row
    assert "quality_score" not in prompt_row
    assert "Do not rely on git history or network access." in prompt_row["prompt"]
