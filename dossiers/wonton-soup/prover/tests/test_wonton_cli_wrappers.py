from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
import typer


def _capture_keyword_calls(monkeypatch, owner: object, attr: str) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(owner, attr, fake)
    return calls


def test_lean_run_forwards_defaults_sync_and_extended_options(monkeypatch) -> None:
    import wonton

    calls = _capture_keyword_calls(monkeypatch, wonton, "_run_lean_command")

    wonton.lean_run(sync=False)
    wonton.lean_run(
        sync=True,
        deepseek_model_path="/tmp/deepseek.gguf",
        search_seed=17,
        no_solution_artifacts=True,
        baseline_solved_only=True,
        intervention_name=["cut"],
        extra_intervention=["nocases:cases"],
    )

    defaults, extended = calls
    assert defaults["no_sync"] is True
    assert defaults["mode"] == "dev"
    assert defaults["mcts_mode"] == "centralized"
    assert defaults["workers"] == 1
    assert defaults["offset"] == 0
    assert defaults["goal_sig"] == "ast"
    assert defaults["tactic_ranker"] == "none"
    assert defaults["tactic_ranker_alpha"] == 1.0
    optioninfo = typer.models.OptionInfo
    assert not any(isinstance(v, optioninfo) for v in defaults.values())

    assert extended["no_sync"] is False
    assert extended["deepseek_model_path"] == "/tmp/deepseek.gguf"
    assert extended["search_seed"] == 17
    assert extended["no_solution_artifacts"] is True
    assert extended["baseline_solved_only"] is True
    assert extended["intervention_name"] == ["cut"]
    assert extended["extra_intervention"] == ["nocases:cases"]


def test_lean_basin_forces_basin_mode_without_interventions(monkeypatch) -> None:
    import wonton

    calls = _capture_keyword_calls(monkeypatch, wonton, "_run_lean_command")

    wonton.lean_basin(
        seeds=7,
        blind=True,
        mcts_expansion_policy="first-success",
        sync=False,
    )

    captured = calls[0]
    assert captured["basin_seeds"] == 7
    assert captured["basin_blind"] is True
    assert captured["wild_only"] is False
    assert captured["with_interventions"] is False
    assert captured["analysis"] is False
    assert captured["mcts_expansion_policy"] == "first-success"
    assert captured["no_sync"] is True


def test_lean_suite_runs_main_and_basin_with_expected_overrides(monkeypatch) -> None:
    import wonton

    calls = _capture_keyword_calls(monkeypatch, wonton, "_run_lean_command")

    wonton.lean_suite(seeds=3, blind=True, run_id="suite-a", sync=False, analysis=False)

    assert len(calls) == 2
    assert calls[0]["run_id"] == "suite-a/run"
    assert calls[0]["basin_seeds"] is None
    assert calls[0]["analysis"] is False
    assert calls[0]["no_sync"] is True

    assert calls[1]["run_id"] == "suite-a/basin-3"
    assert calls[1]["basin_seeds"] == 3
    assert calls[1]["basin_blind"] is True
    assert calls[1]["wild_only"] is False
    assert calls[1]["with_interventions"] is False
    assert calls[1]["analysis"] is False


def test_lean_run_wrapper_leaves_validation_to_runtime(monkeypatch) -> None:
    import wonton

    captured: dict[str, object] = {}

    def fake_run_lean_backend(args):
        captured["sample"] = args.sample
        captured["seed"] = args.seed

    monkeypatch.setattr(wonton, "_run_lean_backend", fake_run_lean_backend)

    wonton.lean_run(sample=5, seed=None, sync=False)

    assert captured == {"sample": 5, "seed": None}


def test_run_lean_normalizes_typer_style_args_before_dispatch(monkeypatch) -> None:
    import os

    import wonton
    from orchestrator import lean as lean_runtime

    captured: dict[str, object] = {}

    def fake_run_from_args(args, *, parser_error=None):
        captured["parser_error"] = parser_error
        captured["theorem"] = args.theorem
        captured["wild_only"] = args.wild_only
        captured["trace_mcts"] = args.trace_mcts
        captured["goal_sig"] = args.goal_sig
        captured["plain"] = args.plain

    monkeypatch.setattr(lean_runtime, "run_from_args", fake_run_from_args)
    monkeypatch.delenv("LEAN_PROJECT_PATH", raising=False)

    args = SimpleNamespace(
        lean_project="/tmp/lean-project",
        watch=False,
        run_id="corpus-demo",
        theorem=["demo_theorem"],
        wild_only=False,
        with_interventions=True,
        trace_mcts=False,
        no_trace_mcts=True,
        goal_sig=None,
        agent=True,
        plain=False,
    )

    wonton._run_lean(args)

    assert os.environ["LEAN_PROJECT_PATH"] == "/tmp/lean-project"
    assert captured == {
        "parser_error": None,
        "theorem": "demo_theorem",
        "wild_only": False,
        "trace_mcts": False,
        "goal_sig": "ast",
        "plain": True,
    }


