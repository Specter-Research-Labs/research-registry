from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atp.tptp import e_runner, vampire_runner
from atp.z3 import runner as z3_runner
from atp.z3.proof_parser import extract_proof_block
from corpus.artifacts import (
    compute_build_id,
    iter_jsonl,
    parse_corpus_ref,
    resolve_corpus_build_dir,
    sha256_file,
    timestamp,
    write_current_id,
    write_json_atomic,
    write_jsonl,
)


def _load_manifest(build_dir: Path) -> dict[str, Any]:
    path = build_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest.json (not an object): {path}")
    return data


@dataclass(frozen=True)
class ExternalCapabilitySweepResult:
    backend: str
    corpus_ref: str
    build_dir: Path
    capability_path: Path
    derived_feasible_dir: Path
    reachable_count: int
    total_count: int
    reachable_rate: float


def _derive_feasible_slice(
    *,
    build_dir: Path,
    backend: str,
    corpus_id: str,
    parent_build_id: str,
    parent_manifest: dict[str, Any],
    capability_path: Path,
    reachable_ids: set[str],
    meta: dict[str, Any],
) -> Path:
    derived_root = build_dir / "derived" / "feasible"
    derived_root.mkdir(parents=True, exist_ok=True)

    items_path = build_dir / str(parent_manifest.get("items_file") or "items.jsonl")
    items: list[dict[str, Any]] = []
    for row in iter_jsonl(items_path):
        item_id = row.get("item_id")
        if isinstance(item_id, str) and item_id in reachable_ids:
            items.append(row)

    tmp_dir = derived_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_items = tmp_dir / f"items.{os.getpid()}.jsonl.tmp"
    write_jsonl(tmp_items, items)
    derived_items_sha = sha256_file(tmp_items)
    capability_sha = sha256_file(capability_path)

    fingerprint = {
        "kind": "derived_feasible",
        "parent_build_id": parent_build_id,
        "parent_items_sha256": str(parent_manifest.get("items_sha256") or ""),
        "capability_sha256": capability_sha,
        "derived_items_sha256": derived_items_sha,
        "derived_items_total": len(items),
    }
    derived_build_id = compute_build_id(fingerprint)
    derived_dir = derived_root / derived_build_id
    if derived_dir.exists():
        write_current_id(derived_root, derived_build_id)
        copied = derived_dir / "capability.jsonl"
        if not copied.exists():
            shutil.copy2(capability_path, copied)
        if tmp_items.exists():
            tmp_items.unlink()
        return derived_dir

    derived_dir.mkdir(parents=True, exist_ok=False)
    tmp_items.replace(derived_dir / "items.jsonl")
    shutil.copy2(capability_path, derived_dir / "capability.jsonl")

    provenance = list(parent_manifest.get("provenance") or [])
    provenance.append(
        {
            "kind": "derived",
            "derived_kind": "feasible",
            "parent_build_id": parent_build_id,
            "capability_sha256": capability_sha,
            **meta,
        }
    )
    build_config = dict(parent_manifest.get("build_config") or {})
    build_config.update(
        {
            "derived_kind": "feasible",
            "parent_build_id": parent_build_id,
            "capability_sha256": capability_sha,
            **meta,
        }
    )
    manifest = {
        **parent_manifest,
        "build_id": derived_build_id,
        "created_at": timestamp(),
        "provenance": provenance,
        "build_config": build_config,
        "counts": {"items_total": len(items)},
        "items_file": "items.jsonl",
        "items_sha256": derived_items_sha,
        "parent": {
            "build_id": parent_build_id,
            "items_sha256": str(parent_manifest.get("items_sha256") or ""),
        },
    }
    write_json_atomic(derived_dir / "manifest.json", manifest)
    write_current_id(derived_root, derived_build_id)
    if tmp_dir.exists():
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return derived_dir


