from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RECEIPT_FILE = "receipt.json"
LENIA_SOURCE_ID = "lenia_swarm"
RECEIPT_VERSION = 1


@dataclass(frozen=True)
class RunProvenance:
    engine_id: str
    source_commit: str | None
    receipt_sha256: str | None


def read_run_provenance(run_dir: Path, *, legacy_engine_id: str | None) -> RunProvenance:
    """Mirror of LeniaCLI's compendium rule: a receipt names the engine; only a run without one may be named by hand."""
    receipt_path = run_dir / RECEIPT_FILE
    if not receipt_path.is_file():
        if legacy_engine_id is None:
            raise ValueError(
                f"{run_dir} has no {RECEIPT_FILE}; pass --engine-id <id> to ingest a legacy run "
                "written before receipts (track1-verify reports a pinned engine's signature)"
            )
        return RunProvenance(engine_id=legacy_engine_id, source_commit=None, receipt_sha256=None)
    data = receipt_path.read_bytes()
    receipt = json.loads(data)
    if receipt["receipt_version"] != RECEIPT_VERSION:
        raise ValueError(
            f"{receipt_path}: receipt_version {receipt['receipt_version']} is not {RECEIPT_VERSION}"
        )
    engine_id = str(receipt["engine_id"])
    if legacy_engine_id is not None and legacy_engine_id != engine_id:
        raise ValueError(
            f"--engine-id {legacy_engine_id} contradicts {receipt_path}, which names engine {engine_id}"
        )
    return RunProvenance(
        engine_id=engine_id,
        source_commit=str(receipt["build"]["source_commit"]),
        receipt_sha256=hashlib.sha256(data).hexdigest(),
    )


def parse_pool_engines(value: str | None) -> frozenset[str] | None:
    if value is None:
        return None
    engines = frozenset(part.strip() for part in value.split(",") if part.strip())
    if len(engines) < 2:
        raise ValueError(f"--pool-engines needs at least two engine ids, got {value!r}")
    return engines


def require_engine_pool(
    engine_ids: Iterable[str | None],
    *,
    pool_engines: frozenset[str] | None,
    what: str,
) -> list[str]:
    """Refuses to pool records from different engines unless every engine is named in --pool-engines."""
    present = set(engine_ids)
    if None in present:
        raise ValueError(
            f"{what} includes records without engine_id; re-ingest them from runs with receipts "
            "or name the legacy engine with --engine-id"
        )
    engines = sorted(engine for engine in present if engine is not None)
    if len(engines) <= 1:
        return engines
    if pool_engines is None:
        raise ValueError(
            f"{what} mixes engines {', '.join(engines)}; filter to one engine "
            "or pass --pool-engines with every engine to pool them explicitly"
        )
    outside = sorted(set(engines) - pool_engines)
    if outside:
        raise ValueError(f"{what} includes engines {', '.join(outside)} that --pool-engines does not name")
    return engines


def lenia_engine_pool(
    observations: Iterable[Mapping[str, Any]],
    *,
    pool_engines: frozenset[str] | None,
    what: str,
) -> list[str]:
    """Only Lenia observations carry an engine; biological sources are compared, never pooled by engine."""
    return require_engine_pool(
        (row["engineId"] for row in observations if row["sourceId"] == LENIA_SOURCE_ID),
        pool_engines=pool_engines,
        what=what,
    )
