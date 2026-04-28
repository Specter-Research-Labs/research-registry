import csv
import json

from fly_competency_atlas.lamina_local import execute_local_manifest


def test_execute_local_manifest_writes_completed_records(tmp_path) -> None:
    dossier_root = tmp_path / "lamina_cartridge"
    asset_root = dossier_root / "upstream"
    manifest_dir = dossier_root / "manifests"
    asset_root.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    connection_csv = asset_root / "connection.csv"
    with connection_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["", "R1", "L1", "L2"])
        writer.writerow(["R1", "0", "0", "0"])
        writer.writerow(["L1", "0", "0", "1"])
        writer.writerow(["L2", "1", "0", "0"])
    manifest_path = manifest_dir / "mini_panel.json"
    manifest_path.write_text(
        json.dumps(
            {
                "asset_root": str(asset_root),
                "cases": [
                    {
                        "case_id": "uniform__none",
                        "family": "mini_panel",
                        "input_pattern": "uniform",
                        "lesion_name": "none",
                        "disabled_neurons": [],
                        "active_channels": ["R1"],
                        "amplitude": 10000.0,
                        "start_s": 0.05,
                        "stop_s": 0.15,
                        "duration_s": 0.2,
                        "dt_s": 0.001,
                        "output_targets": ["L1"],
                        "metric_slots": [],
                    },
                    {
                        "case_id": "uniform__disable_L2",
                        "family": "mini_panel",
                        "input_pattern": "uniform",
                        "lesion_name": "disable_L2",
                        "disabled_neurons": ["L2"],
                        "active_channels": ["R1"],
                        "amplitude": 10000.0,
                        "start_s": 0.05,
                        "stop_s": 0.15,
                        "duration_s": 0.2,
                        "dt_s": 0.001,
                        "output_targets": ["L1"],
                        "metric_slots": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = execute_local_manifest(manifest_path)
    assert result.case_count == 2
    assert result.result_path.name == "mini_panel.local.ndjson"
    records = [
        json.loads(line)
        for line in result.result_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all(record["status"] == "completed" for record in records)
    assert all(record["execution_backend"] == "local_linear_v1" for record in records)
    lesion_record = next(record for record in records if record["lesion_name"] == "disable_L2")
    assert lesion_record["metrics"]["efficiency_over_blind"] is not None
    assert lesion_record["metrics"]["lesion_tolerance"] is not None
    assert lesion_record["metrics"]["basin_preservation"] is not None
