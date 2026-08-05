from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from lenia_swarm_analysis.morphospace.common_morphology import (
    FEATURE_SPACE_ID as COMMON_FEATURE_SPACE_ID,
)
from lenia_swarm_analysis.morphospace.derive_lenia_features import (
    FEATURE_SPACE_ID as TERMINAL_FEATURE_SPACE_ID,
)
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
    common_axes = ["elongation", "bilateral_symmetry", "radial_symmetry", "compactness"]
    terminal_axes = ["fragmentation", "spread"]
    for index, axis in enumerate(common_axes):
        connection.execute(
            "INSERT INTO feature_axes VALUES (?, ?, ?)",
            [COMMON_FEATURE_SPACE_ID, axis, index],
        )
    for index, axis in enumerate(terminal_axes):
        connection.execute(
            "INSERT INTO feature_axes VALUES (?, ?, ?)",
            [TERMINAL_FEATURE_SPACE_ID, axis, index],
        )

    source_algorithm = "fixture-algorithm"
    target_region = (
        "elongation:mid|bilateral_symmetry:low|radial_symmetry:high|compactness:mid"
    )
    source_packet = tmp_path / "source.json"
    source_packet.write_text(
        json.dumps({"rankedSharedHighFiberRegions": [{"region": target_region}]}),
        encoding="utf-8",
    )

    for index in range(10):
        specimen_id = f"specimen-{index}"
        in_target = index < 3
        common = {
            "elongation": 0.0 if in_target else 0.8,
            "bilateral_symmetry": -0.8 if in_target else 0.0,
            "radial_symmetry": 0.8 if in_target else 0.0,
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
            feature_space_id=COMMON_FEATURE_SPACE_ID,
            values=common,
        )
        _insert_feature(
            connection,
            specimen_id=specimen_id,
            source_algorithm=source_algorithm,
            feature_space_id=TERMINAL_FEATURE_SPACE_ID,
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

    source_packet.write_text(
        json.dumps(
            {
                "rankedSharedHighFiberRegions": [
                    {
                        "region": (
                            "component_count:mid|bilateral_symmetry:low|"
                            "coverage:high|compactness:mid"
                        )
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="do not match v3 axes"):
        build_high_fiber_null_validation_packet(
            connection,
            source_packet_path=source_packet,
            target_region_limit=1,
            null_replicates=4,
            family_algorithms={"fixture": source_algorithm},
        )
