from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.logs import read_json, read_json_gz


@dataclass(frozen=True)
class BasinExtractReport:
    basin_run_rows: int
    basin_seed_rows: int
    basin_structure_rows: int
    errors: list[str]


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    return int(v) if isinstance(v, int) else None


def _as_float(v: Any) -> float | None:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return float(v)


def _as_bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _as_str(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def _extract_paper_k(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if not isinstance(v, dict):
        return None

    k_val = v.get("K")
    if isinstance(k_val, (int, float)) and not isinstance(k_val, bool):
        return float(k_val)
    if isinstance(k_val, dict):
        lower = _as_float(k_val.get("lower_bound_censored_at_H"))
        if lower is not None:
            return lower
        conditional = _as_float(k_val.get("conditional_on_both_solved"))
        if conditional is not None:
            return conditional

    lower = _as_float(v.get("lower_bound_censored_at_H"))
    if lower is not None:
        return lower
    conditional = _as_float(v.get("conditional_on_both_solved"))
    if conditional is not None:
        return conditional
    return None


def _read_basin(path: Path) -> dict[str, Any] | None:
    if path.with_suffix(".json.gz").exists():
        return read_json_gz(path.with_suffix(".json.gz"))
    if path.exists():
        return read_json(path)
    return None


def extract_basin_facts(
    conn: duckdb.DuckDBPyConnection,
    *,
    root_dir: Path,
    run_rows: list[tuple[str, str]],
) -> BasinExtractReport:
    errors: list[str] = []
    basin_run_rows = 0
    basin_seed_rows = 0
    basin_structure_rows = 0

    for run_key, rel in run_rows:
        run_dir = (root_dir / rel).resolve()
        if not run_dir.exists():
            continue

        theorem_dirs = [
            d for d in run_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
            and not d.name.startswith("provider=")
        ]
        if not theorem_dirs:
            continue

        has_basin = False
        for theorem_dir in theorem_dirs:
            basin_path = theorem_dir / "basin_analysis.json"
            data = None
            try:
                data = _read_basin(basin_path)
            except Exception as exc:
                conn.execute(
                    "INSERT INTO extract_errors(run_key, stage, error) VALUES (?, ?, ?)",
                    [run_key, "read_basin", f"{theorem_dir.name}: {type(exc).__name__}: {exc}"],
                )
                errors.append(f"{rel}/{theorem_dir.name}: read_basin: {type(exc).__name__}: {exc}")
                continue

            if data is None or not isinstance(data, dict):
                continue

            theorem = data.get("theorem_name")
            if not isinstance(theorem, str) or not theorem:
                theorem = theorem_dir.name

            if not has_basin:
                has_basin = True
                conn.execute("DELETE FROM basin_runs WHERE run_key = ?", [run_key])
                conn.execute("DELETE FROM basin_seed WHERE run_key = ?", [run_key])
                conn.execute("DELETE FROM basin_structure_counts WHERE run_key = ?", [run_key])

            seeds = data.get("seeds")
            seeds_requested = len(seeds) if isinstance(seeds, list) else None

            paper_k = _extract_paper_k(data.get("paper_k"))

            conn.execute(
                """
                INSERT INTO basin_runs(
                  run_key, theorem, seeds_requested, solve_rate,
                  unique_structures, dominant_structure_frequency,
                  blind_solve_rate, paper_k
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_key,
                    theorem,
                    seeds_requested,
                    _as_float(data.get("solve_rate")),
                    _as_int(data.get("unique_structures")),
                    _as_float(data.get("dominant_structure_frequency")),
                    _as_float(data.get("blind_solve_rate")),
                    paper_k,
                ],
            )
            basin_run_rows += 1

            seed_results = data.get("seed_results")
            if isinstance(seed_results, list):
                for sr in seed_results:
                    if not isinstance(sr, dict):
                        continue
                    seed = sr.get("seed")
                    if not isinstance(seed, int) or isinstance(seed, bool):
                        continue
                    conn.execute(
                        """
                        INSERT INTO basin_seed(
                          run_key, theorem, seed, solved,
                          structure_hash, iterations_to_solve,
                          attempts_total,
                          blind_solved, blind_structure_hash,
                          blind_iterations_to_solve,
                          blind_attempts_total
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            run_key,
                            theorem,
                            seed,
                            _as_bool(sr.get("solved")),
                            _as_str(sr.get("structure_hash")),
                            _as_int(sr.get("iterations_to_solve")),
                            _as_int(sr.get("attempts_total")),
                            _as_bool(sr.get("blind_solved")),
                            _as_str(sr.get("blind_structure_hash")),
                            _as_int(sr.get("blind_iterations_to_solve")),
                            _as_int(sr.get("blind_attempts_total")),
                        ],
                    )
                    basin_seed_rows += 1

            structure_dist = data.get("structure_distribution")
            if isinstance(structure_dist, dict):
                for structure_hash, count in structure_dist.items():
                    if not isinstance(structure_hash, str):
                        continue
                    c = _as_int(count)
                    if c is None or c <= 0:
                        continue
                    conn.execute(
                        """
                        INSERT INTO basin_structure_counts(
                          run_key, theorem, structure_hash, count
                        ) VALUES (?, ?, ?, ?)
                        """,
                        [run_key, theorem, structure_hash, c],
                    )
                    basin_structure_rows += 1

    return BasinExtractReport(
        basin_run_rows=basin_run_rows,
        basin_seed_rows=basin_seed_rows,
        basin_structure_rows=basin_structure_rows,
        errors=errors,
    )
