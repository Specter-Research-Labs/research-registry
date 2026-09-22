from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.lean_artifacts import run_lean_request


class CompilerError(RuntimeError):
    """The pure compiler failed or disagreed with Lean execution."""


def run_compiler(
    input_path: str | Path,
    *,
    project_root: str | Path | None = None,
    build: bool = True,
) -> dict[str, Any]:
    root = _project_root(project_root)
    source_path = Path(input_path).resolve()
    binary = root / ".lake" / "build" / "bin" / "tactic_compile"
    if build:
        _build(root, "tactic_compile")
    if not binary.is_file():
        raise CompilerError(f"compiler binary is missing: {binary}")
    completed = subprocess.run(
        [str(binary), "--input", str(source_path)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = _error_detail(completed.stderr.strip() or completed.stdout.strip())
        raise CompilerError(f"compiler rejected {source_path.name}: {detail}")
    response = _json_object(completed.stdout)
    validate_compiler_response(response)
    return response


def run_compiler_pipeline(
    input_path: str | Path,
    *,
    project_root: str | Path | None = None,
    build: bool = True,
) -> dict[str, Any]:
    root = _project_root(project_root)
    if build:
        _build(root, "tactic_compile", "tactic_bridge")
    compiler = run_compiler(input_path, project_root=root, build=False)
    target = _object(_object(compiler, "compilation"), "target_request")
    with tempfile.TemporaryDirectory(prefix="tactic-compiler-") as raw:
        path = Path(raw) / "target.json"
        path.write_text(json.dumps(target), encoding="utf-8")
        lean = run_lean_request(path, project_root=root, build=False)
    agreement = compare_prediction_with_lean(compiler, lean)
    if not agreement["passed"]:
        raise CompilerError(f"compiler prediction disagreed with Lean: {agreement['failed']}")
    return {
        "schema_version": 1,
        "status": "success",
        "compiler": compiler,
        "agreement": agreement,
        "lean": lean,
    }


def validate_compiler_response(response: dict[str, Any]) -> None:
    if response.get("schema_version") != 1 or response.get("status") != "success":
        raise CompilerError("expected a successful v1 compiler response")
    source = _object(response, "source")
    if source.get("round_trip_checked") is not True:
        raise CompilerError("source serialization did not round-trip")
    canonical = _object(source, "canonical_source")
    compilation = _object(response, "compilation")
    target = _object(compilation, "target_request")
    required = {
        "pure_compiler_no_metam",
        "source_goal_stack_exhausted",
        "target_request_validated",
    }
    if not required.issubset(set(_string_list(compilation, "certificates"))):
        raise CompilerError("compiler omitted a required invariant certificate")
    code = _object_list(canonical, "code")
    prediction = _object_list(compilation, "prediction")
    if compilation.get("instruction_count") != len(code) or len(prediction) != len(code):
        raise CompilerError("compiler instruction and prediction counts disagree")
    for key in ("schema_version", "request_id", "imports", "problem"):
        if canonical.get(key) != target.get(key):
            raise CompilerError(f"lowered request changed source field {key}")
    _object(target, "program")

    by_goal: dict[str, dict[str, Any]] = {}
    child_ids: set[str] = set()
    for step in prediction:
        goal_id = step.get("goal_id")
        if not isinstance(goal_id, str) or goal_id in by_goal:
            raise CompilerError("predicted goal ids must be unique strings")
        children = _object_list(step, "children")
        ids = [child.get("goal_id") for child in children]
        if step.get("branch_arity") != len(children) or step.get("child_order") != ids:
            raise CompilerError(f"predicted branch shape does not match {goal_id}")
        by_goal[goal_id] = step
        child_ids.update(value for value in ids if isinstance(value, str))
    if "g0" not in by_goal or child_ids.difference(by_goal):
        raise CompilerError("prediction contains an unresolved goal")
    if set(by_goal).difference({"g0"}, child_ids):
        raise CompilerError("prediction contains an unreachable step")


def compare_prediction_with_lean(
    compiler: dict[str, Any], lean: dict[str, Any]
) -> dict[str, Any]:
    validate_compiler_response(compiler)
    compilation = _object(compiler, "compilation")
    expected = _object_list(compilation, "prediction")
    serialization = _object(lean, "serialization")
    actual = _object_list(_object(lean, "execution"), "steps")
    failed: list[str] = []
    if _object(compilation, "target_request") != _object(serialization, "canonical_request"):
        failed.append("lowered request")
    if len(expected) != len(actual):
        failed.append("step count")
    for index, (predicted, observed) in enumerate(zip(expected, actual, strict=False)):
        projected_expected = {
            "goal_id": predicted.get("goal_id"),
            "operator": predicted.get("operator"),
            "resolved_term": predicted.get("resolved_term"),
            "branch_arity": predicted.get("branch_arity"),
            "continuation_kind": predicted.get("continuation_kind"),
            "target": predicted.get("target"),
            "children": [
                {"goal_id": child.get("goal_id"), "target": child.get("target")}
                for child in _object_list(predicted, "children")
            ],
            "coupling": predicted.get("coupling"),
            "child_order": predicted.get("child_order"),
            "residual": predicted.get("residual_template"),
        }
        projected_actual = {
            "goal_id": observed.get("goal_id"),
            "operator": observed.get("operator"),
            "resolved_term": observed.get("resolved_term"),
            "branch_arity": observed.get("branch_arity"),
            "continuation_kind": observed.get("continuation_kind"),
            "target": observed.get("target_ir"),
            "children": [
                {"goal_id": child.get("goal_id"), "target": child.get("target_ir")}
                for child in _object_list(observed, "children")
            ],
            "coupling": observed.get("coupling"),
            "child_order": _object(observed, "residual_builder").get("child_order"),
            "residual": observed.get("partial_term_after"),
        }
        if projected_expected != projected_actual:
            failed.append(f"step {index}")
    return {"passed": not failed, "failed": failed}


def compiler_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    compilation = _object(_object(receipt, "compiler"), "compilation")
    certificate = _object(_object(receipt, "lean"), "kernel_certificate")
    return {
        "request_id": _object(compilation, "target_request").get("request_id"),
        "instructions": compilation.get("instruction_count"),
        "agreement": _object(receipt, "agreement").get("passed"),
        "kernel_checked": certificate.get("kernel_checked"),
        "open_metavariables": certificate.get("open_metavariables"),
        "uses_sorry": certificate.get("uses_sorry"),
    }


def _project_root(project_root: str | Path | None) -> Path:
    return Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]


def _build(root: Path, *targets: str) -> None:
    built = subprocess.run(
        ["lake", "build", *targets], cwd=root, check=False, capture_output=True, text=True
    )
    if built.returncode != 0:
        raise CompilerError(f"Lean build failed:\n{(built.stderr or built.stdout).strip()}")


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CompilerError("compiler returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise CompilerError("compiler response must be an object")
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
        raise CompilerError(f"{key} must be an object")
    return value


def _object_list(mapping: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CompilerError(f"{key} must be a list of objects")
    return value


def _string_list(mapping: dict[str, Any], key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CompilerError(f"{key} must be a list of strings")
    return value
