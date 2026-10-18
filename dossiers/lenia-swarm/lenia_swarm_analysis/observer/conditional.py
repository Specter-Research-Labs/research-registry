"""Conditional prequential codelength: the bits needed to code target b's training stream when b's
learner starts from source a's trained learner instead of from scratch.

The zero-shot transfer matrix asks how well a's finished model predicts b. This asks how much of what
a learned is reusable for learning b, which is the codelength of b given a. The target stream is the
same one `measure` coded from scratch, so saving = scratch codelength - conditional codelength.

Pairs are a JSONL file of {"source": <campaign>, "target": <campaign>}; choosing them (nearest under
transfer distance, random controls, within/between groups) belongs to the study. Writes
conditional_<observer>_<pairs file stem>.jsonl into the measure directory.

Usage: lenia-swarm-observer conditional --measure <dir> --observer <name> --pairs <pairs.jsonl> --device mps
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from .measure import TRAIN_STREAM, stream, train
from .prequential import epiplexity
from .run import MeasureRun
from .states import load_states


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lenia-swarm-observer conditional", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--measure", type=Path, required=True)
    parser.add_argument("--observer", required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=["mps", "cuda", "cpu"])
    args = parser.parse_args(argv)

    run = MeasureRun.open(args.measure)
    observer = run.observer(args.observer)
    config = run.config
    out_path = args.measure / f"conditional_{observer.name}_{args.pairs.stem}.jsonl"
    if out_path.exists():
        raise FileExistsError(out_path)
    index = {c: i for i, c in enumerate(run.campaigns)}
    pairs = [json.loads(line) for line in args.pairs.read_text().splitlines()]
    unknown = {p[k] for p in pairs for k in ("source", "target")} - index.keys()
    if unknown:
        raise ValueError(f"pairs name campaigns outside {args.measure}: {sorted(unknown)[:5]}")
    params = run.params(observer.name, args.device)
    scratch = run.curves(observer.name).sum(1) * config.batch
    with out_path.open("w") as fh:
        for g0 in range(0, len(pairs), config.group):
            group = pairs[g0:g0 + config.group]
            sources = torch.tensor([index[p["source"]] for p in group], device=args.device)
            targets = [load_states(run.replay / "campaigns" / p["target"]) for p in group]
            init = [w[sources].clone().requires_grad_() for w in params]
            curve = train(observer, config, init, [stream(s, config, TRAIN_STREAM) for s in targets],
                          args.device)
            s_bits, h_bits = epiplexity(curve, batch=config.batch, tail=config.tail)
            for p, c, s_val, h_val in zip(group, curve, s_bits, h_bits, strict=True):
                bits = float(c.sum() * config.batch)
                fh.write(json.dumps({**p, "codelength": bits, "scratch": float(scratch[index[p["target"]]]),
                                     "saving": float(scratch[index[p["target"]]]) - bits,
                                     "S": float(s_val), "H": float(h_val)}) + "\n")
            print(f"conditional {g0 + len(group)}/{len(pairs)}", flush=True)
    return 0
