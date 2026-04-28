import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from paths import RuntimeLayout

USER_AGENT = "specter-labs/equational-theories-distillation"


@dataclass(frozen=True)
class SourceAsset:
    name: str
    url: str
    filename: str


SOURCE_ASSETS = (
    SourceAsset(
        name="normal",
        url=(
            "https://huggingface.co/datasets/SAIRfoundation/"
            "equational-theories-selected-problems/resolve/main/data/normal.jsonl"
        ),
        filename="normal.jsonl",
    ),
    SourceAsset(
        name="hard",
        url=(
            "https://huggingface.co/datasets/SAIRfoundation/"
            "equational-theories-selected-problems/resolve/main/data/hard.jsonl"
        ),
        filename="hard.jsonl",
    ),
    SourceAsset(
        name="equations",
        url="https://raw.githubusercontent.com/teorth/equational_theories/main/data/equations.txt",
        filename="equations.txt",
    ),
    SourceAsset(
        name="graph",
        url="https://teorth.github.io/equational_theories/implications/graph.json",
        filename="graph.json",
    ),
)


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read()


def fetch_sources(layout: RuntimeLayout, refresh: bool = False) -> dict[str, Path]:
    layout.sources_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, object]] = []
    resolved: dict[str, Path] = {}
    fetched_at = datetime.now(tz=UTC).isoformat()

    for asset in SOURCE_ASSETS:
        path = layout.sources_dir / asset.filename
        if refresh or not path.exists():
            payload = _download_bytes(asset.url)
            path.write_bytes(payload)
        else:
            payload = path.read_bytes()

        digest = hashlib.sha256(payload).hexdigest()
        manifest_entries.append(
            {
                "name": asset.name,
                "url": asset.url,
                "filename": asset.filename,
                "bytes": len(payload),
                "sha256": digest,
                "fetched_at": fetched_at,
            }
        )
        resolved[asset.name] = path

    manifest_path = layout.sources_dir / "sources.manifest.json"
    manifest_path.write_text(
        json.dumps({"assets": manifest_entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolved


def require_source_files(layout: RuntimeLayout) -> dict[str, Path]:
    missing = []
    resolved: dict[str, Path] = {}
    for asset in SOURCE_ASSETS:
        path = layout.sources_dir / asset.filename
        if not path.exists():
            missing.append(asset.filename)
        resolved[asset.name] = path
    if missing:
        joined = ", ".join(sorted(missing))
        raise FileNotFoundError(
            f"missing source files in {layout.sources_dir}: {joined}. Run `fetch` first."
        )
    return resolved
