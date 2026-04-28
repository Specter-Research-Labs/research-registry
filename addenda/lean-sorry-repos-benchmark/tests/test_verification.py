from __future__ import annotations

import shutil

import pytest

from lean_sorry_repos_benchmark.verification import (
    SyntheticLeanVerifier,
    SyntheticVerificationConfig,
    build_synthetic_script,
    classify_verification_error,
    verification_error_domain,
)


def test_build_synthetic_script_simple_goal() -> None:
    script = build_synthetic_script(
        goal_text="x : Nat\n⊢ x = x",
        tactic="rfl",
        imports=(),
    )
    assert "example" in script
    assert "(x : Nat)" in script
    assert ": x = x := by" in script
    assert script.strip().endswith("rfl")


def test_build_synthetic_script_missing_goal_marker_raises() -> None:
    with pytest.raises(ValueError, match="goal marker"):
        build_synthetic_script(
            goal_text="x : Nat",
            tactic="rfl",
            imports=(),
        )


def test_classify_verification_error_known_cases() -> None:
    assert classify_verification_error("timeout after 1.0s") == "timeout"
    assert classify_verification_error("unknown identifier 'x'") == "unknown_identifier"
    assert classify_verification_error("type mismatch") == "type_mismatch"
    assert verification_error_domain("missing_dependency") == "infra"
    assert verification_error_domain("unknown_identifier") == "model"


@pytest.mark.skipif(shutil.which("lean") is None, reason="lean binary not available")
def test_synthetic_verifier_executes_lean() -> None:
    verifier = SyntheticLeanVerifier(
        SyntheticVerificationConfig(
            lean_cmd="lean",
            timeout_seconds=10.0,
            imports=(),
            error_kind="warning",
            workdir=None,
        )
    )
    ok = verifier.verify(goal_text="x : Nat\n⊢ x = x", tactic="rfl")
    assert ok.attempted is True
    assert ok.success is True
    assert ok.error is None
    assert ok.error_kind is None

    bad = verifier.verify(goal_text="x : Nat\n⊢ x = x", tactic="exact False")
    assert bad.attempted is True
    assert bad.success is False
    assert bad.error is not None
    assert bad.error_kind is not None
