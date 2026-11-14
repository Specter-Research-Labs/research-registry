import hashlib
import json
from pathlib import Path

import pytest

from orchestrator import provenance
from orchestrator.lean_runner import _premise_interventions
from prover.dependencies import CheckStatus, KernelCheck
from prover.providers.weights import local_weights, pinned_revision


def _check(status: CheckStatus, premises: tuple[str, ...]) -> KernelCheck:
    return KernelCheck(
        status=status,
        error=None,
        tactics=("simp",),
        term_hash="0" * 64,
        premises=premises,
        self_citation=None,
        blocked_hits=(),
    )


def test_premise_lesions_come_only_from_checked_proofs() -> None:
    lesions = _premise_interventions(_check("checked", ("List.append_nil", "Nat.add_zero")))
    assert [(i.name, i.blocked, i.blocked_premises) for i in lesions] == [
        ("block_premise_List.append_nil", set(), frozenset({"List.append_nil"})),
        ("block_premise_Nat.add_zero", set(), frozenset({"Nat.add_zero"})),
    ]
    assert _premise_interventions(_check("check_failed", ("Nat.add_zero",))) == []
    assert _premise_interventions(None) == []


def test_local_weights_hash_every_weight_file(tmp_path: Path) -> None:
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    (tmp_path / "config.json").write_text("{}")
    assert local_weights(tmp_path)["weights_sha256"] == {
        "model.safetensors": hashlib.sha256(b"weights").hexdigest()
    }


def test_local_weights_require_weight_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        local_weights(tmp_path)


def test_unpinned_model_is_rejected() -> None:
    with pytest.raises(KeyError, match="no pinned revision"):
        pinned_revision("someone/unpinned-model")


def test_lean_provenance_reads_mathlib_rev_from_manifest(tmp_path: Path) -> None:
    (tmp_path / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
    (tmp_path / "lake-manifest.json").write_text(
        json.dumps({"name": "proj", "packages": [{"name": "mathlib", "rev": "abc123"}]})
    )
    assert provenance.lean_provenance(tmp_path) == {
        "toolchain": "leanprover/lean4:v4.25.0",
        "mathlib": {"source": "lake-manifest", "rev": "abc123", "dirty": False},
    }


def test_resume_rejects_changed_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        provenance, "source_provenance", lambda: ({"base_commit": "new", "dirty": True}, b"diff")
    )
    monkeypatch.setattr(provenance, "lean_provenance", lambda _path: {"toolchain": "t"})
    monkeypatch.setattr(provenance, "python_provenance", lambda: {"leantree": "x"})
    (tmp_path / "run_config.json").write_text(
        json.dumps({"provenance": {"source": {"base_commit": "old"}}})
    )
    with pytest.raises(RuntimeError, match="provenance changed"):
        provenance.record_run_provenance(tmp_path, tmp_path, resume=True)

    recorded = provenance.record_run_provenance(tmp_path, tmp_path, resume=False)
    assert recorded["tactic_limit"]["kind"] == "heartbeats"
    assert (tmp_path / provenance.SOURCE_PATCH_NAME).read_bytes() == b"diff"
