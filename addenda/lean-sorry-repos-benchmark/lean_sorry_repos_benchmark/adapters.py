from __future__ import annotations

import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, cast

from lean_sorry_repos_benchmark.data import BenchmarkRow


@dataclass(frozen=True)
class AdapterResult:
    raw_response: str
    tactic: str
    latency_ms: int
    error: str | None


class Adapter(Protocol):
    def infer(
        self,
        row: BenchmarkRow,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        ...

    @property
    def adapter_name(self) -> str:
        ...

    @property
    def model_name(self) -> str:
        ...


def classify_generation_error(error: str) -> str:
    lower = error.lower()
    if "timeout after" in lower:
        return "timeout"
    if lower.startswith("http "):
        return "http_error"
    if "connection refused" in lower or "failed to establish a new connection" in lower:
        return "endpoint_unreachable"
    if "name or service not known" in lower or "nodename nor servname provided" in lower:
        return "dns_error"
    if "invalid json response" in lower or "missing response field" in lower:
        return "invalid_response"
    return "other"


def generation_error_domain(kind: str) -> str:
    if kind in {
        "timeout",
        "http_error",
        "endpoint_unreachable",
        "dns_error",
        "invalid_response",
    }:
        return "infra"
    return "model"


def _extract_first_tactic(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("```lean", "```")
    if "```" in cleaned:
        parts = cleaned.split("```")
        block = parts[1] if len(parts) > 1 else parts[0]
        cleaned = block
    cleaned = cleaned.replace("[TAC]", "").replace("[/TAC]", "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


class MockAdapter:
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
        row: BenchmarkRow,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _ = prompt
        start = time.perf_counter()
        base_digest = hashlib.sha256(row.item_id.encode("utf-8")).hexdigest()
        base_token = int(base_digest[:2], 16) % 4
        if sample_index == 0:
            token = base_token
        else:
            sample_digest = hashlib.sha256(
                f"{row.item_id}:{sample_seed}".encode("utf-8")
            ).hexdigest()
            sample_token = int(sample_digest[:2], 16) % 4
            token = (base_token + sample_token + sample_index) % 4
        if token == 0:
            response = "simp"
        elif token == 1:
            response = "aesop"
        elif token == 2:
            response = "exact?"
        else:
            response = "admit"
        latency_ms = int((time.perf_counter() - start) * 1000)
        return AdapterResult(
            raw_response=response,
            tactic=_extract_first_tactic(response),
            latency_ms=latency_ms,
            error=None,
        )


class OllamaAdapter:
    def __init__(
        self,
        *,
        model: str,
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        num_predict: int = 64,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if num_predict <= 0:
            raise ValueError("num_predict must be > 0")
        self._model = model
        self._endpoint = endpoint
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._num_predict = num_predict

    @property
    def adapter_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def infer(
        self,
        row: BenchmarkRow,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _ = row
        _ = sample_index
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._num_predict,
                "seed": sample_seed,
            },
        }
        req = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:  # noqa: S310 - explicit local endpoint by default
                body = resp.read()
        except TimeoutError:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"timeout after {self._timeout_seconds:.1f}s",
            )
        except socket.timeout:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"timeout after {self._timeout_seconds:.1f}s",
            )
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"http {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            reason = exc.reason
            if isinstance(reason, TimeoutError | socket.timeout):
                error = f"timeout after {self._timeout_seconds:.1f}s"
            else:
                error = str(reason)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=error,
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return AdapterResult(
                raw_response=body.decode("utf-8", errors="replace"),
                tactic="",
                latency_ms=latency_ms,
                error="invalid json response",
            )
        if not isinstance(data, dict):
            return AdapterResult(
                raw_response=str(data),
                tactic="",
                latency_ms=latency_ms,
                error="invalid response object",
            )
        text = data.get("response")
        if not isinstance(text, str):
            return AdapterResult(
                raw_response=json.dumps(data, sort_keys=True),
                tactic="",
                latency_ms=latency_ms,
                error="missing response field",
            )
        return AdapterResult(
            raw_response=text,
            tactic=_extract_first_tactic(text),
            latency_ms=latency_ms,
            error=None,
        )


def _extract_openai_message_content(message: object) -> str | None:
    if not isinstance(message, dict):
        return None
    message_obj = cast(dict[str, object], message)
    content = message_obj.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_obj = cast(dict[str, object], part)
            text = part_obj.get("text")
            if isinstance(text, str):
                chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    return None


def _extract_openai_choice_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    payload_obj = cast(dict[str, object], payload)
    choices = payload_obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    first_obj = cast(dict[str, object], first)
    text = first_obj.get("text")
    if isinstance(text, str):
        return text
    return _extract_openai_message_content(first_obj.get("message"))


class OpenAIAdapter:
    def __init__(
        self,
        *,
        model: str,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
        api_key: str,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_tokens: int = 64,
        organization: str | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be non-empty")
        if not endpoint.strip():
            raise ValueError("endpoint must be non-empty")
        if not api_key.strip():
            raise ValueError("api_key must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        self._model = model
        self._endpoint = endpoint
        self._api_key = api_key
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._organization = organization.strip() if organization is not None else None

    @property
    def adapter_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def infer(
        self,
        row: BenchmarkRow,
        prompt: str,
        *,
        sample_index: int,
        sample_seed: int,
    ) -> AdapterResult:
        _ = row
        _ = sample_index
        _ = sample_seed
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        req = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:  # noqa: S310 - caller controls endpoint and key
                body = resp.read()
        except TimeoutError:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"timeout after {self._timeout_seconds:.1f}s",
            )
        except socket.timeout:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"timeout after {self._timeout_seconds:.1f}s",
            )
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=f"http {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            reason = exc.reason
            if isinstance(reason, TimeoutError | socket.timeout):
                error = f"timeout after {self._timeout_seconds:.1f}s"
            else:
                error = str(reason)
            return AdapterResult(
                raw_response="",
                tactic="",
                latency_ms=latency_ms,
                error=error,
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return AdapterResult(
                raw_response=body.decode("utf-8", errors="replace"),
                tactic="",
                latency_ms=latency_ms,
                error="invalid json response",
            )
        text = _extract_openai_choice_text(data)
        if text is None:
            raw_response = (
                json.dumps(data, sort_keys=True)
                if isinstance(data, (dict, list))
                else str(data)
            )
            return AdapterResult(
                raw_response=raw_response,
                tactic="",
                latency_ms=latency_ms,
                error="missing response field",
            )
        return AdapterResult(
            raw_response=text,
            tactic=_extract_first_tactic(text),
            latency_ms=latency_ms,
            error=None,
        )
