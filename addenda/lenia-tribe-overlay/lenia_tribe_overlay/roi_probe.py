from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import paths, rois
from .probes import probe_set
from .tribe_client import TribeClient


def _load_client(args: argparse.Namespace) -> TribeClient:
    if args.fake:
        from .tribe_fake import FakeTribeClient

        return FakeTribeClient(seed=args.seed)
    from .tribe_real import RealTribeClient

    return RealTribeClient(device=args.device)


def _predictions_cache_path(checkpoint_revision: str, seed: int) -> Path:
    slug = checkpoint_revision.replace("/", "_")
    return paths.ensure(paths.artifact_root() / "predictions") / f"{slug}.seed{seed}.npz"


def _save_predictions(
    cache: Path,
    stimulus_names: list[str],
    voxel_matrix: np.ndarray,
) -> None:
    np.savez(
        cache,
        stimulus_names=np.asarray(stimulus_names),
        voxels=voxel_matrix,
    )


def _load_predictions(cache: Path) -> tuple[list[str], np.ndarray]:
    loaded = np.load(cache)
    names = [str(s) for s in loaded["stimulus_names"]]
    voxels = loaded["voxels"]
    return names, voxels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe TRIBE ROI activations on the OOD probe set.")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--rebuild-rois",
        action="store_true",
        help="Rebuild the Destrieux mask cache before applying.",
    )
    parser.add_argument(
        "--rebuild-predictions",
        action="store_true",
        help="Re-run TRIBE even if a cached prediction matrix exists.",
    )
    args = parser.parse_args(argv)

    bundle = rois.build_bundle(force_rebuild=args.rebuild_rois)
    stimuli = list(probe_set(seed=args.seed))

    client = _load_client(args)
    pred_cache = _predictions_cache_path(client.checkpoint_revision, args.seed)
    if pred_cache.exists() and not args.rebuild_predictions:
        cached_names, voxel_matrix = _load_predictions(pred_cache)
        if cached_names != [s.name for s in stimuli]:
            raise RuntimeError(
                f"prediction cache at {pred_cache} mismatches current probe set: "
                f"cached={cached_names}, current={[s.name for s in stimuli]}"
            )
    else:
        voxels = [client.predict(s).voxels for s in stimuli]
        voxel_matrix = np.stack(voxels, axis=0)
        _save_predictions(pred_cache, [s.name for s in stimuli], voxel_matrix)

    rows: list[dict[str, float | str]] = []
    for stim, vox in zip(stimuli, voxel_matrix, strict=True):
        row: dict[str, float | str] = {
            "stimulus": stim.name,
            "stimulus_class": stim.stimulus_class,
            "whole_cortex": float(vox.mean()),
        }
        for name, mask in bundle.items():
            row[name] = rois.apply(vox, mask)
        rows.append(row)

    report = {
        "checkpoint_revision": client.checkpoint_revision,
        "n_voxels": client.n_voxels,
        "seed": args.seed,
        "timestamp": datetime.now(UTC).isoformat(),
        "rois": {name: {"label_names": list(mask.label_names), "n_vertices": int(mask.indices.size)}
                  for name, mask in bundle.items()},
        "rows": rows,
    }
    out_dir = paths.ensure(paths.artifact_root() / "roi-probe")
    slug = client.checkpoint_revision.replace("/", "_")
    out = out_dir / f"{slug}.{report['timestamp'].replace(':', '-')}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))

    header = ["stimulus", "class", "whole", *bundle.keys()]
    print("\t".join(header))
    for row in rows:
        cells = [
            str(row["stimulus"]),
            str(row["stimulus_class"]),
            f"{row['whole_cortex']:+.4f}",
            *[f"{row[name]:+.4f}" for name in bundle.keys()],
        ]
        print("\t".join(cells))
    print(f"\nroi probe report: {out}")
    print(f"prediction cache: {pred_cache}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
