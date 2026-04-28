from __future__ import annotations

import json

from atp.log_writer import ExternalRunWriter


def test_write_run_status_preserves_existing_started_at_and_capabilities(tmp_path) -> None:
    writer = ExternalRunWriter(tmp_path, {"provider": "coq", "corpus": "coq"})
    writer.write_run_status(status="running", started_at="2026-03-06T12:00:00Z")

    status_path = tmp_path / "run_status.json"
    payload = json.loads(status_path.read_text())
    payload["capabilities"] = {
        "has_proof_term": True,
        "has_proof_term_pretty": False,
        "has_assembly_trace": False,
        "has_process_trace": True,
        "has_proof_term_metrics": True,
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")

    writer.write_run_status(status="completed", completed_at="2026-03-06T12:05:00Z")

    updated = json.loads(status_path.read_text())
    assert updated["started_at"] == "2026-03-06T12:00:00Z"
    assert updated["completed_at"] == "2026-03-06T12:05:00Z"
    assert updated["capabilities"]["has_proof_term"] is True
    assert updated["capabilities"]["has_process_trace"] is True
