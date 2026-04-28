from __future__ import annotations

import inspect
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


def _install_lake_sync_fixture(
    monkeypatch,
    wonton,
    tmp_path: Path,
    *,
    local_fp: dict[str, object],
    remote_fp: dict[str, object] | None = None,
    state: dict[str, object] | None = None,
) -> dict[str, object]:
    remote_root = tmp_path / "remote-artifacts"
    local_lake_root = tmp_path / "local-lake"
    local_db = local_lake_root / "lake.duckdb"
    remote_lake_root = remote_root / "lake"
    remote_db = remote_lake_root / "lake.duckdb"
    state_path = tmp_path / ".lake_sync_state.json"
    captured: dict[str, object] = {"remote_root": remote_root}

    monkeypatch.setattr(
        wonton,
        "_resolve_lake_sync_roots",
        lambda: wonton.LakeSyncRoots(
            remote_root=remote_root,
            local_lake_root=local_lake_root,
            local_db=local_db,
            remote_lake_root=remote_lake_root,
            remote_db=remote_db,
        ),
    )
    monkeypatch.setattr(
        wonton,
        "_run_standard_path_sync_command",
        lambda **kwargs: captured.update(sync_kwargs=kwargs),
    )
    monkeypatch.setattr(
        wonton,
        "_lake_db_fingerprint",
        lambda path: remote_fp if remote_fp is not None and path == remote_db else local_fp,
    )
    monkeypatch.setattr(wonton, "ssh_config_for_root", lambda _path: None)
    monkeypatch.setattr(wonton, "_lake_sync_state_path", lambda _root: state_path)
    monkeypatch.setattr(
        wonton,
        "_write_lake_sync_state",
        lambda path, payload: captured.update(state_path=path, payload=payload),
    )
    if state is not None:
        monkeypatch.setattr(wonton, "_read_lake_sync_state", lambda _path: state)
    return captured


def test_z3_wrapper_passes_all_run_args_and_no_typer_optioninfo(monkeypatch, tmp_path) -> None:
    # Regression test: wrapper commands (e.g. `wonton.py z3`) call `run()` directly.
    # If the wrapper omits a newer `run()` parameter, `run()` may receive Typer
    # `OptionInfo` sentinel defaults, which can trip backend validation.
    import wonton

    run_param_names = set(inspect.signature(wonton.run).parameters.keys())
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(wonton, "run", fake_run)

    wonton.z3(
        smtlib_root=str(tmp_path),
        limit=None,
        offset=None,
        sample=None,
        seed=None,
        timeout=1,
        binary=None,
        extra_args=None,
        log_dir=None,
        agent=False,
    )

    assert set(captured.keys()) == run_param_names
    assert captured["backend"] == wonton.Backend.z3
    assert captured["smtlib_root"] == str(tmp_path)

    # Crucial invariant: no Typer sentinel defaults leak into `run()`.
    optioninfo = typer.models.OptionInfo
    assert not any(isinstance(v, optioninfo) for v in captured.values())


