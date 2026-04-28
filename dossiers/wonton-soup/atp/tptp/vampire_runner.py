from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SZS_SOLVED = {"Theorem", "Unsatisfiable", "Contradictory"}


@dataclass(frozen=True)
class VampireConfig:
    binary: str = "vampire"
    timeout_sec: int = 30
    extra_args: list[str] | None = None


def _extract_szs_status(output: str) -> str | None:
    for line in output.splitlines():
        if "SZS status" in line:
            match = re.search(r"SZS status\s+([A-Za-z]+)", line)
            if match:
                return match.group(1)
    return None


def _run_vampire(problem: Path, config: VampireConfig, cwd: Path | None) -> str:
    args = [config.binary]
    if config.extra_args:
        args.extend(config.extra_args)
    args.append(str(problem))
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=config.timeout_sec,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Vampire not found: {config.binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Vampire timed out after {config.timeout_sec}s") from exc
    return result.stdout + "\n" + result.stderr

