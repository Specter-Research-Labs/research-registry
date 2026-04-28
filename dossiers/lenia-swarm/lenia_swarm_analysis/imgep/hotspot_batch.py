from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .history_seed import build_history_seed

DEFAULT_FEATURES = [
    "gyration",
    "center_velocity",
    "moment_anisotropy",
    "largest_component_anisotropy",
]
DEFAULT_TOP_K = 32

SCALE_TO_STD = {
    "small": 0.005,
    "medium": 0.01,
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _find_bundle(export_root: Path, specimen: str) -> Path:
    matches = sorted(
        path
        for path in export_root.iterdir()
        if path.is_dir() and path.name.startswith(f"{specimen}-")
    )
    if not matches:
        raise SystemExit(f"{export_root}: no export bundle found for specimen prefix {specimen!r}")
    return matches[0]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _anchored_config(
    template_config: dict[str, Any],
    bundle_base: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(template_config)
    for key, value in bundle_base.items():
        if key == "params":
            continue
        payload[key] = value
    template_params = template_config.get("params")
    bundle_params = bundle_base.get("params")
    if not isinstance(template_params, dict) or not isinstance(bundle_params, dict):
        raise SystemExit("template config and bundle base must both contain params objects")
    merged_params = dict(template_params)
    for key, value in bundle_params.items():
        if key == "ranges":
            continue
        merged_params[key] = value
    payload["params"] = merged_params
    return payload


def _anchored_search(bundle_search: dict[str, Any]) -> dict[str, Any]:
    payload = dict(bundle_search)
    payload["top_k"] = DEFAULT_TOP_K
    collection = payload.get("collection")
    merged_collection = dict(collection) if isinstance(collection, dict) else {}
    merged_collection["enabled"] = True
    merged_collection["require_filters_passed"] = True
    merged_collection["require_stable"] = False
    merged_collection["export_enabled"] = True
    if "min_score" not in merged_collection:
        merged_collection["min_score"] = None
    payload["collection"] = merged_collection
    return payload


def _transport_targets(hotspot_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = hotspot_packet.get("hotspots")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit("hotspot packet is missing hotspots[]")
    targets = [row for row in rows if row.get("kind") == "transport_group"]
    return sorted(targets, key=lambda row: -float(row["score"]))


def build_imgep_hotspot_batch(
    *,
    hotspot_packet_path: Path,
    export_root: Path,
    output_root: Path,
    features: list[str],
) -> dict[str, Any]:
    hotspot_packet = _read_json(hotspot_packet_path)
    template_config_path = export_root.parent / "config.json"
    template_config = _read_json(template_config_path)
    runs: list[dict[str, Any]] = []
    targets = _transport_targets(hotspot_packet)
    for target in targets:
        group_id = str(target["id"])
        specimen = group_id.split("-", 1)[0]
        bundle = _find_bundle(export_root, specimen)
        base_path = output_root / specimen / "config.json"
        anchored_config = _anchored_config(template_config, _read_json(bundle / "base.json"))
        _write_json(base_path, anchored_config)
        search_path = output_root / specimen / "search.json"
        anchored_search = _anchored_search(_read_json(bundle / "search.json"))
        _write_json(search_path, anchored_search)
        history_seed_path = output_root / specimen / "history-seed.json"
        history_seed = build_history_seed([bundle], features)
        _write_json(history_seed_path, history_seed)
        for scale in ("small", "medium"):
            std = SCALE_TO_STD[scale]
            imgep_config = {
                "iterations": 128,
                "warmupIterations": 0,
                "batchSize": 8,
                "seedsPerCandidate": 1,
                "goal": {
                    "features": features,
                    "boundsMode": "auto",
                    "bounds": None,
                },
                "mutation": {
                    "std": std,
                    "clip": True,
                },
            }
            imgep_path = output_root / specimen / f"imgep-{scale}.json"
            _write_json(imgep_path, imgep_config)
            runs.append(
                {
                    "name": f"{specimen}-targeted-imgep-{scale}",
                    "specimen": specimen,
                    "controlGroup": group_id,
                    "recommendedBecause": target,
                    "templateConfig": str(template_config_path),
                    "bundle": str(bundle),
                    "config": str(base_path),
                    "search": str(search_path),
                    "imgep": str(imgep_path),
                    "historySeed": str(history_seed_path),
                    "output": str(output_root / specimen / f"run-{scale}"),
                }
            )
    return {
        "version": 1,
        "packetKind": "imgep_hotspot_batch_v1",
        "sourceHotspotPacket": str(hotspot_packet_path),
        "exportRoot": str(export_root),
        "features": features,
        "runCount": len(runs),
        "runs": runs,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build targeted IMGEP run specs from transport/cycle hotspot packets."
    )
    parser.add_argument("--hotspot-packet", required=True, help="Path to hotspot packet JSON")
    parser.add_argument(
        "--export-root",
        required=True,
        help="Flow export root containing strict replay bundles",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="Output directory for seeds/configs/spec",
    )
    parser.add_argument("--feature", action="append", default=[], help="Override goal feature")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    features = list(args.feature) if args.feature else list(DEFAULT_FEATURES)
    packet = build_imgep_hotspot_batch(
        hotspot_packet_path=Path(args.hotspot_packet).expanduser().resolve(),
        export_root=Path(args.export_root).expanduser().resolve(),
        output_root=Path(args.output_root).expanduser().resolve(),
        features=features,
    )
    output_path = Path(args.output_root).expanduser().resolve() / "imgep-hotspot-batch.json"
    _write_json(output_path, packet)
    print(
        "IMGEP hotspot batch:"
        f" runs={packet['runCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
