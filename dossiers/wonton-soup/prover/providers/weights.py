"""Pinned model revisions and the hashes of the weight files a run loads."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

PINNED_REVISIONS = {
    "kaiyuy/leandojo-lean4-tacgen-byt5-small": "67a2c53cc36186fe8539d0a342fc42c50edc68fd",
    "kaiyuy/leandojo-lean4-retriever-byt5-small": "ebccee9d0fb1b043db797a7493c30dfde6aa8ce2",
    "internlm/internlm2_5-step-prover": "9cb19fbd40b41a55a7586aed881df435bdef5e9f",
    "ByteDance-Seed/BFS-Prover-V1-7B": "750e39030cf25f4af4fcdc81d358123659656cbe",
}
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".npz", ".gguf")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def pinned_revision(repo_id: str) -> str:
    if repo_id not in PINNED_REVISIONS:
        raise KeyError(f"{repo_id} has no pinned revision; add one to PINNED_REVISIONS")
    return PINNED_REVISIONS[repo_id]


def _weight_files(root: Path) -> list[Path]:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in WEIGHT_SUFFIXES)
    if not files:
        raise FileNotFoundError(f"no weight files ({', '.join(WEIGHT_SUFFIXES)}) under {root}")
    return files


def hub_weights(repo_id: str) -> dict[str, Any]:
    """Weight hashes of the pinned snapshot in the local Hugging Face cache.

    The cache stores each LFS file as a blob named by its sha256, so the hash is
    read from the blob the snapshot links to instead of rehashing gigabytes.
    """
    from huggingface_hub import snapshot_download

    revision = pinned_revision(repo_id)
    snapshot = Path(snapshot_download(repo_id, revision=revision, local_files_only=True))
    hashes = {}
    for path in _weight_files(snapshot):
        blob = path.resolve().name
        if _SHA256_RE.fullmatch(blob) is None:
            raise ValueError(f"{path} does not link to a sha256-named LFS blob (got {blob!r})")
        hashes[str(path.relative_to(snapshot))] = blob
    return {"repo_id": repo_id, "revision": revision, "weights_sha256": hashes}


def local_weights(model_dir: Path) -> dict[str, Any]:
    hashes = {}
    for path in _weight_files(model_dir):
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 24), b""):
                digest.update(chunk)
        hashes[str(path.relative_to(model_dir))] = digest.hexdigest()
    return {"model_dir": str(model_dir), "weights_sha256": hashes}
