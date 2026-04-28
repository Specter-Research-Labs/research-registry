from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import lean_sorry_repos_benchmark.cli as cli_module
from lean_sorry_repos_benchmark.adapters import AdapterResult
from lean_sorry_repos_benchmark.cli import main
from lean_sorry_repos_benchmark.verification import VerificationResult


def _write_index(path: Path) -> None:
    rows = [
        {
            "item_id": "id-1",
            "repo_remote": "https://github.com/org/repo-a",
            "repo_commit": "abc",
            "repo_lean_version": "4.28.0",
            "location_path": "A.lean",
            "location_start_line": 1,
            "location_start_column": 1,
            "location_end_line": 1,
            "location_end_column": 6,
            "goal_sha256": "g1",
            "goal_text": "x : Nat\n⊢ x = x",
            "source_url": "https://github.com/org/repo-a/blob/abc/A.lean#L1",
        },
        {
            "item_id": "id-2",
            "repo_remote": "https://github.com/org/repo-b",
            "repo_commit": "def",
            "repo_lean_version": "4.28.0",
            "location_path": "B.lean",
            "location_start_line": 2,
            "location_start_column": 1,
            "location_end_line": 2,
            "location_end_column": 6,
            "goal_sha256": "g2",
            "goal_text": "P Q : Prop\nhp : P\n⊢ P",
            "source_url": "https://github.com/org/repo-b/blob/def/B.lean#L2",
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _read_attempts(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_profile_config(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mock_run_args(index_path: Path, *extra: str, out_dir: Path | None = None) -> list[str]:
    args = [
        "run",
        "--index",
        str(index_path),
        "--adapter",
        "mock",
        "--model",
        "mock-v1",
        *extra,
    ]
    if out_dir is not None:
        args.extend(["--out-dir", str(out_dir)])
    return args


def _run_mock(index_path: Path, *extra: str, out_dir: Path | None = None) -> int:
    return main(_mock_run_args(index_path, *extra, out_dir=out_dir))


class _AlwaysRflAdapter:
    def __init__(self, *, model: str = "mock-v1") -> None:
        self._model = model

    @property
    def adapter_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model

    def infer(
        self,
        row: object,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _ = row
        _ = prompt
        _ = sample_index
        _ = sample_seed
        return AdapterResult(raw_response="rfl", tactic="rfl", latency_ms=1, error=None)


class _AlwaysSimpAdapter(_AlwaysRflAdapter):
    def infer(
        self,
        row: object,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _ = row
        _ = prompt
        _ = sample_index
        _ = sample_seed
        return AdapterResult(raw_response="simp", tactic="simp", latency_ms=1, error=None)


class _CountingRflAdapter(_AlwaysRflAdapter):
    infer_calls = 0

    def infer(
        self,
        row: object,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _CountingRflAdapter.infer_calls += 1
        return super().infer(row, prompt, sample_index=sample_index, sample_seed=sample_seed)


class _SuccessfulReplayVerifier:
    prepare_calls = 0
    init_cache_dirs: list[str] = []
    prepare_batches: list[list[str]] = []

    def __init__(self, config: object) -> None:
        cache_dir = getattr(config, "cache_dir", None)
        if cache_dir is not None:
            self.init_cache_dirs.append(str(cache_dir))

    @classmethod
    def reset(cls) -> None:
        cls.prepare_calls = 0
        cls.init_cache_dirs = []
        cls.prepare_batches = []

    def prepare_rows(self, rows: object) -> dict[tuple[str, str], str]:
        type(self).prepare_calls += 1
        if isinstance(rows, list):
            type(self).prepare_batches.append(sorted(getattr(row, "item_id") for row in rows))
        return {}

    def verify(self, *, row: object, tactic: str) -> VerificationResult:
        _ = row
        _ = tactic
        return VerificationResult(
            attempted=True,
            success=True,
            error=None,
            error_kind=None,
            exit_code=0,
            latency_ms=1,
        )


def test_cli_mock_smoke_multi_sample(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir_one = tmp_path / "run-ms-1"
    out_dir_two = tmp_path / "run-ms-2"
    _write_index(index_path)

    base_argv = _mock_run_args(index_path, "--samples-per-item", "3")
    rc_one = main([*base_argv, "--out-dir", str(out_dir_one)])
    rc_two = main([*base_argv, "--out-dir", str(out_dir_two)])
    assert rc_one == 0
    assert rc_two == 0

    attempts_one = _read_attempts(out_dir_one / "attempts.jsonl")
    attempts_two = _read_attempts(out_dir_two / "attempts.jsonl")
    assert len(attempts_one) == 6
    assert len(attempts_two) == 6

    key_to_seed_one = {
        (attempt["item_id"], attempt["sample_index"]): attempt["sample_seed"]
        for attempt in attempts_one
    }
    key_to_seed_two = {
        (attempt["item_id"], attempt["sample_index"]): attempt["sample_seed"]
        for attempt in attempts_two
    }
    assert key_to_seed_one == key_to_seed_two
    assert {attempt["sample_index"] for attempt in attempts_one} == {0, 1, 2}

    summary = json.loads((out_dir_one / "summary.json").read_text(encoding="utf-8"))
    verify_metrics = summary["verification"]["metrics"]
    assert summary["selection"]["samples_per_item"] == 3
    assert summary["verification"]["pass_at_k_requested"] == [1, 5, 10]
    assert summary["verification"]["pass_at_k_effective"] == [1, 3]
    assert verify_metrics["verification_pass_at_k_ks"] == [1, 3]
    assert verify_metrics["verification_pass_at_k_success_count"] == {"1": 0, "3": 0}
    assert verify_metrics["verification_pass_at_k_success_rate"] == {"1": 0.0, "3": 0.0}
    assert verify_metrics["verification_success_rate_total_ci"] == {"low": 0.0, "high": 0.0}
    assert verify_metrics["verification_success_rate_attempted_ci"] is None
    assert verify_metrics["verification_pass_at_k_success_rate_ci"] == {
        "1": {"low": 0.0, "high": 0.0},
        "3": {"low": 0.0, "high": 0.0},
    }
    assert summary["verification"]["statistical"] == {
        "method": "bootstrap_percentile",
        "bootstrap_iters": 2000,
        "confidence_level": 0.95,
        "bootstrap_seed": 0,
    }
    assert summary["scoring"]["metrics"]["attempts_total"] == 6


def test_cli_openai_smoke_uses_env_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-openai"
    _write_index(index_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class FakeOpenAIAdapter:
        last_init: dict[str, object] = {}

        def __init__(
            self,
            *,
            model: str,
            endpoint: str,
            api_key: str,
            temperature: float,
            timeout_seconds: float,
            max_tokens: int,
            organization: str | None,
        ) -> None:
            self._model = model
            FakeOpenAIAdapter.last_init = {
                "endpoint": endpoint,
                "api_key": api_key,
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
                "max_tokens": max_tokens,
                "organization": organization,
            }

        @property
        def adapter_name(self) -> str:
            return "openai"

        @property
        def model_name(self) -> str:
            return self._model

        def infer(
            self,
            row: object,
            prompt: str,
            *,
            sample_index: int,
            sample_seed: int,
        ) -> AdapterResult:
            _ = row
            _ = prompt
            _ = sample_index
            _ = sample_seed
            return AdapterResult(raw_response="rfl", tactic="rfl", latency_ms=2, error=None)

    monkeypatch.setattr(cli_module, "OpenAIAdapter", FakeOpenAIAdapter)
    rc = main(
        [
            "run",
            "--index",
            str(index_path),
            "--adapter",
            "openai",
            "--model",
            "gpt-5.2",
            "--openai-endpoint",
            "https://example.invalid/v1/chat/completions",
            "--openai-timeout-seconds",
            "12",
            "--openai-max-tokens",
            "33",
            "--openai-temperature",
            "0.1",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["adapter"] == "openai"
    assert summary["model"] == "gpt-5.2"
    assert summary["inference"]["openai_endpoint"] == "https://example.invalid/v1/chat/completions"
    assert summary["inference"]["openai_api_key_env"] == "OPENAI_API_KEY"
    assert summary["inference"]["openai_timeout_seconds"] == 12.0
    assert summary["inference"]["openai_max_tokens"] == 33
    assert summary["inference"]["openai_temperature"] == 0.1
    assert summary["scoring"]["metrics"]["valid_rate"] == 1.0
    assert FakeOpenAIAdapter.last_init["api_key"] == "sk-test"


def test_cli_openai_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(index_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="Missing API key for --adapter openai"):
        main(
            [
                "run",
                "--index",
                str(index_path),
                "--adapter",
                "openai",
                "--model",
                "gpt-5.2",
            ]
        )


def test_cli_attempts_include_row_provenance_fields(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-provenance"
    _write_index(index_path)
    rc = _run_mock(index_path, out_dir=out_dir)
    assert rc == 0
    attempts = _read_attempts(out_dir / "attempts.jsonl")
    assert len(attempts) == 2
    first = attempts[0]
    assert first["repo_commit"] == "abc"
    assert first["repo_lean_version"] == "4.28.0"
    assert first["location_path"] == "A.lean"
    assert first["location_start_line"] == 1
    assert first["location_start_column"] == 1
    assert first["location_end_line"] == 1
    assert first["location_end_column"] == 6


def test_cli_shard_selection(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir_a = tmp_path / "run-shard-a"
    out_dir_b = tmp_path / "run-shard-b"
    _write_index(index_path)

    rc_a = _run_mock(index_path, "--shard-count", "2", "--shard-index", "0", out_dir=out_dir_a)
    rc_b = _run_mock(index_path, "--shard-count", "2", "--shard-index", "1", out_dir=out_dir_b)
    assert rc_a == 0
    assert rc_b == 0

    items_a = {str(attempt["item_id"]) for attempt in _read_attempts(out_dir_a / "attempts.jsonl")}
    items_b = {str(attempt["item_id"]) for attempt in _read_attempts(out_dir_b / "attempts.jsonl")}
    assert items_a == {"id-1"}
    assert items_b == {"id-2"}

    summary_a = json.loads((out_dir_a / "summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((out_dir_b / "summary.json").read_text(encoding="utf-8"))
    assert summary_a["selection"]["selected_rows_pre_shard"] == 2
    assert summary_a["selection"]["selected_rows"] == 1
    assert summary_a["selection"]["shard_count"] == 2
    assert summary_a["selection"]["shard_index"] == 0
    assert summary_b["selection"]["shard_index"] == 1


def test_cli_invalid_shard_configuration(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(index_path)
    with pytest.raises(SystemExit, match="--shard-count must be >= 1"):
        main(_mock_run_args(index_path, "--shard-count", "0"))
    with pytest.raises(SystemExit, match="--shard-index must be in"):
        main(_mock_run_args(index_path, "--shard-count", "2", "--shard-index", "2"))


def test_cli_repo_replay_preflight_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(index_path)
    _CountingRflAdapter.infer_calls = 0

    class FailingReplayVerifier:
        def __init__(self, config: object) -> None:
            _ = config

        def prepare_rows(self, rows: object) -> dict[tuple[str, str], str]:
            _ = rows
            return {("https://github.com/org/repo-a", "abc"): "git clone failed: boom"}

        def verify(self, *, row: object, tactic: str) -> VerificationResult:
            _ = row
            _ = tactic
            raise AssertionError("verify should not run when preflight fails")

    monkeypatch.setattr(cli_module, "MockAdapter", _CountingRflAdapter)
    monkeypatch.setattr(cli_module, "RepoReplayVerifier", FailingReplayVerifier)
    with pytest.raises(SystemExit, match="Repo replay preflight failed"):
        main(_mock_run_args(index_path, "--verification-mode", "repo_replay"))
    assert _CountingRflAdapter.infer_calls == 0


def test_cli_repo_replay_preflight_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-replay-preflight"
    _write_index(index_path)
    _SuccessfulReplayVerifier.reset()

    monkeypatch.setattr(cli_module, "RepoReplayVerifier", _SuccessfulReplayVerifier)
    rc = _run_mock(index_path, "--verification-mode", "repo_replay", out_dir=out_dir)
    assert rc == 0
    assert _SuccessfulReplayVerifier.prepare_calls == 1

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    replay_cfg = summary["verification"]["repo_replay"]
    assert replay_cfg["preflight_repo_targets"] == 2
    assert replay_cfg["preflight_error_count"] == 0


def test_cli_repo_replay_profile_strict_unmatched_fails_before_infer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    profile_path = tmp_path / "profiles.json"
    _write_index(index_path)
    _write_profile_config(
        profile_path,
        {
            "schema_version": 1,
            "profiles": [
                {
                    "id": "mathlib4",
                    "match": {
                        "repo_remote_prefix": "https://github.com/leanprover-community/mathlib4"
                    },
                    "overrides": {"timeout_seconds": 30},
                }
            ],
        },
    )
    _CountingRflAdapter.infer_calls = 0

    monkeypatch.setattr(cli_module, "MockAdapter", _CountingRflAdapter)
    with pytest.raises(SystemExit, match="no replay profile matched"):
        main(
            _mock_run_args(
                index_path,
                "--verification-mode",
                "repo_replay",
                "--repo-replay-profile-config",
                str(profile_path),
                "--repo-replay-profile-strict",
            )
        )
    assert _CountingRflAdapter.infer_calls == 0


def test_cli_repo_replay_profile_config_provenance_and_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-replay-profiles"
    profile_path = tmp_path / "profiles.json"
    _write_index(index_path)
    _write_profile_config(
        profile_path,
        {
            "schema_version": 1,
            "profiles": [
                {
                    "id": "repo-a",
                    "match": {"repo_remote": "https://github.com/org/repo-a"},
                    "overrides": {
                        "lean_cmd": "lake env lean",
                        "prepare_cmd": None,
                        "timeout_seconds": 30,
                        "cold_start_timeout_seconds": 60,
                    },
                }
            ],
        },
    )

    _SuccessfulReplayVerifier.reset()

    monkeypatch.setattr(cli_module, "MockAdapter", _AlwaysRflAdapter)
    monkeypatch.setattr(cli_module, "RepoReplayVerifier", _SuccessfulReplayVerifier)
    rc = _run_mock(
        index_path,
        "--verification-mode",
        "repo_replay",
        "--repo-replay-profile-config",
        str(profile_path),
        out_dir=out_dir,
    )
    assert rc == 0
    assert len(_SuccessfulReplayVerifier.init_cache_dirs) == 2
    assert any(
        cache_dir.endswith("profile-repo-a")
        for cache_dir in _SuccessfulReplayVerifier.init_cache_dirs
    )
    assert sorted(_SuccessfulReplayVerifier.prepare_batches) == [["id-1"], ["id-2"]]

    attempts = _read_attempts(out_dir / "attempts.jsonl")
    by_item = {str(attempt["item_id"]): attempt for attempt in attempts}
    assert by_item["id-1"]["repo_replay_profile_id"] == "repo-a"
    assert by_item["id-2"]["repo_replay_profile_id"] is None

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    replay_cfg = summary["verification"]["repo_replay"]
    assert replay_cfg["profile_config_path"] == str(profile_path)
    assert replay_cfg["profile_strict"] is False
    assert replay_cfg["profiles_loaded"] == ["repo-a"]
    assert replay_cfg["profile_match_counts"] == {"default": 1, "repo-a": 1}
    assert replay_cfg["preflight_repo_targets"] == 2
    assert replay_cfg["preflight_profile_targets"] == 2


def test_cli_generation_retries_infra_only_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-retry-default"
    _write_index(index_path)

    class MixedRetryAdapter:
        calls: dict[tuple[str, int], int] = {}

        def __init__(self, *, model: str = "mock-v1") -> None:
            self._model = model

        @property
        def adapter_name(self) -> str:
            return "mock"

        @property
        def model_name(self) -> str:
            return self._model

        def infer(
            self,
            row: object,
            prompt: str,
            *,
            sample_index: int,
            sample_seed: int,
        ) -> AdapterResult:
            _ = prompt
            _ = sample_seed
            item_id = getattr(row, "item_id")
            key = (item_id, sample_index)
            calls = self.calls.get(key, 0) + 1
            self.calls[key] = calls
            if item_id == "id-1":
                if calls == 1:
                    return AdapterResult(
                        raw_response="",
                        tactic="",
                        latency_ms=1,
                        error="timeout after 1.0s",
                    )
                return AdapterResult(raw_response="simp", tactic="simp", latency_ms=1, error=None)
            if calls == 1:
                return AdapterResult(
                    raw_response="",
                    tactic="",
                    latency_ms=1,
                    error="model saturation",
                )
            return AdapterResult(raw_response="simp", tactic="simp", latency_ms=1, error=None)

    monkeypatch.setattr(cli_module, "MockAdapter", MixedRetryAdapter)
    rc = _run_mock(index_path, "--generation-retry-count", "1", out_dir=out_dir)
    assert rc == 0

    attempts = _read_attempts(out_dir / "attempts.jsonl")
    attempts_by_id = {str(attempt["item_id"]): attempt for attempt in attempts}
    id_1 = attempts_by_id["id-1"]
    id_2 = attempts_by_id["id-2"]
    assert id_1["generation_retry_count"] == 1
    assert id_1["generation_recovered_after_retry"] is True
    assert id_1["generation_error_domain"] is None
    assert id_2["generation_retry_count"] == 0
    assert id_2["generation_error_domain"] == "model"
    assert id_2["generation_error_kind"] == "other"

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["runtime_reliability"]["generation_retry_policy"]["retry_domains"] == ["infra"]
    assert summary["runtime_reliability"]["generation_retry_metrics"]["retry_attempt_count"] == 1
    retry_attempted_domains = summary["runtime_reliability"]["generation_retry_metrics"][
        "retry_attempted_domains"
    ]
    assert retry_attempted_domains == {"infra": 1, "model": 0}
    assert summary["scoring"]["generation_error_domains"] == {"infra": 0, "model": 1}
    assert summary["scoring"]["generation_observed_error_domains"] == {"infra": 1, "model": 1}


def test_cli_generation_retry_kind_filter_blocks_non_matching_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-retry-kind-filter"
    _write_index(index_path)

    class InfraTimeoutAdapter:
        calls: dict[tuple[str, int], int] = {}

        def __init__(self, *, model: str = "mock-v1") -> None:
            self._model = model

        @property
        def adapter_name(self) -> str:
            return "mock"

        @property
        def model_name(self) -> str:
            return self._model

        def infer(
            self,
            row: object,
            prompt: str,
            *,
            sample_index: int,
            sample_seed: int,
        ) -> AdapterResult:
            _ = prompt
            _ = sample_seed
            key = (getattr(row, "item_id"), sample_index)
            calls = self.calls.get(key, 0) + 1
            self.calls[key] = calls
            if calls == 1:
                return AdapterResult(
                    raw_response="",
                    tactic="",
                    latency_ms=1,
                    error="timeout after 1.0s",
                )
            return AdapterResult(raw_response="simp", tactic="simp", latency_ms=1, error=None)

    monkeypatch.setattr(cli_module, "MockAdapter", InfraTimeoutAdapter)
    rc = _run_mock(
        index_path,
        "--max-items",
        "1",
        "--generation-retry-count",
        "1",
        "--generation-retry-kinds",
        "http_error",
        out_dir=out_dir,
    )
    assert rc == 0

    attempts = _read_attempts(out_dir / "attempts.jsonl")
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["generation_retry_count"] == 0
    assert attempt["generation_error_kind"] == "timeout"
    assert attempt["generation_error_domain"] == "infra"

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert (
        summary["runtime_reliability"]["generation_retry_policy"]["retry_kinds"]
        == ["http_error"]
    )
    assert summary["runtime_reliability"]["generation_retry_metrics"]["retry_attempt_count"] == 0
    assert summary["scoring"]["generation_error_domains"] == {"infra": 1, "model": 0}


def test_cli_release_readiness_and_verification_domain_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-readiness"
    _write_index(index_path)

    class InfraFailureVerifier:
        def __init__(self, config: object) -> None:
            _ = config

        def verify(self, *, goal_text: str, tactic: str) -> VerificationResult:
            _ = goal_text
            _ = tactic
            return VerificationResult(
                attempted=True,
                success=False,
                error="unknown module prefix",
                error_kind="missing_dependency",
                exit_code=1,
                latency_ms=2,
            )

    monkeypatch.setattr(cli_module, "MockAdapter", _AlwaysSimpAdapter)
    monkeypatch.setattr(cli_module, "SyntheticLeanVerifier", InfraFailureVerifier)
    rc = _run_mock(
        index_path,
        "--verification-mode",
        "synthetic",
        "--min-release-selected-items",
        "3",
        "--min-release-selected-samples",
        "3",
        out_dir=out_dir,
    )
    assert rc == 0

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    release = summary["release_reporting"]
    assert release["selected_items"] == 2
    assert release["selected_samples"] == 2
    assert release["selected_items_ready"] is False
    assert release["selected_samples_ready"] is False
    assert release["ready"] is False
    assert release["failed_requirements"] == [
        "selected_items_below_minimum: 2 < 3",
        "selected_samples_below_minimum: 2 < 3",
    ]

    verification_metrics = summary["verification"]["metrics"]
    assert verification_metrics["verification_error_domains"] == {"infra": 2, "model": 0}
    assert verification_metrics["verification_error_kinds_by_domain"]["infra"] == {
        "missing_dependency": 2
    }

    attempts = _read_attempts(out_dir / "attempts.jsonl")
    assert {attempt["verification_error_domain"] for attempt in attempts} == {"infra"}
    assert summary["scoring"]["generation_error_domains"] == {"infra": 0, "model": 0}


@pytest.mark.skipif(shutil.which("lean") is None, reason="lean binary not available")
def test_cli_mock_with_synthetic_verification(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "run-verify"
    rows = [
        {
            "item_id": "goal1",
            "repo_remote": "https://github.com/org/repo-a",
            "repo_commit": "abc",
            "repo_lean_version": "4.28.0",
            "location_path": "A.lean",
            "location_start_line": 1,
            "location_start_column": 1,
            "location_end_line": 1,
            "location_end_column": 6,
            "goal_sha256": "g1",
            "goal_text": "x : Nat\n⊢ x = x",
            "source_url": "https://github.com/org/repo-a/blob/abc/A.lean#L1",
        }
    ]
    with index_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    rc = main(
        [
            "run",
            "--index",
            str(index_path),
            "--adapter",
            "mock",
            "--model",
            "mock-v1",
            "--verification-mode",
            "synthetic",
            "--lean-cmd",
            "lean",
            "--lean-timeout-seconds",
            "60",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    verify_metrics = summary["verification"]["metrics"]
    assert summary["verification"]["mode"] == "synthetic"
    assert verify_metrics["verification_attempted_count"] == 1
    assert verify_metrics["verification_success_count"] == 1
