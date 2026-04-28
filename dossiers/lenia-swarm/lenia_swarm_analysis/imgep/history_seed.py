from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, cast


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _features_from_imgep_config(path: Path) -> list[str]:
    config = _read_json(path)
    goal = config.get("goal")
    if not isinstance(goal, dict):
        raise SystemExit(f"{path}: missing goal block")
    features = goal.get("features")
    if not isinstance(features, list) or any(not isinstance(item, str) for item in features):
        raise SystemExit(f"{path}: goal.features must be a list of strings")
    return cast(list[str], features)


def _bundle_entry(bundle_path: Path, features: list[str]) -> dict[str, Any]:
    meta = _read_json(bundle_path / "meta.json")
    creature = meta.get("creature")
    if not isinstance(creature, dict):
        raise SystemExit(f"{bundle_path}: missing creature block in meta.json")
    genotype = creature.get("genotype")
    metrics = creature.get("metrics")
    phenotype = creature.get("phenotype")
    if not isinstance(genotype, dict) or not isinstance(metrics, dict):
        raise SystemExit(f"{bundle_path}: meta.json is missing genotype or metrics")
    if not all(feature in metrics for feature in features):
        missing = [feature for feature in features if feature not in metrics]
        raise SystemExit(f"{bundle_path}: metrics missing features {missing}")
    seed = 0
    if isinstance(phenotype, dict):
        phenotype_seed = phenotype.get("seed")
        if isinstance(phenotype_seed, int):
            seed = phenotype_seed
    score = creature.get("score")
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, str(bundle_path))),
        "seed": seed,
        "params": genotype,
        "metrics": metrics,
        "embedding": [float(metrics[feature]) for feature in features],
        "goal": None,
        "score": float(score) if isinstance(score, (int, float)) else None,
    }


def build_history_seed(bundle_paths: list[Path], features: list[str]) -> list[dict[str, Any]]:
    if not bundle_paths:
        raise SystemExit("at least one --bundle is required")
    if not features:
        raise SystemExit("at least one feature is required")
    return [_bundle_entry(path, features) for path in bundle_paths]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build seeded IMGEP history entries from strict replay bundles."
    )
    parser.add_argument(
        "--bundle",
        action="append",
        default=[],
        help="Path to strict replay bundle",
    )
    parser.add_argument("--feature", action="append", default=[], help="Goal feature to embed")
    parser.add_argument("--imgep-config", help="IMGEP config JSON to read goal.features from")
    parser.add_argument("--output", required=True, help="Output path for history seed JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    features = list(args.feature)
    if args.imgep_config:
        features.extend(_features_from_imgep_config(Path(args.imgep_config).expanduser().resolve()))
    ordered_features = list(dict.fromkeys(features))
    entries = build_history_seed(
        [Path(item).expanduser().resolve() for item in args.bundle],
        ordered_features,
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "IMGEP history seed:"
        f" entries={len(entries)}"
        f" features={len(ordered_features)}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
