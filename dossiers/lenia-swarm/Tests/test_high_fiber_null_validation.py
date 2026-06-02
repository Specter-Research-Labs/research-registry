from __future__ import annotations

import json
from pathlib import Path

import duckdb

from lenia_swarm_analysis.morphospace.high_fiber_null_validation import (
    build_high_fiber_null_validation_packet,
)


def _insert_feature(
    connection: duckdb.DuckDBPyConnection,
    *,
    specimen_id: str,
    source_algorithm: str,
    feature_space_id: str,
    values: dict[str, float],
) -> None:
    for axis_id, value in values.items():
        connection.execute(
            """
            INSERT INTO comparison_feature_values_vw
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                specimen_id,
                "run-a",
                "lenia_swarm",
                source_algorithm,
                feature_space_id,
                axis_id,
                value,
            ],
        )


def test_high_fiber_null_validation_tests_terminal_label_shuffle(tmp_path: Path) -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE feature_axes (
            feature_space_id text,
            axis_id text,
            axis_index integer
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE comparison_feature_values_vw (
            specimen_id text,
            run_id text,
            source_id text,
            source_algorithm text,
            feature_space_id text,
            axis_id text,
            normalized_value double
        )
        """
    )
    common_axes = ["component_count", "bilateral_symmetry", "coverage", "compactness"]
    terminal_axes = ["fragmentation", "spread"]
    for index, axis in enumerate(common_axes):
        connection.execute(
            "INSERT INTO feature_axes VALUES ('common_morphology_v1', ?, ?)",
            [axis, index],
        )
    for index, axis in enumerate(terminal_axes):
        connection.execute(
            "INSERT INTO feature_axes VALUES ('lenia_terminal_v1', ?, ?)",
            [axis, index],
        )

    source_algorithm = "fixture-algorithm"
    target_region = "component_count:mid|bilateral_symmetry:low|coverage:high|compactness:mid"
    source_packet = tmp_path / "source.json"
    source_packet.write_text(
        json.dumps({"rankedSharedHighFiberRegions": [{"region": target_region}]}),
        encoding="utf-8",
    )

    for index in range(10):
        specimen_id = f"specimen-{index}"
        in_target = index < 3
        common = {
            "component_count": 0.0 if in_target else 0.8,
            "bilateral_symmetry": -0.8 if in_target else 0.0,
            "coverage": 0.8,
            "compactness": 0.0,
        }
        terminal = (
            {"fragmentation": float(index * 10), "spread": 0.0}
            if in_target
            else {"fragmentation": 0.0, "spread": 0.0}
        )
        _insert_feature(
            connection,
            specimen_id=specimen_id,
            source_algorithm=source_algorithm,
            feature_space_id="common_morphology_v1",
            values=common,
        )
        _insert_feature(
            connection,
            specimen_id=specimen_id,
            source_algorithm=source_algorithm,
            feature_space_id="lenia_terminal_v1",
            values=terminal,
        )

    packet = build_high_fiber_null_validation_packet(
        connection,
        source_packet_path=source_packet,
        target_region_limit=1,
        null_replicates=32,
        seed=7,
        min_region_count=2,
        family_algorithms={"fixture": source_algorithm},
    )

    family = packet["regions"][0]["families"]["fixture"]
    assert family["status"] == "measured"
    assert family["count"] == 3
    assert family["observed"]["terminalRmsDispersion"] > (
        family["terminalLabelShuffleNull"]["terminalRmsDispersion"]["mean"]
    )
    assert family["terminalLabelShuffleNull"]["terminalRmsOneSidedPValue"] < 0.5
    assert family["examples"]["nearestTerminalCentroidSpecimenId"] == "specimen-1"
    assert len(family["exampleRanks"]["nearestTerminalCentroid"]) == 3
    assert len(family["exampleRanks"]["farthestTerminal"]) == 3
    assert family["exampleRanks"]["nearestTerminalCentroid"][0]["specimenId"] == "specimen-1"
