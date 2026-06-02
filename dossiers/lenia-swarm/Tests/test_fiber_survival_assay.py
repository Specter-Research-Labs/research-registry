from __future__ import annotations

import json
import sys
from pathlib import Path

from lenia_swarm_analysis.fiber.survival_assay import (
    build_spec_from_null_validation,
    compare_panel,
    parse_axis_spec,
    run_spec,
    write_loops,
)
from lenia_swarm_analysis.fiber.survival_assay import main as survival_assay_main


def _write_bundle(root: Path, run_id: str, seed: int) -> None:
    bundle = root / run_id / "exports" / f"crystal-form-{seed % 10000}-ABCDEF"
    bundle.mkdir(parents=True)
    (bundle / "base.json").write_text(
        json.dumps(
            {
                "params": {
                    "mode": "explicit",
                    "m": [0.23],
                    "s": [0.045],
                    "R": 9.0,
                }
            }
        ),
        encoding="utf-8",
    )


def _rank(specimen_id: str, distance: float) -> dict[str, object]:
    return {"rank": 1, "specimenId": specimen_id, "distanceToTerminalCentroid": distance}


def test_build_spec_from_null_validation_writes_positive_and_control_runs(tmp_path: Path) -> None:
    flow_root = tmp_path / "flow"
    for seed in (1001, 1002, 2001, 2002):
        _write_bundle(flow_root, "run-a", seed)
    positive_region = (
        "component_count:mid|bilateral_symmetry:low|coverage:high|compactness:low"
    )
    control_region = (
        "component_count:mid|bilateral_symmetry:high|coverage:low|compactness:mid"
    )
    null_packet = {
        "packetKind": "track1_high_fiber_null_validation_v1",
        "regions": [
            {
                "region": positive_region,
                "families": {
                    "2c10_r17_20": {
                        "status": "measured",
                        "terminalLabelShuffleNull": {"ratioOneSidedPValue": 0.01},
                        "exampleRanks": {
                            "nearestTerminalCentroid": [
                                _rank("result:run-a|overall|1001", 0.1)
                            ],
                            "farthestTerminal": [_rank("result:run-a|overall|1002", 9.0)],
                        },
                        "otherRegionControls": {
                            "bottomByRatio": [
                                {
                                    "region": control_region,
                                    "exampleRanks": {
                                        "nearestTerminalCentroid": [
                                            _rank("result:run-a|overall|2001", 0.2)
                                        ],
                                        "farthestTerminal": [
                                            _rank("result:run-a|overall|2002", 4.0)
                                        ],
                                    },
                                }
                            ]
                        },
                    }
                },
            }
        ],
    }

    spec = build_spec_from_null_validation(
        null_validation=null_packet,
        null_validation_path=tmp_path / "null.json",
        flow_runs_root=flow_root,
        output_root=tmp_path / "assay",
        cli_binary=".build/release/LeniaCLI",
        path_root=tmp_path,
        families=["2c10_r17_20"],
        positive_regions=None,
        pair_limit=1,
        axes=[parse_axis_spec("m.0:0.03:0.001:0.999"), parse_axis_spec("R:0.75:1.0:")],
        samples_per_segment=2,
        p_value_max=0.05,
    )

    assert spec["runCount"] == 8
    assert {run["case"] for run in spec["runs"]} == {"positive", "control"}
    assert {run["axis"] for run in spec["runs"]} == {"m.0", "R"}
    assert all(run["loop"]["samples_per_segment"] == 2 for run in spec["runs"])

    loop_count = write_loops(spec)
    assert loop_count == 8
    assert Path(spec["runs"][0]["loopPath"]).exists()


