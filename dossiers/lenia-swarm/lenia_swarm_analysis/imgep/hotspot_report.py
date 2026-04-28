from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

DEFAULT_REPLAY_LIMIT = 8


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{path}: expected a JSON array of objects")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SystemExit(f"{path}: expected JSONL object rows")
        rows.append(value)
    return rows


def _run_scale(run_spec: dict[str, Any]) -> str:
    name = run_spec.get("name")
    if not isinstance(name, str):
        raise SystemExit("run spec is missing name")
    parts = name.rsplit("-", 1)
    if len(parts) != 2 or parts[1] not in {"small", "medium", "large"}:
        raise SystemExit(f"{name}: could not infer scale suffix")
    return parts[1]


def _float_embedding(row: dict[str, Any], features: list[str]) -> list[float]:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        raise SystemExit("row is missing metrics")
    embedding: list[float] = []
    for feature in features:
        value = metrics.get(feature)
        if not isinstance(value, (int, float)):
            raise SystemExit(f"row is missing numeric metric {feature!r}")
        embedding.append(float(value))
    return embedding


def _distance(lhs: list[float], rhs: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lhs, rhs, strict=True)))


def _pairwise_summary(embeddings: list[list[float]]) -> dict[str, float | None]:
    if len(embeddings) < 2:
        return {"mean": None, "median": None}
    distances = [
        _distance(embeddings[i], embeddings[j])
        for i in range(len(embeddings))
        for j in range(i + 1, len(embeddings))
    ]
    return {
        "mean": statistics.fmean(distances),
        "median": statistics.median(distances),
    }


def _ranges(embeddings: list[list[float]]) -> list[float]:
    if not embeddings:
        return []
    dims = list(zip(*embeddings, strict=True))
    return [max(values) - min(values) for values in dims]


