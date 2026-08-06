import asyncio
import gzip
import json
from pathlib import Path

import pytest
from leantree.repl_adapter.interaction import LeanProcessException

import setup_lean
from corpus.lean.theorems import Intervention, Theorem
from orchestrator import lean as lean_mod
from orchestrator import lean_basin, lean_checkpoints, lean_reporting, lean_runner
from prover import ExplorationHistory, GoalCache, MCTSTree, ProofGraph
from prover.adapters.lean import LeanAdapter
from prover.goal_signature import GoalSignatureConfig


def test_ensure_mathlib_requirement_is_idempotent(tmp_path: Path) -> None:
    lakefile = tmp_path / "lakefile.toml"
    lakefile.write_text('name = "lean_project"\n', encoding="utf-8")

    setup_lean._ensure_mathlib_requirement(lakefile, "v4.25.0")
    first = lakefile.read_text(encoding="utf-8")

    setup_lean._ensure_mathlib_requirement(lakefile, "v4.25.0")
    second = lakefile.read_text(encoding="utf-8")

    assert first == second
    assert 'name = "mathlib"' in second
    assert 'rev = "v4.25.0"' in second


def test_assert_lean_project_ready_rejects_cold_mathlib(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "lean_project"
    (project / ".lake" / "packages" / "mathlib" / "Mathlib").mkdir(parents=True)
    repl_path = tmp_path / "repl"
    repl_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_mod, "_lean_repl_exe_path", lambda: repl_path)

    with pytest.raises(SystemExit):
        lean_mod._assert_lean_project_ready(project)

    out = capsys.readouterr().out
    assert "Lean project cache is cold or missing" in out
    assert "uv run python setup_lean.py" in out


def test_assert_lean_project_ready_accepts_warm_mathlib(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "lean_project"
    mathlib_root = (
        project / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib" / "lean" / "Mathlib"
    )
    mathlib_root.mkdir(parents=True)
    (mathlib_root / "Basic.olean").write_text("", encoding="utf-8")
    repl_path = tmp_path / "repl"
    repl_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_mod, "_lean_repl_exe_path", lambda: repl_path)

    assert lean_mod._assert_lean_project_ready(project) == project.resolve()


def test_open_mcts_trace_writer_materializes_spooled_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    spool_path = tmp_path / "spool" / "trace.jsonl"
    captured: dict[str, object] = {}

    class _FakeTraceWriter:
        def __init__(self, path: Path) -> None:
            captured["path"] = path

        def close(self) -> None:
            captured["closed"] = True

    def fake_materialize_spooled_file(*, spool_path: Path, final_path: Path, logger) -> None:
        captured["spool_path"] = spool_path
        captured["final_path"] = final_path
        captured["logger_name"] = logger.name

    monkeypatch.setattr(lean_mod, "_io_spooling_enabled", lambda: True)
    monkeypatch.setattr(
        lean_mod,
        "_io_spool_path",
        lambda *, log_dir, relpath: spool_path,
    )
    monkeypatch.setattr(lean_mod, "MCTSTraceWriter", _FakeTraceWriter)
    monkeypatch.setattr(lean_mod, "_materialize_spooled_file", fake_materialize_spooled_file)

    with lean_mod._open_mcts_trace_writer(
        enabled=True,
        log_dir=log_dir,
        theorem_name="t1",
        filename="wild_type_mcts_trace.jsonl",
    ) as trace:
        assert isinstance(trace, _FakeTraceWriter)

    assert captured["path"] == spool_path
    assert captured["closed"] is True
    assert captured["spool_path"] == spool_path
    assert captured["final_path"] == log_dir / "t1" / "wild_type_mcts_trace.jsonl"
    assert captured["logger_name"] == "orchestrator.lean"


def test_write_run_result_artifacts_writes_core_outputs(tmp_path: Path) -> None:
    theorem = Theorem("t1", "theorem {name} : True := by trivial")
    theorem_result = _minimal_theorem_result(theorem)
    theorem_dir = tmp_path / theorem.name
    theorem_dir.mkdir(parents=True)

    metrics = lean_mod._write_run_result_artifacts(
        theorem_dir,
        stem="wild_type",
        run_result=theorem_result.wild_type,
        include_root_goal_sigs=True,
    )

    assert (theorem_dir / "wild_type_graph.json").exists()
    assert (theorem_dir / "wild_type_history.json").exists()
    assert (theorem_dir / "wild_type_mcts_tree.json").exists()
    assert (theorem_dir / "wild_type_metrics.json").exists()
    assert metrics["trajectory"]["total_iterations"] == 0
    assert metrics["root_goal_sigs"] == []
    assert metrics["tactic_fingerprint"] is None


