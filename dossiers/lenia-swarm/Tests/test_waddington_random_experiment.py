from __future__ import annotations

import pytest

from lenia_swarm_analysis.waddington.random_experiment import _sync_randomized_manifest


def test_sync_randomized_manifest_rewrites_ids_and_clears_template_snapshots() -> None:
    entry = {
        "creature": {"id": "new-id", "genotype": {"R": 9.0}},
        "specimen_manifest": {
            "creatureID": "old-creature",
            "specimenID": "old-specimen",
            "snapshots": {"morphometrics": {"pathTortuosity": 0.5}},
        },
    }

    _sync_randomized_manifest(entry, "new-id")

    manifest = entry["specimen_manifest"]
    assert manifest["creatureID"] == "new-id"
    assert manifest["specimenID"] == "new-id"
    assert manifest["snapshots"] == {}


def test_sync_randomized_manifest_requires_a_manifest() -> None:
    with pytest.raises(SystemExit, match="no specimen_manifest"):
        _sync_randomized_manifest({"creature": {"id": "new-id"}}, "new-id")
