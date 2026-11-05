import base64
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.compact import (
    RECEIPT_DIR,
    compact_file,
    initial_condition_family,
    main,
    swift_float,
)
from lenia_swarm_analysis.trace_codec import FIELD_ENCODING, state_patch_values

FAMILY_FIXTURE = (
    Path(__file__).parent / "LeniaCoreTests" / "Fixtures" / "initial-condition-family.json"
)
VALUES = np.linspace(-1.5, 2.5, 24, dtype="<f4")
CREATURE_ID = "0a1b2c3d-0000-4000-8000-00000000abcd"


def f32le_patch(values: np.ndarray = VALUES) -> dict:
    return {
        "center": [8, 8],
        "channels": 2,
        "data": base64.b64encode(values.astype("<f4").tobytes()).decode(),
        "encoding": "f32le",
        "height": 3,
        "width": 4,
    }


def swift_pretty(doc: object) -> str:
    text = json.dumps(doc, indent=2, separators=(",", " : "), sort_keys=True)
    return text.replace("/", "\\/")


def creature(**extra: object) -> dict:
    return {
        "genotype": {"R": 12.0, "r": [0.5]},
        "id": CREATURE_ID,
        "initialCondition": {
            "a_uniform": {"high": 0.35, "low": 0.1},
            "patches": [],
            "seed": 3,
            "state_patch": f32le_patch(),
        },
        "metrics": {"mass": 1.25},
        "name": "fixture",
        "ownerId": "local",
        "timestamp": 790000000.5,
        **extra,
    }


def compact(root: Path, relative: str, dry_run: bool = False) -> dict:
    return compact_file((str(root), relative, dry_run))


def test_patch_conversion_keeps_raw_bytes_style_and_is_idempotent(tmp_path: Path) -> None:
    doc = {"init": {"state_patch": f32le_patch()}, "out_dir": "runs/a", "seed": 1}
    path = tmp_path / "config.json"
    path.write_text(swift_pretty(doc) + "\n")

    result = compact(tmp_path, "config.json")

    assert result["changed"] and result["patches_converted"] == 1
    assert result["raw_sha256"] == [hashlib.sha256(VALUES.tobytes()).hexdigest()]
    text = path.read_text()
    rewritten = json.loads(text)
    patch = rewritten["init"]["state_patch"]
    assert patch["encoding"] == FIELD_ENCODING
    assert state_patch_values(patch).tobytes() == VALUES.tobytes()
    assert text == swift_pretty(rewritten) + "\n"
    assert compact(tmp_path, "config.json") == {"path": "config.json", "changed": False}


def test_jsonl_rewrites_only_lines_that_need_it(tmp_path: Path) -> None:
    pending = json.dumps({"state_patch": f32le_patch()}, separators=(",", ":"))
    current = json.dumps({"note": "already current", "value": 1.0})
    path = tmp_path / "rows.jsonl"
    path.write_text(f"{current}\n{pending}\n")

    assert compact(tmp_path, "rows.jsonl")["patches_converted"] == 1

    lines = path.read_text().split("\n")
    assert lines[0] == current and lines[2] == ""
    assert ": " not in lines[1]
    assert json.loads(lines[1])["state_patch"]["encoding"] == FIELD_ENCODING


def test_unknown_encoding_fails_and_leaves_the_file(tmp_path: Path) -> None:
    patch = {**f32le_patch(), "encoding": "f16"}
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"state_patch": patch}))
    before = path.read_bytes()

    result = compact(tmp_path, "config.json")

    assert "unknown field encoding 'f16'" in result["error"]
    assert path.read_bytes() == before


def library_entry(snapshots: dict) -> dict:
    record = creature()
    return {
        "creature": record,
        "recorded_at": 790000001.0,
        "run_id": "run-1",
        "runtime_capabilities": ["archive", "warehouse_ingest"],
        "runtime_family": "flow_lenia",
        "specimen_manifest": {
            "creatureID": CREATURE_ID.upper(),
            "runID": "run-1",
            "runtimeCapabilities": ["archive", "warehouse_ingest"],
            "runtimeFamily": "flow_lenia",
            "snapshots": snapshots,
            "sourceKind": "library",
            "specimenID": CREATURE_ID.upper(),
            "version": 1,
        },
    }


def test_duplicated_snapshots_are_dropped_and_morphometrics_kept(tmp_path: Path) -> None:
    base = creature()
    snapshots = {
        "genotype": base["genotype"],
        "initialCondition": copy.deepcopy(base["initialCondition"]),
        "metrics": base["metrics"],
        "morphometrics": {"area": 4.0},
    }
    path = tmp_path / "library" / "index.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(library_entry(snapshots), sort_keys=True) + "\n")

    result = compact(tmp_path, "library/index.jsonl")

    assert result["snapshots_dropped"] == 3 and result["patches_converted"] == 1
    row = json.loads(path.read_text())
    assert row["specimen_manifest"]["snapshots"] == {"morphometrics": {"area": 4.0}}


def test_snapshot_that_is_not_a_duplicate_fails(tmp_path: Path) -> None:
    path = tmp_path / "library" / "index.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(library_entry({"genotype": {"R": 9.0, "r": [0.5]}})) + "\n")
    before = path.read_bytes()

    result = compact(tmp_path, "library/index.jsonl")

    assert "it is not a duplicate" in result["error"]
    assert path.read_bytes() == before


