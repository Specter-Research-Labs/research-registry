from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import duckdb

from . import paths

LENIA_FEATURE_SPACE = "lenia_terminal_v1"


@dataclass(frozen=True)
class OverlayRow:
    name: str
    specimen_id: str
    whole_cortex: float
    roi_scores: dict[str, float]
    descriptor_axes: dict[str, float]


@dataclass(frozen=True)
class OverlayPayload:
    feature_space: str
    warehouse: str
    score_report: str
    n_linked: int
    n_unlinked: int
    unlinked_names: list[str]
    rois: list[str]
    rows: list[OverlayRow]

    def to_json(self) -> str:
        return json.dumps(
            {
                "feature_space": self.feature_space,
                "warehouse": self.warehouse,
                "score_report": self.score_report,
                "n_linked": self.n_linked,
                "n_unlinked": self.n_unlinked,
                "unlinked_names": self.unlinked_names,
                "rois": self.rois,
                "rows": [
                    {
                        "name": r.name,
                        "specimen_id": r.specimen_id,
                        "whole_cortex": r.whole_cortex,
                        "roi_scores": r.roi_scores,
                        "descriptor_axes": r.descriptor_axes,
                    }
                    for r in self.rows
                ],
            },
            indent=2,
            sort_keys=True,
        )


def _load_score_rows(report_path: Path) -> tuple[list[dict[str, object]], list[str]]:
    raw: object = json.loads(report_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"score report {report_path} root must be an object")
    report = cast(dict[str, object], raw)
    rows_obj = report.get("rows")
    if not isinstance(rows_obj, list):
        raise ValueError(f"score report {report_path} has no 'rows' array")
    rois_obj = report.get("rois")
    if not isinstance(rois_obj, dict):
        raise ValueError(f"score report {report_path} has no 'rois' object")
    rows: list[dict[str, object]] = []
    for r in rows_obj:
        if not isinstance(r, dict):
            raise ValueError(f"score report {report_path} contains a non-object row")
        rows.append(cast(dict[str, object], r))
    return rows, [str(k) for k in cast(dict[str, object], rois_obj).keys()]


def _fetch_descriptors(
    warehouse: Path, specimen_ids: list[str]
) -> dict[str, dict[str, float]]:
    """Return {specimen_id: {axis_id: normalized_value}} for lenia_terminal_v1.

    invariant: feature_values.normalized_value is the descriptor in axis-local units
    (per the warehouse metadata for lenia_terminal_v1). raw_value is the un-transformed
    Lenia descriptor; we use normalized for cross-axis comparability.
    """
    if not warehouse.is_file():
        raise FileNotFoundError(f"morphospace warehouse not found: {warehouse}")
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        placeholders = ",".join("?" for _ in specimen_ids)
        sql = f"""
            SELECT s.specimen_id, fv.axis_id, fv.normalized_value
            FROM specimens s
            JOIN observations o ON s.specimen_id = o.specimen_id
            JOIN feature_values fv ON o.observation_id = fv.observation_id
            WHERE fv.feature_space_id = ?
              AND s.specimen_id IN ({placeholders})
        """
        rows = con.execute(sql, [LENIA_FEATURE_SPACE, *specimen_ids]).fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, float]] = {}
    for sid, axis_id, value in rows:
        out.setdefault(sid, {})[str(axis_id)] = float(value)
    return out


def join(report_path: Path, warehouse: Path) -> OverlayPayload:
    rows, roi_names = _load_score_rows(report_path)
    linked = [r for r in rows if r.get("specimen_id")]
    unlinked_names = [str(r["name"]) for r in rows if not r.get("specimen_id")]
    if not linked:
        raise ValueError(
            f"score report {report_path} has no rows with specimen_id; "
            "rerun lenia-tribe-score with --manifest to attach specimen_ids"
        )
    specimen_ids = [str(r["specimen_id"]) for r in linked]
    descriptors = _fetch_descriptors(warehouse, specimen_ids)
    missing = sorted(set(specimen_ids) - set(descriptors.keys()))
    if missing:
        raise KeyError(
            f"specimen_ids in manifest not found in warehouse for {LENIA_FEATURE_SPACE}: {missing}"
        )
    overlay_rows = [
        OverlayRow(
            name=str(r["name"]),
            specimen_id=str(r["specimen_id"]),
            whole_cortex=float(r["whole_cortex"]),  # ty: ignore[invalid-argument-type]
            roi_scores={name: float(r[name]) for name in roi_names},  # ty: ignore[invalid-argument-type]
            descriptor_axes=descriptors[str(r["specimen_id"])],
        )
        for r in linked
    ]
    return OverlayPayload(
        feature_space=LENIA_FEATURE_SPACE,
        warehouse=str(warehouse.resolve()),
        score_report=str(report_path.resolve()),
        n_linked=len(overlay_rows),
        n_unlinked=len(unlinked_names),
        unlinked_names=unlinked_names,
        rois=roi_names,
        rows=overlay_rows,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Join a TRIBE score report to lenia-swarm morphospace descriptors."
    )
    parser.add_argument("--score-report", type=Path, required=True)
    parser.add_argument(
        "--warehouse",
        type=Path,
        required=True,
        help="Path to lenia-swarm morphospace.duckdb.",
    )
    args = parser.parse_args(argv)

    payload = join(args.score_report, args.warehouse)
    out_dir = paths.ensure(paths.artifact_root() / "overlays")
    stem = args.score_report.stem
    out = out_dir / f"{stem}.overlay.json"
    out.write_text(payload.to_json())

    header = ["name", "specimen_id", "whole", *payload.rois]
    print("\t".join(header))
    for row in payload.rows:
        cells = [row.name, row.specimen_id, f"{row.whole_cortex:+.4f}"]
        for roi_name in payload.rois:
            cells.append(f"{row.roi_scores[roi_name]:+.4f}")
        print("\t".join(cells))
    print(f"\noverlay report: {out}")
    print(f"linked: {payload.n_linked}  unlinked: {payload.n_unlinked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
