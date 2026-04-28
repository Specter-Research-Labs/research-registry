from __future__ import annotations

import os
import select
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from atp.sexp import parse_sexpr


@dataclass(frozen=True)
class SerapiConfig:
    binary: str = "sertop"
    extra_args: list[str] = field(default_factory=lambda: ["--print0"])
    read_timeout_sec: float = 30.0


class SerapiSession:
    def __init__(self, config: SerapiConfig | None = None) -> None:
        if config is None:
            config = SerapiConfig()
        args = [config.binary]
        args.extend(config.extra_args)
        self._timeout = config.read_timeout_sec
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._buffer = b""
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Failed to start SerAPI session")

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)

    def _read_chunk(self) -> str:
        if self.proc.stdout is None:
            raise RuntimeError("SerAPI stdout unavailable")
        while True:
            nul = self._buffer.find(b"\0")
            if nul != -1:
                chunk = self._buffer[:nul]
                self._buffer = self._buffer[nul + 1 :]
                return chunk.decode("utf-8", errors="replace").strip()
            self._wait_for_output()
            data = os.read(self.proc.stdout.fileno(), 4096)
            if not data:
                if self._buffer:
                    chunk = self._buffer
                    self._buffer = b""
                    return chunk.decode("utf-8", errors="replace").strip()
                return ""
            self._buffer += data

    def _wait_for_output(self) -> None:
        if self.proc.stdout is None:
            raise RuntimeError("SerAPI stdout unavailable")
        start = time.time()
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError("SerAPI terminated unexpectedly")
            remaining = self._timeout - (time.time() - start)
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for SerAPI output")
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if ready:
                return

    def _read_responses(self) -> list[Any]:
        responses: list[Any] = []
        while True:
            raw = self._read_chunk()
            if not raw:
                break
            try:
                responses.append(parse_sexpr(raw))
            except Exception:
                continue
            if _is_completed(responses[-1]):
                break
        return responses

    def send(self, command: str) -> list[Any]:
        if self.proc.stdin is None:
            raise RuntimeError("SerAPI stdin unavailable")
        self.proc.stdin.write((command + "\n").encode())
        self.proc.stdin.flush()
        return self._read_responses()


def _find_int(token: Any) -> int | None:
    if isinstance(token, int):
        return token
    if isinstance(token, str) and token.isdigit():
        return int(token)
    return None


def extract_added_state(responses: list[Any]) -> int | None:
    for resp in responses:
        if not isinstance(resp, list):
            continue
        for item in resp:
            if isinstance(item, list) and item and item[0] == "Added":
                for entry in item[1:]:
                    value = _find_int(entry)
                    if value is not None:
                        return value
    return None


def extract_constr_sexpr(responses: list[Any]) -> Any | None:
    def visit(node: Any) -> Any | None:
        if isinstance(node, list) and node:
            head = node[0]
            if isinstance(head, str) and head in {"Constr", "CoqConstr"}:
                return node
            for child in node:
                found = visit(child)
                if found is not None:
                    return found
        return None

    for resp in responses:
        found = visit(resp)
        if found is not None:
            return found
    return None


def _decode_serapi_quoted_token(token: str, prefix: str) -> str | None:
    if not token.startswith(prefix) or not token.endswith('"'):
        return None
    raw = token[len(prefix) : -1]
    try:
        # SerAPI uses C-style escapes in quoted payloads.
        return bytes(raw, "utf-8").decode("unicode_escape")
    except Exception:
        return raw


def extract_feedback_strings(responses: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, str):
            decoded = _decode_serapi_quoted_token(node, 'str"')
            if decoded is not None and decoded not in seen:
                seen.add(decoded)
                out.append(decoded)
            return
        if isinstance(node, list):
            for child in node:
                visit(child)

    for response in responses:
        visit(response)
    return out


def _is_completed(response: Any) -> bool:
    return (
        isinstance(response, list)
        and len(response) >= 3
        and response[0] == "Answer"
        and response[-1] == "Completed"
    )
