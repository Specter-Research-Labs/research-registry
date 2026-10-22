"""Requalify historically selected bodies under the creature definition.

Members come from a historical selection (a long-horizon screen or a gap-search requalification)
together with the replay inputs it was run from. Each member keeps its parameters and initial patch
and is replayed on the torus at multiple arena sizes, as `classify-creatures` requires.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_jsonl, sha256_bytes
from lenia_swarm_analysis.trace_codec import state_patch_values, trace_field

SCREEN_LITERALS = (
    "individuality_pass",
    "locality_pass",
    "translation_pass",
    "orbit_or_gyration_pass",
    "individuality_axes",
)


def _canonical_sha(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _body_spec(base: dict[str, Any]) -> dict[str, Any]:
    patch = base["init"]["state_patch"]
    native = base["grid"]["sx"]
    if base["grid"]["sy"] != native or patch["center"] != [native // 2, native // 2]:
        raise ValueError("expected a square grid with the initial patch centred")
    # init.seed only drives random patches and uniform noise, so it is free once both are off.
    if base["init"]["patches"] or base["init"]["a_uniform"] != {"low": 0, "high": 0}:
        raise ValueError("expected a state patch as the only initial condition")
    return {
        "params_sha256": _canonical_sha(base["params"]),
        "state_patch_sha256": sha256_bytes(state_patch_values(patch).tobytes()),
        "state_patch_shape": [patch["channels"], patch["height"], patch["width"]],
        "native_arena": native,
        "native_border": base["reintegration"]["border"],
    }


REQUAL_COHERENCE_MIN = 0.8


def _screen_selection(path: Path, qualified: bool) -> dict[str, dict[str, Any]]:
    """Rows of a long-horizon screen whose individuality-and-locality qualification equals `qualified`."""
    selected = {}
    for raw in read_jsonl(path):
        row = {
            k: ast.literal_eval(v) if k in SCREEN_LITERALS and isinstance(v, str) else v
            for k, v in raw.items()
        }
        gates = {"individuality": row["individuality_pass"], "locality": row["locality_pass"]}
        if all(gates.values()) != qualified:
            continue
        if row["translation_pass"]:
            motion = "translating"
        elif row["orbit_or_gyration_pass"]:
            motion = "orbiting"
        else:
            motion = "stationary"
        selected[row["source_creature_id"]] = {
            "selection": row["screen_id"],
            "campaign": row["candidate_id"],
            "gates": gates,
            "individuality_class": row["individuality_class"],
            "temporal_individuality": row["individuality_axes"]["temporal_individuality_score"],
            "motion_class": motion,
            "replay_config_path": row["replay"]["config_path"],
        }
    return selected


def _requal_selection(path: Path, qualified: bool) -> dict[str, dict[str, Any]]:
    """Records of a gap-search requalification whose qualification equals `qualified`."""
    requal = json.loads(path.read_text())
    configs = {p.parent.name: p for p in path.parent.glob("replay/*/campaigns/*/config.json")}
    selected = {}
    for r in requal["records"]:
        gates = {
            "individuality": r["individuality_pass"],
            "locality": r["locality_pass"],
            "coherence": r["coherence_min_1e-6"] >= REQUAL_COHERENCE_MIN,
        }
        if all(gates.values()) != r["qualified"]:
            raise ValueError(f"{path}: {r['campaign']} gates disagree with its qualification")
        if r["qualified"] != qualified:
            continue
        config = configs[r["campaign"]]
        if sha256_bytes(config.read_bytes()) != r["config_sha256"]:
            raise ValueError(f"{config}: config changed since the requalification")
        selected[r["source_creature_id"]] = {
            "selection": str(path),
            "campaign": r["campaign"],
            "gates": gates,
            "individuality_class": r["individuality_class"],
            "coherence_min_1e-6": r["coherence_min_1e-6"],
            "in_target_cells": r["in_target_cells"],
            "replay_config_path": str(config),
        }
    return selected


def collect_members(
    *, sources: list[tuple[str, str, Path, Path]], qualified: bool, output_path: Path
) -> dict[str, Any]:
    """Join each selection with the replay inputs it was run from.

    `qualified` picks the bodies that passed the historical gates, or, when false, those that failed.

    A source is (cohort, kind, input index.jsonl, selection), kind "screen" for a screened.jsonl of a
    long-horizon screen and "requal" for a gap-search requal.json. The replayed configuration must
    carry the input's parameters and initial patch.
    """
    readers = {"screen": _screen_selection, "requal": _requal_selection}
    members, provenance = [], []
    for cohort, kind, index_path, selection_path in sources:
        selected = readers[kind](selection_path, qualified)
        inputs = {r["creatureId"]: r for r in read_jsonl(index_path)}
        missing = sorted(set(selected) - set(inputs))
        if missing:
            raise ValueError(f"{cohort}: selected bodies absent from {index_path}: {missing}")
        for body, original in sorted(selected.items()):
            row = inputs[body]
            spec = _body_spec(json.loads(Path(row["baseConfigPath"]).read_text()))
            replayed = _body_spec(json.loads(Path(original["replay_config_path"]).read_text()))
            for key in ("params_sha256", "state_patch_sha256", "native_arena", "native_border"):
                if spec[key] != replayed[key]:
                    raise ValueError(f"{cohort}/{body}: replayed {key} differs from the input")
            members.append(
                {"cohort": cohort, "body": body, "input": row, "original": original, **spec}
            )
        provenance.append(
            {
                "cohort": cohort,
                "kind": kind,
                "input_index": str(index_path),
                "input_index_sha256": sha256_bytes(index_path.read_bytes()),
                "selection": str(selection_path),
                "selection_sha256": sha256_bytes(selection_path.read_bytes()),
                "members": len(selected),
            }
        )
    bodies = Counter(m["body"] for m in members)
    repeated = sorted(b for b, n in bodies.items() if n > 1)
    if repeated:
        raise ValueError(f"bodies selected by more than one source: {repeated}")
    output_path.write_text(
        json.dumps({"qualified": qualified, "sources": provenance, "members": members}, indent=1)
    )
    return {
        "output": str(output_path),
        "members": len(members),
        "by_cohort_and_native_arena": {
            f"{c}/{n}": k
            for (c, n), k in sorted(
                Counter((m["cohort"], m["native_arena"]) for m in members).items()
            )
        },
    }


def write_torus_inputs(
    *, members_path: Path, scales: list[int], steps: int, output_root: Path
) -> dict[str, Any]:
    """Write one replay input per native arena size and scale, on the torus, `steps` long.

    Each body keeps its parameters and initial patch, centred in the scaled grid; cells are named
    n<native>-torus<size>.
    """
    members = json.loads(members_path.read_text())["members"]
    for m in members:
        base = json.loads((Path(m["input"]["exportDir"]) / "base.json").read_text())
        if _body_spec(base)["params_sha256"] != m["params_sha256"]:
            raise ValueError(
                f"{m['input']['exportDir']}: input changed since members were collected"
            )
    return _write_arena_cells(
        rows=[(m["body"], m["native_arena"], m["input"]) for m in members],
        source={"members_sha256": sha256_bytes(members_path.read_bytes())},
        scales=scales,
        steps=steps,
        output_root=output_root,
    )


def write_arena_inputs(
    *, index_path: Path, scales: list[int], steps: int, output_root: Path
) -> dict[str, Any]:
    """Write torus replay inputs for every body of an export index, as `write_torus_inputs` does."""
    rows = []
    for row in read_jsonl(index_path):
        base = json.loads((Path(row["exportDir"]) / "base.json").read_text())
        rows.append((row["creatureId"], _body_spec(base)["native_arena"], row))
    bodies = Counter(body for body, _, _ in rows)
    repeated = sorted(b for b, n in bodies.items() if n > 1)
    if repeated:
        raise ValueError(f"bodies listed more than once in {index_path}: {repeated}")
    return _write_arena_cells(
        rows=rows,
        source={"index_sha256": sha256_bytes(index_path.read_bytes())},
        scales=scales,
        steps=steps,
        output_root=output_root,
    )


def _write_arena_cells(
    *,
    rows: list[tuple[str, int, dict[str, Any]]],
    source: dict[str, str],
    scales: list[int],
    steps: int,
    output_root: Path,
) -> dict[str, Any]:
    output_root.mkdir()
    receipt: dict[str, Any] = {**source, "cells": {}}
    for native in sorted({n for _, n, _ in rows}):
        group = [(body, row) for body, n, row in rows if n == native]
        for scale in scales:
            size = native * scale
            cell = output_root / f"n{native}-torus{size}"
            written, bases = [], {}
            for body, row in group:
                src = Path(row["exportDir"])
                base = json.loads((src / "base.json").read_text())
                base["grid"] = {**base["grid"], "sx": size, "sy": size}
                base["init"]["state_patch"]["center"] = [size // 2, size // 2]
                base["reintegration"]["border"] = "torus"
                search = json.loads((src / "search.json").read_text())
                search["steps"] = steps
                d = cell / src.name
                d.mkdir(parents=True)
                (d / "base.json").write_text(json.dumps(base))
                (d / "search.json").write_text(json.dumps(search))
                (d / "meta.json").write_bytes((src / "meta.json").read_bytes())
                written.append(
                    {
                        **row,
                        "exportDir": str(d),
                        "baseConfigPath": str(d / "base.json"),
                        "searchConfigPath": str(d / "search.json"),
                    }
                )
                bases[body] = sha256_bytes((d / "base.json").read_bytes())
            (cell / "index.jsonl").write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in written)
            )
            receipt["cells"][cell.name] = {"arena": size, "steps": steps, "base_sha256": bases}
    (output_root / "receipt.json").write_text(json.dumps(receipt, indent=1))
    return {
        "output": str(output_root),
        "cells": {k: len(v["base_sha256"]) for k, v in receipt["cells"].items()},
    }


def compare_verdicts(
    *,
    members_path: Path,
    assessments: list[Path],
    ensembles: list[Path],
    prior_ensembles: list[Path],
    output_path: Path,
) -> dict[str, Any]:
    """Tabulate each member's ensemble verdict, per-arena failed criteria and any prior verdict."""
    members = json.loads(members_path.read_text())["members"]
    verdicts: dict[str, dict[str, Any]] = {}
    for path in ensembles:
        for body, v in json.loads(path.read_text())["bodies"].items():
            if body in verdicts:
                raise ValueError(f"{body} classified twice")
            verdicts[body] = v
    prior: dict[str, str] = {}
    for path in prior_ensembles:
        for body, v in json.loads(path.read_text())["bodies"].items():
            prior[body] = v["verdict"]
    per_arena: dict[str, dict[str, dict[str, Any]]] = {}
    for path in assessments:
        for b in json.loads(path.read_text())["bodies"]:
            adult = b["adult"]
            per_arena.setdefault(b["body"], {})[str(b["arena"])] = {
                "failed": sorted(k for k, ok in b["criteria"].items() if not ok),
                "onset_step": adult["onset_step"],
                "min_lifetime_runs": (
                    min(adult["lifetime_runs"].values()) if adult["lifetime_runs"] else None
                ),
                "captured": adult["reference"]["captured"],
                "body_radius": adult["reference"]["body_radius"],
            }
    missing = sorted(m["body"] for m in members if m["body"] not in verdicts)
    if missing:
        raise ValueError(f"members without a verdict: {missing}")
    rows = []
    for m in members:
        rows.append(
            {
                "cohort": m["cohort"],
                "body": m["body"],
                "native_arena": m["native_arena"],
                "motion_class": m["original"].get("motion_class"),
                "failed_gates": sorted(g for g, ok in m["original"]["gates"].items() if not ok),
                "verdict": verdicts[m["body"]]["verdict"],
                "prior_verdict": prior.get(m["body"]),
                "arenas": per_arena[m["body"]],
            }
        )
    summary = {
        cohort: dict(Counter(r["verdict"] for r in rows if r["cohort"] == cohort))
        for cohort in sorted({r["cohort"] for r in rows})
    }
    transitions = Counter(
        f"{r['prior_verdict']}->{r['verdict']}" for r in rows if r["prior_verdict"] is not None
    )
    tally: dict[str, Counter[str]] = {}
    for r in rows:
        key = f"{r['cohort']}/{'+'.join(r['failed_gates']) or 'none'}"
        tally.setdefault(key, Counter())[r["verdict"]] += 1
    by_gates = {k: dict(v) for k, v in sorted(tally.items())}
    output_path.write_text(
        json.dumps(
            {
                "verdicts": summary,
                "verdicts_by_failed_gates": by_gates,
                "prior_transitions": dict(transitions),
                "members": rows,
            },
            indent=1,
        )
    )
    return {
        "output": str(output_path),
        "verdicts": summary,
        "verdicts_by_failed_gates": by_gates,
        "prior_transitions": dict(transitions),
    }


