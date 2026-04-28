from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leantree.repl_adapter.interaction import LeanInteractionException, LeanProcessException

from analysis.logs import (
    ProviderRun,
    iter_provider_runs,
    read_json,
    read_json_gz,
    sha256_file,
    utc_timestamp,
    write_json_atomic,
)
from prover.adapters.lean import LeanAdapter

VERIFY_LOCAL_VERSION = 1
VERIFY_LOCAL_SUMMARY_NAME = "verify_local_summary.json"
VERIFY_LOCAL_REPORT_NAME = "wild_type_verify_local.json"
VERIFY_LOCAL_CANDIDATE_NAME = "wild_type_verify_local.lean"
VERIFY_LOCAL_IMPORTS = "\n".join(
    [
        "import Mathlib",
        "open BigOperators Real Nat Topology",
        "set_option maxRecDepth 2000",
        "set_option maxHeartbeats 200000",
    ]
)


@dataclass(frozen=True)
class _TheoremInputs:
    theorem_name: str
    theorem_dir: Path
    candidate_path: Path
    statement_template: str
    theorem_with_sorry: str
    candidate_name: str
    history_path: Path
    history_sha256: str | None
    statement_sha256: str
    solution_path: list[dict[str, Any]]


@dataclass
class _LeanReplaySession:
    lean_project: Path
    adapter: LeanAdapter | None = None
    base_checkpoint: Any = None

    async def ensure(self) -> None:
        if self.adapter is not None and self.base_checkpoint is not None:
            return
        self.adapter, self.base_checkpoint = await _open_adapter(self.lean_project)

    async def reset(self) -> None:
        await self.close()
        await self.ensure()

    async def close(self) -> None:
        await _close_adapter(self.adapter)
        self.adapter = None
        self.base_checkpoint = None


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def _read_json_dict(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _read_json_gz_dict(path: Path) -> dict[str, Any]:
    payload = read_json_gz(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _load_statement_templates(items_path: Path) -> dict[str, str]:
    statements: dict[str, str] = {}
    with items_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"items_path line {line_no} must be an object")
            item_id = row.get("item_id")
            payload = row.get("payload")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"items_path line {line_no} missing item_id")
            if not isinstance(payload, dict):
                raise ValueError(f"items_path line {line_no} missing payload")
            statement = payload.get("statement")
            if not isinstance(statement, str) or "{name}" not in statement:
                raise ValueError(f"items_path line {line_no} missing payload.statement template")
            statements[item_id] = statement
    return statements


