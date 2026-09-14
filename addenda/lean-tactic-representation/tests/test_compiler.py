from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from core.compiler_artifacts import (
    CompilerError,
    compare_prediction_with_lean,
    run_compiler,
    run_compiler_pipeline,
)
from core.lean_artifacts import LeanBridgeError, validate_lean_response

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def built_binaries() -> None:
    subprocess.run(
        ["lake", "build", "tactic_compile", "tactic_bridge"],
        cwd=ROOT,
        check=True,
    )


@pytest.fixture(scope="module")
def constructor_receipt() -> dict:
    return run_compiler_pipeline(
        ROOT / "scenarios/source/constructor.json", project_root=ROOT, build=False
    )


@pytest.mark.parametrize(
    ("scenario", "operators"),
    [
        ("constructor.json", ["constructor", "exact", "exact"]),
        ("apply.json", ["apply", "exact", "exact"]),
    ],
)
def test_compiler_execution_agrees_and_kernel_accepts(
    scenario: str, operators: list[str]
) -> None:
    receipt = run_compiler_pipeline(
        ROOT / "scenarios/source" / scenario, project_root=ROOT, build=False
    )

    assert receipt["agreement"] == {"passed": True, "failed": []}
    assert [
        step["operator"] for step in receipt["lean"]["execution"]["steps"]
    ] == operators
    certificate = receipt["lean"]["kernel_certificate"]
    assert {key: certificate[key] for key in (
        "kernel_checked", "definitionally_equal", "open_metavariables", "uses_sorry"
    )} == {
        "kernel_checked": True,
        "definitionally_equal": True,
        "open_metavariables": 0,
        "uses_sorry": False,
    }


def test_compiler_rejects_invalid_source_before_lean(tmp_path: Path) -> None:
    source = json.loads((ROOT / "scenarios/source/apply.json").read_text())
    source["code"] = [{"op": "exact", "hypothesis": "missing"}]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(CompilerError, match="unknown hypothesis"):
        run_compiler(path, project_root=ROOT, build=False)


def test_kernel_and_correspondence_checks_fail_closed(constructor_receipt: dict) -> None:
    bad_kernel = copy.deepcopy(constructor_receipt["lean"])
    bad_kernel["kernel_certificate"]["kernel_checked"] = False
    with pytest.raises(LeanBridgeError, match="kernel_checked"):
        validate_lean_response(bad_kernel)

    bad_trace = copy.deepcopy(constructor_receipt["lean"])
    bad_trace["execution"]["steps"][0]["operator"] = "exact"
    agreement = compare_prediction_with_lean(constructor_receipt["compiler"], bad_trace)
    assert agreement == {"passed": False, "failed": ["step 0"]}
