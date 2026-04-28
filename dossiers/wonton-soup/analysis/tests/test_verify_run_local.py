from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from leantree.repl_adapter.interaction import LeanProcessException

from analysis.logs import ProviderRun, sha256_file
from analysis.verify_run_local import (
    VERIFY_LOCAL_CANDIDATE_NAME,
    VERIFY_LOCAL_REPORT_NAME,
    VERIFY_LOCAL_SUMMARY_NAME,
    VERIFY_LOCAL_VERSION,
    verify_provider_run_local,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_verify_provider_run_local_writes_reports(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    lean_project = tmp_path / "lean_project"
    lean_project.mkdir(parents=True, exist_ok=True)
    items_path = tmp_path / "items.jsonl"
    _write_jsonl(
        items_path,
        [
            {
                "item_id": "solved_one",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            },
            {
                "item_id": "unsolved_one",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            },
        ],
    )
    _write_json(
        run_dir / "run_config.json",
        {
            "backend": "lean",
            "corpus_meta": {"items_path": str(items_path)},
            "resolved": {"project_path": str(lean_project)},
        },
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "theorems": [
                {"name": "solved_one", "wild_type": {"solved": True}},
                {"name": "unsolved_one", "wild_type": {"solved": False}},
            ],
            "aggregates": {},
        },
    )
    _write_json(
        run_dir / "solved_one" / "wild_type_history.json",
        {"solution_path": [{"goal": "g0", "tactic": "trivial"}]},
    )

    sent_commands: list[str] = []

    class _FakeEnv:
        def checkpoint(self) -> str:
            return "base"

        def rollback_to(self, checkpoint: str) -> None:
            assert checkpoint == "base"

        async def send_command_async(self, command: str) -> dict[str, object]:
            sent_commands.append(command)
            return {"env": 1}

    class _FakeAdapter:
        def __init__(self) -> None:
            self.env = _FakeEnv()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def replay_solution_path(self, theorem_with_sorry: str, solution_path: list[dict]):
            tactics = [step["tactic"] for step in solution_path]
            return SimpleNamespace(
                success=True,
                error=None,
                applied_tactics=tactics,
                proof_term=None,
            )

    async def _fake_create(project_path: Path | str) -> _FakeAdapter:
        assert Path(project_path) == lean_project
        return _FakeAdapter()

    monkeypatch.setattr("analysis.verify_run_local.LeanAdapter.create", _fake_create)

    report = verify_provider_run_local(ProviderRun(run_dir=run_dir, provider=None))

    assert report["counts"]["eligible"] == 1
    assert report["counts"]["verified"] == 1
    assert report["counts"]["skipped_unsolved"] == 1
    assert report["selection"]["selected_theorems"] == ["solved_one"]

    theorem_report = json.loads((run_dir / "solved_one" / VERIFY_LOCAL_REPORT_NAME).read_text())
    assert theorem_report["status"] == "verified"
    assert theorem_report["applied_tactics"] == ["trivial"]

    candidate_text = (run_dir / "solved_one" / VERIFY_LOCAL_CANDIDATE_NAME).read_text(
        encoding="utf-8"
    )
    assert "theorem solved_one__verify_local : True := by" in candidate_text
    assert "  trivial" in candidate_text
    assert any("theorem solved_one__verify_local" in command for command in sent_commands)
    assert (run_dir / VERIFY_LOCAL_SUMMARY_NAME).exists()


def test_verify_provider_run_local_marks_candidate_process_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run"
    lean_project = tmp_path / "lean_project"
    lean_project.mkdir(parents=True, exist_ok=True)
    items_path = tmp_path / "items.jsonl"
    _write_jsonl(
        items_path,
        [
            {
                "item_id": "solved_one",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            }
        ],
    )
    _write_json(
        run_dir / "run_config.json",
        {
            "backend": "lean",
            "corpus_meta": {"items_path": str(items_path)},
            "resolved": {"project_path": str(lean_project)},
        },
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "theorems": [{"name": "solved_one", "wild_type": {"solved": True}}],
            "aggregates": {},
        },
    )
    _write_json(
        run_dir / "solved_one" / "wild_type_history.json",
        {"solution_path": [{"goal": "g0", "tactic": "trivial"}]},
    )

    class _CrashEnv:
        def checkpoint(self) -> str:
            return "base"

        def rollback_to(self, checkpoint: str) -> None:
            assert checkpoint == "base"

        async def send_command_async(self, command: str) -> dict[str, object]:
            raise LeanProcessException("compile crashed")

    class _CrashAdapter:
        def __init__(self) -> None:
            self.env = _CrashEnv()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def replay_solution_path(self, theorem_with_sorry: str, solution_path: list[dict]):
            tactics = [step["tactic"] for step in solution_path]
            return SimpleNamespace(
                success=True,
                error=None,
                applied_tactics=tactics,
                proof_term=None,
            )

    async def _fake_create(project_path: Path | str) -> _CrashAdapter:
        assert Path(project_path) == lean_project
        return _CrashAdapter()

    monkeypatch.setattr("analysis.verify_run_local.LeanAdapter.create", _fake_create)

    report = verify_provider_run_local(ProviderRun(run_dir=run_dir, provider=None))

    assert report["counts"]["candidate_failed"] == 1
    theorem_report = json.loads((run_dir / "solved_one" / VERIFY_LOCAL_REPORT_NAME).read_text())
    assert theorem_report["status"] == "candidate_failed"
    assert theorem_report["candidate_error"] == "compile crashed"
    assert theorem_report["replay_error"] is None


