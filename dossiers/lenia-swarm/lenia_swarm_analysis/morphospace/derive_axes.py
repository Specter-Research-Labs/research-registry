from __future__ import annotations

import json
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    developmental_trace_from_samples,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

from .warehouse import replace_development_sample_axes, replace_specimen_axes


def derive_axes(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        specimen_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT specimen_id FROM specimens ORDER BY specimen_id"
            ).fetchall()
        ]
    else:
        specimen_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT specimen_id
                FROM study_specimens
                WHERE study_id = ?
                ORDER BY specimen_id
                """,
                [study_id],
            ).fetchall()
        ]
    updated = 0
    for specimen_id in specimen_ids:
        row = connection.execute(
            "SELECT provenance_json FROM specimens WHERE specimen_id = ?",
            [specimen_id],
        ).fetchone()
        if row is None:
            continue
        provenance = json.loads(row[0]) if row[0] else {}
        sample_rows = connection.execute(
            """
            SELECT step, center_x, center_y, terminal_descriptor_json
            FROM development_samples
            WHERE specimen_id = ?
            ORDER BY step
            """,
            [specimen_id],
        ).fetchall()

        if sample_rows:
            trace_samples: list[dict[str, Any]] = []
            for step, center_x, center_y, terminal_descriptor_json in sample_rows:
                trace_samples.append(
                    {
                        "step": int(step),
                        "centerX": float(center_x),
                        "centerY": float(center_y),
                        "terminal": json.loads(terminal_descriptor_json),
                    }
                )
            terminal = provenance.get("terminal")
            if not isinstance(terminal, dict):
                terminal = trace_samples[-1]["terminal"]
            trajectory = provenance.get("trajectory")
            if not isinstance(trajectory, dict):
                trajectory = {"centerVelocity": 0.0, "pathTortuosity": 0.0}
            terminal_axes = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal,
                trajectory=trajectory,
                specimen_id=specimen_id,
            )
            transformed_terminal = transform_axes(terminal_axes)
            development = developmental_trace_from_samples(
                specimen_id=specimen_id,
                trace_samples=trace_samples,
                meander_final=float(terminal_axes["meander"]),
            )
            replace_specimen_axes(
                connection,
                specimen_id=specimen_id,
                axis_rows=[
                    *[
                        (
                            axis_id,
                            "terminal",
                            float(terminal_axes[axis_id]),
                            float(transformed_terminal[axis_id]),
                        )
                        for axis_id in TERMINAL_AXIS_IDS
                    ],
                    *[
                        (
                            axis_id,
                            "developmental",
                            (
                                None
                                if development["developmentalAxes"][axis_id] is None
                                else float(development["developmentalAxes"][axis_id])
                            ),
                            (
                                None
                                if development["transformedDevelopmentalAxes"][axis_id] is None
                                else float(development["transformedDevelopmentalAxes"][axis_id])
                            ),
                        )
                        for axis_id in DEVELOPMENTAL_AXIS_IDS
                    ],
                ],
            )
            trace_axis_rows = []
            for axis_id, values in development["traceAxes"].items():
                for step, value in zip(development["steps"], values, strict=True):
                    trace_axis_rows.append((int(step), str(axis_id), float(value)))
            replace_development_sample_axes(
                connection,
                specimen_id=specimen_id,
                axis_rows=trace_axis_rows,
            )
            updated += 1
            continue

        terminal = provenance.get("terminal")
        trajectory = provenance.get("trajectory")
        if isinstance(terminal, dict):
            if not isinstance(trajectory, dict):
                trajectory = {"centerVelocity": 0.0, "pathTortuosity": 0.0}
            terminal_axes = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal,
                trajectory=trajectory,
                specimen_id=specimen_id,
            )
            transformed_terminal = transform_axes(terminal_axes)
            replace_specimen_axes(
                connection,
                specimen_id=specimen_id,
                axis_rows=[
                    (
                        axis_id,
                        "terminal",
                        float(value),
                        float(transformed_terminal[axis_id]),
                    )
                    for axis_id, value in terminal_axes.items()
                ],
            )
            updated += 1
    return updated
