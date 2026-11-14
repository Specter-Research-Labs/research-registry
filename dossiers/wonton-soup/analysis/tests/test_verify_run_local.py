from __future__ import annotations

import gzip
import json
from pathlib import Path

import duckdb
import pytest

from analysis.lake.db import ensure_schema, run_key_for_run_dir
from analysis.lake.verdicts import ingest_replay_verdicts
from analysis.logs import ProviderRun
from analysis.verify_run_local import VERDICTS_NAME, verify_provider_run_local
from corpus.lean.theorems import Theorem
from prover.dependencies import KernelCheck

STATEMENT = "theorem {name} : True := by\n  sorry"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _history(run_dir: Path, theorem: str, variant: str, tactic: str) -> None:
    _write_json(
        run_dir / theorem / f"{variant}_history.json",
        {"solution_path": [{"goal": "g0", "tactic": tactic}]},
    )


def _run(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "run"
    lean_project = tmp_path / "lean_project"
    lean_project.mkdir()
    _write_json(
        run_dir / "run_config.json",
        {
            "backend": "lean",
            "corpus_spec": "fixture",
            "corpus_meta": {"items_sha256": "abc"},
            "resolved": {"project_path": str(lean_project)},
        },
    )
    summary = {
        "theorems": [
            {
                "name": "archived",
                "wild_type": {"solved": True},
                "interventions": [
                    {"name": "block_simp", "solved": True},
                    {"name": "block_omega", "solved": False},
                ],
            },
            {
                "name": "checked",
                "wild_type": {"solved": False, "tree_solved": True},
                "interventions": [
                    {
                        "name": "block_premise_P",
                        "solved": False,
                        "tree_solved": True,
                        "blocked_premises": ["P"],
                    },
                ],
            },
            {"name": "unsolved", "wild_type": {"solved": False}, "interventions": []},
        ]
    }
    with gzip.open(run_dir / "summary.json.gz", "wt") as handle:
        json.dump(summary, handle)
    _history(run_dir, "archived", "wild_type", "trivial")
    _history(run_dir, "archived", "block_simp", "exact True.intro")
    _history(run_dir, "checked", "wild_type", "simp")
    _history(run_dir, "checked", "block_premise_P", "uses_P")
    return run_dir, lean_project


@pytest.fixture
def fake_adapter(monkeypatch):
    theorems = [Theorem(name, STATEMENT) for name in ("archived", "checked", "unsolved")]
    monkeypatch.setattr(
        "analysis.verify_run_local.load_corpus",
        lambda spec: (theorems, {"items_sha256": "abc"}, None),
    )
    calls: list[tuple[str, tuple[str, ...], frozenset[str]]] = []

    class _FakeAdapter:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def kernel_check(self, statement, solution_path, *, library_name, blocked_premises):
            tactics = tuple(step["tactic"] for step in solution_path)
            calls.append((statement, tactics, blocked_premises))
            if tactics == ("uses_P",):
                status, error, premises = "blocked_premise", "proof uses blocked premise P", ("P",)
            elif tactics == ("simp",):
                status, error, premises = "check_failed", "kernel rejected", ()
            else:
                status, error, premises = "checked", None, ("True.intro",)
            check = KernelCheck(
                status=status,
                error=error,
                tactics=tactics,
                term_hash=None,
                premises=premises,
                self_citation=None,
                blocked_hits=("P",) if status == "blocked_premise" else (),
            )
            return check, None

    async def _create(project_path):
        return _FakeAdapter()

    monkeypatch.setattr("analysis.verify_run_local.LeanAdapter.create", _create)
    return calls


def test_checks_every_closed_variant_and_writes_ingestable_verdicts(
    tmp_path: Path, fake_adapter
) -> None:
    run_dir, _ = _run(tmp_path)

    result = verify_provider_run_local(
        ProviderRun(run_dir=run_dir, provider=None),
        theorem_names=None,
        limit=None,
        lean_project=None,
    )

    assert [(t.theorem.name, t.variant) for t, _ in result.checks] == [
        ("archived", "wild_type"),
        ("archived", "block_simp"),
        ("checked", "wild_type"),
        ("checked", "block_premise_P"),
    ]
    assert fake_adapter[0][0] == "theorem archived_verify : True := by\n  sorry"
    assert fake_adapter[3][2] == frozenset({"P"})
    assert result.verdicts_path == run_dir / VERDICTS_NAME

    conn = duckdb.connect(str(tmp_path / "lake.duckdb"))
    ensure_schema(conn)
    assert ingest_replay_verdicts(conn, result.verdicts_path) == 4
    rows = conn.execute(
        "SELECT run_key, theorem, variant, replay_status, replay_error, premises "
        "FROM replay_verdict ORDER BY theorem, variant"
    ).fetchall()
    conn.close()
    run_key = run_key_for_run_dir(run_dir)
    assert rows == [
        (run_key, "archived", "block_simp", "checked", None, '["True.intro"]'),
        (run_key, "archived", "wild_type", "checked", None, '["True.intro"]'),
        (
            run_key,
            "checked",
            "block_premise_P",
            "blocked_premise",
            "proof uses blocked premise P",
            '["P"]',
        ),
        (run_key, "checked", "wild_type", "check_failed", "kernel rejected", "[]"),
    ]


def test_selection_filters_and_limits(tmp_path: Path, fake_adapter) -> None:
    run_dir, lean_project = _run(tmp_path)
    provider_run = ProviderRun(run_dir=run_dir, provider=None)

    limited = verify_provider_run_local(
        provider_run, theorem_names=None, limit=1, lean_project=lean_project
    )
    assert {t.theorem.name for t, _ in limited.checks} == {"archived"}

    named = verify_provider_run_local(
        provider_run, theorem_names=["checked"], limit=None, lean_project=lean_project
    )
    assert {t.theorem.name for t, _ in named.checks} == {"checked"}

    with pytest.raises(ValueError, match="not found in summary: missing"):
        verify_provider_run_local(
            provider_run, theorem_names=["missing"], limit=None, lean_project=lean_project
        )


def test_closed_tree_without_history_fails_loudly(tmp_path: Path, fake_adapter) -> None:
    run_dir, _ = _run(tmp_path)
    (run_dir / "archived" / "block_simp_history.json").unlink()

    with pytest.raises(FileNotFoundError, match="block_simp_history.json"):
        verify_provider_run_local(
            ProviderRun(run_dir=run_dir, provider=None),
            theorem_names=None,
            limit=None,
            lean_project=None,
        )


def test_changed_corpus_items_fail_loudly(tmp_path: Path, fake_adapter, monkeypatch) -> None:
    run_dir, _ = _run(tmp_path)
    monkeypatch.setattr(
        "analysis.verify_run_local.load_corpus", lambda spec: ([], {"items_sha256": "def"}, None)
    )

    with pytest.raises(ValueError, match="items changed since the run"):
        verify_provider_run_local(
            ProviderRun(run_dir=run_dir, provider=None),
            theorem_names=None,
            limit=None,
            lean_project=None,
        )
