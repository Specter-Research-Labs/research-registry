"""Requalify historically selected bodies under the creature definition.

Members come from a historical selection (a long-horizon screen or a gap-search requalification)
together with the replay inputs it was run from. Each member keeps its parameters and initial patch
and is replayed on the torus at multiple arena sizes, as `classify-creatures` requires.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCREEN_LITERALS = (
    "individuality_pass",
    "locality_pass",
    "translation_pass",
    "orbit_or_gyration_pass",
    "individuality_axes",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(value: Any) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _body_spec(base: dict[str, Any]) -> dict[str, Any]:
    patch = base["init"]["state_patch"]
    native = base["grid"]["sx"]
    if base["grid"]["sy"] != native or patch["center"] != [native // 2, native // 2]:
        raise ValueError("expected a square grid with the initial patch centred")
    if base["init"]["patches"] or base["init"]["seed"] != 0:
        raise ValueError("expected a state patch as the only initial condition")
    return {
        "params_sha256": _canonical_sha(base["params"]),
        "state_patch_sha256": _sha(base64.b64decode(patch["data"])),
        "state_patch_shape": [patch["channels"], patch["height"], patch["width"]],
        "native_arena": native,
        "native_border": base["reintegration"]["border"],
    }


REQUAL_COHERENCE_MIN = 0.8


def _screen_selection(path: Path, qualified: bool) -> dict[str, dict[str, Any]]:
    """Rows of a long-horizon screen whose individuality-and-locality qualification equals `qualified`."""
    selected = {}
    for raw in _read_jsonl(path):
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
        if _sha(config.read_bytes()) != r["config_sha256"]:
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
        inputs = {r["creatureId"]: r for r in _read_jsonl(index_path)}
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
                "input_index_sha256": _sha(index_path.read_bytes()),
                "selection": str(selection_path),
                "selection_sha256": _sha(selection_path.read_bytes()),
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
    output_root.mkdir()
    receipt: dict[str, Any] = {"members_sha256": _sha(members_path.read_bytes()), "cells": {}}
    for native in sorted({m["native_arena"] for m in members}):
        group = [m for m in members if m["native_arena"] == native]
        for scale in scales:
            size = native * scale
            cell = output_root / f"n{native}-torus{size}"
            written, bases = [], {}
            for m in group:
                src = Path(m["input"]["exportDir"])
                base = json.loads((src / "base.json").read_text())
                if _body_spec(base)["params_sha256"] != m["params_sha256"]:
                    raise ValueError(f"{src}: input changed since members were collected")
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
                        **m["input"],
                        "exportDir": str(d),
                        "baseConfigPath": str(d / "base.json"),
                        "searchConfigPath": str(d / "search.json"),
                    }
                )
                bases[m["body"]] = _sha((d / "base.json").read_bytes())
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


def _trace_key(path: Path) -> tuple[int, str]:
    arena = re.search(r"torus(\d+)", str(path))
    if arena is None:
        raise ValueError(f"{path}: no torus arena size in the path")
    return int(arena.group(1)), path.parent.name.rsplit("-", 1)[1].lower()


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
                kept.append({"path": str(trace), "sha256": _sha(raw), "bytes": len(raw)})
                continue
            stripped = []
            for i, f in enumerate(frames):
                field = f.get("fieldF16Base64")
                if field is None:
                    raise ValueError(f"{trace}: already stripped")
                f["fieldF16Sha256"] = _sha(base64.b64decode(field))
                if i != len(frames) - 1:
                    del f["fieldF16Base64"]
                stripped.append(json.dumps(f, sort_keys=True))
            text = ("\n".join(stripped) + "\n").encode()
            rows.append(
                {
                    "path": str(trace),
                    "sha256": _sha(raw),
                    "bytes": len(raw),
                    "stripped_sha256": _sha(text),
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


def compare_trace_digests(*, manifests: list[Path], prior_manifests: list[Path]) -> dict[str, Any]:
    """Match whole-trace SHA-256 digests by torus arena size and body between two runs.

    Manifests are retirement manifests: {"stripped": [...], "kept": [...]} or a JSONL of stripped
    rows, each row with the original trace path and sha256.
    """

    def digests(paths: list[Path]) -> dict[tuple[int, str], str]:
        out: dict[tuple[int, str], str] = {}
        for path in paths:
            text = path.read_text()
            if path.suffix == ".jsonl":
                rows = [json.loads(line) for line in text.splitlines() if line.strip()]
                rows = [{**r, "path": str(path.parent / r["path"])} for r in rows]
            else:
                manifest = json.loads(text)
                rows = manifest["stripped"] + manifest["kept"]
            for r in rows:
                out[_trace_key(Path(r["path"]))] = r["sha256"]
        return out

    new, old = digests(manifests), digests(prior_manifests)
    shared = sorted(set(new) & set(old))
    differ = [f"torus{a}/{b}" for a, b in shared if new[(a, b)] != old[(a, b)]]
    return {"shared": len(shared), "identical": len(shared) - len(differ), "differ": differ}