def run_tptp_capability_sweep(
    *,
    corpus_ref: str,
    use_e: bool = True,
    use_vampire: bool = True,
    timeout_sec: int = 10,
    e_binary: str = "eprover",
    vampire_binary: str = "vampire",
    min_feasible_rate: float = 0.05,
    allow_low_feasible: bool = False,
) -> ExternalCapabilitySweepResult:
    ref = parse_corpus_ref(corpus_ref)
    if ref.derived is not None:
        raise ValueError(
            "Capability sweep expects a base corpus ref (no #derived): "
            f"{corpus_ref!r}"
        )
    if not use_e and not use_vampire:
        raise ValueError("At least one prover must be enabled (use_e/use_vampire)")
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be >= 1")

    build_dir = resolve_corpus_build_dir(ref)
    manifest = _load_manifest(build_dir)
    backend = str(manifest.get("backend") or ref.backend)
    if backend != "tptp":
        raise ValueError(f"Expected backend=tptp, got: {backend}")
    corpus_id = str(manifest.get("corpus_id") or ref.corpus_id)
    parent_build_id = str(manifest.get("build_id") or "")
    if not parent_build_id:
        raise ValueError("manifest.json missing build_id")

    tptp_root = Path(str(manifest.get("build_config", {}).get("tptp_root") or ""))
    if not tptp_root.exists():
        raise FileNotFoundError(
            "TPTP root not found (manifest build_config.tptp_root): "
            f"{tptp_root}"
        )

    proof_cwd = tptp_root.parent
    env = os.environ.copy()
    env.setdefault("TPTP", str(proof_cwd))

    e_cfg = e_runner.EConfig(
        binary=e_binary,
        timeout_sec=timeout_sec,
        extra_args=["--auto", "--output-level=2"],
    )
    v_cfg = vampire_runner.VampireConfig(
        binary=vampire_binary,
        timeout_sec=timeout_sec,
        extra_args=[],
    )

    items_path = build_dir / str(manifest.get("items_file") or "items.jsonl")
    rows: list[dict[str, Any]] = []
    reachable_ids: set[str] = set()
    for row in iter_jsonl(items_path):
        item_id = row.get("item_id")
        payload = row.get("payload")
        relpath = payload.get("relpath") if isinstance(payload, dict) else None
        if not isinstance(item_id, str) or not isinstance(relpath, str):
            raise ValueError(f"Invalid TPTP item row in {items_path}")
        path = tptp_root / relpath
        if not path.exists():
            raise FileNotFoundError(f"TPTP problem not found: {path}")

        e_status = None
        e_solved = False
        e_error = None
        if use_e:
            try:
                out = e_runner._run_e(path, e_cfg, proof_cwd, env)
                e_status = e_runner._extract_szs_status(out)
                e_solved = bool(e_status in e_runner.SZS_SOLVED) if e_status else False
            except Exception as exc:
                e_error = str(exc)[:200]

        v_status = None
        v_solved = False
        v_error = None
        if use_vampire:
            try:
                out = vampire_runner._run_vampire(path, v_cfg, proof_cwd)
                v_status = vampire_runner._extract_szs_status(out)
                v_solved = bool(v_status in vampire_runner.SZS_SOLVED) if v_status else False
            except Exception as exc:
                v_error = str(exc)[:200]

        reachable = bool(e_solved or v_solved)
        if reachable:
            reachable_ids.add(item_id)
        rows.append(
            {
                "item_id": item_id,
                "reachable": reachable,
                "e": {"enabled": use_e, "solved": e_solved, "status": e_status, "error": e_error},
                "vampire": {
                    "enabled": use_vampire,
                    "solved": v_solved,
                    "status": v_status,
                    "error": v_error,
                },
            }
        )

    capability_path = build_dir / "capability.jsonl"
    write_jsonl(capability_path, rows)

    total = len(rows)
    reachable_count = len(reachable_ids)
    reachable_rate = (reachable_count / total) if total else 0.0
    if total == 0:
        raise RuntimeError(f"No items found for {corpus_ref}")
    if reachable_rate < min_feasible_rate and not allow_low_feasible:
        raise RuntimeError(
            f"Feasible fraction too low for {corpus_ref}: {reachable_rate:.1%} "
            f"({reachable_count}/{total}); set --allow-low-feasible to override."
        )

    derived_feasible_dir = _derive_feasible_slice(
        build_dir=build_dir,
        backend=backend,
        corpus_id=corpus_id,
        parent_build_id=parent_build_id,
        parent_manifest=manifest,
        capability_path=capability_path,
        reachable_ids=reachable_ids,
        meta={
            "backend": "tptp",
            "timeout_sec": timeout_sec,
            "use_e": use_e,
            "use_vampire": use_vampire,
            "e_binary": e_binary,
            "vampire_binary": vampire_binary,
        },
    )
    return ExternalCapabilitySweepResult(
        backend=backend,
        corpus_ref=corpus_ref,
        build_dir=build_dir,
        capability_path=capability_path,
        derived_feasible_dir=derived_feasible_dir,
        reachable_count=reachable_count,
        total_count=total,
        reachable_rate=reachable_rate,
    )