def test_verify_provider_run_local_reuses_fresh_theorem_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run"
    lean_project = tmp_path / "lean_project"
    lean_project.mkdir(parents=True, exist_ok=True)
    items_path = tmp_path / "items.jsonl"
    _write_jsonl(
        items_path,
        [
            {
                "item_id": "solved_one",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            }
        ],
    )
    _write_json(
        run_dir / "run_config.json",
        {
            "backend": "lean",
            "corpus_meta": {"items_path": str(items_path)},
            "resolved": {"project_path": str(lean_project)},
        },
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "theorems": [{"name": "solved_one", "wild_type": {"solved": True}}],
            "aggregates": {},
        },
    )
    history_path = run_dir / "solved_one" / "wild_type_history.json"
    _write_json(
        history_path,
        {"solution_path": [{"goal": "g0", "tactic": "trivial"}]},
    )
    candidate_path = run_dir / "solved_one" / VERIFY_LOCAL_CANDIDATE_NAME
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        "import Mathlib\n\ntheorem solved_one__verify_local : True := by\n  trivial\n",
        encoding="utf-8",
    )
    _write_json(
        run_dir / "solved_one" / VERIFY_LOCAL_REPORT_NAME,
        {
            "version": VERIFY_LOCAL_VERSION,
            "theorem": "solved_one",
            "variant": "wild_type",
            "status": "verified",
            "verified_at": "2026-03-06T00:00:00+00:00",
            "replay_verified": True,
            "candidate_compiled": True,
            "applied_tactics": ["trivial"],
            "replay_error": None,
            "candidate_error": None,
            "candidate_name": "solved_one__verify_local",
            "candidate_sha256": sha256_file(candidate_path),
            "inputs": {
                "history_sha256": sha256_file(history_path),
                "statement_sha256": hashlib.sha256(
                    "theorem {name} : True := by\n  sorry".encode("utf-8")
                ).hexdigest(),
                "solution_path_length": 1,
            },
        },
    )

    async def _unexpected_create(*args, **kwargs):
        raise AssertionError("LeanAdapter.create should not be called for a fresh cached report")

    monkeypatch.setattr("analysis.verify_run_local.LeanAdapter.create", _unexpected_create)

    report = verify_provider_run_local(ProviderRun(run_dir=run_dir, provider=None))

    assert report["counts"]["skipped_existing"] == 1
    assert report["counts"]["verified"] == 1
