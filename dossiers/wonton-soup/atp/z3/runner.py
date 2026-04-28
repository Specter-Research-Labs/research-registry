from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Z3Config:
    binary: str = "z3"
    timeout_sec: int = 30
    extra_args: list[str] | None = None


def _prepare_input(problem: Path) -> str:
    content = problem.read_text()
    if "(set-option :produce-proofs true)" not in content:
        content = "(set-option :produce-proofs true)\n" + content
    if "(get-proof)" not in content:
        if "(exit)" in content:
            before, after = content.rsplit("(exit)", 1)
            content = before.rstrip() + "\n(get-proof)\n(exit)" + after
        else:
            content = content + "\n(get-proof)\n"
    return content


def _run_z3(input_text: str, config: Z3Config) -> str:
    args = [config.binary, "-smt2", "-in"]
    if config.extra_args:
        args.extend(config.extra_args)
    try:
        result = subprocess.run(
            args,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=config.timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Z3 not found: {config.binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Z3 timed out after {config.timeout_sec}s") from exc
    return result.stdout + "\n" + result.stderr


def _extract_status(output: str) -> str | None:
    for line in output.splitlines():
        token = line.strip()
        if token in {"sat", "unsat", "unknown"}:
            return token
    return None