def retire_trace_fields(
    *,
    replay_roots: list[Path],
    assessments: list[Path],
    keep_bodies: list[str],
    manifest_path: Path,
    apply: bool,
) -> dict[str, Any]:
    """Strip raw fields from assessed development traces, keeping the terminal frame.

    Every stripped frame keeps fieldF16Sha256, the SHA-256 of its decoded float16 field. Traces of
    `keep_bodies` stay whole. Without `apply` only the manifest is written.
    """
    assessed = set()
    for path in assessments:
        for b in json.loads(path.read_text())["bodies"]:
            assessed.add((b["arena"], b["campaign"]))
    keep = {b.lower() for b in keep_bodies}
    rows, kept = [], []
    for root in replay_roots:
        for trace in sorted(root.glob("campaigns/*/development-trace.jsonl")):
            body = json.loads((trace.parent / "replay-manifest.json").read_text())[
                "sourceCreatureId"
            ]
            raw = trace.read_bytes()
            frames = [json.loads(line) for line in raw.decode().splitlines()]
            arena = frames[0]["width"]
            if (arena, trace.parent.name) not in assessed:
                raise ValueError(f"{trace}: not covered by the given assessments")
            if body.lower() in keep:
                kept.append({"path": str(trace), "sha256": sha256_bytes(raw), "bytes": len(raw)})
                continue
            stripped = []
            for i, f in enumerate(frames):
                if "fieldF16Base64" not in f:
                    raise ValueError(f"{trace}: already stripped")
                f["fieldF16Sha256"] = sha256_bytes(trace_field(f).tobytes())
                if i != len(frames) - 1:
                    del f["fieldF16Base64"]
                stripped.append(json.dumps(f, sort_keys=True))
            text = ("\n".join(stripped) + "\n").encode()
            rows.append(
                {
                    "path": str(trace),
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "stripped_sha256": sha256_bytes(text),
                    "stripped_bytes": len(text),
                }
            )
            if apply:
                tmp = trace.with_suffix(".stripped")
                tmp.write_bytes(text)
                tmp.replace(trace)
    manifest = {"applied": apply, "stripped": rows, "kept": kept}
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return {
        "manifest": str(manifest_path),
        "applied": apply,
        "stripped": len(rows),
        "kept": len(kept),
        "freed_bytes": sum(r["bytes"] - r["stripped_bytes"] for r in rows),
    }