def test_build_spec_keeps_repeated_family_controls_distinct(tmp_path: Path) -> None:
    flow_root = tmp_path / "flow"
    for seed in (1001, 1002, 2001, 2002):
        _write_bundle(flow_root, "run-a", seed)
    first_region = "component_count:mid|bilateral_symmetry:mid|coverage:high|compactness:mid"
    second_region = "component_count:mid|bilateral_symmetry:low|coverage:high|compactness:low"
    shared_control = "component_count:mid|bilateral_symmetry:high|coverage:low|compactness:mid"

    def family_row() -> dict[str, object]:
        return {
            "status": "measured",
            "terminalLabelShuffleNull": {"ratioOneSidedPValue": 0.01},
            "exampleRanks": {
                "nearestTerminalCentroid": [_rank("result:run-a|overall|1001", 0.1)],
                "farthestTerminal": [_rank("result:run-a|overall|1002", 9.0)],
            },
            "otherRegionControls": {
                "bottomByRatio": [
                    {
                        "region": shared_control,
                        "exampleRanks": {
                            "nearestTerminalCentroid": [
                                _rank("result:run-a|overall|2001", 0.2)
                            ],
                            "farthestTerminal": [_rank("result:run-a|overall|2002", 4.0)],
                        },
                    }
                ]
            },
        }

    null_packet = {
        "packetKind": "track1_high_fiber_null_validation_v1",
        "regions": [
            {"region": first_region, "families": {"2c10_r17_20": family_row()}},
            {"region": second_region, "families": {"2c10_r17_20": family_row()}},
        ],
    }

    spec = build_spec_from_null_validation(
        null_validation=null_packet,
        null_validation_path=tmp_path / "null.json",
        flow_runs_root=flow_root,
        output_root=tmp_path / "assay",
        cli_binary=".build/release/LeniaCLI",
        path_root=tmp_path,
        families=["2c10_r17_20"],
        positive_regions=None,
        pair_limit=1,
        axes=[parse_axis_spec("R:0.75:1.0:")],
        samples_per_segment=2,
        p_value_max=0.05,
    )

    names = [run["name"] for run in spec["runs"]]
    assert spec["runCount"] == 8
    assert len(set(names)) == len(names)
    assert {run["sourceRegion"] for run in spec["runs"]} == {
        first_region,
        second_region,
    }


def test_run_spec_executes_commands_and_captures_run_log(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-output"
    spec = {
        "packetKind": "fiber_survival_assay_spec_v1",
        "sourceSpec": "spec.json",
        "runs": [
            {
                "name": "smoke",
                "case": "positive",
                "family": "2c10_r17_20",
                "sourceRegion": "positive-region",
                "region": "positive-region",
                "role": "nearestTerminalCentroidSpecimenId",
                "axis": "R",
                "outputPath": str(output_dir),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib, sys; "
                        "out = pathlib.Path(sys.argv[1]); "
                        "out.mkdir(parents=True, exist_ok=True); "
                        "(out / 'holonomy-manifest.json').write_text('{}\\n')"
                    ),
                    str(output_dir),
                ],
            }
        ],
    }

    packet = run_spec(
        spec,
        output=tmp_path / "run-log.json",
        jobs=1,
        rerun=False,
        limit=None,
    )

    assert packet["executedRunCount"] == 1
    assert packet["completedRunCount"] == 1
    assert packet["failedRunCount"] == 0
    assert packet["runs"][0]["status"] == "completed"


def test_compare_panel_pairs_positive_and_control_by_family_axis_and_pair() -> None:
    comparison = compare_panel(_comparison_panel())

    assert comparison["completedComparisonCount"] == 1
    assert comparison["positiveBeatsControlOnBoth"] == 1
    assert comparison["comparisons"][0]["survivalRatioDelta"] == 1.0
    assert comparison["comparisons"][0]["endTerminalSeparationDelta"] == 8.0


def test_compare_command_records_source_panel(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.json"
    output_path = tmp_path / "comparison.json"
    panel_path.write_text(json.dumps(_comparison_panel()), encoding="utf-8")

    assert (
        survival_assay_main(
            [
                "compare",
                "--panel",
                str(panel_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    comparison = json.loads(output_path.read_text(encoding="utf-8"))
    assert comparison["sourcePanel"] == str(panel_path.resolve())
    assert comparison["sourceSpec"] == "spec.json"


def _comparison_panel() -> dict[str, object]:
    return {
        "packetKind": "fiber_survival_assay_panel_v1",
        "sourceSpec": "spec.json",
        "rolePairScores": [
            {
                "case": "positive",
                "pairIndex": 1,
                "family": "2c10_r17_20",
                "sourceRegion": "positive-region",
                "region": "positive-region",
                "axis": "R",
                "survivalRatio": 1.5,
                "endTerminalSeparation": 12.0,
            },
            {
                "case": "control",
                "pairIndex": 1,
                "family": "2c10_r17_20",
                "sourceRegion": "positive-region",
                "region": "control-region",
                "axis": "R",
                "survivalRatio": 0.5,
                "endTerminalSeparation": 4.0,
            },
        ],
    }
