"""Build a merged export index per rule config for replay-with-capture.

Each rule's specimens are sharded across many run directories. We round-robin across all shards
(deterministic by creatureId hash) so the replay set spans the whole rule rather than one seed
band, taking filter-passing export records up to the per-config target. Export records carry
absolute base/search config paths, so a single merged index replays from any working directory.
"""

from __future__ import annotations

import json

from ._common import stable_rank
from .study import CONFIGS, INPUTS_DIR, RUN_ROOT, SPECIMENS_PER_CONFIG, RuleConfig, input_index_path


def build_config_index(config: RuleConfig, target: int) -> int:
    shards = sorted(RUN_ROOT.glob(config.shard_glob))
    if not shards:
        raise SystemExit(f"{config.label}: no shards match {config.shard_glob} under {RUN_ROOT}")
    per_shard = -(-target // len(shards))
    picks: list[str] = []
    for shard in shards:
        index_path = shard / "exports" / "index.jsonl"
        if not index_path.exists():
            raise SystemExit(f"missing export index: {index_path}")
        rows = []
        with index_path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("filtersPassed") is False:
                    continue
                rows.append((stable_rank(record["creatureId"]), line.rstrip("\n")))
        rows.sort(key=lambda r: r[0])
        picks.extend(line for _, line in rows[:per_shard])

    picks = picks[:target]
    out_path = input_index_path(config.config_hash)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as out:
        for line in picks:
            out.write(line + "\n")
    return len(picks)


def build_all() -> None:
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    for config in CONFIGS:
        n = build_config_index(config, SPECIMENS_PER_CONFIG)
        path = input_index_path(config.config_hash)
        print(f"{config.label} ({config.config_hash}): {n} specimens -> {path}")


if __name__ == "__main__":
    build_all()
