from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value:
            values[value] = values.get(value, 0) + 1
    return dict(sorted(values.items()))


def _optional_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else {}


def _video_path(frames_dir: str | None) -> str | None:
    if not isinstance(frames_dir, str) or not frames_dir:
        return None
    candidate = Path(frames_dir).expanduser().resolve().parent / "development.mp4"
    if candidate.exists():
        return str(candidate)
    return None


def _matches_lens(row: dict[str, Any], lens: str | None) -> bool:
    if lens is None:
        return True
    coherence_class = row.get("coherenceClass")
    creature_bucket = row.get("creatureBucket")
    mean_body_plan_class_shift = row.get("meanBodyPlanClassShiftScore")
    mean_coherence_drop = row.get("meanCoherenceDropScore")
    if lens == "coherent-bodies":
        return coherence_class in {"coherent_body", "soft_body"}
    if lens == "enclosing-bodies":
        return creature_bucket == "coherent_enclosing"
    if lens == "mobile-coherent-bodies":
        return creature_bucket == "coherent_mobile"
    if lens == "articulated-multipart-bodies":
        return creature_bucket == "articulated_multipart"
    if lens == "context-preserving-bodies":
        return (
            isinstance(mean_body_plan_class_shift, (int, float))
            and isinstance(mean_coherence_drop, (int, float))
            and float(mean_body_plan_class_shift) <= 0.34
            and float(mean_coherence_drop) <= 0.2
        )
    raise SystemExit(f"unsupported creature discovery lens: {lens}")


def export_creature_discovery(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None = None,
    lens: str | None = None,
) -> dict[str, Any]:
    if study_id is None:
        rows = connection.execute(
            """
            SELECT *
            FROM creature_discovery_candidates_vw
            ORDER BY creature_bucket, family_kind, specimen_id
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT *
            FROM creature_discovery_candidates_vw
            WHERE study_id = ?
            ORDER BY creature_bucket, family_kind, specimen_id
            """,
            [study_id],
        ).fetchall()
    columns = [column[0] for column in connection.description]
    candidates: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(zip(columns, row, strict=True))
        provenance = _optional_json(payload.get("provenance_json"))
        resolution_metadata = _optional_json(payload.get("resolution_metadata_json"))
        candidate = {
            "stateId": payload["state_id"],
            "specimenId": payload["specimen_id"],
            "studyId": payload["study_id"],
            "studyKind": payload["study_kind"],
            "sourceKind": payload["source_kind"],
            "sourceRef": payload["source_ref"],
            "familyKind": payload["family_kind"],
            "regimeFamily": payload["regime_family"],
            "geometryFamily": payload["geometry_family"],
            "canonicalFamily": payload["canonical_family"],
            "score": payload["score"],
            "coherenceClass": payload["coherence_class"],
            "organizationClass": payload["organization_class"],
            "mobilityClass": payload["mobility_class"],
            "creatureBucket": payload["creature_bucket"],
            "signals": {
                "largestComponentShareFinal": payload["largest_component_share_final"],
                "coherenceMean": payload["coherence_mean"],
                "coherenceMin": payload["coherence_min"],
                "fragmentationPeak": payload["fragmentation_peak"],
                "fragmentationVariability": payload["fragmentation_variability"],
                "partPersistenceScore": payload["part_persistence_score"],
                "shapePersistenceScore": payload["shape_persistence_score"],
                "symmetryStabilityScore": payload["symmetry_stability_score"],
                "polarityStabilityScore": payload["polarity_stability_score"],
                "enclosurePersistenceScore": payload["enclosure_persistence_score"],
                "wholeBodyMotionScore": payload["whole_body_motion_score"],
                "deformationWithoutDissolutionScore": payload[
                    "deformation_without_dissolution_score"
                ],
                "localizationScore": payload["localization_score"],
                "extentStabilityScore": payload["extent_stability_score"],
                "temporalIndividualityScore": payload["temporal_individuality_score"],
            },
            "replayable": payload["replayable"],
            "resolutionSource": payload["resolution_source"],
            "originalExportDir": payload["original_export_dir"],
            "resolvedExportDir": payload["resolved_export_dir"],
            "paths": {
                "resultsPath": payload["results_path"],
                "exportDir": payload["export_dir"],
                "resolvedExportDir": payload["resolved_export_dir"],
                "fingerprintPath": payload["fingerprint_path"],
                "activityPath": payload["activity_path"],
                "developmentTracePath": resolution_metadata.get("developmentTracePath")
                or provenance.get("developmentTracePath"),
                "developmentFramesDir": resolution_metadata.get("developmentFramesDir")
                or provenance.get("developmentFramesDir"),
                "developmentVideoPath": _video_path(
                    resolution_metadata.get("developmentFramesDir")
                    or provenance.get("developmentFramesDir")
                ),
            },
            "contextPreservation": {
                "meanBodyPlanErrorScore": payload["mean_body_plan_error_score"],
                "meanBodyPlanClassShiftScore": payload["mean_body_plan_class_shift_score"],
                "meanCoherenceDropScore": payload["mean_coherence_drop_score"],
                "meanOrganizationDropScore": payload["mean_organization_drop_score"],
                "meanWholeBodyMotionChangeScore": payload[
                    "mean_whole_body_motion_change_score"
                ],
            },
            "taxonomy": {
                "family": provenance.get("taxonomy_family_id"),
                "genus": provenance.get("taxonomy_genus_id"),
                "species": provenance.get("taxonomy_species_id"),
            },
        }
        if _matches_lens(candidate, lens):
            candidates.append(candidate)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        bucket = candidate.get("creatureBucket")
        bucket_key = str(bucket) if isinstance(bucket, str) and bucket else "unbucketed"
        candidate["creatureBucket"] = bucket_key
        grouped[bucket_key].append(candidate)
    return {
        "version": 1,
        "packetKind": "creature_discovery_v1",
        "sourceArtifacts": {
            "studyId": study_id,
            "lens": lens,
        },
        "summary": {
            "candidateCount": len(candidates),
            "bucketCount": len(grouped),
            "replayableCount": sum(1 for row in candidates if row.get("replayable") is True),
            "byCreatureBucket": _counts(candidates, "creatureBucket"),
            "byFamilyKind": _counts(candidates, "familyKind"),
        },
        "buckets": [
            {
                "creatureBucket": bucket,
                "candidateCount": len(bucket_rows),
                "byFamilyKind": _counts(bucket_rows, "familyKind"),
                "candidates": bucket_rows,
            }
            for bucket, bucket_rows in sorted(grouped.items())
        ],
    }
