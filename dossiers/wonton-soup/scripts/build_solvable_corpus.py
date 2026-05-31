#!/usr/bin/env python3
"""Build a ~1000-theorem corpus solvable by both reprover and deepseek.

Priority order (highest ROI first):
  1. Re-screen existing single-provider theorems with the missing provider
  2. Tier-1 escalation on tier-0 failures
  3. Mine deepseek-prover-v1 only if still short

Phases:
  harvest     Scan all existing run logs for solvability data.
  assemble    Build final corpus from confirmed-both theorems.

Screening is done directly via `wonton.py lean run`. This script handles
harvest (collecting results) and assembly.

Usage (on quietbox):
  .venv/bin/python scripts/build_solvable_corpus.py harvest
  .venv/bin/python scripts/build_solvable_corpus.py assemble --target 1000
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1]


def _logs_root() -> Path:
    for p in [
        Path("/shared/dev/specter-labs-wonton-abstract-runfix/dossiers/wonton-soup"),
        DOSSIER,
    ]:
        if (p / "logs").is_dir():
            return p
    raise RuntimeError("Cannot find wonton-soup logs root")


def _corpora_root() -> Path:
    for p in [
        Path("/shared/specter-runtime/wonton-soup/corpora"),
        DOSSIER / "corpora",
    ]:
        if p.is_dir():
            return p
    raise RuntimeError("Cannot find corpora root")


def _work_dir() -> Path:
    d = Path("/shared/specter-runtime/solvable-corpus-build")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _checkpoint_solved(cp: Path) -> tuple[bool, set[str]]:
    try:
        with gzip.open(cp, "rt") as f:
            data = json.load(f)
    except Exception:
        return False, set()
    phases: set[str] = set()
    if data.get("wild_type", {}).get("solved", False):
        phases.add("wild_type")
    for i in data.get("interventions", []):
        if i.get("intervention_run", {}).get("solved", False):
            name = i.get("intervention", "unknown")
            phases.add(str(name) if not isinstance(name, str) else name)
    return bool(phases), phases


# All run directories to scan (relative to logs root)
# Includes both original runs and screening runs
def _all_run_dirs(root: Path) -> dict[str, tuple[str, Path]]:
    """Return {label: (provider, path)} for all known run directories."""
    runs: dict[str, tuple[str, Path]] = {}

    # Original runs
    known = {
        "mathlib/reprover_c": ("reprover", "logs/2026-03-23-abstract/p1-shared/provider=reprover/mcts=centralized"),
        "mathlib/reprover_d": ("reprover", "logs/2026-03-31-abstract-matrix/provider=reprover/mcts=distributed"),
        "mathlib/deepseek_c": ("deepseek", "logs/2026-03-31-abstract-matrix/provider=deepseek/mcts=centralized"),
        "mathlib/deepseek_d": ("deepseek", "logs/2026-03-31-abstract-matrix/provider=deepseek/mcts=distributed"),
        "crossatp/reprover_c": ("reprover", "logs/2026-03-31-cross-atp-expanded/provider=reprover/mcts=centralized"),
        "crossatp/reprover_d": ("reprover", "logs/2026-04-03-cross-atp-expanded/provider=reprover/mcts=distributed"),
        "crossatp/deepseek_c": ("deepseek", "logs/2026-04-03-cross-atp-expanded/provider=deepseek/mcts=centralized"),
    }
    for label, (prov, rel) in known.items():
        p = root / rel
        if p.is_dir():
            runs[label] = (prov, p)

    # Auto-discover screening runs (*/solvable-1000-screen/*)
    screen_base = root / "logs"
    for d in sorted(screen_base.glob("*solvable-1000-screen/*")):
        if not d.is_dir():
            continue
        name = d.name
        if "reprover" in name:
            prov = "reprover"
        elif "deepseek" in name:
            prov = "deepseek"
        else:
            continue
        label = f"screen/{name}"
        runs[label] = (prov, d)

    return runs


def harvest():
    root = _logs_root()
    work = _work_dir()
    print(f"Scanning: {root}")

    solvability: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    sources: dict[str, str] = {}

    all_runs = _all_run_dirs(root)
    for label, (provider, base) in sorted(all_runs.items()):
        corpus_tag = label.split("/")[0]
        n_solved = 0
        dirs = [e for e in base.iterdir() if e.is_dir()]
        for td in dirs:
            cp = td / "theorem_result.checkpoint.json.gz"
            if not cp.exists():
                continue
            ok, phases = _checkpoint_solved(cp)
            if ok:
                solvability[td.name][provider].update(phases)
                sources.setdefault(td.name, corpus_tag)
                n_solved += 1
        print(f"  {label}: {n_solved}/{len(dirs)} solved")

    # Merge log-based data for cross-atp (catches lost checkpoints)
    cross_log = Path("/shared/specter-runtime/cross-atp.log")
    if cross_log.exists():
        stage_to_provider = {
            "[1/4]": "reprover", "[2/4]": "reprover",
            "[3/4]": "deepseek", "[4/4]": "deepseek",
        }
        provider = thm = None
        added = 0
        for line in cross_log.open():
            line = line.strip()
            for tag, prov in stage_to_provider.items():
                if line.startswith(f"=== {tag}"):
                    provider = prov
            if line.startswith("[") and "/572]" in line and "] " in line:
                thm = line.split("] ", 1)[1].strip()
            if thm and provider and "-> SOLVED" in line:
                if not solvability[thm][provider]:
                    solvability[thm][provider].add("wild_type_from_log")
                    sources.setdefault(thm, "crossatp")
                    added += 1
        print(f"  cross-atp.log: +{added} entries")

    both = {t for t, p in solvability.items() if "reprover" in p and "deepseek" in p}
    reprover_only = {t for t, p in solvability.items() if "reprover" in p and "deepseek" not in p}
    deepseek_only = {t for t, p in solvability.items() if "deepseek" in p and "reprover" not in p}
    any_solved = set(solvability.keys())

    print(f"\n=== Results ===")
    print(f"Both providers:    {len(both)}")
    print(f"Reprover only:     {len(reprover_only)}  (needs deepseek screen)")
    print(f"Deepseek only:     {len(deepseek_only)}  (needs reprover screen)")
    print(f"Any provider:      {len(any_solved)}")
    print(f"Gap to 1000:       {max(0, 1000 - len(both))}")

    manifest = {
        "harvested_at": datetime.now().isoformat(),
        "both": sorted(both),
        "reprover_only": sorted(reprover_only),
        "deepseek_only": sorted(deepseek_only),
        "any_solved": sorted(any_solved),
        "by_theorem": {
            t: {
                "source": sources.get(t, "unknown"),
                "reprover": bool(p.get("reprover")),
                "deepseek": bool(p.get("deepseek")),
            }
            for t, p in solvability.items()
        },
    }
    out = work / "harvest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote: {out}")
    return manifest


def assemble(target: int = 1000):
    work = _work_dir()
    corpora = _corpora_root()

    harvest_path = work / "harvest.json"
    if not harvest_path.exists():
        print("No harvest data. Run 'harvest' first.")
        sys.exit(1)

    h = json.loads(harvest_path.read_text())
    confirmed = set(h.get("both", []))
    any_solved = set(h.get("any_solved", []))
    reprover_only = set(h.get("reprover_only", []))
    deepseek_only = set(h.get("deepseek_only", []))

    print(f"Confirmed both: {len(confirmed)}")
    print(f"Reprover only:  {len(reprover_only)}")
    print(f"Deepseek only:  {len(deepseek_only)}")

    # Build the final set: confirmed-both first, then pad if needed
    final_ids = set(confirmed)
    shortfall = target - len(final_ids)
    if shortfall > 0:
        # Pad with any-solved, preferring reprover-only (likely deepseek-solvable)
        bonus = sorted(reprover_only) + sorted(deepseek_only)
        final_ids |= set(bonus[:shortfall])
        print(f"Padded with {min(shortfall, len(bonus))} single-provider theorems")

    print(f"Final target: {len(final_ids)} theorems")

    # Load items from all corpus sources
    all_items: dict[str, dict] = {}
    corpus_patterns = [
        "lean/solvable-both-v1/*/items.jsonl",
        "lean/broad-mathlib-abstract-*/*/items.jsonl",
        "lean/coq-paired-expanded-*/*/items.jsonl",
        "lean/broad-mathlib-reprover-*/*/items.jsonl",
        "lean/deepseek-prover-v1/*/items.jsonl",
    ]
    for pattern in corpus_patterns:
        for p in corpora.glob(pattern):
            if "derived" in str(p):
                continue
            n = 0
            with open(p) as f:
                for line in f:
                    item = json.loads(line)
                    if item["item_id"] in final_ids and item["item_id"] not in all_items:
                        all_items[item["item_id"]] = item
                        n += 1
            if n:
                print(f"  {p.parent.parent.name}: {n}")

    missing = final_ids - set(all_items.keys())
    if missing:
        print(f"WARNING: {len(missing)} theorems not found in any corpus")
        for t in sorted(missing)[:10]:
            print(f"  {t}")

    # Write
    sorted_items = sorted(all_items.values(), key=lambda x: x["item_id"])
    out_dir = work / "corpus"
    out_dir.mkdir(parents=True, exist_ok=True)
    items_path = out_dir / "items.jsonl"
    with open(items_path, "w") as f:
        for item in sorted_items:
            f.write(json.dumps(item) + "\n")

    sha = hashlib.sha256(items_path.read_bytes()).hexdigest()
    n_both = len(set(i["item_id"] for i in sorted_items) & confirmed)

    manifest = {
        "corpus_id": "solvable-1000-v1",
        "build_date": datetime.now().isoformat(),
        "items_count": len(sorted_items),
        "items_sha256": sha,
        "confirmed_both": n_both,
        "single_provider_bonus": len(sorted_items) - n_both,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Deploy
    dest = corpora / "lean" / "solvable-1000-v1" / sha
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(items_path, dest / "items.jsonl")
    shutil.copy(out_dir / "manifest.json", dest / "manifest.json")

    print(f"\n=== Corpus: solvable-1000-v1 ===")
    print(f"Items:          {len(sorted_items)}")
    print(f"Confirmed both: {n_both}")
    print(f"Bonus:          {len(sorted_items) - n_both}")
    print(f"SHA256:         {sha}")
    print(f"Deployed:       {dest}")
    print(f"\nRun: python wonton.py lean run -m research -c lean:solvable-1000-v1 ...")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("harvest")
    sp = sub.add_parser("assemble")
    sp.add_argument("--target", type=int, default=1000)
    args = parser.parse_args()

    if args.cmd == "harvest":
        harvest()
    elif args.cmd == "assemble":
        assemble(target=args.target)
    else:
        parser.print_help()
