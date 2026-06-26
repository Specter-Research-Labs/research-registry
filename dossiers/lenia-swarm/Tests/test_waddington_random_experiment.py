from __future__ import annotations

from lenia_swarm_analysis.waddington.random_experiment import _sync_randomized_manifest


def test_sync_randomized_manifest_updates_genotype_snapshot_and_ids() -> None:
    genotype = {"R": 9.0, "m": [0.2]}
    entry = {
        "creature": {"id": "new-id", "genotype": genotype},
        "specimen_manifest": {
            "creatureID": "old-creature",
            "specimenID": "old-specimen",
            "snapshots": {"genotype": {"R": 1.0}, "metrics": {"mass": 0.5}},
        },
    }

    _sync_randomized_manifest(entry, "new-id", genotype)

    manifest = entry["specimen_manifest"]
    assert manifest["creatureID"] == "new-id"
    assert manifest["specimenID"] == "new-id"
    assert manifest["snapshots"]["genotype"] == genotype
    assert manifest["snapshots"]["metrics"] == {"mass": 0.5}


def test_sync_randomized_manifest_creates_missing_snapshots_object() -> None:
    genotype = {"R": 6.0}
    entry = {
        "creature": {"id": "new-id", "genotype": genotype},
        "specimen_manifest": {"creatureID": "old-creature", "specimenID": "old-specimen"},
    }

    _sync_randomized_manifest(entry, "new-id", genotype)

    assert entry["specimen_manifest"]["snapshots"]["genotype"] == genotype