def test_library_entry_without_manifest_gets_one(tmp_path: Path) -> None:
    record = creature(descriptorBundle={"descriptorVersion": 1})
    entry = {
        "campaign_id": "0001",
        "creature": record,
        "recorded_at": 790000001.0,
        "run_id": "run-1",
        "specimen_manifest": None,
    }
    (tmp_path / "index.jsonl").write_text(json.dumps(entry) + "\n")

    result = compact(tmp_path, "index.jsonl")

    assert result["manifests_written"] == 1
    row = json.loads((tmp_path / "index.jsonl").read_text())
    manifest = row["specimen_manifest"]
    assert manifest == {
        "campaignID": "0001",
        "creatureID": CREATURE_ID.upper(),
        "initialConditionFamily": initial_condition_family(record["initialCondition"], "t"),
        "recordedAt": 790000001.0,
        "replay": {},
        "runID": "run-1",
        "runtimeCapabilities": ["archive", "topology", "warehouse_ingest"],
        "runtimeFamily": "flow_lenia",
        "snapshots": {},
        "sourceKind": "library",
        "specimenID": CREATURE_ID.upper(),
        "version": 1,
    }
    assert row["runtime_family"] == "flow_lenia"
    assert row["runtime_capabilities"] == manifest["runtimeCapabilities"]


def test_library_entry_without_owner_fails(tmp_path: Path) -> None:
    record = creature()
    del record["ownerId"]
    entry = {"creature": record, "recorded_at": 1.0, "run_id": "r", "specimen_manifest": None}
    (tmp_path / "index.jsonl").write_text(json.dumps(entry) + "\n")

    assert "missing required ['ownerId']" in compact(tmp_path, "index.jsonl")["error"]


def test_qd24_export_metadata_takes_bundle_kind_from_the_export_index(tmp_path: Path) -> None:
    record = creature(phenotype=creature()["initialCondition"])
    del record["initialCondition"]
    meta = {
        "creature": record,
        "exportedAt": 790000002.0,
        "reason": "seed-bank",
        "runId": "qd-run",
        "runtimeCapabilities": ["native-replay", "phenotype-queryable"],
        "runtimeFamily": "qd-2024",
    }
    exports = tmp_path / "exports"
    (exports / "bundle").mkdir(parents=True)
    (exports / "bundle" / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    index_row = {
        "bundleKind": "qd24_paper_replay_bundle_v1",
        "creatureId": CREATURE_ID.upper(),
        "exportDir": str(exports / "bundle"),
    }
    (exports / "index.jsonl").write_text(json.dumps(index_row) + "\n")

    result = compact(tmp_path, "exports/bundle/meta.json")

    assert result["manifests_written"] == 1
    rewritten = json.loads((exports / "bundle" / "meta.json").read_text())
    assert rewritten["bundleKind"] == "qd24_paper_replay_bundle_v1"
    assert rewritten["runtimeFamily"] == "qd24_paper"
    capabilities = ["archive", "intervention", "media", "replay", "warehouse_ingest"]
    assert rewritten["runtimeCapabilities"] == capabilities
    assert "phenotype" not in rewritten["creature"]
    assert rewritten["creature"]["initialCondition"]["state_patch"]["encoding"] == FIELD_ENCODING
    manifest = rewritten["specimenManifest"]
    assert manifest["sourceKind"] == "export_metadata"
    assert manifest["replay"] == {"bundleKind": "qd24_paper_replay_bundle_v1"}
    assert manifest["runtimeCapabilities"] == capabilities


def test_compendium_release_detail_keeps_its_own_phenotype_key(tmp_path: Path) -> None:
    detail = {
        "creature": {"genotype": {}, "id": CREATURE_ID, "owner_id": "x", "phenotype": {"seed": 1}},
        "published_at": "2026-02-28",
        "recorded_at": "2026-02-28",
        "run_id": "run-1",
    }
    (tmp_path / "detail.json").write_text(json.dumps(detail))

    assert compact(tmp_path, "detail.json") == {"path": "detail.json", "changed": False}


def test_main_writes_receipt_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "config.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"state_patch": f32le_patch()}, indent=2))
    before = path.read_bytes()

    assert main([str(tmp_path), "--dry-run", "--jobs", "1"]) == 0
    assert path.read_bytes() == before
    assert not (tmp_path / RECEIPT_DIR).exists()

    assert main([str(tmp_path), "--jobs", "1"]) == 0
    receipts = list((tmp_path / RECEIPT_DIR).iterdir())
    assert len(receipts) == 1
    header, entry = (json.loads(line) for line in receipts[0].read_text().splitlines())
    assert header["kind"] == "run" and header["root"] == str(tmp_path.resolve())
    assert entry["path"] == "runs/config.json"
    assert entry["bytes_before"] == len(before) and entry["bytes_after"] == path.stat().st_size
    assert entry["sha256_after"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry["raw_sha256"] == [hashlib.sha256(VALUES.tobytes()).hexdigest()]


def test_main_exits_nonzero_on_errors(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(json.dumps({"state_patch": {**f32le_patch(), "width": 5}}))

    assert main([str(tmp_path), "--jobs", "1"]) == 1


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0"),
        (0.1, "0.1"),
        (0.0001, "0.0001"),
        (9.9e-05, "9.9e-05"),
        (1e-05, "1e-05"),
        (12345678, "12345678"),
        (16777216, "16777216"),
        (16777218, "1.6777218e+07"),
        (1e8, "1e+08"),
        (-2.5, "-2.5"),
    ],
)
def test_swift_float_matches_foundation(value: float, text: str) -> None:
    assert swift_float(value, "t") == text


def test_initial_condition_family_matches_swift_fixture() -> None:
    cases = json.loads(FAMILY_FIXTURE.read_text())["cases"]
    for case in cases:
        assert initial_condition_family(case["initialCondition"], "t") == case["family"]
