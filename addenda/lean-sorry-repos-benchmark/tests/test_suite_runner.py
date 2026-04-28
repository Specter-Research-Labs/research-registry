from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pytest

import lean_sorry_repos_benchmark.suite_runner as suite_runner
from lean_sorry_repos_benchmark.suite_runner import (
    SuiteConfig,
    SuiteRunResult,
    SuiteRunSpec,
    load_suite_config,
    render_summary_markdown,
    run_suite,
)


def test_load_suite_config_parses_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "common_args": [
                    "--index",
                    str(tmp_path / "index.jsonl"),
                    "--max-items",
                    "25",
                    "--seed",
                    "7",
                ],
                "runs": [
                    {"adapter": "mock", "model": "mock-v1"},
                    {
                        "name": "qwen-small",
                        "adapter": "ollama",
                        "model": "qwen2.5:0.5b",
                        "args": ["--ollama-timeout-seconds", "30"],
                    },
                    {
                        "name": "gpt-5.2",
                        "adapter": "openai",
                        "model": "gpt-5.2",
                        "args": ["--openai-timeout-seconds", "45"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_suite_config(config_path)
    assert config.schema_version == 1
    assert config.common_args[0] == "--index"
    assert [run.name for run in config.runs] == ["mock:mock-v1", "qwen-small", "gpt-5.2"]
    assert config.runs[1].args == ("--ollama-timeout-seconds", "30")
    assert config.runs[2].args == ("--openai-timeout-seconds", "45")


def test_load_suite_config_rejects_reserved_override(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "common_args": ["--index", str(tmp_path / "index.jsonl")],
                "runs": [
                    {
                        "adapter": "mock",
                        "model": "mock-v1",
                        "args": ["--out-dir", str(tmp_path / "forbidden")],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not include --out-dir"):
        load_suite_config(config_path)


@pytest.mark.parametrize(
    "flag",
    [
        "--index",
        "--split-policy",
        "--repo-holdout-fraction",
        "--goal-slice",
        "--seed",
        "--samples-per-item",
        "--pass-at-k",
        "--verification-mode",
    ],
)
def test_load_suite_config_rejects_protocol_critical_per_run_override(
    tmp_path: Path, flag: str
) -> None:
    config_path = tmp_path / "suite.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "common_args": ["--index", str(tmp_path / "index.jsonl"), "--seed", "7"],
                "runs": [
                    {
                        "adapter": "mock",
                        "model": "mock-v1",
                        "args": [flag, "forbidden"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=re.escape(f"must not include {flag}")):
        load_suite_config(config_path)


def test_args_parses_max_parallel_runs(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"

    parsed_default = suite_runner._args(["--config", str(config_path)])
    assert parsed_default.max_parallel_runs == 1

    parsed_explicit = suite_runner._args(
        ["--config", str(config_path), "--max-parallel-runs", "3"]
    )
    assert parsed_explicit.max_parallel_runs == 3


def test_run_suite_preserves_config_order_under_parallel_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = SuiteConfig(
        schema_version=1,
        common_args=("--index", str(tmp_path / "index.jsonl")),
        runs=(
            SuiteRunSpec(name="first", adapter="mock", model="m1", args=()),
            SuiteRunSpec(name="second", adapter="mock", model="m2", args=()),
            SuiteRunSpec(name="third", adapter="mock", model="m3", args=()),
        ),
    )
    completion_order: list[str] = []
    completion_lock = threading.Lock()
    start_barrier = threading.Barrier(3)
    release_third = threading.Event()
    release_first = threading.Event()

    def fake_run_one(
        spec: SuiteRunSpec, *, common_args: tuple[str, ...], run_dir: Path
    ) -> SuiteRunResult:
        assert common_args == config.common_args
        start_barrier.wait(timeout=1.0)
        if spec.name == "second":
            with completion_lock:
                completion_order.append(spec.name)
            release_third.set()
        elif spec.name == "third":
            assert release_third.wait(timeout=1.0)
            with completion_lock:
                completion_order.append(spec.name)
            release_first.set()
        else:
            assert release_first.wait(timeout=1.0)
            with completion_lock:
                completion_order.append(spec.name)
        return SuiteRunResult(
            name=spec.name,
            adapter=spec.adapter,
            model=spec.model,
            run_dir=str(run_dir),
            status="success",
            exit_code=0,
            selected_rows=None,
            valid_rate=None,
            verification_success_rate_attempted=None,
            verification_success_rate_attempted_ci=None,
            verification_pass_at_k_success_rate={},
            verification_pass_at_k_success_rate_ci={},
            generation_error_count=0,
            generation_error_kinds={},
            verification_error_count=0,
            infra_failure_kind=None,
            infra_failure_reason=None,
            failure_domain=None,
            failure_reason=None,
            attempts_jsonl=None,
            summary_json=None,
        )

    monkeypatch.setattr(suite_runner, "_run_one", fake_run_one)
    results = run_suite(config, out_dir=tmp_path / "suite-out", max_parallel_runs=3)

    expected_order = [run.name for run in config.runs]
    assert completion_order == ["second", "third", "first"]
    assert completion_order != expected_order
    assert [result.name for result in results] == expected_order


def test_render_summary_markdown_shows_model_and_infra_fields() -> None:
    rows = [
        SuiteRunResult(
            name="mock:ok",
            adapter="mock",
            model="mock-v1",
            run_dir="/tmp/runs/01",
            status="success",
            exit_code=0,
            selected_rows=100,
            valid_rate=0.66,
            verification_success_rate_attempted=0.4,
            verification_success_rate_attempted_ci={"low": 0.2, "high": 0.6},
            verification_pass_at_k_success_rate={"1": 0.3, "3": 0.5},
            verification_pass_at_k_success_rate_ci={
                "1": {"low": 0.1, "high": 0.5},
                "3": {"low": 0.2, "high": 0.8},
            },
            generation_error_count=3,
            generation_error_kinds={"timeout": 2, "http_error": 1},
            verification_error_count=5,
            infra_failure_kind=None,
            infra_failure_reason=None,
            failure_domain="model",
            failure_reason="3 generation errors",
            attempts_jsonl="/tmp/runs/01/attempts.jsonl",
            summary_json="/tmp/runs/01/summary.json",
        ),
        SuiteRunResult(
            name="ollama:fail",
            adapter="ollama",
            model="qwen2.5:7b",
            run_dir="/tmp/runs/02",
            status="failed",
            exit_code=1,
            selected_rows=None,
            valid_rate=None,
            verification_success_rate_attempted=None,
            verification_success_rate_attempted_ci=None,
            verification_pass_at_k_success_rate={},
            verification_pass_at_k_success_rate_ci={},
            generation_error_count=None,
            generation_error_kinds={},
            verification_error_count=None,
            infra_failure_kind="missing_summary",
            infra_failure_reason="missing benchmark summary",
            failure_domain="infra",
            failure_reason="missing benchmark summary",
            attempts_jsonl=None,
            summary_json=None,
        ),
    ]

    table = render_summary_markdown(rows)
    assert "- infra_failures: 1" in table
    assert "- runs_with_model_errors: 1" in table
    assert "1:0.3000 [0.1000, 0.5000], 3:0.5000 [0.2000, 0.8000]" in table
    assert "0.4000 [0.2000, 0.6000]" in table
    assert "3 (http_error:1, timeout:2)" in table
    assert "missing_summary: missing benchmark summary" in table