def test_save_results_writes_intervention_comparison_payloads(tmp_path: Path) -> None:
    theorem = Theorem("t1", "theorem {name} : True := by trivial")
    theorem_result = _minimal_theorem_result(theorem)
    intervention_run = lean_mod.RunResult(
        solved=False,
        stats={},
        graph=ProofGraph.for_search_trace(backend="lean"),
        history=ExplorationHistory.create(theorem.name),
        mcts_tree=MCTSTree.create(f"{theorem.name}:int-root", "True"),
    )
    theorem_result.interventions.append(
        lean_mod.InterventionResult(
            intervention=Intervention(name="block_intro", blocked={"intro"}),
            wild_type=theorem_result.wild_type,
            intervention_run=intervention_run,
            ged=0.0,
        )
    )

    lean_mod.save_results(
        tmp_path,
        [theorem_result],
        crashed=[],
        goal_sig_config=GoalSignatureConfig(scheme="text"),
    )

    comparison_path = tmp_path / theorem.name / "block_intro_comparison.json"
    summary_path = tmp_path / "summary.json.gz"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    with gzip.open(summary_path, "rt") as handle:
        summary = json.load(handle)

    assert comparison["ged_search_graph"]["value"] == 0.0
    assert comparison["goal_novelty"]["valid"] is False
    assert comparison["solution_path_soft_distance"]["dp_cells"] == 0
    theorem_summary = summary["theorems"][0]
    intervention_summary = theorem_summary["interventions"][0]
    assert intervention_summary["name"] == "block_intro"
    assert intervention_summary["ged_search_graph"]["value"] == 0.0
    assert summary["aggregates"]["theorem_count"] == 1
    assert summary["aggregates"]["wild_type_solve_rate"] == 0
    assert summary["aggregates"]["intervention_count"] == 1
    assert summary["aggregates"]["intervention_solve_rate"] == 0
    assert summary["aggregates"]["run_stats"] == {
        "theorem_total": 1,
        "crashed": 0,
        "wild_solved": 0,
        "wild_aborted": 0,
        "intervention_total": 1,
        "intervention_solved": 0,
        "avg_iters": 0,
    }
    assert summary["aggregates"]["ged_validity"] == {
        "ged_search_graph": {"valid": 1, "invalid": 0},
        "ged_search_graph_soft": {"valid": 0, "invalid": 1},
        "ged_proof_graph": {"valid": 0, "invalid": 0},
        "ged_trace_graph": {"valid": 0, "invalid": 0},
    }


def test_save_results_marks_missing_ged_invalid(tmp_path: Path) -> None:
    theorem = Theorem("t1", "theorem {name} : True := by trivial")
    theorem_result = _minimal_theorem_result(theorem)
    intervention_run = lean_mod.RunResult(
        solved=True,
        stats={},
        graph=ProofGraph.for_search_trace(backend="lean"),
        history=ExplorationHistory.create(theorem.name),
        mcts_tree=MCTSTree.create(f"{theorem.name}:int-root", "True"),
    )
    theorem_result.interventions.append(
        lean_mod.InterventionResult(
            intervention=Intervention(name="block_intro", blocked={"intro"}),
            wild_type=theorem_result.wild_type,
            intervention_run=intervention_run,
            ged=None,
        )
    )

    lean_mod.save_results(
        tmp_path,
        [theorem_result],
        crashed=[],
        goal_sig_config=GoalSignatureConfig(scheme="text"),
    )

    comparison = json.loads(
        (tmp_path / theorem.name / "block_intro_comparison.json").read_text(encoding="utf-8")
    )
    with gzip.open(tmp_path / "summary.json.gz", "rt") as handle:
        summary = json.load(handle)

    assert comparison["ged_search_graph"] == {
        "value": None,
        "normalized": None,
        "valid": False,
        "validity_notes": [],
        "trace_source": "mcts",
        "trace_completeness": "full",
    }
    assert summary["aggregates"]["ged_validity"]["ged_search_graph"] == {
        "valid": 0,
        "invalid": 1,
    }


