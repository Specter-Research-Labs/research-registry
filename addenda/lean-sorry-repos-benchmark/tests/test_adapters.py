from __future__ import annotations

import json

import pytest

import lean_sorry_repos_benchmark.adapters as adapters_module
from lean_sorry_repos_benchmark.adapters import OpenAIAdapter
from lean_sorry_repos_benchmark.data import BenchmarkRow


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        _ = exc_type
        _ = exc
        _ = tb
        return False

    def read(self) -> bytes:
        return self._body


def _row() -> BenchmarkRow:
    return BenchmarkRow(
        item_id="row-1",
        repo_remote="https://example.invalid/repo",
        repo_commit="abc",
        repo_lean_version="4.28.0",
        location_path="Main.lean",
        location_start_line=1,
        location_start_column=1,
        location_end_line=1,
        location_end_column=6,
        goal_sha256="goal",
        goal_text="x : Nat\n⊢ x = x",
        goal_bucket="core_easy",
        source_url="https://example.invalid/repo/blob/abc/Main.lean#L1",
        raw={},
    )


def test_openai_adapter_reads_message_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(req: object, timeout: float) -> _FakeHTTPResponse:
        _ = timeout
        assert isinstance(req, adapters_module.urllib.request.Request)
        assert req.headers["Authorization"] == "Bearer sk-test"
        payload = {
            "choices": [{"message": {"content": "simp\nexact? should not be used"}}],
        }
        return _FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(adapters_module.urllib.request, "urlopen", _fake_urlopen)
    adapter = OpenAIAdapter(model="gpt-test", api_key="sk-test")
    result = adapter.infer(_row(), "prompt", sample_index=0, sample_seed=7)
    assert result.error is None
    assert result.tactic == "simp"
    assert result.raw_response.startswith("simp")


def test_openai_adapter_reads_structured_content_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(req: object, timeout: float) -> _FakeHTTPResponse:
        _ = req
        _ = timeout
        payload = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "rfl"},
                            {"type": "text", "text": "trailing"},
                        ]
                    }
                }
            ],
        }
        return _FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(adapters_module.urllib.request, "urlopen", _fake_urlopen)
    adapter = OpenAIAdapter(model="kimi-k2", api_key="sk-test")
    result = adapter.infer(_row(), "prompt", sample_index=0, sample_seed=7)
    assert result.error is None
    assert result.tactic == "rfl"


def test_openai_adapter_reports_missing_response_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(req: object, timeout: float) -> _FakeHTTPResponse:
        _ = req
        _ = timeout
        return _FakeHTTPResponse(b'{"choices":[]}')

    monkeypatch.setattr(adapters_module.urllib.request, "urlopen", _fake_urlopen)
    adapter = OpenAIAdapter(model="glm-4", api_key="sk-test")
    result = adapter.infer(_row(), "prompt", sample_index=0, sample_seed=7)
    assert result.error == "missing response field"
    assert result.tactic == ""
