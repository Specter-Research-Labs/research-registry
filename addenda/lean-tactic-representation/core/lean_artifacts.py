from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class LeanBridgeError(RuntimeError):
    """The Lean bridge could not build, execute, or certify a request."""


def run_lean_request(
    input_path: str | Path,
    *,
    project_root: str | Path | None = None,
    build: bool = True,
) -> dict[str, Any]:
    root = _project_root(project_root)
    request_path = Path(input_path).resolve()
    binary = root / ".lake" / "build" / "bin" / "tactic_bridge"
    if build:
        _build(root, "tactic_bridge")
    if not binary.is_file():
        raise LeanBridgeError(f"Lean bridge binary is missing: {binary}")

    completed = subprocess.run(
        [str(binary), "--input", str(request_path)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = _error_detail(completed.stderr.strip() or completed.stdout.strip())
        raise LeanBridgeError(f"Lean bridge rejected {request_path.name}: {detail}")
    response = _json_object(completed.stdout, "Lean bridge")
    validate_lean_response(response)
    return response


def validate_lean_response(response: dict[str, Any]) -> None:
    """Validate only the execution and kernel invariants used by the bridge."""
    if response.get("schema_version") != 1 or response.get("status") != "success":
        raise LeanBridgeError("expected a successful v1 Lean response")
    certificate = _object(response, "kernel_certificate")
    required = {
        "kernel_checked": True,
        "definitionally_equal": True,
        "open_metavariables": 0,
        "uses_sorry": False,
    }
    for key, expected in required.items():
        if certificate.get(key) != expected:
            raise LeanBridgeError(f"kernel certificate requires {key}={expected!r}")

    serialization = _object(response, "serialization")
    if serialization.get("round_trip_checked") is not True:
        raise LeanBridgeError("request serialization did not round-trip")
    _object(serialization, "canonical_request")

    execution = _object(response, "execution")
    root = execution.get("root_goal_id")
    steps = _object_list(execution, "steps")
    if not isinstance(root, str) or not steps:
        raise LeanBridgeError("execution must have a root and at least one step")
    by_goal: dict[str, dict[str, Any]] = {}
    child_ids: set[str] = set()
    for step in steps:
        goal_id = step.get("goal_id")
        if not isinstance(goal_id, str) or goal_id in by_goal:
            raise LeanBridgeError("execution goal ids must be unique strings")
        children = _object_list(step, "children")
        ids = [child.get("goal_id") for child in children]
        if step.get("branch_arity") != len(children):
            raise LeanBridgeError(f"branch arity does not match {goal_id}")
        if _object(step, "residual_builder").get("child_order") != ids:
            raise LeanBridgeError(f"residual child order does not match {goal_id}")
        by_goal[goal_id] = step
        child_ids.update(value for value in ids if isinstance(value, str))
    if root not in by_goal or child_ids.difference(by_goal):
        raise LeanBridgeError("execution contains an unresolved obligation")
    if set(by_goal).difference({root}, child_ids):
        raise LeanBridgeError("execution contains an unreachable step")


def lean_summary(response: dict[str, Any]) -> dict[str, Any]:
    validate_lean_response(response)
    certificate = _object(response, "kernel_certificate")
    execution = _object(response, "execution")
    return {
        "request_id": response.get("request_id"),
        "steps": len(_object_list(execution, "steps")),
        "kernel_checked": certificate["kernel_checked"],
        "open_metavariables": certificate["open_metavariables"],
        "uses_sorry": certificate["uses_sorry"],
    }


def _project_root(project_root: str | Path | None) -> Path:
    return Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]


def _build(root: Path, *targets: str) -> None:
    built = subprocess.run(
        ["lake", "build", *targets], cwd=root, check=False, capture_output=True, text=True
    )
    if built.returncode != 0:
        raise LeanBridgeError(f"Lean build failed:\n{(built.stderr or built.stdout).strip()}")


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LeanBridgeError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LeanBridgeError(f"{label} response must be an object")
    return value


def _error_detail(raw: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return value.get("message", raw) if isinstance(value, dict) else raw


def _object(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise LeanBridgeError(f"{key} must be an object")
    return value


def _object_list(mapping: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LeanBridgeError(f"{key} must be a list of objects")
    return value