def test_summarize_from_summary_prefers_saved_run_stats() -> None:
    summary = {
        "theorems": [{"wild_type": {"solved": False, "metrics": {"trajectory": {}}}}],
        "crashed": [],
        "aggregates": {
            "run_stats": {
                "theorem_total": 7,
                "crashed": 2,
                "wild_solved": 3,
                "wild_aborted": 1,
                "intervention_total": 11,
                "intervention_solved": 5,
                "avg_iters": 42,
            }
        },
    }

    assert lean_reporting._summarize_from_summary(summary) == summary["aggregates"]["run_stats"]


def test_list_theorem_dirs_skips_hidden_and_non_dirs(tmp_path: Path) -> None:
    visible_a = tmp_path / "a"
    visible_b = tmp_path / "b"
    hidden = tmp_path / ".hidden"
    file_path = tmp_path / "note.txt"
    visible_a.mkdir()
    visible_b.mkdir()
    hidden.mkdir()
    file_path.write_text("x", encoding="utf-8")

    assert lean_reporting._list_theorem_dirs(tmp_path) == [visible_a, visible_b]


def test_run_post_analysis_reuses_filtered_theorem_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import analysis.corpus as corpus_mod
    import analysis.failures as failures_mod

    theorem_a = tmp_path / "a"
    theorem_b = tmp_path / "b"
    theorem_a.mkdir()
    theorem_b.mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "note.txt").write_text("ignored", encoding="utf-8")

    failure_calls: list[Path] = []
    analysis_calls: list[Path] = []

    monkeypatch.setattr(
        failures_mod,
        "analyze_failed_theorem",
        lambda theorem_dir: failure_calls.append(theorem_dir) or {"name": theorem_dir.name},
    )
    monkeypatch.setattr(
        failures_mod,
        "generate_report",
        lambda failures, log_dir: {
            "failures": [item["name"] for item in failures],
            "log_dir": str(log_dir),
        },
    )
    monkeypatch.setattr(
        corpus_mod,
        "analyze_theorem",
        lambda theorem_dir: analysis_calls.append(theorem_dir) or [{"name": theorem_dir.name}],
    )
    monkeypatch.setattr(
        corpus_mod,
        "generate_report",
        lambda analyses, log_dir: {
            "analyses": [item["name"] for item in analyses],
            "log_dir": str(log_dir),
        },
    )

    lean_reporting.run_post_analysis(tmp_path)

    assert failure_calls == [theorem_a, theorem_b]
    assert analysis_calls == [theorem_a, theorem_b]
    assert json.loads((tmp_path / "failure_analysis.json").read_text(encoding="utf-8")) == {
        "failures": ["a", "b"],
        "log_dir": str(tmp_path),
    }
    assert json.loads((tmp_path / "analysis_report.json").read_text(encoding="utf-8")) == {
        "analyses": ["a", "b"],
        "log_dir": str(tmp_path),
    }


class _TimeoutEnvContext:
    def __init__(self, env: object) -> None:
        self._env = env

    async def __aenter__(self) -> object:
        return self._env

    async def __aexit__(self, *_args: object) -> None:
        return None


class _TimeoutProject:
    def __init__(self, env: object) -> None:
        self._env = env

    def environment(self) -> _TimeoutEnvContext:
        return _TimeoutEnvContext(self._env)


class _TimeoutEnv:
    async def send_command_async(self, _command: str) -> dict[str, object]:
        return {}

    async def __aexit__(self, *_args: object) -> None:
        return None


def test_lean_adapter_timeout_message_points_to_flake_and_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    env = _TimeoutEnv()
    adapter = LeanAdapter(project=_TimeoutProject(env))

    async def _raise_timeout(awaitable: object, timeout: float) -> object:
        if hasattr(awaitable, "close"):
            awaitable.close()
        del timeout
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)

    with pytest.raises(LeanProcessException) as excinfo:
        asyncio.run(adapter.__aenter__())

    message = str(excinfo.value)
    assert "nix develop .#wonton-soup" in message
    assert "uv sync --python" in message
    assert "uv run python setup_lean.py" in message


