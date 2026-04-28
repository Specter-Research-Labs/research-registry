from __future__ import annotations

import json

from duckdb import DuckDBPyConnection

from .creature_signals import creature_labels, derive_creature_signal_axes
from .warehouse import replace_creature_signal_axes, upsert_creature_state_labels


def _baseline_state_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> list[tuple[str, str, str]]:
    if study_id is None:
        rows = connection.execute(
            """
            SELECT anatomical_states.state_id,
                   anatomical_states.specimen_id,
                   anatomical_states.study_id
            FROM anatomical_states
            JOIN studies ON studies.study_id = anatomical_states.study_id
            JOIN contexts USING (context_id)
            WHERE anatomical_states.source_kind = 'specimen_baseline'
              AND contexts.context_kind = 'baseline'
              AND studies.study_kind = 'replay_batch'
            ORDER BY anatomical_states.study_id, anatomical_states.specimen_id
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT anatomical_states.state_id,
                   anatomical_states.specimen_id,
                   anatomical_states.study_id
            FROM anatomical_states
            JOIN contexts USING (context_id)
            WHERE anatomical_states.study_id = ?
              AND anatomical_states.source_kind = 'specimen_baseline'
              AND contexts.context_kind = 'baseline'
            ORDER BY anatomical_states.specimen_id
            """,
            [study_id],
        ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


def _trace_samples(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT step, center_x, center_y, terminal_descriptor_json
        FROM development_samples
        WHERE specimen_id = ?
        ORDER BY step
        """,
        [specimen_id],
    ).fetchall()
    samples: list[dict[str, object]] = []
    for step, center_x, center_y, terminal_descriptor_json in rows:
        terminal = json.loads(terminal_descriptor_json) if terminal_descriptor_json else {}
        samples.append(
            {
                "step": int(step),
                "centerX": float(center_x),
                "centerY": float(center_y),
                "terminal": terminal,
            }
        )
    return samples


def _raw_state_axes(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
) -> dict[str, float]:
    return {
        str(axis_id): float(raw_value)
        for axis_id, raw_value in connection.execute(
            """
            SELECT axis_id, raw_value
            FROM anatomical_state_axes
            WHERE state_id = ? AND raw_value IS NOT NULL
            """,
            [state_id],
        ).fetchall()
    }


def derive_creature_signals(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    state_rows = _baseline_state_rows(connection, study_id=study_id)
    if study_id is not None and not state_rows:
        raise SystemExit(
            f"{study_id}: derive-creature-signals requires "
            "baseline anatomical states from replay data"
        )
    updated = 0
    for state_id, specimen_id, state_study_id in state_rows:
        trace_samples = _trace_samples(connection, specimen_id=specimen_id)
        if not trace_samples:
            if study_id is not None:
                raise SystemExit(
                    f"{state_study_id}/{specimen_id}: missing development_samples "
                    "for creature signals"
                )
            continue
        signal_axes = derive_creature_signal_axes(
            specimen_id=specimen_id,
            trace_samples=trace_samples,
        )
        raw_axes = _raw_state_axes(connection, state_id=state_id)
        labels = creature_labels(raw_axes=raw_axes, creature_axes=signal_axes)
        replace_creature_signal_axes(
            connection,
            state_id=state_id,
            axis_rows=[
                (axis_id, float(value), float(value))
                for axis_id, value in sorted(signal_axes.items())
            ],
        )
        upsert_creature_state_labels(
            connection,
            state_id=state_id,
            coherence_class=labels["coherence_class"],
            organization_class=labels["organization_class"],
            mobility_class=labels["mobility_class"],
            creature_bucket=labels["creature_bucket"],
            metadata_json={
                "sourceStudyId": state_study_id,
                "sampleCount": len(trace_samples),
                "signalAxes": sorted(signal_axes),
            },
        )
        updated += 1
    return updated