def _canonical_frames(trace: Path) -> list[str]:
    out = []
    for line in trace.read_text().splitlines():
        f = json.loads(line)
        if "fieldF16Base64" in f:
            digest = sha256_bytes(trace_field(f).tobytes())
            if f.setdefault("fieldF16Sha256", digest) != digest:
                raise ValueError(
                    f"{trace}: step {f['step']} field does not match its fieldF16Sha256"
                )
            del f["fieldF16Base64"]
        out.append(json.dumps(f, sort_keys=True))
    return out


def _arena_traces(roots: list[Path]) -> dict[tuple[str, str], Path]:
    out: dict[tuple[str, str], Path] = {}
    for root in roots:
        arena = re.search(r"(torus|wall)\d+", root.name)
        if arena is None:
            raise ValueError(f"{root}: no torus or wall arena size in the replay root name")
        for trace in sorted(root.glob("campaigns/*/development-trace.jsonl")):
            body = json.loads((trace.parent / "replay-manifest.json").read_text())[
                "sourceCreatureId"
            ]
            key = (arena.group(0), body.lower())
            if key in out:
                raise ValueError(f"{trace}: second trace of {key}")
            out[key] = trace
    return out


def compare_trace_frames(
    *, replay_roots: list[Path], prior_replay_roots: list[Path]
) -> dict[str, Any]:
    """Compare development traces frame by frame between two runs, by arena and body.

    Each frame is compared as sorted-key JSON with its raw field replaced by fieldF16Sha256, so raw
    traces and traces stripped by retire_trace_fields compare alike. Whole-file digests cannot be
    compared across runs because LeniaCLI writes frame keys in varying order. Replay roots are
    named with their arena, as in n128-torus256 or 003-wall256.
    """
    new, old = _arena_traces(replay_roots), _arena_traces(prior_replay_roots)
    shared = sorted(set(new) & set(old))
    differ = []
    for key in shared:
        a, b = _canonical_frames(new[key]), _canonical_frames(old[key])
        if a != b:
            first = next(
                (i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y),
                min(len(a), len(b)),
            )
            differ.append(
                {"arena": key[0], "body": key[1], "frames": [len(a), len(b)], "first": first}
            )
    return {
        "shared": len(shared),
        "identical": len(shared) - len(differ),
        "differ": differ,
        "only_new": len(set(new) - set(old)),
        "only_prior": len(set(old) - set(new)),
    }