def test_lean_run_forwards_defaults_sync_and_extended_options(monkeypatch) -> None:
    import wonton

    calls = _capture_keyword_calls(monkeypatch, wonton, "_run_lean_command")

    wonton.lean_run(sync=False)
    wonton.lean_run(
        sync=True,
        deepseek_model_path="/tmp/deepseek.gguf",
        search_seed=17,
        no_solution_artifacts=True,
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
    assert extended["intervention_name"] == ["cut"]
    assert extended["extra_intervention"] == ["nocases:cases"]


def test_lean_basin_forces_basin_mode_without_interventions(monkeypatch) -> None:
    import wonton

    calls = _capture_keyword_calls(monkeypatch, wonton, "_run_lean_command")

    wonton.lean_basin(seeds=7, blind=True, sync=False)

    captured = calls[0]
    assert captured["basin_seeds"] == 7
    assert captured["basin_blind"] is True
    assert captured["wild_only"] is False
    assert captured["with_interventions"] is False
    assert captured["analysis"] is False
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


@pytest.mark.parametrize("watch", [True, False])
def test_run_external_corpus_selects_watch_or_progress_ui(
    monkeypatch,
    tmp_path,
    watch: bool,
) -> None:
    import wonton

    log_dir = tmp_path / "logs"
    progress_token = object()
    captured: dict[str, object] = {"closed": False}

    def fake_run_with_watch_ui(log_dir_arg, run_fn, *, refresh=0.25):
        assert watch
        captured["log_dir"] = log_dir_arg
        captured["refresh"] = refresh
        run_fn()

    def fake_build_external_progress_ui(enabled: bool):
        assert not watch
        captured["enabled"] = enabled

        def close() -> None:
            captured["closed"] = True

        return progress_token, close

    monkeypatch.setattr(wonton, "_run_with_watch_ui", fake_run_with_watch_ui)
    monkeypatch.setattr(wonton, "_build_external_progress_ui", fake_build_external_progress_ui)

    progress_values: list[object | None] = []
    args = SimpleNamespace(watch=watch, agent=False, plain=False)

    def run_batch(progress_cb):
        progress_values.append(progress_cb)

    result = wonton._run_external_corpus(args, log_dir=log_dir, run_batch=run_batch)

    assert result == log_dir
    if watch:
        assert captured["log_dir"] == log_dir
        assert progress_values == [None]
        assert captured["closed"] is False
    else:
        assert captured["enabled"] is True
        assert captured["closed"] is True
        assert progress_values == [progress_token]


def test_run_external_backend_sets_default_coq_stdlib_log_dir(monkeypatch, tmp_path) -> None:
    import wonton

    captured: dict[str, object] = {}
    expected_log_dir = tmp_path / "coq-stdlib"

    def fake_default_log_dir(label: str):
        captured["label"] = label
        return expected_log_dir

    def fake_run_coq(args):
        captured["log_dir"] = args.log_dir
        return Path(args.log_dir)

    monkeypatch.setattr(wonton, "_default_log_dir", fake_default_log_dir)
    monkeypatch.setattr(wonton, "_run_coq", fake_run_coq)

    args = SimpleNamespace(
        backend=wonton.Backend.coq,
        coq_mode=wonton.CoqMode.stdlib,
        log_dir=None,
        agent=False,
    )

    result = wonton._run_external_backend(args)

    assert captured["label"] == "coq-stdlib"
    assert captured["log_dir"] == str(expected_log_dir)
    assert result == expected_log_dir


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

    expected_log_dir = tmp_path / "z3-run"
    events: list[dict[str, object]] = []

    monkeypatch.setattr(wonton, "_validate_backend_args", lambda args: None)
    monkeypatch.setattr(wonton, "_emit_agent_event", events.append)
    monkeypatch.setattr(wonton, "_default_log_dir", lambda _label: expected_log_dir)

    def fake_run(args):
        if failure is not None:
            raise failure
        return Path(args.log_dir)

    monkeypatch.setattr(wonton, "_run_external_backend", fake_run)

    if failure is None:
        wonton.run(backend=wonton.Backend.z3, smtlib_root=str(tmp_path), agent=True)
    else:
        with pytest.raises(RuntimeError, match=str(failure)):
            wonton.run(backend=wonton.Backend.z3, smtlib_root=str(tmp_path), agent=True)

    assert events[0] == {"event": "start", "backend": "z3", "log_dir": str(expected_log_dir)}
    end_event = {
        "event": "end",
        "status": expected_status,
        "errors": expected_errors,
        "backend": "z3",
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


def test_run_sync_root_command_resolves_target_and_prints_report(monkeypatch, tmp_path) -> None:
    import wonton

    local_root = tmp_path / "local"
    remote_root = tmp_path / "remote"
    target = local_root / "nested"
    report = SimpleNamespace(src_root=target, dst_root=remote_root, copied_files=2, skipped_files=1)
    captured: dict[str, object] = {}

    def fake_ensure_remote_accessible(path: Path, *, label: str) -> None:
        captured["remote_root"] = path
        captured["remote_label"] = label

    def fake_resolve_sync_target(root: Path, rel: str | None, *, label: str) -> Path:
        captured["local_root"] = root
        captured["rel"] = rel
        captured["rel_label"] = label
        return target

    def fake_sync(path: Path):
        captured["sync_target"] = path
        return report

    def fake_print_sync_report(label: str, printed_report) -> None:
        captured["report_label"] = label
        captured["report"] = printed_report

    monkeypatch.setattr(wonton, "_ensure_remote_accessible", fake_ensure_remote_accessible)
    monkeypatch.setattr(wonton, "_resolve_sync_target", fake_resolve_sync_target)
    monkeypatch.setattr(wonton, "_print_sync_report", fake_print_sync_report)

    wonton._run_sync_root_command(
        local_root=local_root,
        rel="nested",
        rel_label="subpath",
        remote_root=remote_root,
        remote_label="SPECTER_REMOTE_ROOT",
        missing_remote_message="missing remote root",
        missing_config_message="missing sync config",
        sync_fn=fake_sync,
        report_label="artifacts push",
    )

    assert captured == {
        "local_root": local_root,
        "rel": "nested",
        "rel_label": "subpath",
        "remote_root": remote_root,
        "remote_label": "SPECTER_REMOTE_ROOT",
        "sync_target": target,
        "report_label": "artifacts push",
        "report": report,
    }


def test_run_sync_root_command_dies_when_sync_is_not_configured(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import wonton

    monkeypatch.setattr(wonton, "_ensure_remote_accessible", lambda *_args, **_kwargs: None)

    with pytest.raises(typer.Exit, match=None) as exc_info:
        wonton._run_sync_root_command(
            local_root=tmp_path / "local",
            rel=None,
            rel_label="run_id",
            remote_root=tmp_path / "remote",
            remote_label="SPECTER_REMOTE_ROOT",
            missing_remote_message="missing remote root",
            missing_config_message="missing sync config",
            sync_fn=lambda _target: None,
            report_label="logs push",
        )

    assert exc_info.value.exit_code == 1
    assert "missing sync config" in capsys.readouterr().err


def test_require_accessible_remote_root_validates_presence_and_access(
    monkeypatch,
    tmp_path,
) -> None:
    import wonton

    remote_root = tmp_path / "remote"
    captured: dict[str, object] = {}

    def fake_ensure_remote_accessible(path: Path, *, label: str) -> None:
        captured["path"] = path
        captured["label"] = label

    monkeypatch.setattr(wonton, "_ensure_remote_accessible", fake_ensure_remote_accessible)

    resolved = wonton._require_accessible_remote_root(
        remote_root,
        label="SPECTER_REMOTE_ROOT",
        missing_message="missing remote root",
    )

    assert resolved == remote_root
    assert captured == {"path": remote_root, "label": "SPECTER_REMOTE_ROOT"}


def test_sync_corpora_push_uses_corpora_env_label_when_remote_root_is_missing(
    monkeypatch,
    capsys,
) -> None:
    import wonton

    monkeypatch.setattr(wonton, "configured_remote_corpora_root", lambda: None)

    with pytest.raises(typer.Exit) as exc_info:
        wonton.sync_corpora_push(subpath=None)

    assert exc_info.value.exit_code == 1
    assert (
        "SPECTER_CORPORA_ROOT is not set; no remote corpora root configured."
        in capsys.readouterr().err
    )


def test_resolve_lake_sync_roots_uses_artifact_remote_root(monkeypatch, tmp_path) -> None:
    import wonton

    remote_root = tmp_path / "remote-artifacts"
    local_lake_root = tmp_path / "local-lake"
    local_db = local_lake_root / "lake.duckdb"
    remote_lake_root = remote_root / "lake"
    remote_db = remote_lake_root / "lake.duckdb"
    captured: dict[str, object] = {}

    def fake_require_accessible_remote_root(root: Path | None, *, label: str, missing_message: str):
        captured["root"] = root
        captured["label"] = label
        captured["missing_message"] = missing_message
        return remote_root

    monkeypatch.setattr(
        wonton,
        "_require_accessible_remote_root",
        fake_require_accessible_remote_root,
    )
    monkeypatch.setattr(wonton, "configured_remote_artifacts_root", lambda: remote_root)
    monkeypatch.setattr(
        wonton,
        "_lake_paths",
        lambda: (local_lake_root, local_db, remote_lake_root, remote_db),
    )

    assert wonton._resolve_lake_sync_roots() == wonton.LakeSyncRoots(
        remote_root=remote_root,
        local_lake_root=local_lake_root,
        local_db=local_db,
        remote_lake_root=remote_lake_root,
        remote_db=remote_db,
    )
    assert captured == {
        "root": remote_root,
        "label": "SPECTER_ARTIFACT_ROOT",
        "missing_message": (
            "SPECTER_ARTIFACT_ROOT is not set; no remote artifacts root configured."
        ),
    }


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


@pytest.mark.parametrize("direction", ["pull", "push"])
def test_sync_lake_transfer_uses_shared_artifact_sync_helper(
    monkeypatch,
    tmp_path,
    direction: str,
) -> None:
    import wonton

    local_fp = {"exists": True, "sha256": "local", "bytes": 10}
    remote_fp = {"exists": True, "sha256": "remote", "bytes": 11}
    captured = _install_lake_sync_fixture(
        monkeypatch,
        wonton,
        tmp_path,
        local_fp=local_fp,
        remote_fp=remote_fp if direction == "pull" else local_fp,
        state={"last_pull_at": "2026-04-06T12:00:00", "remote_db": local_fp},
    )

    if direction == "pull":
        wonton.sync_lake_pull()
    else:
        wonton.sync_lake_push(force=False, snapshot_remote=False)

    assert captured["sync_kwargs"] == {
        "kind": "artifacts",
        "direction": direction,
        "rel": "lake",
        "report_label_override": f"lake {direction}",
        "remote_root_override": captured["remote_root"],
    }
    assert captured["state_path"] == tmp_path / ".lake_sync_state.json"
    assert captured["payload"]["schema_version"] == 1
    assert captured["payload"]["local_db"] == local_fp
    if direction == "pull":
        assert captured["payload"]["remote_db"] == remote_fp
        assert isinstance(captured["payload"]["last_pull_at"], str)
    else:
        assert captured["payload"]["last_pull_at"] == "2026-04-06T12:00:00"
        assert captured["payload"]["remote_db"] == local_fp
        assert isinstance(captured["payload"]["last_push_at"], str)


def test_verify_lake_cleanable_requires_remote_fingerprint_match(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import wonton

    local_lake_root = tmp_path / "lake"
    local_db = local_lake_root / "lake.duckdb"
    remote_lake_root = tmp_path / "remote-lake"
    remote_db = remote_lake_root / "lake.duckdb"

    monkeypatch.setattr(
        wonton,
        "_lake_db_fingerprint",
        lambda path: {"exists": True, "path": str(path)},
    )
    monkeypatch.setattr(wonton, "_ensure_remote_accessible", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wonton, "ssh_config_for_root", lambda _path: None)
    monkeypatch.setattr(wonton, "_fingerprint_matches", lambda _local, _remote: False)

    with pytest.raises(typer.Exit) as exc_info:
        wonton._verify_lake_cleanable(
            local_lake_root=local_lake_root,
            local_db=local_db,
            remote_lake_root=remote_lake_root,
            remote_db=remote_db,
        )

    assert exc_info.value.exit_code == 1
    assert "Local lake DB differs from remote." in capsys.readouterr().err


def test_verify_lake_cleanable_requires_prior_push_in_ssh_mode(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import wonton

    local_lake_root = tmp_path / "lake"
    local_db = local_lake_root / "lake.duckdb"
    remote_lake_root = tmp_path / "remote-lake"
    remote_db = remote_lake_root / "lake.duckdb"

    monkeypatch.setattr(wonton, "_lake_db_fingerprint", lambda _path: {"exists": True})
    monkeypatch.setattr(wonton, "_ensure_remote_accessible", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wonton, "ssh_config_for_root", lambda _path: object())
    monkeypatch.setattr(wonton, "_read_lake_sync_state", lambda _path: {})

    with pytest.raises(typer.Exit) as exc_info:
        wonton._verify_lake_cleanable(
            local_lake_root=local_lake_root,
            local_db=local_db,
            remote_lake_root=remote_lake_root,
            remote_db=remote_db,
        )

    assert exc_info.value.exit_code == 1
    assert "Cannot verify remote in SSH mode without a prior push." in capsys.readouterr().err


def test_sync_lake_clean_local_deletes_root_when_force_is_true(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import wonton

    local_lake_root = tmp_path / "lake"
    local_lake_root.mkdir()
    local_db = local_lake_root / "lake.duckdb"
    local_db.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        wonton,
        "_lake_paths",
        lambda: (local_lake_root, local_db, tmp_path / "remote-lake", tmp_path / "remote-db"),
    )
    monkeypatch.setattr(
        wonton,
        "_verify_lake_cleanable",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("force should skip verification")),
    )

    wonton.sync_lake_clean_local(force=True)

    assert not local_lake_root.exists()
    assert f"Removed local lake root: {local_lake_root}" in capsys.readouterr().out


def test_echo_counted_samples_prints_count_and_preview(capsys) -> None:
    import wonton

    wonton._echo_counted_samples(
        "runs.local_missing_in_lake",
        ["run-a", "run-b", "run-c"],
        sample_limit=2,
    )

    out = capsys.readouterr().out
    assert "runs.local_missing_in_lake.count=3" in out
    assert "  runs.local_missing_in_lake: run-a" in out
    assert "  runs.local_missing_in_lake: run-b" in out
    assert "run-c" not in out


def test_sync_status_prints_root_settings(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    ssh = SimpleNamespace(user="alice", host="example.com", port=2222)
    monkeypatch.setattr(wonton, "ssh_config_for_root", lambda _path: ssh)
    monkeypatch.setattr(
        wonton,
        "configured_remote_log_archives_root",
        lambda: tmp_path / "remote-archives",
    )
    monkeypatch.setattr(wonton, "configured_remote_logs_root", lambda: tmp_path / "remote-logs")
    monkeypatch.setattr(
        wonton,
        "configured_remote_artifacts_root",
        lambda: tmp_path / "remote-artifacts",
    )
    monkeypatch.setattr(wonton, "configured_remote_corpora_root", lambda: None)
    monkeypatch.setattr(wonton, "resolve_logs_root", lambda: tmp_path / "logs")
    monkeypatch.setattr(wonton, "resolve_artifacts_root", lambda: tmp_path / "artifacts")
    monkeypatch.setattr(wonton, "resolve_corpora_root", lambda: tmp_path / "corpora")

    wonton.sync_status()

    out = capsys.readouterr().out
    assert "ssh.target=alice@example.com:2222" in out
    assert f"logs.local={tmp_path / 'logs'}" in out
    assert f"logs.remote={tmp_path / 'remote-logs'}" in out
    assert "corpora.remote=-" in out


def test_sync_lake_status_reports_ssh_remote_and_state(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    local_lake_root = tmp_path / "local-lake"
    local_db = local_lake_root / "lake.duckdb"
    remote_lake_root = tmp_path / "remote-lake"
    remote_db = remote_lake_root / "lake.duckdb"
    local_fp = {"exists": True, "sha256": "local-sha", "bytes": 10}
    remote_fp = {"exists": True, "sha256": "remote-sha", "bytes": 11}
    state = {
        "last_pull_at": "2026-04-02T12:00:00",
        "last_push_at": "2026-04-02T12:05:00",
        "remote_db": remote_fp,
    }

    monkeypatch.setattr(
        wonton,
        "_lake_paths",
        lambda: (local_lake_root, local_db, remote_lake_root, remote_db),
    )
    monkeypatch.setattr(
        wonton,
        "_lake_sync_state_path",
        lambda _root: tmp_path / ".lake_sync_state.json",
    )
    monkeypatch.setattr(wonton, "_read_lake_sync_state", lambda _path: state)
    monkeypatch.setattr(wonton, "_lake_db_fingerprint", lambda _path: local_fp)
    monkeypatch.setattr(wonton, "_format_fingerprint", lambda fp: fp["sha256"])
    monkeypatch.setattr(
        wonton,
        "ssh_config_for_root",
        lambda path: object() if path == remote_lake_root else None,
    )

    wonton.sync_lake_status()

    out = capsys.readouterr().out
    assert f"lake.local_root={local_lake_root}" in out
    assert f"lake.remote_root={remote_lake_root}" in out
    assert "lake.remote=ssh (fingerprint requires lake-pull)" in out
    assert "lake.last_known_remote=remote-sha" in out
    assert "lake.last_pull_at=2026-04-02T12:00:00" in out
    assert "lake.last_push_at=2026-04-02T12:05:00" in out


def test_sync_durability_status_reuses_counted_samples(monkeypatch, tmp_path, capsys) -> None:
    import wonton

    logs_local = tmp_path / "logs"
    local_db = tmp_path / "lake.duckdb"
    monkeypatch.setattr(
        wonton,
        "_durability_snapshot",
        lambda: {
            "ssh": False,
            "logs_local": logs_local,
            "logs_remote": None,
            "logs_remote_archives": None,
            "local_run_ids": {"a", "b", "c"},
            "remote_run_ids": {"a"},
            "archive_run_ids": {"a", "b"},
            "archive_known": True,
            "local_only_not_archived": ["c"],
            "run_ids_in_lake": {"a"},
            "local_missing_in_lake": ["b", "c"],
            "stale_in_lake": ["stale-1"],
            "local_lake_db": local_db,
            "remote_lake_db": None,
            "local_lake_fp": {"exists": False},
            "remote_lake_fp": None,
            "lake_in_sync": None,
        },
    )
    monkeypatch.setattr(
        wonton,
        "_format_fingerprint",
        lambda fp: "missing" if not fp["exists"] else "ok",
    )

    wonton.sync_durability_status(sample_limit=1)

    out = capsys.readouterr().out
    assert "runs.local_only_not_archived.count=1" in out
    assert "  runs.local_only_not_archived: c" in out
    assert "runs.local_missing_in_lake.count=2" in out
    assert "  runs.local_missing_in_lake: b" in out
    assert "runs.stale_in_lake.count=1" in out
    assert "  runs.stale_in_lake: stale-1" in out


def test_run_bulk_sync_sections_uses_shared_progress_and_skip_footer(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import wonton

    progress_token = object()
    logs_root = tmp_path / "logs"
    artifacts_root = tmp_path / "artifacts"
    corpora_root = tmp_path / "corpora"
    calls: list[tuple[str, Path, bool, object]] = []
    reports: list[tuple[str, object]] = []

    monkeypatch.setattr(wonton, "_sync_progress_handler", lambda: progress_token)
    monkeypatch.setattr(
        wonton,
        "_print_sync_report",
        lambda label, report: reports.append((label, report)),
    )

    def make_sync(name: str, report: object | None):
        def fake_sync(root: Path, *, require_src: bool, progress_callback: object):
            calls.append((name, root, require_src, progress_callback))
            return report

        return fake_sync

    logs_report = SimpleNamespace(name="logs-report")
    corpora_report = SimpleNamespace(name="corpora-report")
    wonton._run_bulk_sync_sections(
        "push",
        [
            ("logs", logs_root, make_sync("logs", logs_report)),
            ("artifacts", artifacts_root, make_sync("artifacts", None)),
            ("corpora", corpora_root, make_sync("corpora", corpora_report)),
        ],
    )

    out = capsys.readouterr().out
    assert "==> Syncing logs..." in out
    assert "artifacts push: (skipped, no remote configured)" in out
    assert "==> All syncs complete!" in out
    assert calls == [
        ("logs", logs_root, False, progress_token),
        ("artifacts", artifacts_root, False, progress_token),
        ("corpora", corpora_root, False, progress_token),
    ]
    assert reports == [
        ("logs push", logs_report),
        ("corpora push", corpora_report),
    ]


@pytest.mark.parametrize(
    ("command_name", "expected_action", "expected_functions"),
    [
        (
            "sync_push_all",
            "push",
            ("sync_logs_to_remote", "sync_artifacts_to_remote", "sync_corpora_to_remote"),
        ),
        (
            "sync_pull_all",
            "pull",
            (
                "sync_logs_from_remote",
                "sync_artifacts_from_remote",
                "sync_corpora_from_remote",
            ),
        ),
    ],
)
def test_bulk_sync_commands_forward_expected_sections(
    monkeypatch,
    tmp_path,
    command_name: str,
    expected_action: str,
    expected_functions: tuple[str, str, str],
) -> None:
    import wonton

    logs_root = tmp_path / "logs"
    artifacts_root = tmp_path / "artifacts"
    corpora_root = tmp_path / "corpora"
    captured: dict[str, object] = {}

    monkeypatch.setattr(wonton, "resolve_logs_dir", lambda: logs_root)
    monkeypatch.setattr(wonton, "resolve_artifacts_root", lambda: artifacts_root)
    monkeypatch.setattr(wonton, "resolve_corpora_root", lambda: corpora_root)

    def fake_run_bulk_sync_sections(action: str, sections) -> None:
        captured["action"] = action
        captured["names"] = [name for name, _, _ in sections]
        captured["roots"] = [root for _, root, _ in sections]
        captured["functions"] = [fn.__name__ for _, _, fn in sections]

    monkeypatch.setattr(wonton, "_run_bulk_sync_sections", fake_run_bulk_sync_sections)

    getattr(wonton, command_name)()

    assert captured == {
        "action": expected_action,
        "names": ["logs", "artifacts", "corpora"],
        "roots": [logs_root, artifacts_root, corpora_root],
        "functions": list(expected_functions),
    }


def test_sync_durable_push_uses_shared_log_sync_helper(monkeypatch, tmp_path) -> None:
    import wonton

    logs_root = tmp_path / "logs"
    log_remote_root = tmp_path / "remote-logs"
    artifact_remote_root = tmp_path / "remote-artifacts"
    captured: dict[str, object] = {}

    monkeypatch.setattr(wonton, "resolve_logs_dir", lambda: logs_root)

    def fake_require_accessible_remote_root(
        root: Path | None,
        *,
        label: str,
        missing_message: str,
    ) -> Path:
        if label == "SPECTER_LOG_ROOT":
            captured["log_root"] = root
            return log_remote_root
        captured["artifact_root"] = root
        return artifact_remote_root

    def fake_run_sync_root_command(**kwargs) -> None:
        captured["sync_kwargs"] = kwargs

    monkeypatch.setattr(
        wonton,
        "_require_accessible_remote_root",
        fake_require_accessible_remote_root,
    )
    monkeypatch.setattr(wonton, "_run_sync_root_command", fake_run_sync_root_command)
    monkeypatch.setattr(wonton, "configured_remote_logs_root", lambda: log_remote_root)
    monkeypatch.setattr(
        wonton,
        "configured_remote_artifacts_root",
        lambda: artifact_remote_root,
    )
    monkeypatch.setattr(
        wonton,
        "sync_lake_push",
        lambda *, force, snapshot_remote: captured.update(
            lake_push=(force, snapshot_remote)
        ),
    )
    monkeypatch.setattr(
        wonton,
        "_durability_snapshot",
        lambda: {
            "archive_known": False,
            "local_only_not_archived": [],
            "local_missing_in_lake": [],
            "lake_in_sync": True,
        },
    )

    wonton.sync_durable_push(force=True, snapshot_remote=False)

    assert captured["log_root"] == log_remote_root
    assert captured["artifact_root"] == artifact_remote_root
    assert captured["sync_kwargs"]["local_root"] == logs_root
    assert captured["sync_kwargs"]["remote_root"] == log_remote_root
    assert captured["sync_kwargs"]["report_label"] == "durable logs push"
    assert captured["lake_push"] == (True, False)


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
