from __future__ import annotations

import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

GOAL_MARKER = "⊢"


@dataclass(frozen=True)
class SyntheticVerificationConfig:
    lean_cmd: str
    timeout_seconds: float
    imports: tuple[str, ...]
    error_kind: str | None
    workdir: Path | None
    max_error_chars: int = 400


@dataclass(frozen=True)
class VerificationResult:
    attempted: bool
    success: bool
    error: str | None
    error_kind: str | None
    exit_code: int | None
    latency_ms: int


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _trim_error(text: str, *, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3] + "..."


def classify_verification_error(error: str) -> str:
    lower = error.lower()
    if "timeout after" in lower:
        return "timeout"
    if "git clone failed" in lower:
        return "git_clone_failed"
    if "git fetch failed" in lower:
        return "git_fetch_failed"
    if "git checkout failed" in lower:
        return "git_checkout_failed"
    if "prepare command failed" in lower:
        return "prepare_failed"
    if "file not found" in lower or "no such file or directory" in lower:
        return "missing_file"
    if "target file missing" in lower:
        return "target_file_missing"
    if "unknown module prefix" in lower or "unknown package" in lower:
        return "missing_dependency"
    if "repository setup previously failed" in lower:
        return "repo_setup_failed"
    if "invalid location span" in lower:
        return "invalid_span"
    if "unknown constant" in lower or "unknown identifier" in lower:
        return "unknown_identifier"
    if "type mismatch" in lower:
        return "type_mismatch"
    if "unsolved goals" in lower or "goals to be solved" in lower:
        return "unsolved_goals"
    if "unexpected token" in lower or "unexpected end of input" in lower:
        return "parse_error"
    if "empty tactic" in lower:
        return "empty_tactic"
    if "goal_text missing goal marker" in lower or "empty goal_text" in lower:
        return "invalid_goal_state"
    return "other"


def verification_error_domain(kind: str | None) -> str | None:
    if kind is None:
        return None
    if kind in {
        "timeout",
        "git_clone_failed",
        "git_fetch_failed",
        "git_checkout_failed",
        "prepare_failed",
        "missing_file",
        "target_file_missing",
        "missing_dependency",
        "repo_setup_failed",
        "invalid_span",
        "invalid_goal_state",
    }:
        return "infra"
    if kind in {
        "unknown_identifier",
        "type_mismatch",
        "unsolved_goals",
        "parse_error",
        "empty_tactic",
        "other",
    }:
        return "model"
    return "model"


def _split_goal_state(goal_text: str) -> tuple[list[str], str]:
    lines = [line.rstrip() for line in goal_text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and lines[0].strip().startswith("case "):
        lines.pop(0)
    if not lines:
        raise ValueError("empty goal_text")

    marker_idx = -1
    marker_prefix = ""
    marker_suffix = ""
    for idx, line in enumerate(lines):
        if GOAL_MARKER in line:
            marker_idx = idx
            marker_prefix, marker_suffix = line.split(GOAL_MARKER, 1)
            break
    if marker_idx < 0:
        raise ValueError("goal_text missing goal marker `⊢`")

    context_lines: list[str] = []
    for raw in lines[:marker_idx]:
        text = raw.strip()
        if not text or text.startswith("case "):
            continue
        if ":=" in text and ":" in text:
            text = text.split(":=", 1)[0].rstrip()
        compact = _collapse_whitespace(text)
        if compact:
            context_lines.append(compact)

    if marker_prefix.strip():
        compact = _collapse_whitespace(marker_prefix.strip())
        if compact:
            context_lines.append(compact)

    goal_parts: list[str] = []
    first = marker_suffix.strip()
    if first:
        goal_parts.append(first)
    for raw in lines[marker_idx + 1 :]:
        text = raw.strip()
        if text:
            goal_parts.append(text)
    goal_expr = _collapse_whitespace(" ".join(goal_parts))
    if not goal_expr:
        raise ValueError("goal_text has empty goal after `⊢`")
    return context_lines, goal_expr


def build_synthetic_script(
    *,
    goal_text: str,
    tactic: str,
    imports: tuple[str, ...],
) -> str:
    tactic_line = tactic.strip()
    if not tactic_line:
        raise ValueError("empty tactic")
    if "\n" in tactic_line:
        lines = [line.strip() for line in tactic_line.splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty tactic")
        tactic_line = lines[0]

    context_lines, goal_expr = _split_goal_state(goal_text)

    script_lines: list[str] = []
    for module in imports:
        module_name = module.strip()
        if not module_name:
            continue
        script_lines.append(f"import {module_name}")
    if script_lines:
        script_lines.append("")
    script_lines.append("set_option autoImplicit false")
    script_lines.append("")
    script_lines.append("example")
    for context in context_lines:
        script_lines.append(f"  ({context})")
    script_lines.append(f"  : {goal_expr} := by")
    script_lines.append(f"  {tactic_line}")
    script_lines.append("")
    return "\n".join(script_lines)


class SyntheticLeanVerifier:
    def __init__(self, config: SyntheticVerificationConfig) -> None:
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if not config.lean_cmd.strip():
            raise ValueError("lean_cmd must be non-empty")
        self._config = config
        self._lean_argv = shlex.split(config.lean_cmd)
        if not self._lean_argv:
            raise ValueError("lean_cmd must parse into an argv")

    def verify(self, *, goal_text: str, tactic: str) -> VerificationResult:
        start = time.perf_counter()
        try:
            script = build_synthetic_script(
                goal_text=goal_text,
                tactic=tactic,
                imports=self._config.imports,
            )
        except ValueError as exc:
            return VerificationResult(
                attempted=True,
                success=False,
                error=str(exc),
                error_kind=classify_verification_error(str(exc)),
                exit_code=None,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".lean",
            encoding="utf-8",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(script)

        cmd = [*self._lean_argv]
        if self._config.error_kind:
            cmd.extend(["-E", self._config.error_kind])
        cmd.append(str(tmp_path))

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._config.workdir) if self._config.workdir is not None else None,
                capture_output=True,
                text=True,
                timeout=self._config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            tmp_path.unlink(missing_ok=True)
            return VerificationResult(
                attempted=True,
                success=False,
                error=str(exc),
                error_kind=classify_verification_error(str(exc)),
                exit_code=None,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except subprocess.TimeoutExpired:
            tmp_path.unlink(missing_ok=True)
            timeout_error = f"timeout after {self._config.timeout_seconds:.1f}s"
            return VerificationResult(
                attempted=True,
                success=False,
                error=timeout_error,
                error_kind=classify_verification_error(timeout_error),
                exit_code=None,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        latency_ms = int((time.perf_counter() - start) * 1000)
        if proc.returncode == 0:
            return VerificationResult(
                attempted=True,
                success=True,
                error=None,
                error_kind=None,
                exit_code=0,
                latency_ms=latency_ms,
            )

        combined = (proc.stdout + "\n" + proc.stderr).strip()
        if not combined:
            combined = f"lean exited with code {proc.returncode}"
        trimmed = _trim_error(combined, max_chars=self._config.max_error_chars)
        return VerificationResult(
            attempted=True,
            success=False,
            error=trimmed,
            error_kind=classify_verification_error(trimmed),
            exit_code=proc.returncode,
            latency_ms=latency_ms,
        )
