from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lenia_swarm_analysis.hotspot.neighborhood import (
    build_hotspot_neighborhood_packet,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_hotspot_neighborhood_packet_maps_candidates_to_replay_and_compendium(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "crystal" / "run-medium"
    _write_json(
        run_dir / "top.json",
        [
            {
                "seed": 7,
                "init_seed": 50007,
                "metrics": {"gyration": 123.0},
                "descriptor_bundle": {
                    "terminal": {"fingerprintHash12": "fp1234567890"},
                    "genotype": {"hash12": "geno12345678"},
                },
            }
        ],
    )
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "groups": [
                {
                    "controlGroup": "crystal-mh",
                    "specimen": "crystal",
                    "recommendedReplayScale": "medium",
                    "followupScales": ["small"],
                }
            ],
            "selectedCandidates": [
                {
                    "candidateId": "crystal-mh-medium-01",
                    "controlGroup": "crystal-mh",
                    "specimen": "crystal",
                    "scale": "medium",
                    "sourceRunDir": str(run_dir),
                    "sourceIndex": 0,
                    "sourceSeed": 7,
                    "sourceInitSeed": 50007,
                    "distanceToSeedEmbedding": 1.5,
                    "featureEmbedding": [1.0, 2.0],
                    "metrics": {"gyration": 123.0},
                }
            ],
        },
    )
    export_root = tmp_path / "replay-candidates"
    export_dir = export_root / "exports" / "candidate-01"
    export_dir.mkdir(parents=True)
    (export_dir / "base.json").write_text("{}", encoding="utf-8")
    (export_dir / "search.json").write_text("{}", encoding="utf-8")
    export_packet = tmp_path / "export.json"
    _write_json(
        export_packet,
        {
            "candidates": [
                {
                    "candidateId": "crystal-mh-medium-01",
                    "exportDir": str(export_dir),
                }
            ]
        },
    )
    empirical = tmp_path / "empirical.json"
    _write_json(
        empirical,
        {
            "topHotspots": [
                {"kind": "transport_group", "id": "crystal-mh"},
                {"kind": "cycle_generator", "id": "h1-rank01-feature0028"},
            ]
        },
    )
    db_path = tmp_path / "compendium.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        create table specimens (
            id text primary key,
            result_id text,
            creature_id text,
            run_id text not null,
            campaign_id text,
            source_kind text not null,
            recorded_at text,
            seed integer,
            init_seed integer,
            source_mode text,
            source_algorithm text,
            config_hash text,
            initial_condition_family text,
            descriptor_version integer not null,
            symmetry_policy text not null,
            genotype_descriptor_json text not null,
            terminal_descriptor_json text not null,
            trajectory_descriptor_json text,
            activity_path text,
            fingerprint_path text,
            provenance_json text
        )
        """
    )
    conn.execute(
        """
        insert into specimens (
            id, run_id, campaign_id, source_kind, descriptor_version, symmetry_policy,
            genotype_descriptor_json, terminal_descriptor_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "spec-1",
            "imgep-hotspot-crystal-medium-20260324",
            "campaign-1",
            "result",
            1,
            "none",
            json.dumps({"hash12": "geno12345678"}),
            json.dumps({"fingerprintHash12": "fp1234567890"}),
        ),
    )
    conn.commit()
    conn.close()

    packet = build_hotspot_neighborhood_packet(
        report_path=report,
        export_packet_path=export_packet,
        compendium_db_path=db_path,
        empirical_packet_path=empirical,
    )

    assert packet["packetKind"] == "hotspot_neighborhood_packet_v1"
    assert packet["groupCount"] == 1
    assert packet["selectedCandidateCount"] == 1
    assert packet["matchedCandidateCount"] == 1
    row = packet["groups"][0]
    assert row["controlGroup"] == "crystal-mh"
    assert row["recommendedReplayScale"] == "medium"
    assert row["isTopTransportHotspot"] is True
    assert row["strictSpecimenCount"] == 1
    candidate = row["selectedCandidates"][0]
    assert candidate["fingerprintHash12"] == "fp1234567890"
    assert candidate["exportDir"] == str(export_dir)
    assert candidate["compendiumMatches"][0]["specimenId"] == "spec-1"