class _StartupFailProvider:
    def describe(self) -> str:
        return "startup-fail-provider"


class _NoopAdapter:
    async def __aenter__(self) -> "_NoopAdapter":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _CountingAdapter(_NoopAdapter):
    def __init__(self, name: str, events: list[tuple[str, str]]) -> None:
        self.name = name
        self._events = events

    async def __aenter__(self) -> "_CountingAdapter":
        self._events.append(("enter", self.name))
        return self

    async def __aexit__(self, *_args: object) -> None:
        self._events.append(("exit", self.name))
        return None


def _minimal_theorem_result(theorem: Theorem, *, search_seed: int | None = None):
    graph = ProofGraph.for_search_trace(backend="lean")
    history = ExplorationHistory.create(theorem.name)
    tree = MCTSTree.create(f"{theorem.name}:root", "True")
    return lean_mod.TheoremResult(
        theorem=theorem,
        wild_type=lean_mod.RunResult(
            solved=False,
            stats={},
            graph=graph,
            history=history,
            mcts_tree=tree,
        ),
        search_seed=search_seed,
    )


def _write_resume_goal_cache(path: Path) -> GoalCache:
    goal_cache = GoalCache(GoalSignatureConfig(scheme="text"))
    goal_cache.add_goal(
        mvar_id="resume-mvar",
        type_str="True",
        type_expr=None,
        hyp_types=[],
        hyp_exprs=[],
    )
    goal_cache.record_outcome("resume-mvar", 3, True)
    goal_cache.save(path)
    return goal_cache


def _patch_corpus_runtime(
    monkeypatch: pytest.MonkeyPatch,
    logs_dir: Path,
    theorems: list[Theorem],
) -> None:
    monkeypatch.setattr(lean_mod, "resolve_logs_dir", lambda: logs_dir)
    monkeypatch.setattr(
        lean_mod,
        "load_corpus",
        lambda _corpus: (theorems, {"name": "test", "total_theorems": len(theorems)}, None),
    )
    monkeypatch.setattr(
        lean_mod,
        "create_provider",
        lambda *_args, **_kwargs: _StartupFailProvider(),
    )


def _patch_noop_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _create_noop_adapter(_project_path: Path | str) -> _NoopAdapter:
        return _NoopAdapter()

    monkeypatch.setattr(lean_mod.LeanAdapter, "create", staticmethod(_create_noop_adapter))


def _patch_reporting_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lean_reporting, "generate_report", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(lean_reporting, "_compute_run_stats", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(lean_reporting, "_format_run_summary", lambda **_kwargs: "summary")
    monkeypatch.setattr(
        lean_reporting,
        "_write_postprocess_metrics",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        lean_mod,
        "_build_run_capabilities",
        lambda *_args, **_kwargs: {"has_goal_cache": True},
    )


def _capture_saved_results(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    saved: dict[str, object] = {}
    monkeypatch.setattr(
        lean_mod,
        "save_results",
        lambda log_dir, results, crashed, goal_sig_config: saved.update(
            {
                "log_dir": log_dir,
                "results": list(results),
                "crashed": list(crashed),
                "goal_sig_config": goal_sig_config,
            }
        ),
    )
    return saved


def _run_corpus_for_test(project_path: Path, run_id: str, **overrides):
    kwargs = {
        "project_path": str(project_path),
        "budget_tiers": [10],
        "provider_name": "heuristic",
        "corpus": "test",
        "run_id": run_id,
        "plain": True,
        "write_latest_run": False,
        "no_sync": True,
    }
    kwargs.update(overrides)
    return asyncio.run(lean_mod.run_corpus(**kwargs))


@pytest.mark.parametrize(
    ("num_workers", "basin_seeds"),
    [
        (1, None),
        (2, None),
        (1, 2),
        (2, 2),
    ],
)
def test_run_corpus_startup_failure_finalizes_run_status_without_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    num_workers: int,
    basin_seeds: int | None,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t1", "theorem {name} : True := by sorry")

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem])

    async def _fail_create(_project_path: Path | str) -> LeanAdapter:
        raise LeanProcessException("startup failed")

    monkeypatch.setattr(lean_mod.LeanAdapter, "create", staticmethod(_fail_create))

    with pytest.raises(LeanProcessException, match="startup failed"):
        _run_corpus_for_test(
            project_path,
            "corpus-startup-fail",
            num_workers=num_workers,
            basin_seeds=basin_seeds,
        )

    run_dir = logs_dir / "corpus-startup-fail"
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "failed"
    assert status_payload["partial_results"] is False
    assert status_payload["completed_at"] is not None
    assert status_payload["error"] == "startup failed"
    assert status_payload["error_summary"] == "startup failed"
    assert (run_dir / "summary.json.gz").exists() is False


