from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import paths, rois
from .corpus import discover_videos, load_video_as_stimulus
from .manifest import ManifestEntry, load_manifest
from .tribe_client import TribeClient


def _load_control_rows(checkpoint_revision: str, bundle: dict[str, rois.RoiMask]) -> list[dict[str, object]]:
    slug = checkpoint_revision.replace("/", "_")
    cache = paths.artifact_root() / "predictions" / f"{slug}.seed0.npz"
    if not cache.exists():
        raise FileNotFoundError(
            f"control predictions not cached at {cache}; run lenia-tribe-roi-probe "
            "with the same checkpoint first, or omit --include-controls"
        )
    loaded = np.load(cache)
    names = [str(s) for s in loaded["stimulus_names"]]
    voxels = loaded["voxels"]
    rows: list[dict[str, object]] = []
    for name, vox in zip(names, voxels, strict=True):
        row: dict[str, object] = {
            "name": f"control:{name}",
            "path": "",
            "whole_cortex": float(vox.mean()),
        }
        for roi_name, mask in bundle.items():
            row[roi_name] = rois.apply(vox, mask)
        rows.append(row)
    return rows


def _load_client(args: argparse.Namespace) -> TribeClient:
    if args.fake:
        from .tribe_fake import FakeTribeClient

        return FakeTribeClient(seed=0, n_voxels=rois.TRIBE_N_VERTICES)
    from .tribe_real import RealTribeClient

    return RealTribeClient(device=args.device)


def _entries_from_corpus(corpus: Path, glob: str, limit: int) -> list[ManifestEntry]:
    if not corpus.is_dir():
        raise NotADirectoryError(f"--corpus must be a directory; got {corpus}")
    video_paths = discover_videos(corpus, glob)
    if limit:
        video_paths = video_paths[:limit]
    return [
        ManifestEntry(name=p.stem, mp4_path=p, specimen_id=None, notes=None)
        for p in video_paths
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a directory of Lenia videos by TRIBE ROI engagement."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--corpus",
        type=Path,
        help="Directory containing Lenia MP4 renders (recursive search).",
    )
    source.add_argument(
        "--manifest",
        type=Path,
        help=(
            "JSON manifest enumerating MP4s with optional specimen_id linkage to the "
            "lenia-swarm morphospace warehouse. Required for downstream overlay."
        ),
    )
    parser.add_argument("--glob", default="*.mp4")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int, default=0, help="Cap the number of videos scored (0 = all).")
    parser.add_argument(
        "--include-controls",
        action="store_true",
        help="Append the cached OOD probe predictions (from roi-probe) to the table for context.",
    )
    args = parser.parse_args(argv)

    if args.manifest is not None:
        entries = load_manifest(args.manifest)
        if args.limit:
            entries = entries[: args.limit]
    else:
        entries = _entries_from_corpus(args.corpus, args.glob, args.limit)

    bundle = rois.build_bundle()
    client = _load_client(args)
    rows: list[dict[str, object]] = []
    for entry in entries:
        stim = load_video_as_stimulus(entry.mp4_path, name=entry.name)
        prediction = client.predict(stim)
        whole = float(prediction.voxels.mean())
        roi_means = {name: rois.apply(prediction.voxels, mask) for name, mask in bundle.items()}
        row: dict[str, object] = {
            "name": stim.name,
            "path": str(entry.mp4_path),
            "specimen_id": entry.specimen_id,
            "notes": entry.notes,
            "whole_cortex": whole,
            **roi_means,
        }
        rows.append(row)

    if args.include_controls:
        rows.extend(_load_control_rows(client.checkpoint_revision, bundle))

    timestamp = datetime.now(UTC).isoformat()
    source: dict[str, object] = (
        {"kind": "manifest", "path": str(args.manifest.resolve())}
        if args.manifest is not None
        else {"kind": "corpus", "path": str(args.corpus.resolve()), "glob": args.glob}
    )
    report = {
        "checkpoint_revision": client.checkpoint_revision,
        "n_voxels": client.n_voxels,
        "source": source,
        "n_videos": len(rows),
        "timestamp": timestamp,
        "rois": {
            name: {"label_names": list(mask.label_names), "n_vertices": int(mask.indices.size)}
            for name, mask in bundle.items()
        },
        "rows": rows,
    }
    out_dir = paths.ensure(paths.artifact_root() / "lenia-scores")
    slug = client.checkpoint_revision.replace("/", "_")
    out = out_dir / f"{slug}.{timestamp.replace(':', '-')}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))

    header = ["name", "whole", *bundle.keys()]
    print("\t".join(header))
    for row in rows:
        cells = [str(row["name"]), f"{row['whole_cortex']:+.4f}"]
        for roi_name in bundle:
            cells.append(f"{row[roi_name]:+.4f}")
        print("\t".join(cells))
    print(f"\nlenia score report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
