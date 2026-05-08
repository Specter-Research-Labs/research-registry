from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    mp4_path: Path
    specimen_id: str | None
    notes: str | None


def load_manifest(path: Path) -> list[ManifestEntry]:
    """Read a scoring manifest. Paths inside the manifest are resolved relative to its parent dir.

    invariant: manifest is a list (top-level) of objects with required 'mp4' and 'name' keys
    and optional 'specimen_id' and 'notes'. specimen_id is the only field that connects a
    scored creature to the lenia-swarm morphospace warehouse.
    """
    raw: object = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"manifest {path} must be a JSON array; got {type(raw).__name__}")
    base = path.parent
    entries: list[ManifestEntry] = []
    seen_names: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"manifest entry {i} must be an object")
        item_dict = cast(dict[str, object], item)
        if "mp4" not in item_dict or "name" not in item_dict:
            raise ValueError(f"manifest entry {i} missing required 'mp4' and/or 'name'")
        name = str(item_dict["name"])
        if name in seen_names:
            raise ValueError(f"manifest entry {i}: duplicate name {name!r}")
        seen_names.add(name)
        mp4 = (base / str(item_dict["mp4"])).resolve()
        if not mp4.is_file():
            raise FileNotFoundError(f"manifest entry {i}: mp4 not found at {mp4}")
        spec_id_raw = item_dict.get("specimen_id")
        notes_raw = item_dict.get("notes")
        entries.append(
            ManifestEntry(
                name=name,
                mp4_path=mp4,
                specimen_id=str(spec_id_raw) if spec_id_raw is not None else None,
                notes=str(notes_raw) if notes_raw is not None else None,
            )
        )
    if not entries:
        raise ValueError(f"manifest {path} is empty")
    return entries