def test_run_corpus_basin_failure_marks_partial_results_after_completed_theorem(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem1 = Theorem("t1", "theorem {name} : True := by trivial")
    theorem2 = Theorem("t2", "theorem {name} : True := by trivial")

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem1, theorem2])
    _patch_noop_adapter(monkeypatch)
    monkeypatch.setattr(
        lean_mod,
        "_build_run_capabilities",
        lambda *_args, **_kwargs: {"has_goal_cache": False},
    )

    class _FakeBasinResult:
        solve_rate = 0.5
        unique_structures = 1
        dominant_structure_frequency = 1.0

        def serialize(self) -> dict[str, object]:
            return {"seed_results": [], "solve_rate": self.solve_rate}

    calls: list[str] = []

    async def _fake_run_basin_analysis(*, theorem, **_kwargs):
        calls.append(theorem.name)
        if theorem.name == "t1":
            return _FakeBasinResult()
        raise RuntimeError("basin boom")

    monkeypatch.setattr(lean_basin, "run_basin_analysis", _fake_run_basin_analysis)

    with pytest.raises(RuntimeError, match="basin boom"):
        _run_corpus_for_test(project_path, "corpus-basin-fail", basin_seeds=2)

    run_dir = logs_dir / "corpus-basin-fail"
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert calls == ["t1", "t2"]
    assert status_payload["status"] == "failed"
    assert status_payload["partial_results"] is True
    assert (run_dir / "t1" / "basin_analysis.json").exists()
    assert (run_dir / "summary.json.gz").exists() is False


def test_run_corpus_selection_error_uses_failed_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t1", "theorem {name} : True := by sorry")

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem])

    result = _run_corpus_for_test(
        project_path,
        "corpus-selection-fail",
        theorem_name="missing_theorem",
    )

    assert result == []
    run_dir = logs_dir / "corpus-selection-fail"
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "failed"
    assert status_payload["partial_results"] is False
    assert status_payload["completed_at"] is not None
    assert status_payload["error"] == "Theorem 'missing_theorem' not found in corpus 'test'"
    assert status_payload["error_summary"] == "Theorem 'missing_theorem' not found in corpus 'test'"
    assert (run_dir / "summary.json.gz").exists() is False


def test_run_corpus_writes_postprocess_metrics_for_completed_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t1", "theorem {name} : True := by trivial")

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem])
    _patch_noop_adapter(monkeypatch)
    results_saved = _capture_saved_results(monkeypatch)

    async def _fake_run_theorem(_adapter, theorem, *_args, **_kwargs):
        return _minimal_theorem_result(theorem)

    monkeypatch.setattr(lean_runner, "run_theorem", _fake_run_theorem)
    _patch_reporting_stubs(monkeypatch)
    postprocess_calls: list[Path] = []
    callback_statuses: list[dict[str, object]] = []
    monkeypatch.setattr(
        lean_reporting,
        "_write_postprocess_metrics",
        lambda log_dir, *, progress_cb=None: (
            postprocess_calls.append(log_dir),
            progress_cb is not None
            and progress_cb(
                {
                    "event": "postprocess_progress",
                    "run_dir": str(log_dir),
                    "theorem_idx": 1,
                    "theorems_total": 1,
                    "theorem": "t1",
                    "updated_interventions": 2,
                    "skipped_interventions": 0,
                }
            ),
            callback_statuses.append(
                json.loads((log_dir / "run_status.json").read_text(encoding="utf-8"))
            ),
        )[-1],
    )

    result = _run_corpus_for_test(project_path, "corpus-postprocess", run_analysis=False)

    run_dir = logs_dir / "corpus-postprocess"
    assert len(result) == 1
    assert results_saved["log_dir"] == run_dir
    assert postprocess_calls == [run_dir]
    assert callback_statuses
    callback_current = callback_statuses[0]["progress"]["current"]
    assert callback_current["phase"] == "postprocess"
    assert callback_current["theorem"] == "t1"
    assert callback_current["stage_label"] == "theorems"
    assert callback_current["stage_step"] == 1
    assert callback_current["stage_total"] == 1
    assert callback_current["stage_note"] == "updated=2 skipped=0"
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"