def _history_summary(
    *,
    seed_embedding: list[float],
    history_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    embeddings: list[list[float]] = []
    for row in history_rows:
        value = row.get("embedding")
        if not isinstance(value, list) or any(not isinstance(v, (int, float)) for v in value):
            raise SystemExit("history row is missing numeric embedding")
        embeddings.append([float(v) for v in value])
    seed_distances = [_distance(seed_embedding, embedding) for embedding in embeddings]
    pairwise = _pairwise_summary(embeddings)
    return {
        "recordedHistoryCount": len(history_rows),
        "seedToLastDistance": (
            _distance(seed_embedding, embeddings[-1]) if embeddings else None
        ),
        "seedToMaxDistance": max(seed_distances) if seed_distances else None,
        "pairwiseMeanDistance": pairwise["mean"],
        "pairwiseMedianDistance": pairwise["median"],
        "ranges": _ranges(embeddings),
    }


def _top_summary(
    top_rows: list[dict[str, Any]],
    features: list[str],
) -> tuple[dict[str, Any], list[list[float]]]:
    embeddings = [_float_embedding(row, features) for row in top_rows]
    pairwise = _pairwise_summary(embeddings)
    return (
        {
            "topCount": len(top_rows),
            "pairwiseMeanDistance": pairwise["mean"],
            "pairwiseMedianDistance": pairwise["median"],
            "ranges": _ranges(embeddings),
            "filtersPassedCount": sum(1 for row in top_rows if row.get("filters_passed") is True),
        },
        embeddings,
    )


def _nearest_seed_index(
    *,
    seed_embedding: list[float],
    embeddings: list[list[float]],
) -> int:
    distances = [_distance(seed_embedding, embedding) for embedding in embeddings]
    indices = list(range(len(distances)))
    return min(indices, key=lambda idx: distances[idx])


def _farthest_point_indices(
    *,
    seed_embedding: list[float],
    embeddings: list[list[float]],
    limit: int,
) -> list[int]:
    if not embeddings:
        return []
    selected = [_nearest_seed_index(seed_embedding=seed_embedding, embeddings=embeddings)]
    remaining = set(range(len(embeddings))) - set(selected)
    while remaining and len(selected) < limit:
        best_index = max(
            remaining,
            key=lambda idx: min(_distance(embeddings[idx], embeddings[cur]) for cur in selected),
        )
        selected.append(best_index)
        remaining.remove(best_index)
    return selected


def _run_record(run_spec: dict[str, Any], features: list[str]) -> dict[str, Any]:
    output = Path(str(run_spec["output"])).expanduser().resolve()
    summary = _read_json(output / "summary.json")
    history_rows = _read_jsonl(output / "history.jsonl")
    top_rows = _read_json_array(output / "top.json") if (output / "top.json").exists() else []
    seed_rows = _read_json_array(Path(str(run_spec["historySeed"])).expanduser().resolve())
    if not seed_rows:
        raise SystemExit(f"{run_spec['historySeed']}: expected at least one history seed entry")
    seed_embedding = seed_rows[0].get("embedding")
    if not isinstance(seed_embedding, list) or any(
        not isinstance(value, (int, float)) for value in seed_embedding
    ):
        raise SystemExit(f"{run_spec['historySeed']}: seed entry is missing embedding")
    history_summary = _history_summary(
        seed_embedding=[float(value) for value in seed_embedding],
        history_rows=history_rows,
    )
    top_summary, top_embeddings = _top_summary(top_rows, features)
    return {
        "name": str(run_spec["name"]),
        "scale": _run_scale(run_spec),
        "specimen": str(run_spec["specimen"]),
        "controlGroup": str(run_spec["controlGroup"]),
        "output": str(output),
        "config": str(Path(str(run_spec["config"])).expanduser().resolve()),
        "search": str(Path(str(run_spec["search"])).expanduser().resolve()),
        "historySeed": str(Path(str(run_spec["historySeed"])).expanduser().resolve()),
        "summary": summary,
        "history": history_summary,
        "top": top_summary,
        "seedEmbedding": [float(value) for value in seed_embedding],
        "topRows": top_rows,
        "topEmbeddings": top_embeddings,
        "recommendedBecause": run_spec.get("recommendedBecause"),
    }


def _recommended_replay_scale(run_records: list[dict[str, Any]]) -> str:
    ranked = sorted(
        run_records,
        key=lambda row: (
            -int(row["top"]["topCount"]),
            -float(row["top"]["pairwiseMeanDistance"] or 0.0),
            -float(row["history"]["pairwiseMeanDistance"] or 0.0),
            str(row["scale"]),
        ),
    )
    return str(ranked[0]["scale"])


def _followup_scales(
    run_records: list[dict[str, Any]],
    recommended_replay_scale: str,
) -> list[str]:
    because = next(
        (
            row.get("recommendedBecause")
            for row in run_records
            if isinstance(row.get("recommendedBecause"), dict)
        ),
        None,
    )
    if not isinstance(because, dict):
        return []
    followup: set[str] = set()
    for key in ("bestScaleByStateClosure", "bestScaleByRatio"):
        value = because.get(key)
        if isinstance(value, dict):
            scale = value.get("scale")
            if isinstance(scale, str) and scale != recommended_replay_scale:
                followup.add(scale)
    return sorted(followup)


def _candidate_rows(
    *,
    control_group: str,
    specimen: str,
    run_record: dict[str, Any],
    features: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    top_rows = list(run_record["topRows"])
    top_embeddings = list(run_record["topEmbeddings"])
    selected_indices = _farthest_point_indices(
        seed_embedding=list(run_record["seedEmbedding"]),
        embeddings=top_embeddings,
        limit=min(limit, len(top_rows)),
    )
    rows: list[dict[str, Any]] = []
    for rank, index in enumerate(selected_indices, start=1):
        source_row = top_rows[index]
        embedding = top_embeddings[index]
        rows.append(
            {
                "candidateId": f"{control_group}-{run_record['scale']}-{rank:02d}",
                "controlGroup": control_group,
                "specimen": specimen,
                "scale": str(run_record["scale"]),
                "sourceRunName": str(run_record["name"]),
                "sourceRunDir": str(run_record["output"]),
                "sourceConfigPath": str(run_record["config"]),
                "sourceSearchPath": str(run_record["search"]),
                "sourceIndex": index,
                "sourceSeed": int(source_row["seed"]),
                "sourceInitSeed": int(source_row["init_seed"]),
                "distanceToSeedEmbedding": _distance(list(run_record["seedEmbedding"]), embedding),
                "featureEmbedding": embedding,
                "metrics": {
                    feature: float(source_row["metrics"][feature])
                    for feature in features
                },
            }
        )
    return rows


def build_imgep_hotspot_report(
    *,
    batch_packet_path: Path,
    replay_limit: int,
) -> dict[str, Any]:
    packet = _read_json(batch_packet_path)
    raw_features = packet.get("features")
    runs = packet.get("runs")
    if not isinstance(raw_features, list) or any(
        not isinstance(row, str) for row in raw_features
    ):
        raise SystemExit("batch packet is missing features[]")
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
        raise SystemExit("batch packet is missing runs[]")
    features = [str(row) for row in raw_features]

    records_by_group: dict[str, list[dict[str, Any]]] = {}
    for run_spec in runs:
        record = _run_record(run_spec, features)
        records_by_group.setdefault(str(record["controlGroup"]), []).append(record)

    group_rows: list[dict[str, Any]] = []
    selected_candidates: list[dict[str, Any]] = []
    for control_group in sorted(records_by_group):
        run_records = sorted(records_by_group[control_group], key=lambda row: str(row["scale"]))
        specimen = str(run_records[0]["specimen"])
        replay_scale = _recommended_replay_scale(run_records)
        replay_record = next(row for row in run_records if row["scale"] == replay_scale)
        followup_scales = _followup_scales(run_records, replay_scale)
        candidates = _candidate_rows(
            control_group=control_group,
            specimen=specimen,
            run_record=replay_record,
            features=features,
            limit=replay_limit,
        )
        selected_candidates.extend(candidates)
        group_rows.append(
            {
                "controlGroup": control_group,
                "specimen": specimen,
                "runCount": len(run_records),
                "recommendedReplayScale": replay_scale,
                "followupScales": followup_scales,
                "runs": [
                    {
                        "name": row["name"],
                        "scale": row["scale"],
                        "output": row["output"],
                        "summary": row["summary"],
                        "history": row["history"],
                        "top": row["top"],
                    }
                    for row in run_records
                ],
                "selectedCandidateIds": [row["candidateId"] for row in candidates],
            }
        )

    return {
        "version": 1,
        "packetKind": "imgep_hotspot_report_v1",
        "sourceBatchPacket": str(batch_packet_path),
        "features": features,
        "groupCount": len(group_rows),
        "selectedCandidateCount": len(selected_candidates),
        "groups": group_rows,
        "selectedCandidates": selected_candidates,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare targeted hotspot IMGEP runs and select replay candidates."
    )
    parser.add_argument("--batch-packet", required=True, help="Path to imgep-hotspot-batch.json")
    parser.add_argument("--replay-limit", type=int, default=DEFAULT_REPLAY_LIMIT)
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.replay_limit <= 0:
        raise SystemExit("--replay-limit must be > 0")
    report = build_imgep_hotspot_report(
        batch_packet_path=Path(args.batch_packet).expanduser().resolve(),
        replay_limit=args.replay_limit,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(args.batch_packet).expanduser().resolve().parent / "imgep-hotspot-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "IMGEP hotspot report:"
        f" groups={report['groupCount']}"
        f" selected_candidates={report['selectedCandidateCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
