from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import duckdb

TARGET_PROVIDERS = ("deepseek", "heuristic", "reprover")
FOLLOWUP_MARKER = "followup-2026-03"
P2_PREFIX = "p2-paired/"
P4_PREFIX = "p4-basin-deep/"
DEFAULT_DB_CANDIDATES = (
    os.environ.get("LAKE_DB_PATH"),
    "/Volumes/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb",
    "/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb",
)

INK = "#1f2937"
MUTED = "#6b7280"
BG = "#ffffff"
PANEL = "#f5f7fb"
BLUE = "#5b8ff9"
GREEN = "#52c41a"
RED = "#d64545"
PURPLE = "#7c4dff"
GRID = "#d6dde8"


def resolve_db_path(explicit: str | None) -> Path:
    candidates = [explicit, *DEFAULT_DB_CANDIDATES]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        if path.exists():
            return path
    raise FileNotFoundError("Could not locate lake.duckdb for paper figures")


def parse_run_status(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def completed_runs(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, str, str, str | None]]:
    rows = conn.execute(
        """
        SELECT run_key, run_id, provider, created_at, run_status
        FROM runs
        WHERE provider IN ('deepseek','heuristic','reprover')
          AND backend = 'lean'
          AND mode = 'research'
        """
    ).fetchall()
    out: list[tuple[str, str, str, str | None]] = []
    for run_key, run_id, provider, created_at, run_status in rows:
        if not isinstance(run_key, str) or not isinstance(run_id, str) or not isinstance(provider, str):
            continue
        status = parse_run_status(run_status)
        if status.get("status") != "completed":
            continue
        if status.get("partial_results"):
            continue
        out.append((run_key, run_id, provider, created_at if isinstance(created_at, str) else None))
    return out


def selected_run_keys(
    runs: list[tuple[str, str, str, str | None]],
    *,
    phase_prefixes: tuple[str, ...],
) -> list[str]:
    filtered: list[tuple[str, str, str, str | None]] = []
    for run_key, run_id, provider, created_at in runs:
        parts = run_id.split("/", 1)
        if len(parts) != 2:
            continue
        root, rest = parts
        if FOLLOWUP_MARKER not in root:
            continue
        if not any(rest.startswith(prefix) for prefix in phase_prefixes):
            continue
        filtered.append((run_key, run_id, provider, created_at))

    filtered.sort(key=lambda row: ((row[3] is None), row[3] or "", row[1], row[0]), reverse=True)
    seen: set[str] = set()
    deduped: list[str] = []
    for run_key, run_id, _, _ in filtered:
        if run_id in seen:
            continue
        seen.add(run_id)
        deduped.append(run_key)
    return deduped


def seed_run_keys(conn: duckdb.DuckDBPyConnection, table_name: str, run_keys: list[str]) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(f"CREATE TEMP TABLE {table_name}(run_key VARCHAR PRIMARY KEY)")
    if run_keys:
        conn.executemany(f"INSERT INTO {table_name} VALUES (?)", [(run_key,) for run_key in run_keys])


def svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        "<style>",
        f'text {{ font-family: -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif; fill: {INK}; }}',
        ".title { font-size: 22px; font-weight: 700; }",
        f'.subtitle {{ font-size: 13px; fill: {MUTED}; }}',
        ".label { font-size: 12px; }",
        f'.small {{ font-size: 11px; fill: {MUTED}; }}',
        f'.tick {{ font-size: 11px; fill: {MUTED}; }}',
        ".value { font-size: 12px; font-weight: 600; }",
        "</style>",
    ]


def write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines + ["</svg>"]) + "\n")


