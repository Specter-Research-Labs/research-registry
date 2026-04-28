from __future__ import annotations

from orchestrator.lean_basin import (
    SeedRunResult,
    _basin_resume_complete,
    _load_seed_results,
)


def test_load_seed_results_parses_valid_entries_only() -> None:
    payload = {
        "seed_results": [
            {
                "seed": 0,
                "solved": True,
                "structure_hash": "abc",
                "iterations_to_solve": 42,
            },
            {
                "seed": "bad",
                "solved": True,
                "structure_hash": "x",
                "iterations_to_solve": 1,
            },
        ]
    }
    parsed = _load_seed_results(payload)
    assert len(parsed) == 1
    assert parsed[0] == SeedRunResult(
        seed=0,
        solved=True,
        structure_hash="abc",
        iterations_to_solve=42,
    )


def test_basin_resume_complete_requires_all_seeds() -> None:
    seed_results = [
        SeedRunResult(seed=0, solved=True, structure_hash="a", iterations_to_solve=1),
    ]
    assert not _basin_resume_complete(seed_results, seeds=[0, 1], include_blind=False)


def test_basin_resume_complete_requires_blind_when_requested() -> None:
    without_blind = [
        SeedRunResult(seed=0, solved=True, structure_hash="a", iterations_to_solve=1),
    ]
    assert not _basin_resume_complete(without_blind, seeds=[0], include_blind=True)

    with_blind = [
        SeedRunResult(
            seed=0,
            solved=True,
            structure_hash="a",
            iterations_to_solve=1,
            blind_solved=False,
            blind_structure_hash=None,
            blind_iterations_to_solve=None,
            blind_attempts_total=2,
        ),
    ]
    assert _basin_resume_complete(with_blind, seeds=[0], include_blind=True)
