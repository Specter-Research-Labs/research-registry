#!/usr/bin/env python3
"""
Measure proof-term monodromy across repeated solves of the same theorem.

The same theorem is solved many times across runs and intervention variants;
each solve records a final proof term in metrics.json. Holding the theorem
(the phenotype) fixed, count how many structurally distinct proof terms (the
genotype) occur. >1 distinct term over one theorem = nontrivial monodromy:
the proof obligation underdetermines the proof object.

Bound variables are de Bruijn indices in the dumped term, so binder names are
decorative; instance binders carry hygiene suffixes that vary run to run.
Normalization strips both so that only structural differences count.

Two regimes are reported separately:
  wild_type  - identical conditions, differences are pure search nondeterminism
  all        - includes intervention variants that perturb the search

Usage:
    python -m analysis.proof_term_monodromy [LOGS_DIR] [--top K] [--show THEOREM]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

_HYGIENE = re.compile(r"_@\.[^ ,:)(]*")
_UNIQ = re.compile(r"_uniq\.[0-9.]+")
_HYG_TAIL = re.compile(r"\._hyg\.[0-9]+")
_FUN = re.compile(r"\(fun [^=]*? =>")
_FORALL = re.compile(r"forall [^:,]*? :")
_WS = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    term = _HYGIENE.sub("", term)
    term = _HYG_TAIL.sub("", term)
    term = _UNIQ.sub("", term)
    term = _FUN.sub("(fun =>", term)
    term = _FORALL.sub("forall :", term)
    return _WS.sub(" ", term).strip()


def _term_of(metrics: dict) -> str | None:
    pt = metrics.get("proof_term_pretty") or metrics.get("proof_term")
    if pt is None:
        return None
    return pt if isinstance(pt, str) else json.dumps(pt, sort_keys=True)


def collect(logs_dir: Path) -> dict[str, dict[str, list[str]]]:
    by_theorem: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for f in logs_dir.rglob("*metrics.json"):
        try:
            metrics = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        term = _term_of(metrics)
        if term is None:
            continue
        theorem = f.parent.name
        variant = f.name.replace("_metrics.json", "")
        by_theorem[theorem][variant].append(normalize_term(term))
    return by_theorem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", nargs="?", default="logs", type=Path)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--show", default=None, help="print distinct terms for one theorem")
    args = parser.parse_args()

    logs_dir = args.logs_dir.resolve()
    if not logs_dir.is_dir():
        raise SystemExit(f"logs dir not found: {logs_dir}")

    data = collect(logs_dir)

    if args.show is not None:
        variants = data.get(args.show)
        if not variants:
            raise SystemExit(f"no solved metrics for {args.show}")
        all_terms = [t for terms in variants.values() for t in terms]
        for i, t in enumerate(sorted(set(all_terms))):
            print(f"--- distinct term {i} ---\n{t[:600]}\n")
        return

    wild_multi = wild_mono = 0
    all_multi = all_mono = 0
    rows = []
    for theorem, variants in data.items():
        wild = variants.get("wild_type", [])
        all_terms = [t for terms in variants.values() for t in terms]
        wild_distinct = len(set(wild))
        all_distinct = len(set(all_terms))
        if len(wild) > 1:
            wild_mono += 1
            if wild_distinct > 1:
                wild_multi += 1
        if len(all_terms) > 1:
            all_mono += 1
            if all_distinct > 1:
                all_multi += 1
        rows.append((theorem, len(all_terms), all_distinct, len(wild), wild_distinct))

    wild_pct = f"{wild_multi / wild_mono:.0%}" if wild_mono else "n/a"
    all_pct = f"{all_multi / all_mono:.0%}" if all_mono else "n/a"
    print(f"theorems with a recorded proof term      : {len(data)}")
    print(f"solved >1x under identical (wild_type)    : {wild_mono}")
    print(f"  of those, >1 distinct term (monodromy)  : {wild_multi} ({wild_pct})")
    print(f"solved >1x across any variant             : {all_mono}")
    print(f"  of those, >1 distinct term (monodromy)  : {all_multi} ({all_pct})")

    rows.sort(key=lambda r: (r[2], r[1]), reverse=True)
    print("\ntop theorems by distinct proof terms:")
    print(f"  {'theorem':52} {'solves':>6} {'distinct':>8} {'wild':>5} {'wild_d':>6}")
    for theorem, solves, distinct, wild_n, wild_d in rows[: args.top]:
        print(f"  {theorem[:52]:52} {solves:>6} {distinct:>8} {wild_n:>5} {wild_d:>6}")


if __name__ == "__main__":
    main()