def test_run_external_corpus_uses_progress_ui(monkeypatch, tmp_path) -> None:
    import wonton

    log_dir = tmp_path / "logs"
    progress_token = object()
    captured: dict[str, object] = {"closed": False}

    def fake_build_external_progress_ui(enabled: bool):
        captured["enabled"] = enabled

        def close() -> None:
            captured["closed"] = True

        return progress_token, close

    monkeypatch.setattr(wonton, "_build_external_progress_ui", fake_build_external_progress_ui)

    progress_values: list[object | None] = []
    args = SimpleNamespace(agent=False, plain=False)

    def run_batch(progress_cb):
        progress_values.append(progress_cb)

    result = wonton._run_external_corpus(args, log_dir=log_dir, run_batch=run_batch)

    assert result == log_dir
    assert captured["enabled"] is True
    assert captured["closed"] is True
    assert progress_values == [progress_token]


def test_run_sets_default_coq_stdlib_log_dir(monkeypatch, tmp_path) -> None:
    import wonton

    captured: dict[str, object] = {}
    expected_log_dir = tmp_path / "coq-stdlib"

    def fake_default_log_dir(label: str):
        captured["label"] = label
        return expected_log_dir

    def fake_run_coq(args):
        captured["log_dir"] = args.log_dir
        return Path(args.log_dir)

    monkeypatch.setattr(wonton, "_validate_backend_args", lambda args: None)
    monkeypatch.setattr(wonton, "_default_log_dir", fake_default_log_dir)
    monkeypatch.setattr(wonton, "_run_coq", fake_run_coq)

    wonton.run(backend=wonton.Backend.coq, coq_mode=wonton.CoqMode.stdlib, agent=True)

    assert captured["label"] == "coq-stdlib"
    assert captured["log_dir"] == str(expected_log_dir)


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_errors"),
    [
        (None, "completed", []),
        (RuntimeError("boom"), "failed", ["boom"]),
    ],
)
def test_run_emits_external_agent_lifecycle_events(
    monkeypatch,
    tmp_path,
    failure: RuntimeError | None,
    expected_status: str,
    expected_errors: list[str],
) -> None:
    import wonton

    expected_log_dir = tmp_path / "coq-run"
    events: list[dict[str, object]] = []

    monkeypatch.setattr(wonton, "_validate_backend_args", lambda args: None)
    monkeypatch.setattr(wonton, "_emit_agent_event", events.append)
    monkeypatch.setattr(wonton, "_default_log_dir", lambda _label: expected_log_dir)

    def fake_run(args):
        if failure is not None:
            raise failure
        return Path(args.log_dir)

    monkeypatch.setattr(wonton, "_run_coq", fake_run)

    if failure is None:
        wonton.run(backend=wonton.Backend.coq, agent=True)
    else:
        with pytest.raises(RuntimeError, match=str(failure)):
            wonton.run(backend=wonton.Backend.coq, agent=True)

    assert events[0] == {"event": "start", "backend": "coq", "log_dir": str(expected_log_dir)}
    end_event = {
        "event": "end",
        "status": expected_status,
        "errors": expected_errors,
        "backend": "coq",
        "log_dir": str(expected_log_dir),
    }
    if failure is None:
        end_event["summary_path"] = str(expected_log_dir / "summary.json.gz")
    assert events[1] == end_event


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("gpt-5", "provider=gpt-5"),
        ("", "provider=single"),
        (None, "provider=single"),
    ],
)
def test_provider_label_handles_missing_provider(provider: object, expected: str) -> None:
    import wonton

    assert wonton._provider_label(provider) == expected


