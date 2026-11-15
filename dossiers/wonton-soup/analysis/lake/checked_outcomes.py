"""Classify every lake row by its kernel verdict and whether the proof cites itself.

`theorem_intervention_checked` inner-joins verdicts, so a solved row without one
drops out of both numerator and denominator. Restating a recovery figure on checked
rows needs those rows kept and labelled, and needs proofs that close a library
theorem by citing that same theorem counted apart.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import duckdb
from duckdb.func import FunctionNullHandling
from duckdb.sqltypes import BOOLEAN, VARCHAR

OUTCOMES = ("unsolved", "checked", "checked_selfcite", "failed_check", "unverified")
MODES = {
    "raw": ("checked", "checked_selfcite", "failed_check", "unverified"),
    "checked": ("checked", "checked_selfcite"),
    "checked_nonself": ("checked",),
}
_FAILED = {"replay_failed", "check_failed"}
_ESCAPE = re.compile(r"_x([0-9a-f]{2,5})")


def _escaped_identifier_char(code: int) -> bool:
    """Lean's isIdRest minus ASCII alphanumerics, which the encoders never escape."""
    return (
        chr(code) in "._'!?"
        or (0x3B1 <= code <= 0x3C9 and code != 0x3BB)
        or (0x391 <= code <= 0x3A9 and code not in (0x3A0, 0x3A3))
        or 0x3CA <= code <= 0x3FB
        or 0x1F00 <= code <= 0x1FFE
        or 0x2100 <= code <= 0x214F
        or 0x1D49C <= code <= 0x1D59F
        or 0x2080 <= code <= 0x2089
        or 0x2090 <= code <= 0x209C
        or 0x1D62 <= code <= 0x1D6A
    )


def decode_name(theorem: str) -> str:
    """Undo the lake's `_x{ord:02x}` escaping, so `Nat_x2eadd_x5fcomm` reads `Nat.add_comm`.

    The escape has no fixed width (`_x2082` is the subscript 2), so each escape takes
    the one width whose character can occur in a Lean identifier.
    """
    out: list[str] = []
    pos = 0
    for match in _ESCAPE.finditer(theorem):
        digits = match.group(1)
        widths = [
            w for w in range(2, len(digits) + 1) if _escaped_identifier_char(int(digits[:w], 16))
        ]
        if len(widths) != 1:
            raise ValueError(f"escape {match.group(0)!r} in {theorem!r} has {len(widths)} readings")
        out.append(theorem[pos : match.start()] + chr(int(digits[: widths[0]], 16)))
        pos = match.start() + 2 + widths[0]
    return "".join(out) + theorem[pos:]


def row_outcome(
    theorem: str, solved: bool | None, check_status: str | None, premises: str | None
) -> str:
    if solved is not True:
        return "unsolved"
    if check_status is None:
        return "unverified"
    if check_status in _FAILED:
        return "failed_check"
    if check_status != "checked":
        raise ValueError(f"solved row of {theorem} has check status {check_status!r}")
    if premises is None:
        raise ValueError(f"checked row of {theorem} has no premises")
    return "checked_selfcite" if decode_name(theorem) in json.loads(premises) else "checked"


def write_outcomes(conn: duckdb.DuckDBPyConnection, out: Path) -> Counter:
    """Write one row per (run_key, theorem, variant) with its outcome and per-mode solved."""
    conn.create_function(
        "wonton_row_outcome",
        row_outcome,
        [VARCHAR, BOOLEAN, VARCHAR, VARCHAR],
        VARCHAR,
        null_handling=FunctionNullHandling.SPECIAL,
    )
    mode_columns = ", ".join(
        f"list_contains({list(outcomes)}, outcome) AS solved_{mode}"
        for mode, outcomes in MODES.items()
    )
    try:
        conn.execute(
            f"""
            CREATE TEMP TABLE wonton_outcomes AS
            WITH variants AS (
              SELECT run_key, theorem, 'wild_type' AS variant, solved FROM theorem_wild
              UNION ALL
              SELECT run_key, theorem, intervention AS variant, solved FROM theorem_intervention
            ), labelled AS (
              SELECT v.run_key, v.theorem, v.variant,
                     wonton_row_outcome(v.theorem, v.solved, t.check_status, t.premises::VARCHAR)
                       AS outcome
              FROM variants v
              LEFT JOIN theorem_variant_verdict t
                ON t.run_key = v.run_key AND t.theorem = v.theorem AND t.variant = v.variant
            )
            SELECT *, {mode_columns} FROM labelled
            """
        )
        duplicated = conn.execute(
            "SELECT count(*) - count(DISTINCT (run_key, theorem, variant)) FROM wonton_outcomes"
        ).fetchone()
        assert duplicated is not None
        if duplicated[0]:
            raise ValueError(f"lake has {duplicated[0]} duplicate (run_key, theorem, variant) rows")
        out.parent.mkdir(parents=True, exist_ok=True)
        conn.execute(f"COPY wonton_outcomes TO '{out}' (FORMAT parquet)")
        return Counter(
            dict(
                conn.execute("SELECT outcome, count(*) FROM wonton_outcomes GROUP BY 1").fetchall()
            )
        )
    finally:
        conn.execute("DROP TABLE IF EXISTS wonton_outcomes")
        conn.remove_function("wonton_row_outcome")