def _resolve_lean_project(run_config: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        project = override.resolve()
    else:
        resolved = run_config.get("resolved")
        project_value = resolved.get("project_path") if isinstance(resolved, dict) else None
        if not isinstance(project_value, str) or not project_value.strip():
            raise ValueError(
                "run_config.json missing resolved.project_path; pass --lean-project explicitly"
            )
        project = Path(project_value).expanduser().resolve()
    if not project.exists():
        raise FileNotFoundError(f"Lean project not found: {project}")
    return project


def _resolve_items_path(run_config: dict[str, Any]) -> Path:
    corpus_meta = run_config.get("corpus_meta")
    items_value = corpus_meta.get("items_path") if isinstance(corpus_meta, dict) else None
    if not isinstance(items_value, str) or not items_value.strip():
        raise ValueError("run_config.json missing corpus_meta.items_path")
    items_path = Path(items_value).expanduser().resolve()
    if not items_path.exists():
        raise FileNotFoundError(f"items_path not found: {items_path}")
    return items_path


def _render_theorem(statement_template: str, theorem_name: str, tactics: list[str] | None) -> str:
    if "{name}" not in statement_template:
        raise ValueError("statement template missing {name}")
    theorem_text = statement_template.replace("{name}", theorem_name)
    if tactics is None:
        return theorem_text
    tactic_block = "\n".join(f"  {tactic}" for tactic in tactics)
    rendered = theorem_text.replace("sorry", tactic_block, 1)
    if rendered == theorem_text:
        raise ValueError("statement template missing proof placeholder `sorry`")
    return rendered


def _render_candidate_file(statement_template: str, theorem_name: str, tactics: list[str]) -> str:
    theorem_text = _render_theorem(statement_template, theorem_name, tactics)
    return f"{VERIFY_LOCAL_IMPORTS}\n\n{theorem_text}\n"


def _target_theorems(
    summary: dict[str, Any],
    *,
    theorem_names: set[str] | None,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int]:
    theorem_entries = summary.get("theorems")
    if not isinstance(theorem_entries, list):
        raise ValueError("summary.json.gz missing theorems list")

    selected: list[dict[str, Any]] = []
    present_names: set[str] = set()
    skipped_unsolved = 0
    for entry in theorem_entries:
        if not isinstance(entry, dict):
            raise ValueError("summary.json.gz theorem entry must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("summary.json.gz theorem entry missing name")
        present_names.add(name)
        if theorem_names is not None and name not in theorem_names:
            continue
        wild_type = entry.get("wild_type")
        solved = wild_type.get("solved") if isinstance(wild_type, dict) else False
        if solved is not True:
            skipped_unsolved += 1
            continue
        selected.append(entry)

    if theorem_names is not None:
        missing = sorted(theorem_names - present_names)
        if missing:
            raise ValueError(f"Requested theorem(s) not found in summary: {', '.join(missing)}")
    if limit is not None:
        selected = selected[:limit]
    return selected, skipped_unsolved


def _input_failed_payload(
    theorem_name: str,
    *,
    error: str,
    statement_sha256: str | None = None,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    if statement_sha256 is not None:
        inputs["statement_sha256"] = statement_sha256
    return {
        "version": VERIFY_LOCAL_VERSION,
        "theorem": theorem_name,
        "variant": "wild_type",
        "status": "input_failed",
        "verified_at": utc_timestamp(),
        "replay_verified": False,
        "candidate_compiled": False,
        "applied_tactics": [],
        "replay_error": error,
        "candidate_error": None,
        "candidate_name": None,
        "candidate_sha256": None,
        "inputs": inputs,
    }


def _solution_path_for_theorem(theorem_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    history_path = theorem_dir / "wild_type_history.json"
    if not history_path.exists():
        raise FileNotFoundError(f"Missing history file: {history_path}")
    history = _read_json_dict(history_path)
    solution_path = history.get("solution_path")
    if not isinstance(solution_path, list) or not solution_path:
        raise ValueError(f"Missing non-empty solution_path in {history_path}")
    return solution_path, history_path


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _open_adapter(lean_project: Path) -> tuple[LeanAdapter, Any]:
    adapter = await LeanAdapter.create(lean_project)
    await adapter.__aenter__()
    return adapter, adapter.env.checkpoint()


async def _close_adapter(adapter: LeanAdapter | None) -> None:
    if adapter is None:
        return
    await adapter.__aexit__(None, None, None)


def _build_theorem_inputs(
    *,
    theorem_name: str,
    theorem_dir: Path,
    statement_template: str,
) -> _TheoremInputs:
    solution_path, history_path = _solution_path_for_theorem(theorem_dir)
    return _TheoremInputs(
        theorem_name=theorem_name,
        theorem_dir=theorem_dir,
        candidate_path=theorem_dir / VERIFY_LOCAL_CANDIDATE_NAME,
        statement_template=statement_template,
        theorem_with_sorry=_render_theorem(statement_template, theorem_name, None),
        candidate_name=f"{theorem_name}__verify_local",
        history_path=history_path,
        history_sha256=sha256_file(history_path),
        statement_sha256=_sha256_text(statement_template),
        solution_path=solution_path,
    )


def _existing_report_is_fresh(report_path: Path, inputs: _TheoremInputs) -> bool:
    if not report_path.exists():
        return False
    try:
        existing = _read_json_dict(report_path)
    except Exception:
        return False
    if existing.get("version") != VERIFY_LOCAL_VERSION:
        return False
    payload_inputs = existing.get("inputs")
    if not isinstance(payload_inputs, dict):
        return False
    if payload_inputs.get("history_sha256") != inputs.history_sha256:
        return False
    if payload_inputs.get("statement_sha256") != inputs.statement_sha256:
        return False
    if payload_inputs.get("solution_path_length") != len(inputs.solution_path):
        return False
    candidate_sha = existing.get("candidate_sha256")
    if isinstance(candidate_sha, str) and candidate_sha:
        if sha256_file(inputs.candidate_path) != candidate_sha:
            return False
    return True


async def _verify_theorem_local_async(
    *,
    session: _LeanReplaySession,
    inputs: _TheoremInputs,
) -> dict[str, Any]:
    await session.ensure()
    assert session.adapter is not None
    assert session.base_checkpoint is not None
    session.adapter.env.rollback_to(session.base_checkpoint)

    replay_error: str | None = None
    candidate_error: str | None = None
    replay_verified = False
    candidate_compiled = False
    applied_tactics: list[str] = []
    candidate_sha: str | None = None

    try:
        replay = await session.adapter.replay_solution_path(
            theorem_with_sorry=inputs.theorem_with_sorry,
            solution_path=inputs.solution_path,
        )
        replay_verified = replay.success
        replay_error = replay.error
        applied_tactics = replay.applied_tactics
        if replay.success:
            candidate_source = _render_theorem(
                inputs.statement_template,
                inputs.candidate_name,
                replay.applied_tactics,
            )
            candidate_file = _render_candidate_file(
                inputs.statement_template,
                inputs.candidate_name,
                replay.applied_tactics,
            )
            _write_text_atomic(inputs.candidate_path, candidate_file)
            candidate_sha = _sha256_text(candidate_file)
            session.adapter.env.rollback_to(session.base_checkpoint)
            await session.adapter.env.send_command_async(candidate_source)
            candidate_compiled = True
    except LeanProcessException as exc:
        if replay_verified:
            candidate_error = str(exc)
        else:
            replay_error = str(exc)
        await session.reset()
    except LeanInteractionException as exc:
        if replay_verified:
            candidate_error = str(exc)
        else:
            replay_error = str(exc)
    finally:
        if session.adapter is not None and session.base_checkpoint is not None:
            session.adapter.env.rollback_to(session.base_checkpoint)

    status = "verified"
    if not replay_verified:
        status = "replay_failed"
    elif not candidate_compiled:
        status = "candidate_failed"

    return {
        "version": VERIFY_LOCAL_VERSION,
        "theorem": inputs.theorem_name,
        "variant": "wild_type",
        "status": status,
        "verified_at": utc_timestamp(),
        "replay_verified": replay_verified,
        "candidate_compiled": candidate_compiled,
        "applied_tactics": applied_tactics,
        "replay_error": replay_error,
        "candidate_error": candidate_error,
        "candidate_name": inputs.candidate_name if replay_verified else None,
        "candidate_sha256": candidate_sha,
        "inputs": {
            "history_sha256": inputs.history_sha256,
            "statement_sha256": inputs.statement_sha256,
            "solution_path_length": len(inputs.solution_path),
        },
    }


async def _verify_provider_run_local_async(
    *,
    provider_run: ProviderRun,
    lean_project: Path,
    statements: dict[str, str],
    targets: list[dict[str, Any]],
    force: bool,
) -> dict[str, Any]:
    run_dir = provider_run.run_dir
    session = _LeanReplaySession(lean_project=lean_project)
    theorem_reports: list[dict[str, Any]] = []
    skipped_existing = 0

    try:
        for entry in targets:
            theorem_name = entry["name"]
            theorem_dir = run_dir / theorem_name
            theorem_dir.mkdir(parents=True, exist_ok=True)
            theorem_report_path = theorem_dir / VERIFY_LOCAL_REPORT_NAME

            if theorem_report_path.exists() and not force:
                statement_template = statements.get(theorem_name)
                if isinstance(statement_template, str):
                    try:
                        inputs = _build_theorem_inputs(
                            theorem_name=theorem_name,
                            theorem_dir=theorem_dir,
                            statement_template=statement_template,
                        )
                    except Exception:
                        inputs = None
                    if inputs is not None and _existing_report_is_fresh(
                        theorem_report_path,
                        inputs,
                    ):
                        theorem_reports.append(_read_json_dict(theorem_report_path))
                        skipped_existing += 1
                        continue

            statement_template = statements.get(theorem_name)
            if not isinstance(statement_template, str):
                payload = _input_failed_payload(
                    theorem_name,
                    error=f"Missing theorem statement for {theorem_name}",
                )
            else:
                try:
                    inputs = _build_theorem_inputs(
                        theorem_name=theorem_name,
                        theorem_dir=theorem_dir,
                        statement_template=statement_template,
                    )
                    payload = await _verify_theorem_local_async(session=session, inputs=inputs)
                except Exception as exc:
                    payload = _input_failed_payload(
                        theorem_name,
                        error=str(exc),
                        statement_sha256=_sha256_text(statement_template),
                    )
            write_json_atomic(theorem_report_path, payload)
            theorem_reports.append(payload)
    finally:
        await session.close()

    summary_payload = {
        "version": VERIFY_LOCAL_VERSION,
        "verified_at": utc_timestamp(),
        "run_dir": str(run_dir),
        "provider": provider_run.provider,
        "lean_project": str(lean_project),
        "counts": {
            "eligible": len(targets),
            "verified": sum(1 for item in theorem_reports if item.get("status") == "verified"),
            "replay_failed": sum(
                1 for item in theorem_reports if item.get("status") == "replay_failed"
            ),
            "candidate_failed": sum(
                1 for item in theorem_reports if item.get("status") == "candidate_failed"
            ),
            "input_failed": sum(
                1 for item in theorem_reports if item.get("status") == "input_failed"
            ),
            "skipped_existing": skipped_existing,
        },
        "inputs": {
            "run_config_sha256": sha256_file(run_dir / "run_config.json"),
            "summary_sha256": sha256_file(run_dir / "summary.json.gz"),
        },
        "theorems": theorem_reports,
    }
    return summary_payload


def verify_provider_run_local(
    provider_run: ProviderRun,
    *,
    theorem_names: list[str] | None = None,
    limit: int | None = None,
    lean_project: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")

    run_dir = provider_run.run_dir.resolve()
    run_config_path = run_dir / "run_config.json"
    summary_path = run_dir / "summary.json.gz"
    if not run_config_path.exists():
        raise FileNotFoundError(f"Missing run_config.json: {run_config_path}")
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json.gz: {summary_path}")

    run_config = _read_json_dict(run_config_path)
    backend = run_config.get("backend")
    if backend != "lean":
        raise ValueError(f"verify-run-local supports only backend=lean (got {backend!r})")

    summary = _read_json_gz_dict(summary_path)
    project_path = _resolve_lean_project(run_config, lean_project)
    items_path = _resolve_items_path(run_config)
    statements = _load_statement_templates(items_path)
    theorem_filter = set(theorem_names) if theorem_names else None
    targets, skipped_unsolved = _target_theorems(
        summary,
        theorem_names=theorem_filter,
        limit=limit,
    )

    report = asyncio.run(
        _verify_provider_run_local_async(
            provider_run=provider_run,
            lean_project=project_path,
            statements=statements,
            targets=targets,
            force=force,
        )
    )
    report["counts"]["skipped_unsolved"] = skipped_unsolved
    report["inputs"]["items_sha256"] = sha256_file(items_path)
    report["selection"] = {
        "theorem_names": theorem_names or [],
        "limit": limit,
        "selected_theorems": [entry["name"] for entry in targets],
    }
    write_json_atomic(run_dir / VERIFY_LOCAL_SUMMARY_NAME, report)
    return report


def verify_run_local(
    run_dir: Path,
    *,
    theorem_names: list[str] | None = None,
    limit: int | None = None,
    lean_project: Path | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for provider_run in iter_provider_runs(run_dir):
        reports.append(
            verify_provider_run_local(
                provider_run,
                theorem_names=theorem_names,
                limit=limit,
                lean_project=lean_project,
                force=force,
            )
        )
    return reports
