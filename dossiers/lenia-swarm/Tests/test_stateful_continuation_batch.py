from __future__ import annotations

import json
from pathlib import Path

import pytest

from lenia_swarm_analysis.fiber.continuation_batch import run_batch_from_spec


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_run_batch_from_spec_uses_bundle_center_plus_offsets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = tmp_path / "bundle"
    _write_json(
        bundle / "base.json",
        {
            "params": {
                "m": [0.25],
                "h": [0.5],
            }
        },
    )
    spec_path = tmp_path / "batch.json"
    _write_json(
        spec_path,
        {
            "cliBinary": "/tmp/LeniaCLI",
            "outputRoot": str(tmp_path / "outputs"),
            "runs": [
                {
                    "name": "demo-run",
                    "bundle": str(bundle),
                    "coordinate": "m.0",
                    "offsets": [-0.01, 0.0, 0.02],
                }
            ],
        },
    )

    def _fake_run_stateful_continuation(**kwargs):
        output = Path(kwargs["output"])
        packet_path = output / "stateful-continuation-packet.json"
        return {
            "packet": {
                "pointCount": 3,
                "endpointPhenotypeDistance": 0.1,
                "endpointTransportedStateDistance": 0.4,
                "maxPhenotypeDistanceFromStart": 0.2,
                "maxTransportedStateDistanceFromStart": 0.5,
            },
            "packetPath": packet_path,
            "command": ["LeniaCLI"],
        }

    monkeypatch.setattr(
        "lenia_swarm_analysis.fiber.continuation_batch.run_stateful_continuation",
        _fake_run_stateful_continuation,
    )

    packet = run_batch_from_spec(spec_path)

    assert packet["packetKind"] == "stateful_continuation_batch_packet_v1"
    assert packet["runCount"] == 1
    run = packet["runs"][0]
    assert run["centerValue"] == 0.25
    assert run["values"] == [0.24, 0.25, 0.27]
    assert run["transportToPhenotypeRatio"] == 4.0
    assert packet["interestingRuns"] == ["demo-run"]


def test_run_batch_from_spec_accepts_explicit_loop_vertices(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = tmp_path / "bundle"
    _write_json(bundle / "base.json", {"params": {"m": [0.1], "h": [0.2]}})
    spec_path = tmp_path / "batch-loop.json"
    _write_json(
        spec_path,
        {
            "cliBinary": "/tmp/LeniaCLI",
            "outputRoot": str(tmp_path / "outputs"),
            "runs": [
                {
                    "name": "loop-run",
                    "bundle": str(bundle),
                    "coordinates": ["m.0", "h.0"],
                    "vertices": [
                        [0.1, 0.2],
                        [0.11, 0.2],
                        [0.11, 0.21],
                        [0.1, 0.21],
                        [0.1, 0.2],
                    ],
                    "closed": True,
                    "samplesPerSegment": 2,
                }
            ],
        },
    )

    def _fake_run_stateful_continuation(**kwargs):
        assert kwargs["coordinate"] is None
        assert kwargs["values"] is None
        loop_spec = kwargs["loop_spec"]
        assert loop_spec["closed"] is True
        assert loop_spec["coordinates"] == ["m.0", "h.0"]
        assert loop_spec["samples_per_segment"] == 2
        return {
            "packet": {
                "pointCount": 5,
                "endpointPhenotypeDistance": 0.05,
                "endpointTransportedStateDistance": 0.15,
                "maxPhenotypeDistanceFromStart": 0.07,
                "maxTransportedStateDistanceFromStart": 0.2,
            },
            "packetPath": Path(kwargs["output"]) / "stateful-continuation-packet.json",
            "command": ["LeniaCLI"],
        }

    monkeypatch.setattr(
        "lenia_swarm_analysis.fiber.continuation_batch.run_stateful_continuation",
        _fake_run_stateful_continuation,
    )

    packet = run_batch_from_spec(spec_path)

    run = packet["runs"][0]
    assert run["coordinate"] is None
    assert run["values"] is None
    assert run["loopSpec"]["closed"] is True
    assert run["transportToPhenotypeRatio"] == pytest.approx(3.0)
