from __future__ import annotations

TRACK1_FAMILIES: dict[str, dict[str, str]] = {
    "track1b-2c10-r17-20-initshift": {
        "familyKey": "2c10_r17_20_initshift",
        "sourceAlgorithm": "fl-2c10-r17-20-initshift-harvest",
    },
    "track1b-2c10-r7-10-initshift": {
        "familyKey": "2c10_r7_10_initshift",
        "sourceAlgorithm": "fl-2c10-r7-10-initshift-harvest",
    },
    "track1b-2c20-harvest": {
        "familyKey": "2c20_paper_random",
        "sourceAlgorithm": "fl-2c20-harvest",
    },
    "track1b-3c15-harvest": {
        "familyKey": "3c15_paper_random",
        "sourceAlgorithm": "fl-3c15-harvest",
    },
}


def track1_family_metadata(run_id: str) -> dict[str, str]:
    for prefix, family in TRACK1_FAMILIES.items():
        if run_id.startswith(prefix):
            return family
    raise ValueError(f"unknown Track 1 run family: {run_id}")