def test_run_corpus_restarts_adapter_after_process_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem1 = Theorem("t1", "theorem {name} : True := by trivial")
    theorem2 = Theorem("t2", "theorem {name} : True := by trivial")
    adapter_events: list[tuple[str, str]] = []
    create_calls: list[str] = []
    restart_messages: list[str | None] = []

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem1, theorem2])
    saved = _capture_saved_results(monkeypatch)

    async def _create_counting_adapter(_project_path: Path | str) -> _CountingAdapter:
        name = f"adapter-{len(create_calls)}"
        create_calls.append(name)
        return _CountingAdapter(name, adapter_events)

    monkeypatch.setattr(lean_mod.LeanAdapter, "create", staticmethod(_create_counting_adapter))
    monkeypatch.setattr(
        lean_mod.CorpusProgress,
        "record_repl_restart",
        lambda self, error=None: restart_messages.append(error),
    )

    calls: list[str] = []

    async def _fake_run_theorem(_adapter, theorem, *_args, **_kwargs):
        calls.append(theorem.name)
        if theorem.name == "t1":
            raise LeanProcessException("worker crashed")
        return _minimal_theorem_result(theorem, search_seed=22)

    monkeypatch.setattr(lean_runner, "run_theorem", _fake_run_theorem)
    _patch_reporting_stubs(monkeypatch)

    result = _run_corpus_for_test(project_path, "corpus-worker-restart", run_analysis=False)

    run_dir = logs_dir / "corpus-worker-restart"
    assert calls == ["t1", "t2"]
    assert create_calls == ["adapter-0", "adapter-1"]
    assert restart_messages == ["worker crashed"]
    assert [item.theorem.name for item in result] == ["t2"]
    assert [item.theorem.name for item in saved["results"]] == ["t2"]
    assert len(saved["crashed"]) == 1
    assert adapter_events == [
        ("enter", "adapter-0"),
        ("exit", "adapter-0"),
        ("enter", "adapter-1"),
        ("exit", "adapter-1"),
    ]
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"


def test_run_corpus_resume_skips_checkpointed_theorems(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem1 = Theorem("t1", "theorem {name} : True := by trivial")
    theorem2 = Theorem("t2", "theorem {name} : True := by trivial")
    run_dir = logs_dir / "corpus-resume-normal"
    run_dir.mkdir(parents=True)

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem1, theorem2])
    _patch_noop_adapter(monkeypatch)
    _patch_reporting_stubs(monkeypatch)
    saved = _capture_saved_results(monkeypatch)
    monkeypatch.setattr(lean_mod, "sync_logs_from_remote", lambda *_args, **_kwargs: None)

    checkpoint_result = _minimal_theorem_result(theorem1, search_seed=11)
    lean_checkpoints._write_theorem_result_checkpoint(run_dir, checkpoint_result)

    called: list[str] = []

    async def _fake_run_theorem(_adapter, theorem, *_args, **_kwargs):
        called.append(theorem.name)
        return _minimal_theorem_result(theorem, search_seed=22)

    monkeypatch.setattr(lean_runner, "run_theorem", _fake_run_theorem)

    result = _run_corpus_for_test(
        project_path,
        "corpus-resume-normal",
        run_analysis=False,
        resume=True,
    )

    assert called == ["t2"]
    assert [item.theorem.name for item in result] == ["t1", "t2"]
    assert [item.theorem.name for item in saved["results"]] == ["t1", "t2"]
    assert (run_dir / "t2" / lean_checkpoints.THEOREM_RESULT_CHECKPOINT_NAME).exists()
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"


