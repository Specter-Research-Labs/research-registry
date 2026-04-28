from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lenia_swarm_analysis.fiber.chart import (
    decode_qd24_payload,
    encode_qd24_payload,
    pair_direction_qd24_chart,
    qd24_chart_config,
)
from lenia_swarm_analysis.fiber.packets import (
    generator_by_id,
    generator_edge_pair,
    load_generator_packet,
)


def _sample_payload() -> dict:
    genotype = [
        0.35,
        0.55,
        0.75,
        0.15,
        0.25,
        0.45,
        0.05,
        0.10,
        0.20,
        0.30,
        0.40,
        0.50,
    ]
    return {
        "base": {
            "n_params_size": 3,
        },
        "pattern": {
            "kernels": [{"id": "k0"}],
            "cells": [[[0.0, 0.0], [0.0, 0.0]]],
        },
        "elite": {
            "cell": 17,
            "genotype": genotype,
        },
    }


def test_qd24_chart_round_trips_payload() -> None:
    payload = _sample_payload()
    config = qd24_chart_config(payload, iso_sigma=0.005, line_sigma=0.05)
    chart = encode_qd24_payload(payload, config)
    decoded = decode_qd24_payload(payload, chart, config, cell_seed=17)

    assert decoded["elite"]["cell"] == 17
    assert np.allclose(decoded["elite"]["genotype"], payload["elite"]["genotype"], atol=1e-8)


def test_qd24_pair_direction_is_unit_norm() -> None:
    payload_a = _sample_payload()
    payload_b = _sample_payload()
    payload_b["elite"]["genotype"] = [
        min(value + 0.05, 0.95)
        for value in payload_b["elite"]["genotype"]
    ]
    config = qd24_chart_config(payload_a)

    direction = pair_direction_qd24_chart(payload_a, payload_b, config)

    assert direction.shape == (len(payload_a["elite"]["genotype"]),)
    assert np.isclose(np.linalg.norm(direction), 1.0)


def test_qd24_bounded_logit_chart_rejects_out_of_range_genes() -> None:
    payload = _sample_payload()
    payload["elite"]["genotype"][0] = -0.1

    try:
        qd24_chart_config(payload, transform="bounded_logit")
    except SystemExit as error:
        assert "bounded_logit chart requires" in str(error)
    else:
        raise AssertionError("expected bounded_logit chart to reject out-of-range genes")


def test_load_generator_packet_reads_representatives(tmp_path: Path) -> None:
    path = tmp_path / "packet.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "packetKind": "representative_generators_v1",
                "representation": "fingerprint_only",
                "generators": [
                    {
                        "generatorId": "g0",
                        "persistence": 0.12,
                        "representativeSpecimenIds": ["s0", "s1"],
                        "memberSpecimenIds": ["s0", "s1", "s2"],
                        "cycleEdges": [["s0", "s1"], ["s1", "s2"]],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    packet = load_generator_packet(path)
    generator = generator_by_id(packet, "g0")

    assert packet.packet_kind == "representative_generators_v1"
    assert packet.representation == "fingerprint_only"
    assert generator.representative_specimen_ids == ("s0", "s1")
    assert generator.cycle_edges == (("s0", "s1"), ("s1", "s2"))
    assert generator_edge_pair(generator, 1) == ("s1", "s2")


def test_load_generator_packet_reads_object_cycle_edges(tmp_path: Path) -> None:
    path = tmp_path / "packet-objects.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "packetKind": "topology_generator_packet_v1",
                "representation": "fingerprint_plus_symmetry",
                "generators": [
                    {
                        "generatorId": "g1",
                        "persistence": 0.5,
                        "representativeSpecimenIds": ["a", "b"],
                        "cycleEdges": [
                            {
                                "fromSpecimenId": "a",
                                "toSpecimenId": "b",
                            },
                            {
                                "fromSpecimenId": "b",
                                "toSpecimenId": "c",
                            },
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    packet = load_generator_packet(path)
    generator = generator_by_id(packet, "g1")

    assert generator.cycle_edges == (("a", "b"), ("b", "c"))
    assert generator_edge_pair(generator, 0) == ("a", "b")