def query_provider_outcomes(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = conn.execute(
        """
        WITH control_null AS (
          SELECT run_key, theorem, solved AS control_null_solved
          FROM theorem_intervention WHERE intervention = 'control_null'
        ),
        base AS (
          SELECT r.provider, i.solved AS intervention_solved, i.baseline_solved,
                 cn.control_null_solved, c.hash_mismatch
          FROM theorem_intervention i
          JOIN selected_p2_runs s USING(run_key)
          JOIN runs r USING(run_key)
          LEFT JOIN control_null cn ON cn.run_key = i.run_key AND cn.theorem = i.theorem
          LEFT JOIN theorem_intervention_comparison c
            ON c.run_key = i.run_key AND c.theorem = i.theorem AND c.intervention = i.intervention
          WHERE COALESCE(i.is_control, FALSE) = FALSE AND i.intervention <> 'control_null'
        )
        SELECT provider,
               SUM(CASE WHEN baseline_solved IS TRUE AND control_null_solved IS TRUE AND intervention_solved IS TRUE AND COALESCE(hash_mismatch, FALSE) = FALSE THEN 1 ELSE 0 END) AS main_hash_match_solved,
               SUM(CASE WHEN baseline_solved IS TRUE AND control_null_solved IS TRUE AND intervention_solved IS TRUE AND hash_mismatch IS TRUE THEN 1 ELSE 0 END) AS main_reroute_solved,
               SUM(CASE WHEN baseline_solved IS TRUE AND control_null_solved IS TRUE AND intervention_solved IS NOT TRUE THEN 1 ELSE 0 END) AS main_collapse,
               SUM(CASE WHEN baseline_solved IS FALSE AND intervention_solved IS TRUE THEN 1 ELSE 0 END) AS appendix_rescue,
               SUM(CASE WHEN baseline_solved IS TRUE AND control_null_solved IS NOT TRUE AND intervention_solved IS TRUE THEN 1 ELSE 0 END) AS appendix_null_unstable_solved,
               SUM(CASE WHEN baseline_solved IS TRUE AND control_null_solved IS NOT TRUE AND intervention_solved IS NOT TRUE THEN 1 ELSE 0 END) AS appendix_null_unstable_collapse
        FROM base
        GROUP BY provider
        ORDER BY provider
        """
    ).fetchall()
    return [
        {
            "provider": provider,
            "main_hash_match_solved": int(main_hash_match_solved or 0),
            "main_reroute_solved": int(main_reroute_solved or 0),
            "main_collapse": int(main_collapse or 0),
            "appendix_rescue": int(appendix_rescue or 0),
            "appendix_null_unstable_solved": int(appendix_null_unstable_solved or 0),
            "appendix_null_unstable_collapse": int(appendix_null_unstable_collapse or 0),
        }
        for (
            provider,
            main_hash_match_solved,
            main_reroute_solved,
            main_collapse,
            appendix_rescue,
            appendix_null_unstable_solved,
            appendix_null_unstable_collapse,
        ) in rows
    ]


def query_structural_rows(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = conn.execute(
        """
        WITH control_null AS (
          SELECT run_key, theorem, solved AS control_null_solved
          FROM theorem_intervention WHERE intervention = 'control_null'
        )
        SELECT c.ged_search_norm, c.hash_mismatch
        FROM theorem_intervention i
        JOIN selected_p2_runs s USING(run_key)
        LEFT JOIN control_null cn ON cn.run_key = i.run_key AND cn.theorem = i.theorem
        LEFT JOIN theorem_intervention_comparison c
          ON c.run_key = i.run_key AND c.theorem = i.theorem AND c.intervention = i.intervention
        WHERE COALESCE(i.is_control, FALSE) = FALSE
          AND i.intervention <> 'control_null'
          AND i.baseline_solved IS TRUE
          AND cn.control_null_solved IS TRUE
          AND i.solved IS TRUE
        """
    ).fetchall()
    out = []
    for ged_search_norm, hash_mismatch in rows:
        if not isinstance(ged_search_norm, (int, float)):
            continue
        out.append({
            "ged": float(ged_search_norm),
            "reroute": bool(hash_mismatch),
        })
    return out


def query_basin_rows(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = conn.execute(
        """
        WITH control_null AS (
          SELECT run_key, theorem, solved AS control_null_solved
          FROM theorem_intervention WHERE intervention = 'control_null'
        ),
        p2 AS (
          SELECT r.provider, i.theorem,
                 AVG(CASE WHEN i.solved IS NULL THEN NULL ELSE CAST(i.solved AS DOUBLE) END) AS lesion_recovery_rate
          FROM theorem_intervention i
          JOIN selected_p2_runs s USING(run_key)
          JOIN runs r USING(run_key)
          LEFT JOIN control_null cn ON cn.run_key = i.run_key AND cn.theorem = i.theorem
          WHERE COALESCE(i.is_control, FALSE) = FALSE
            AND i.intervention <> 'control_null'
            AND i.baseline_solved IS TRUE
            AND cn.control_null_solved IS TRUE
          GROUP BY r.provider, i.theorem
        ),
        p4 AS (
          SELECT r.provider, b.theorem,
                 AVG(b.unique_structures) AS unique_structures,
                 AVG(b.paper_k) AS paper_k
          FROM basin_runs b
          JOIN selected_p4_runs s USING(run_key)
          JOIN runs r USING(run_key)
          GROUP BY r.provider, b.theorem
        )
        SELECT p2.provider, p2.theorem, p2.lesion_recovery_rate, p4.unique_structures, p4.paper_k
        FROM p2 JOIN p4 ON p4.provider = p2.provider AND p4.theorem = p2.theorem
        ORDER BY p2.provider, p2.theorem
        """
    ).fetchall()
    return [
        {
            "provider": provider,
            "theorem": theorem,
            "lesion_recovery_rate": float(lesion_recovery_rate),
            "unique_structures": float(unique_structures),
            "paper_k": float(paper_k),
        }
        for provider, theorem, lesion_recovery_rate, unique_structures, paper_k in rows
        if isinstance(provider, str)
        and isinstance(theorem, str)
        and isinstance(lesion_recovery_rate, (int, float))
        and isinstance(unique_structures, (int, float))
        and isinstance(paper_k, (int, float))
    ]


def build_lesion_outcomes(rows: list[dict], out_path: Path) -> None:
    labels = [
        ("deepseek", "deepseek"),
        ("heuristic", "heuristic"),
        ("reprover", "reprover"),
    ]
    values = {
        provider: {
            "main_hash_match_solved": 0,
            "main_reroute_solved": 0,
            "main_collapse": 0,
            "appendix_rescue": 0,
            "appendix_null_unstable_solved": 0,
            "appendix_null_unstable_collapse": 0,
        }
        for provider in TARGET_PROVIDERS
    }
    for row in rows:
        values[row["provider"]] = row

    width, height = 1040, 420
    left_scale = 16.0
    right_scale = 11.0
    left_x = 70
    right_x = 560
    top_y = 125
    row_gap = 82
    lines = svg_header(width, height)
    lines += [
        '<text x="40" y="34" class="title">March p2 lesion outcomes from the shared lake</text>',
        '<text x="40" y="58" class="subtitle">Only followup-2026-03 p2-paired runs. Strict main denominator on the right; appendix-only spillover on the left.</text>',
        f'<rect x="40" y="82" width="470" height="270" rx="10" fill="{PANEL}" stroke="{GRID}"/>',
        f'<rect x="530" y="82" width="470" height="270" rx="10" fill="{PANEL}" stroke="{GRID}"/>',
        '<text x="60" y="108" class="label" style="font-weight:700">Appendix-only spillover</text>',
        '<text x="550" y="108" class="label" style="font-weight:700">Strict main-text denominator</text>',
        f'<rect x="60" y="365" width="14" height="14" fill="{GREEN}"/><text x="82" y="377" class="small">rescue</text>',
        f'<rect x="150" y="365" width="14" height="14" fill="{PURPLE}"/><text x="172" y="377" class="small">null-unstable solved</text>',
        f'<rect x="300" y="365" width="14" height="14" fill="{RED}"/><text x="322" y="377" class="small">null-unstable collapse</text>',
        f'<rect x="550" y="365" width="14" height="14" fill="{BLUE}"/><text x="572" y="377" class="small">hash-match solve</text>',
        f'<rect x="695" y="365" width="14" height="14" fill="{PURPLE}"/><text x="717" y="377" class="small">reroute</text>',
        f'<rect x="785" y="365" width="14" height="14" fill="{RED}"/><text x="807" y="377" class="small">collapse</text>',
    ]
    for idx, (provider, label) in enumerate(labels):
        y = top_y + idx * row_gap
        row = values[provider]
        lines.append(f'<text x="54" y="{y+4}" class="label" text-anchor="end">{label}</text>')
        lines.append(f'<rect x="{left_x}" y="{y-14}" width="400" height="28" fill="none" stroke="{GRID}"/>')
        rescue = row["appendix_rescue"]
        null_solved = row["appendix_null_unstable_solved"]
        null_collapse = row["appendix_null_unstable_collapse"]
        offset = left_x
        for value, color in ((rescue, GREEN), (null_solved, PURPLE), (null_collapse, RED)):
            if value:
                width_px = value * left_scale
                lines.append(f'<rect x="{offset}" y="{y-14}" width="{width_px}" height="28" fill="{color}"/>')
                lines.append(f'<text x="{offset + width_px/2}" y="{y+5}" class="value" text-anchor="middle" fill="white">{value}</text>')
                offset += width_px
        lines.append(f'<text x="544" y="{y+4}" class="label" text-anchor="end">{label}</text>')
        lines.append(f'<rect x="{right_x}" y="{y-14}" width="390" height="28" fill="none" stroke="{GRID}"/>')
        exact = row["main_hash_match_solved"]
        reroute = row["main_reroute_solved"]
        collapse = row["main_collapse"]
        offset = right_x
        for value, color in ((exact, BLUE), (reroute, PURPLE), (collapse, RED)):
            if value:
                width_px = value * right_scale
                lines.append(f'<rect x="{offset}" y="{y-14}" width="{width_px}" height="28" fill="{color}"/>')
                lines.append(f'<text x="{offset + width_px/2}" y="{y+5}" class="value" text-anchor="middle" fill="white">{value}</text>')
                offset += width_px
    write_svg(out_path, lines)


def build_structural_drift(rows: list[dict], out_path: Path) -> None:
    buckets = [
        ("0.00", lambda x: x == 0),
        (".01-.10", lambda x: 0 < x <= 0.10),
        (".11-.20", lambda x: 0.10 < x <= 0.20),
        (".21-.30", lambda x: 0.20 < x <= 0.30),
        (".31-.40", lambda x: 0.30 < x <= 0.40),
        (".41-.50", lambda x: 0.40 < x <= 0.50),
        (".51-.60", lambda x: 0.50 < x <= 0.60),
        (".61-.70", lambda x: 0.60 < x <= 0.70),
        (".71-.80", lambda x: 0.70 < x <= 0.80),
        (".81-.90", lambda x: 0.80 < x <= 0.90),
        (".91-1.0", lambda x: 0.90 < x <= 1.0),
    ]
    exact_counts: list[int] = []
    reroute_counts: list[int] = []
    for _, pred in buckets:
        exact_counts.append(sum(1 for row in rows if pred(row["ged"]) and not row["reroute"]))
        reroute_counts.append(sum(1 for row in rows if pred(row["ged"]) and row["reroute"]))
    total = len(rows)
    nonzero = sum(1 for row in rows if row["ged"] > 0)
    reroutes = sum(1 for row in rows if row["reroute"])
    width, height = 960, 430
    left = 70
    bottom = 345
    chart_h = 210
    bar_w = 55
    gap = 16
    max_count = max((a + b for a, b in zip(exact_counts, reroute_counts)), default=1)
    lines = svg_header(width, height)
    lines += [
        '<text x="40" y="34" class="title">Structural drift among March p2 strict-denominator recoveries</text>',
        f'<text x="40" y="58" class="subtitle">{nonzero} of {total} solved strict-denominator rows have non-zero normalized GED; {reroutes} are explicit solved reroutes.</text>',
        f'<rect x="40" y="82" width="880" height="300" rx="10" fill="{PANEL}" stroke="{GRID}"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{left + 10*(bar_w+gap) + bar_w}" y2="{bottom}" stroke="{INK}" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{left}" y2="{bottom-chart_h}" stroke="{INK}" stroke-width="1.5"/>',
    ]
    for idx, ((label, _), exact, reroute) in enumerate(zip(buckets, exact_counts, reroute_counts)):
        x = left + idx * (bar_w + gap)
        exact_h = 0 if max_count == 0 else exact / max_count * (chart_h - 10)
        reroute_h = 0 if max_count == 0 else reroute / max_count * (chart_h - 10)
        if exact:
            lines.append(f'<rect x="{x}" y="{bottom-exact_h}" width="{bar_w}" height="{exact_h}" fill="{BLUE}" stroke="{INK}"/>')
        if reroute:
            lines.append(f'<rect x="{x}" y="{bottom-exact_h-reroute_h}" width="{bar_w}" height="{reroute_h}" fill="{PURPLE}" stroke="{INK}"/>')
        total_count = exact + reroute
        if total_count:
            lines.append(f'<text x="{x + bar_w/2}" y="{bottom-exact_h-reroute_h-8}" class="value" text-anchor="middle">{total_count}</text>')
        lines.append(f'<text x="{x + bar_w/2}" y="{bottom+20}" class="tick" text-anchor="middle">{label}</text>')
    step = 10 if max_count > 20 else 5 if max_count > 10 else 1
    for tick in range(0, max_count + 1, step):
        y = bottom - (0 if max_count == 0 else tick / max_count * (chart_h - 10))
        lines.append(f'<line x1="{left-6}" y1="{y}" x2="{left}" y2="{y}" stroke="{INK}" stroke-width="1"/>')
        lines.append(f'<text x="{left-12}" y="{y+4}" class="tick" text-anchor="end">{tick}</text>')
    lines += [
        f'<text x="{left + 10*(bar_w+gap)/2}" y="385" class="small" text-anchor="middle">normalized GED on solved strict-denominator rows</text>',
        f'<text x="24" y="230" class="small" transform="rotate(-90 24 230)">count</text>',
        f'<rect x="620" y="100" width="14" height="14" fill="{BLUE}"/><text x="642" y="112" class="small">hash-match solve</text>',
        f'<rect x="760" y="100" width="14" height="14" fill="{PURPLE}"/><text x="782" y="112" class="small">reroute</text>',
    ]
    write_svg(out_path, lines)


def build_basin_resilience(rows: list[dict], out_path: Path) -> None:
    width, height = 960, 460
    left = 90
    bottom = 360
    chart_w = 760
    chart_h = 230
    provider_style = {
        "deepseek": (BLUE, "circle", -0.12),
        "heuristic": (GREEN, "circle", 0.0),
        "reprover": (RED, "square", 0.12),
    }
    x_values = [row["unique_structures"] for row in rows]
    if x_values:
        xmin_raw = min(x_values)
        xmax_raw = max(x_values)
        if math.isclose(xmin_raw, xmax_raw):
            xmin, xmax = xmin_raw - 0.5, xmax_raw + 0.5
        else:
            xmin, xmax = math.floor(xmin_raw) - 0.5, math.ceil(xmax_raw) + 0.5
    else:
        xmin, xmax = -0.5, 1.5
    ymin, ymax = -0.05, 1.05
    providers_present = {row["provider"] for row in rows}
    missing_providers = [provider for provider in TARGET_PROVIDERS if provider not in providers_present]

    if not rows:
        subtitle = "No matched p4-deep basin rows survive the join from March p2 lesion outcomes to March p4 basin runs."
    elif math.isclose(min(x_values), max(x_values)):
        subtitle = (
            f"Matched p4-deep join spans {len(rows)} rows; all rows have unique-structure count {x_values[0]:.0f}, "
            "so this slice cannot identify a basin-width effect yet."
        )
    else:
        subtitle = (
            f"Matched p4-deep join spans {len(rows)} rows with unique-structure counts from {min(x_values):.0f} to {max(x_values):.0f}."
        )

    lines = svg_header(width, height)
    lines += [
        '<text x="40" y="34" class="title">March p4 deep-basin slice from the shared lake</text>',
        f'<text x="40" y="58" class="subtitle">{subtitle}</text>',
        f'<rect x="40" y="82" width="880" height="320" rx="10" fill="{PANEL}" stroke="{GRID}"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{left+chart_w}" y2="{bottom}" stroke="{INK}" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{left}" y2="{bottom-chart_h}" stroke="{INK}" stroke-width="1.5"/>',
    ]

    tick_start = math.ceil(xmin)
    tick_end = math.floor(xmax)
    for x in range(tick_start, tick_end + 1):
        px = left + (x - xmin) / (xmax - xmin) * chart_w
        lines.append(f'<line x1="{px}" y1="{bottom}" x2="{px}" y2="{bottom+6}" stroke="{INK}" stroke-width="1"/>')
        lines.append(f'<text x="{px}" y="{bottom+22}" class="tick" text-anchor="middle">{x}</text>')
    for y in [0.0, 0.25, 0.5, 0.75, 1.0]:
        py = bottom - (y - ymin) / (ymax - ymin) * chart_h
        lines.append(f'<line x1="{left-6}" y1="{py}" x2="{left}" y2="{py}" stroke="{INK}" stroke-width="1"/>')
        lines.append(f'<text x="{left-12}" y="{py+4}" class="tick" text-anchor="end">{y:g}</text>')
        lines.append(f'<line x1="{left}" y1="{py}" x2="{left+chart_w}" y2="{py}" stroke="{GRID}" stroke-dasharray="2 4"/>')
    lines.append(f'<text x="{left+chart_w/2}" y="410" class="small" text-anchor="middle">average unique structures per matched theorem-provider row</text>')
    lines.append(f'<text x="28" y="245" class="small" transform="rotate(-90 28 245)">lesion recovery rate</text>')

    for row in rows:
        color, shape, offset = provider_style[row["provider"]]
        x_val = row["unique_structures"] + offset
        px = left + (x_val - xmin) / (xmax - xmin) * chart_w
        py = bottom - (row["lesion_recovery_rate"] - ymin) / (ymax - ymin) * chart_h
        if shape == "circle":
            lines.append(f'<circle cx="{px}" cy="{py}" r="6" fill="{color}" stroke="{INK}"/>')
        else:
            lines.append(f'<rect x="{px-6}" y="{py-6}" width="12" height="12" fill="{color}" stroke="{INK}"/>')

    lines += [
        f'<circle cx="630" cy="110" r="6" fill="{BLUE}" stroke="{INK}"/><text x="645" y="114" class="small">deepseek</text>',
        f'<circle cx="735" cy="110" r="6" fill="{GREEN}" stroke="{INK}"/><text x="750" y="114" class="small">heuristic</text>',
        f'<rect x="842" y="104" width="12" height="12" fill="{RED}" stroke="{INK}"/><text x="860" y="114" class="small">reprover</text>',
    ]
    if missing_providers:
        lines.append(
            f'<text x="630" y="132" class="small">Missing completed p4-deep providers in this slice: {", ".join(missing_providers)}.</text>'
        )
    write_svg(out_path, lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paper SVG figures directly from the shared Wonton lake")
    parser.add_argument("--db", help="Path to lake.duckdb (defaults to LAKE_DB_PATH or the shared runtime lake)")
    parser.add_argument("--out-dir", required=True, help="Output directory for generated SVGs")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    out_dir = Path(args.out_dir).resolve()

    conn = duckdb.connect(str(db_path), read_only=True)
    runs = completed_runs(conn)
    p2_run_keys = selected_run_keys(runs, phase_prefixes=(P2_PREFIX,))
    p4_run_keys = selected_run_keys(runs, phase_prefixes=(P4_PREFIX,))
    seed_run_keys(conn, "selected_p2_runs", p2_run_keys)
    seed_run_keys(conn, "selected_p4_runs", p4_run_keys)

    provider_rows = query_provider_outcomes(conn)
    structural_rows = query_structural_rows(conn)
    basin_rows = query_basin_rows(conn)

    build_lesion_outcomes(provider_rows, out_dir / "fig17-followup-provider-splits.svg")
    build_structural_drift(structural_rows, out_dir / "fig16-ged-bimodality.svg")
    build_basin_resilience(basin_rows, out_dir / "fig18-followup-basins.svg")


if __name__ == "__main__":
    main()
