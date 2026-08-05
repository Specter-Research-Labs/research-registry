from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    developmental_trace_from_samples,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

from .warehouse import (
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
)

_DERIVATION_BATCH_SIZE = 4096


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _eligible_specimen_batch(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
    after_specimen_id: str | None,
) -> list[tuple[Any, ...]]:
    study_clause = ""
    params: list[Any] = []
    if study_id is not None:
        study_clause = "AND specimens.study_id = ?"
        params.append(study_id)
    return connection.execute(
        f"""
        SELECT specimens.specimen_id,
               specimens.provenance_json,
               specimen_descriptors.terminal_descriptor_json,
               specimen_descriptors.trajectory_descriptor_json
        FROM specimens
        JOIN specimen_descriptors USING (specimen_id)
        JOIN studies ON studies.study_id = specimens.study_id
        WHERE specimens.descriptor_version = ?
          AND specimens.terminal_version = ?
          AND specimens.normalization_policy = ?
          AND specimens.fingerprint_resolution = 32
          AND specimen_descriptors.descriptor_version = ?
          AND specimen_descriptors.terminal_version = ?
          AND specimen_descriptors.normalization_policy = ?
          AND specimen_descriptors.fingerprint_resolution = 32
          AND json_extract_string(
              specimen_descriptors.terminal_descriptor_json,
              '$.borderMode'
          ) = 'torus'
          AND EXISTS (
              SELECT 1
              FROM study_specimens
              WHERE study_specimens.study_id = specimens.study_id
                AND study_specimens.specimen_id = specimens.specimen_id
          )
          {study_clause}
          AND (? IS NULL OR specimens.specimen_id > ?)
        ORDER BY specimens.specimen_id
        LIMIT ?
        """,
        [
            DESCRIPTOR_VERSION,
            TERMINAL_VERSION,
            NORMALIZATION_POLICY,
            DESCRIPTOR_VERSION,
            TERMINAL_VERSION,
            NORMALIZATION_POLICY,
            *params,
            after_specimen_id,
            after_specimen_id,
            _DERIVATION_BATCH_SIZE,
        ],
    ).fetchall()


def _development_samples_by_specimen(
    connection: DuckDBPyConnection,
    specimen_ids: list[str],
) -> dict[str, list[tuple[Any, ...]]]:
    rows = connection.execute(
        """
        SELECT specimen_id, step, width, height, center_x, center_y,
               terminal_descriptor_json
        FROM development_samples
        WHERE specimen_id IN (SELECT unnest(?::VARCHAR[]))
        ORDER BY specimen_id, step
        """,
        [specimen_ids],
    ).fetchall()
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for specimen_id, *sample in rows:
        grouped[str(specimen_id)].append(tuple(sample))
    return grouped


def _replace_axis_batch(
    connection: DuckDBPyConnection,
    *,
    specimen_ids: list[str],
    specimen_axis_rows: list[tuple[str, str, str, float | None, float | None]],
    development_axis_rows: list[tuple[str, int, str, float]],
) -> None:
    connection.execute(
        "DELETE FROM specimen_axes "
        "WHERE specimen_id IN (SELECT unnest(?::VARCHAR[]))",
        [specimen_ids],
    )
    connection.execute(
        "DELETE FROM development_sample_axes "
        "WHERE specimen_id IN (SELECT unnest(?::VARCHAR[]))",
        [specimen_ids],
    )
    if specimen_axis_rows:
        columns = list(zip(*specimen_axis_rows, strict=True))
        connection.execute(
            """
            INSERT INTO specimen_axes (
                specimen_id, axis_id, axis_family, raw_value, transformed_value
            )
            SELECT unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
                   unnest(?::DOUBLE[]), unnest(?::DOUBLE[])
            """,
            [list(column) for column in columns],
        )
    if development_axis_rows:
        columns = list(zip(*development_axis_rows, strict=True))
        connection.execute(
            """
            INSERT INTO development_sample_axes (
                specimen_id, step, axis_id, raw_value
            )
            SELECT unnest(?::VARCHAR[]), unnest(?::INTEGER[]),
                   unnest(?::VARCHAR[]), unnest(?::DOUBLE[])
            """,
            [list(column) for column in columns],
        )


def derive_axes(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    updated = 0
    last_specimen_id: str | None = None
    while batch := _eligible_specimen_batch(
        connection,
        study_id=study_id,
        after_specimen_id=last_specimen_id,
    ):
        specimen_ids = [str(row[0]) for row in batch]
        last_specimen_id = specimen_ids[-1]
        samples_by_specimen = _development_samples_by_specimen(connection, specimen_ids)
        specimen_axis_rows: list[tuple[str, str, str, float | None, float | None]] = []
        development_axis_rows: list[tuple[str, int, str, float]] = []

        for specimen_id, provenance_json, terminal_json, trajectory_json in batch:
            resolved_specimen_id = str(specimen_id)
            provenance = _json_dict(provenance_json)
            terminal = _json_dict(terminal_json) or provenance.get("terminal")
            trajectory = _json_dict(trajectory_json) or provenance.get("trajectory")
            sample_rows = samples_by_specimen.get(resolved_specimen_id, [])
            trace_samples = [
                {
                    "step": int(step),
                    "centerX": float(center_x),
                    "centerY": float(center_y),
                    "width": int(width),
                    "height": int(height),
                    "terminal": _json_dict(sample_terminal_json),
                }
                for step, width, height, center_x, center_y, sample_terminal_json in sample_rows
            ]
            if not isinstance(terminal, dict):
                terminal = trace_samples[-1]["terminal"] if trace_samples else None
            if not isinstance(terminal, dict):
                raise ValueError(f"{resolved_specimen_id}: missing terminal descriptor")
            if not isinstance(trajectory, dict):
                trajectory = {"centerVelocity": 0.0, "pathTortuosity": 0.0}

            terminal_axes = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal,
                trajectory=trajectory,
                specimen_id=resolved_specimen_id,
            )
            transformed_terminal = transform_axes(terminal_axes)
            specimen_axis_rows.extend(
                (
                    resolved_specimen_id,
                    axis_id,
                    "terminal",
                    float(terminal_axes[axis_id]),
                    float(transformed_terminal[axis_id]),
                )
                for axis_id in TERMINAL_AXIS_IDS
            )
            if trace_samples:
                development = developmental_trace_from_samples(
                    specimen_id=resolved_specimen_id,
                    trace_samples=trace_samples,
                    meander_final=float(terminal_axes["meander"]),
                )
                specimen_axis_rows.extend(
                    (
                        resolved_specimen_id,
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
                            else float(
                                development["transformedDevelopmentalAxes"][axis_id]
                            )
                        ),
                    )
                    for axis_id in DEVELOPMENTAL_AXIS_IDS
                )
                for axis_id, values in development["traceAxes"].items():
                    development_axis_rows.extend(
                        (
                            resolved_specimen_id,
                            int(step),
                            str(axis_id),
                            float(value),
                        )
                        for step, value in zip(
                            development["steps"], values, strict=True
                        )
                    )
            updated += 1

        _replace_axis_batch(
            connection,
            specimen_ids=specimen_ids,
            specimen_axis_rows=specimen_axis_rows,
            development_axis_rows=development_axis_rows,
        )
    return updated