def run_smtlib_capability_sweep(
    *,
    corpus_ref: str,
    timeout_sec: int = 10,
    z3_binary: str = "z3",
    z3_extra_args: list[str] | None = None,
    require_proof: bool = False,
    min_feasible_rate: float = 0.05,
    allow_low_feasible: bool = False,
) -> ExternalCapabilitySweepResult:
    ref = parse_corpus_ref(corpus_ref)
    if ref.derived is not None:
        raise ValueError(
            "Capability sweep expects a base corpus ref (no #derived): "
            f"{corpus_ref!r}"
        )
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be >= 1")

    build_dir = resolve_corpus_build_dir(ref)
    manifest = _load_manifest(build_dir)
    backend = str(manifest.get("backend") or ref.backend)
    if backend != "smtlib":
        raise ValueError(f"Expected backend=smtlib, got: {backend}")
    corpus_id = str(manifest.get("corpus_id") or ref.corpus_id)
    parent_build_id = str(manifest.get("build_id") or "")
    if not parent_build_id:
        raise ValueError("manifest.json missing build_id")

    problems_root = build_dir / "problems"
    if not problems_root.exists():
        raise FileNotFoundError(f"SMT-LIB problems dir not found: {problems_root}")

    cfg = z3_runner.Z3Config(
        binary=z3_binary,
        timeout_sec=timeout_sec,
        extra_args=z3_extra_args,
    )

    items_path = build_dir / str(manifest.get("items_file") or "items.jsonl")
    rows: list[dict[str, Any]] = []
    reachable_ids: set[str] = set()
    for row in iter_jsonl(items_path):
        item_id = row.get("item_id")
        payload = row.get("payload")
        relpath = payload.get("relpath") if isinstance(payload, dict) else None
        if not isinstance(item_id, str) or not isinstance(relpath, str):
            raise ValueError(f"Invalid SMT-LIB item row in {items_path}")
        path = problems_root / relpath
        if not path.exists():
            raise FileNotFoundError(f"SMT-LIB problem not found: {path}")

        status = None
        ok = False
        err = None
        try:
            input_text = (
                z3_runner._prepare_input(path)
                if require_proof
                else path.read_text(encoding="utf-8")
            )
            output = z3_runner._run_z3(input_text, cfg)
            status = z3_runner._extract_status(output)
            if status == "unsat":
                if require_proof:
                    ok = extract_proof_block(output) is not None
                    if not ok:
                        err = "missing_proof_block"
                else:
                    ok = True
        except Exception as exc:
            err = str(exc)[:200]

        reachable = bool(ok)
        if reachable:
            reachable_ids.add(item_id)
        rows.append(
            {
                "item_id": item_id,
                "reachable": reachable,
                "z3": {
                    "binary": z3_binary,
                    "timeout_sec": timeout_sec,
                    "require_proof": require_proof,
                    "status": status,
                    "error": err,
                },
            }
        )

    capability_path = build_dir / "capability.jsonl"
    write_jsonl(capability_path, rows)

    total = len(rows)
    reachable_count = len(reachable_ids)
    reachable_rate = (reachable_count / total) if total else 0.0
    if total == 0:
        raise RuntimeError(f"No items found for {corpus_ref}")
    if reachable_rate < min_feasible_rate and not allow_low_feasible:
        raise RuntimeError(
            f"Feasible fraction too low for {corpus_ref}: {reachable_rate:.1%} "
            f"({reachable_count}/{total}); set --allow-low-feasible to override."
        )

    derived_feasible_dir = _derive_feasible_slice(
        build_dir=build_dir,
        backend=backend,
        corpus_id=corpus_id,
        parent_build_id=parent_build_id,
        parent_manifest=manifest,
        capability_path=capability_path,
        reachable_ids=reachable_ids,
        meta={
            "backend": "smtlib",
            "timeout_sec": timeout_sec,
            "z3_binary": z3_binary,
            "z3_extra_args": z3_extra_args or [],
            "require_proof": require_proof,
        },
    )
    return ExternalCapabilitySweepResult(
        backend=backend,
        corpus_ref=corpus_ref,
        build_dir=build_dir,
        capability_path=capability_path,
        derived_feasible_dir=derived_feasible_dir,
        reachable_count=reachable_count,
        total_count=total,
        reachable_rate=reachable_rate,
    )