def test_run_corpus_resume_reuses_saved_selection_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem1 = Theorem("t1", "theorem {name} : True := by trivial")
    theorem2 = Theorem("t2", "theorem {name} : True := by trivial")
    theorem3 = Theorem("t3", "theorem {name} : True := by trivial")
    run_dir = logs_dir / "corpus-resume-frozen-selection"
    run_dir.mkdir(parents=True)

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem3, theorem2, theorem1])
    _patch_noop_adapter(monkeypatch)
    _patch_reporting_stubs(monkeypatch)
    monkeypatch.setattr(lean_mod, "save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lean_mod, "sync_logs_from_remote", lambda *_args, **_kwargs: None)

    lean_mod._write_run_config(
        run_dir,
        {
            "corpus_spec": "test",
            "theorem_selection": {
                "selected_theorems": ["t1", "t2"],
                "selection_seed": 123,
            },
        },
    )
    lean_checkpoints._write_theorem_result_checkpoint(run_dir, _minimal_theorem_result(theorem1))

    called: list[str] = []

    async def _fake_run_theorem(_adapter, theorem, *_args, **_kwargs):
        called.append(theorem.name)
        return _minimal_theorem_result(theorem, search_seed=22)

    monkeypatch.setattr(lean_runner, "run_theorem", _fake_run_theorem)

    result = _run_corpus_for_test(
        project_path,
        "corpus-resume-frozen-selection",
        run_analysis=False,
        resume=True,
    )

    assert called == ["t2"]
    assert [item.theorem.name for item in result] == ["t1", "t2"]


def test_run_corpus_resume_completed_selection_skips_lean_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t1", "theorem {name} : True := by trivial")
    run_dir = logs_dir / "corpus-resume-complete"
    run_dir.mkdir(parents=True)

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem])
    _patch_reporting_stubs(monkeypatch)
    monkeypatch.setattr(lean_mod, "save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lean_mod, "sync_logs_from_remote", lambda *_args, **_kwargs: None)

    create_calls: list[Path | str] = []

    async def _unexpected_create(project: Path | str) -> LeanAdapter:
        create_calls.append(project)
        raise AssertionError("LeanAdapter.create should not run when resume is complete")

    monkeypatch.setattr(lean_mod.LeanAdapter, "create", staticmethod(_unexpected_create))

    lean_checkpoints._write_theorem_result_checkpoint(run_dir, _minimal_theorem_result(theorem))

    result = _run_corpus_for_test(
        project_path,
        "corpus-resume-complete",
        run_analysis=False,
        resume=True,
    )

    assert create_calls == []
    assert [item.theorem.name for item in result] == ["t1"]
    status_payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"


def test_run_corpus_resume_preserves_existing_goal_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t1", "theorem {name} : True := by trivial")
    run_dir = logs_dir / "corpus-resume-goal-cache"
    run_dir.mkdir(parents=True)

    _patch_corpus_runtime(monkeypatch, logs_dir, [theorem])
    _patch_reporting_stubs(monkeypatch)
    monkeypatch.setattr(lean_mod, "save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lean_mod, "sync_logs_from_remote", lambda *_args, **_kwargs: None)

    async def _unexpected_create(_project: Path | str) -> LeanAdapter:
        raise AssertionError("LeanAdapter.create should not run when resume is complete")

    monkeypatch.setattr(lean_mod.LeanAdapter, "create", staticmethod(_unexpected_create))

    lean_checkpoints._write_theorem_result_checkpoint(run_dir, _minimal_theorem_result(theorem))
    original_goal_cache = _write_resume_goal_cache(run_dir / "goal_cache.json")

    _run_corpus_for_test(
        project_path,
        "corpus-resume-goal-cache",
        run_analysis=False,
        resume=True,
    )

    saved_goal_cache = GoalCache.load(run_dir / "goal_cache.json")
    assert saved_goal_cache.mvar_to_sig == original_goal_cache.mvar_to_sig
    assert tuple(saved_goal_cache.entries) == tuple(original_goal_cache.entries)
    sig = saved_goal_cache.get_sig("resume-mvar")
    assert sig is not None
    assert saved_goal_cache.entries[sig].occurrences["resume-mvar"].outcomes == {3: [True]}