def test_resolve_artifact_output_root_prefers_explicit_path(monkeypatch, tmp_path) -> None:
    import analysis.logs as logs_mod
    import wonton

    monkeypatch.setattr(logs_mod, "resolve_artifacts_dir", lambda: tmp_path / "artifacts")

    assert wonton._resolve_artifact_output_root(None, "learning") == (
        tmp_path / "artifacts" / "learning"
    )
    assert wonton._resolve_artifact_output_root(str(tmp_path / "custom"), "learning") == (
        tmp_path / "custom"
    )


def test_emit_provider_results_formats_output(capsys) -> None:
    import wonton

    results = [
        SimpleNamespace(provider="p1", rows_written=3, dataset_path=Path("/tmp/d1")),
        SimpleNamespace(provider=None, rows_written=4, dataset_path=Path("/tmp/d2")),
    ]

    wonton._emit_provider_results(
        results,
        lambda result: f"rows={result.rows_written} -> {result.dataset_path}",
    )

    out = capsys.readouterr().out
    assert "provider=p1: rows=3 -> /tmp/d1" in out
    assert "provider=single: rows=4 -> /tmp/d2" in out


def test_emit_built_corpus_prints_footer_and_syncs(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    sync_calls: list[tuple[list[Path], str]] = []
    built = SimpleNamespace(
        build_dir=tmp_path / "corpus-build",
        ref=lambda: "lean:test@v1",
    )

    monkeypatch.setattr(
        wonton,
        "_auto_sync_paths",
        lambda paths, *, reason: sync_calls.append((paths, reason)),
    )

    wonton._emit_built_corpus(
        built,
        sync=True,
        sync_reason="corpus-build-test",
        extra_lines=["extra detail"],
    )

    out = capsys.readouterr().out
    assert "Built: lean:test@v1" in out
    assert f"Dir: {built.build_dir}" in out
    assert "extra detail" in out
    assert sync_calls == [([built.build_dir], "corpus-build-test")]


def test_lean_1000_plus_manifest_lines_extracts_identifier_summary(tmp_path) -> None:
    import wonton

    build_dir = tmp_path / "build"
    build_dir.mkdir(parents=True)
    (build_dir / "manifest.json").write_text(
        json.dumps(
            {
                "build_config": {
                    "identifier_requested_count": 5,
                    "identifier_resolved_count": 4,
                    "identifier_unresolved_count": 1,
                    "identifier_unresolved_preview": ["foo", "", None, "bar"],
                }
            }
        ),
        encoding="utf-8",
    )

    lines = wonton._lean_1000_plus_manifest_lines(build_dir)

    assert lines == [
        "Identifiers: requested=5, resolved=4, unresolved=1",
        "Unresolved preview: foo, bar",
    ]


def test_emit_validation_result_prints_and_syncs(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    validation_path = tmp_path / "validation.json"
    derived_dir = tmp_path / "derived"
    sync_calls: list[tuple[list[Path], str]] = []

    monkeypatch.setattr(
        wonton,
        "_auto_sync_paths",
        lambda paths, *, reason: sync_calls.append((paths, reason)),
    )

    wonton._emit_validation_result(
        headline="Validated lean test: 3/4 valid (75.0%)",
        validation_path=validation_path,
        derived_dir=derived_dir,
        derived_label="Derived valid dir",
        sync=True,
        sync_reason="corpus-validate",
    )

    out = capsys.readouterr().out
    assert "Validated lean test: 3/4 valid (75.0%)" in out
    assert f"Wrote: {validation_path}" in out
    assert f"Derived valid dir: {derived_dir}" in out
    assert sync_calls == [([validation_path, derived_dir], "corpus-validate")]


def test_emit_capability_sweep_result_prints_and_syncs(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    sweep_root = tmp_path / "sweep-root"
    capability_path = tmp_path / "capability.json"
    derived_dir = tmp_path / "derived"
    sync_calls: list[tuple[list[Path], str]] = []
    result = SimpleNamespace(
        reachable_count=3,
        total_count=5,
        reachable_rate=0.6,
        sweep_root=sweep_root,
        capability_path=capability_path,
        derived_feasible_dir=derived_dir,
    )

    monkeypatch.setattr(
        wonton,
        "_auto_sync_paths",
        lambda paths, *, reason: sync_calls.append((paths, reason)),
    )

    wonton._emit_capability_sweep_result(
        result,
        sync=True,
        sync_reason="corpus-sweep-lean-capability",
        include_sweep_root=True,
    )

    out = capsys.readouterr().out
    assert "Reachable: 3/5 (60.0%)" in out
    assert f"Sweep root: {sweep_root}" in out
    assert f"Wrote: {capability_path}" in out
    assert f"Derived feasible dir: {derived_dir}" in out
    assert sync_calls == [
        ([sweep_root, capability_path, derived_dir], "corpus-sweep-lean-capability")
    ]


def test_open_lake_db_ensures_schema_and_closes(monkeypatch, tmp_path) -> None:
    import analysis.lake.db as lake_db
    import wonton

    captured: dict[str, object] = {}
    expected_db = tmp_path / "lake.duckdb"
    closed: list[bool] = []
    fake_conn = SimpleNamespace(close=lambda: closed.append(True))

    monkeypatch.setattr(
        lake_db,
        "resolve_lake_paths",
        lambda: SimpleNamespace(db_path=expected_db),
    )

    def fake_connect(path: Path) -> SimpleNamespace:
        captured["db_path"] = path
        return fake_conn

    monkeypatch.setattr(lake_db, "connect", fake_connect)
    monkeypatch.setattr(
        lake_db,
        "ensure_schema",
        lambda conn: captured.setdefault("ensured", conn),
    )

    with wonton._open_lake_db(None) as (conn, db_path):
        assert conn is fake_conn
        assert db_path == expected_db

    assert captured["db_path"] == expected_db
    assert captured["ensured"] is fake_conn
    assert closed == [True]


def test_corpus_sweep_lean_capability_requires_seed_with_sample() -> None:
    import wonton

    with pytest.raises(click.BadParameter, match="--seed is required when using --sample"):
        wonton.corpus_sweep_lean_capability(corpus_ref="lean:test", sample=5, seed=None)


def test_postprocess_single_run_dry_run_skips_processing(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import analysis.logs as logs_mod
    import analysis.postprocess_batch as postprocess_batch_mod
    import analysis.postprocess_metrics as postprocess_mod
    import wonton

    run_dir = tmp_path / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)

    def fake_inspect(run_dir_arg, *, params, include_partial):
        assert run_dir_arg == run_dir.resolve()
        assert include_partial is True
        return SimpleNamespace(
            eligible=True,
            needs_processing=True,
            reason="missing_postprocess_metrics",
        )

    def fail_postprocess(*args, **kwargs):
        raise AssertionError("postprocess_run should not be called during --dry-run")

    def fail_write_json_atomic(*args, **kwargs):
        raise AssertionError("write_json_atomic should not be called during --dry-run")

    monkeypatch.setattr(postprocess_batch_mod, "inspect_postprocess_run_state", fake_inspect)
    monkeypatch.setattr(postprocess_mod, "postprocess_run", fail_postprocess)
    monkeypatch.setattr(logs_mod, "write_json_atomic", fail_write_json_atomic)

    wonton.postprocess(run_dir=str(run_dir), dry_run=True, agent=False)

    out = capsys.readouterr().out
    assert "Postprocess dry-run" in out
    assert "Pending: True" in out
    assert not (run_dir / "postprocess_metrics.json").exists()


def test_verify_run_local_wrapper_passes_args(monkeypatch, tmp_path) -> None:
    import analysis.verify_run_local as verify_mod
    import wonton

    captured: dict[str, object] = {}

    def fake_verify_run_local(run_dir, *, theorem_names, limit, lean_project, force):
        captured["run_dir"] = run_dir
        captured["theorem_names"] = theorem_names
        captured["limit"] = limit
        captured["lean_project"] = lean_project
        captured["force"] = force
        return [
            {
                "run_dir": str(run_dir),
                "provider": None,
                "counts": {
                    "eligible": 1,
                    "verified": 1,
                    "candidate_failed": 0,
                    "replay_failed": 0,
                    "input_failed": 0,
                    "skipped_existing": 0,
                    "skipped_unsolved": 0,
                },
            }
        ]

    monkeypatch.setattr(verify_mod, "verify_run_local", fake_verify_run_local)

    wonton.verify_run_local_command(
        run_dir=str(tmp_path),
        theorem=["t1", "t2"],
        limit=5,
        lean_project=str(tmp_path / "lean_project"),
        force=True,
    )

    assert captured["run_dir"] == tmp_path.resolve()
    assert captured["theorem_names"] == ["t1", "t2"]
    assert captured["limit"] == 5
    assert captured["lean_project"] == (tmp_path / "lean_project").resolve()
    assert captured["force"] is True


def test_inspect_proof_ir_wrapper_passes_configs_and_writes_output(monkeypatch, tmp_path) -> None:
    import analysis.inspect_proof_ir as inspect_mod
    import wonton

    captured: dict[str, object] = {}

    def fake_inspect_theorem_ir(run_dir, **kwargs):
        captured["run_dir"] = run_dir
        captured.update(kwargs)
        return SimpleNamespace(
            payload={
                "theorem": "t1",
                "variant": "wild_type",
                "provider": None,
                "graph_source": "wild_type_graph",
                "graph": {
                    "family": "search_trace",
                    "node_count": 2,
                    "edge_count": 1,
                    "max_depth": 1,
                },
                "lexical": {"token_count": 1},
                "proof_ir": {
                    "edge_role_profile": {"fam:intro": 1.0},
                    "operator_profile": {"bind": 1.0},
                    "continuation_profile": {"chain": 1.0},
                    "coupling_profile": {"none": 1.0},
                },
                "actions": [
                    {
                        "index": 1,
                        "operator_kind": "bind",
                        "motif_kind": "motif:bind_open",
                        "action_kind": "tactic_step",
                        "branch_arity": 1,
                        "continuation_kind": "chain",
                        "goal_coupling": "none",
                        "effect_flags": ["opens_binder"],
                    }
                ],
            }
        )

    monkeypatch.setattr(inspect_mod, "inspect_theorem_ir", fake_inspect_theorem_ir)

    output_path = tmp_path / "inspect.json"
    wonton.inspect_proof_ir(
        run_dir=str(tmp_path),
        theorem="t1",
        name_obfuscation="names",
        lexical_ablation="graph_only",
        output=str(output_path),
    )

    assert captured["run_dir"] == tmp_path.resolve()
    assert captured["theorem"] == "t1"
    assert captured["variant"] == "wild_type"
    assert captured["graph_source"] == "wild_type_graph"
    assert captured["name_obfuscation"].mode == "names"
    assert captured["lexical_ablation"].mode == "graph_only"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["theorem"] == "t1"


def test_inspect_proof_ir_pair_defaults_compare_run_dir_and_graph_source(
    monkeypatch,
    tmp_path,
) -> None:
    import analysis.inspect_proof_ir as inspect_mod
    import wonton

    captured: dict[str, object] = {}

    def fake_inspect_theorem_ir_pair(run_dir, **kwargs):
        captured["run_dir"] = run_dir
        captured.update(kwargs)
        return {
            "left": {
                "theorem": "t1",
                "variant": "wild_type",
                "graph": {"family": "search_trace"},
                "proof_ir": {
                    "continuation_profile": {"chain": 1.0},
                    "coupling_profile": {"none": 1.0},
                },
            },
            "right": {
                "theorem": "t2",
                "variant": "wild_type",
                "graph": {"family": "search_trace"},
                "proof_ir": {
                    "continuation_profile": {"chain": 1.0},
                    "coupling_profile": {"none": 1.0},
                },
            },
            "distance": {
                "total": 0.0,
                "graph": 0.0,
                "lexical": 0.0,
                "connective": 0.0,
                "lexical_overlap": 1.0,
                "cross_kind": False,
            },
        }

    monkeypatch.setattr(inspect_mod, "inspect_theorem_ir_pair", fake_inspect_theorem_ir_pair)

    wonton.inspect_proof_ir(
        run_dir=str(tmp_path),
        theorem="t1",
        compare_theorem="t2",
    )

    assert captured["run_dir"] == tmp_path
    assert captured["run_b_dir"] == tmp_path
    assert captured["graph_source_a"] == "wild_type_graph"
    assert captured["graph_source_b"] == "wild_type_graph"
    assert captured["variant_b"] == "wild_type"


def test_emit_text_report_echoes_and_writes_json(tmp_path, capsys) -> None:
    import wonton

    output_path = tmp_path / "report.json"
    payload = {"value": 1}

    wonton._emit_text_report(
        "hello report",
        payload,
        output=str(output_path),
        label="test report",
    )

    out = capsys.readouterr().out
    assert "hello report" in out
    assert f"Wrote test report: {output_path}" in out
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
