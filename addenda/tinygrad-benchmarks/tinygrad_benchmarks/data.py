from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tinygrad_benchmarks import DEFAULT_LANE, SCHEMA_VERSION

_PRIVATE_LIST_FIELDS = {
    "historical_solution_refs",
    "private_source_refs",
    "resolution_source_refs",
}
_PRIVATE_STRING_FIELDS = {
    "gold_commit",
    "gold_patch",
    "gold_patch_sha256",
    "maintainer_notes",
}
_PUBLIC_METADATA_KEYS = {
    "changed_file_count",
    "changed_test_paths",
    "leakage_flags",
    "patch_line_count",
    "quality_components",
    "quality_score",
    "review_priority",
    "source_file_count",
    "task_statement_style",
    "test_file_count",
}
_PRIVATE_SOURCE_REF_PREFIXES = (
    "commit:",
    "discussion:",
    "gh:",
    "github:",
    "issue:",
    "pr:",
    "pull:",
)
_PUBLIC_SOURCE_REF_WHITELIST = {
    "history:curated",
    "history:mined",
}
_TASK_STATEMENT_PRIVATE_PATTERN = re.compile(r"#\d+|\(#\d+\)")


@dataclass(frozen=True)
class BenchmarkRow:
    item_id: str
    task_id: str
    lane: str
    repo_remote: str
    repo_commit: str
    task_statement: str
    source_refs: tuple[str, ...]
    target_paths: tuple[str, ...]
    acceptance_command: tuple[str, ...]
    acceptance_cwd: str
    timeout_seconds: int
    required_capabilities: tuple[str, ...]
    required_env: dict[str, str]
    metadata: dict[str, Any]
    raw: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class SubmissionRow:
    item_id: str
    candidate_id: str
    patch: str
    metadata: dict[str, Any]
    raw: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return dict(self.raw)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field} must not be empty.")
    return trimmed


def _require_text_blob(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    if not value.strip():
        raise ValueError(f"{field} must not be empty.")
    return value


def _validate_repo_relative_path(path: Any, *, field: str, allow_dot: bool = False) -> str:
    normalized = _require_string(path, field=field)
    if allow_dot and normalized == ".":
        return normalized
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"{field} must be repository-relative, got {normalized!r}.")
    segments = normalized.replace("\\", "/").split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(f"{field} must be normalized and stay within the repository.")
    return normalized


def _require_string_list(value: Any, *, field: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings.")
    normalized = [_require_string(item, field=field) for item in value]
    if not normalized and not allow_empty:
        raise ValueError(f"{field} must not be empty.")
    return normalized


def _require_command(value: Any, *, field: str) -> list[str]:
    command = _require_string_list(value, field=field)
    if not command:
        raise ValueError(f"{field} must not be empty.")
    return command


def _require_positive_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer.")
    if value <= 0:
        raise ValueError(f"{field} must be > 0.")
    return value


def _normalize_string_map(value: Any, *, field: str) -> dict[str, str]:
    mapping = _require_mapping(value, field=field)
    normalized: dict[str, str] = {}
    for key, item in mapping.items():
        normalized[_require_string(key, field=field)] = _require_string(item, field=field)
    return dict(sorted(normalized.items()))


def _normalize_metadata(value: Any, *, field: str) -> dict[str, Any]:
    mapping = _require_mapping(value, field=field)
    json.loads(_canonical_json(mapping))
    return dict(mapping)


def build_item_id(record: Mapping[str, Any]) -> str:
    identity = {
        "lane": record["lane"],
        "repo_remote": record["repo_remote"],
        "repo_commit": record["repo_commit"],
        "task_statement": record["task_statement"],
        "source_refs": record["source_refs"],
        "target_paths": record["target_paths"],
        "acceptance_command": record["acceptance_command"],
        "acceptance_cwd": record["acceptance_cwd"],
        "timeout_seconds": record["timeout_seconds"],
    }
    return f"tgbench_{_sha256_text(_canonical_json(identity))[:24]}"


def build_task_id(record: Mapping[str, Any]) -> str:
    identity = {
        "repo_commit": record["repo_commit"],
        "target_paths": record["target_paths"],
        "task_statement": record["task_statement"],
    }
    return f"task-{_sha256_text(_canonical_json(identity))[:16]}"


def _split_source_refs_for_public(source_refs: Sequence[str]) -> tuple[list[str], list[str]]:
    public_refs: list[str] = []
    private_refs: list[str] = []
    for ref in source_refs:
        lowered = ref.casefold()
        if lowered in _PUBLIC_SOURCE_REF_WHITELIST:
            public_refs.append(lowered)
            continue
        if lowered.startswith(_PRIVATE_SOURCE_REF_PREFIXES):
            private_refs.append(ref)
            continue
        if lowered.startswith("history:"):
            private_refs.append(ref)
            continue
        public_refs.append(ref)
    public_unique = sorted(set(public_refs)) or ["history:mined"]
    private_unique = sorted(set(private_refs))
    return public_unique, private_unique


def _split_metadata_for_public(
    metadata: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    public_metadata: dict[str, Any] = {}
    private_metadata: dict[str, Any] = {}
    for key, value in metadata.items():
        target = public_metadata if key in _PUBLIC_METADATA_KEYS else private_metadata
        target[str(key)] = value
    return (
        dict(sorted(public_metadata.items())),
        dict(sorted(private_metadata.items())),
    )


def _prepare_public_record(
    record: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    public_input = dict(record)
    source_refs = _require_string_list(record.get("source_refs"), field="source_refs")
    public_source_refs, private_source_refs = _split_source_refs_for_public(source_refs)
    metadata = _normalize_metadata(record.get("metadata", {}), field="metadata")
    public_metadata, private_metadata = _split_metadata_for_public(metadata)
    if _should_sanitize_task_statement(
        record=record,
        metadata=metadata,
        private_source_refs=private_source_refs,
        private_metadata=private_metadata,
    ):
        public_input["task_statement"] = _fallback_task_statement(record)
    public_input["source_refs"] = public_source_refs
    public_input["metadata"] = public_metadata
    normalized = normalize_benchmark_record(public_input)
    return normalized, private_source_refs, private_metadata


def _should_sanitize_task_statement(
    *,
    record: Mapping[str, Any],
    metadata: Mapping[str, Any],
    private_source_refs: Sequence[str],
    private_metadata: Mapping[str, Any],
) -> bool:
    task_statement = record.get("task_statement")
    if not isinstance(task_statement, str):
        return False
    if not private_source_refs and not private_metadata:
        return False
    commit_subject = metadata.get("commit_subject")
    if isinstance(commit_subject, str) and task_statement.strip() == commit_subject.strip():
        return True
    return bool(_TASK_STATEMENT_PRIVATE_PATTERN.search(task_statement))


def _fallback_task_statement(record: Mapping[str, Any]) -> str:
    target_paths = _require_string_list(record.get("target_paths"), field="target_paths")
    acceptance_command = _require_command(
        record.get("acceptance_command"),
        field="acceptance_command",
    )
    if len(target_paths) == 1:
        target_label = f"`{target_paths[0]}`"
    else:
        target_label = "the targeted implementation files"
    selectors = [
        part
        for part in acceptance_command[3:]
        if isinstance(part, str) and "/" in part and ".py" in part
    ]
    if len(selectors) == 1:
        return f"Update {target_label} so `{selectors[0]}` passes."
    if selectors:
        return f"Update {target_label} so the acceptance tests pass."
    return f"Update {target_label} so the acceptance command passes."


def normalize_benchmark_record(record: Mapping[str, Any]) -> dict[str, Any]:
    lane = _require_string(record.get("lane", DEFAULT_LANE), field="lane")
    repo_remote = _require_string(record.get("repo_remote"), field="repo_remote")
    repo_commit = _require_string(record.get("repo_commit"), field="repo_commit")
    task_statement = _require_string(record.get("task_statement"), field="task_statement")
    source_refs = _require_string_list(record.get("source_refs"), field="source_refs")
    target_paths = [
        _validate_repo_relative_path(path, field="target_paths")
        for path in _require_string_list(record.get("target_paths"), field="target_paths")
    ]
    acceptance_command = _require_command(
        record.get("acceptance_command"),
        field="acceptance_command",
    )
    acceptance_cwd = _validate_repo_relative_path(
        record.get("acceptance_cwd", "."),
        field="acceptance_cwd",
        allow_dot=True,
    )
    timeout_seconds = _require_positive_int(record.get("timeout_seconds"), field="timeout_seconds")
    required_capabilities = _require_string_list(
        record.get("required_capabilities", ["cpu"]),
        field="required_capabilities",
    )
    required_env = _normalize_string_map(record.get("required_env", {}), field="required_env")
    metadata = _normalize_metadata(record.get("metadata", {}), field="metadata")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "repo_remote": repo_remote,
        "repo_commit": repo_commit,
        "task_statement": task_statement,
        "source_refs": source_refs,
        "target_paths": target_paths,
        "acceptance_command": acceptance_command,
        "acceptance_cwd": acceptance_cwd,
        "timeout_seconds": timeout_seconds,
        "required_capabilities": required_capabilities,
        "required_env": required_env,
        "metadata": metadata,
    }
    task_id = record.get("task_id")
    normalized["task_id"] = (
        _require_string(task_id, field="task_id")
        if task_id is not None
        else build_task_id(normalized)
    )
    item_id = record.get("item_id")
    normalized["item_id"] = (
        _require_string(item_id, field="item_id")
        if item_id is not None
        else build_item_id(normalized)
    )
    return normalized


def normalize_submission_record(record: Mapping[str, Any]) -> dict[str, Any]:
    item_id = _require_string(record.get("item_id"), field="item_id")
    patch = _require_text_blob(record.get("patch"), field="patch")
    candidate_id = record.get("candidate_id")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "item_id": item_id,
        "candidate_id": (
            _require_string(candidate_id, field="candidate_id")
            if candidate_id is not None
            else f"{item_id}-candidate-0"
        ),
        "patch": patch,
        "metadata": _normalize_metadata(record.get("metadata", {}), field="metadata"),
    }
    return normalized


def build_private_task_record(
    record: Mapping[str, Any],
    *,
    item_id: str,
    task_id: str,
    private_source_refs: Sequence[str] = (),
    private_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    private_record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "item_id": item_id,
        "task_id": task_id,
    }
    for field in sorted(_PRIVATE_LIST_FIELDS):
        value = record.get(field)
        if value is not None:
            private_record[field] = _require_string_list(value, field=field)
    for field in sorted(_PRIVATE_STRING_FIELDS):
        value = record.get(field)
        if value is None:
            continue
        if field == "gold_patch":
            private_record[field] = _require_text_blob(value, field=field)
        else:
            private_record[field] = _require_string(value, field=field)
    if private_source_refs:
        private_record["private_source_refs"] = _require_string_list(
            list(private_source_refs),
            field="private_source_refs",
        )
    if private_metadata:
        private_record["private_metadata"] = _normalize_metadata(
            private_metadata,
            field="private_metadata",
        )
    if "gold_patch" in private_record and "gold_patch_sha256" not in private_record:
        private_record["gold_patch_sha256"] = _sha256_text(str(private_record["gold_patch"]))
    if len(private_record) == 3:
        return None
    return private_record


def _load_raw_records(path: Path) -> list[Mapping[str, Any]]:
    if path.suffix == ".jsonl":
        rows: list[Mapping[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(_require_mapping(json.loads(stripped), field=f"{path}:{line_no}"))
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [_require_mapping(item, field=str(path)) for item in value]
    mapping = _require_mapping(value, field=str(path))
    rows = mapping.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a top-level list or an object with a 'rows' list.")
    return [_require_mapping(item, field=str(path)) for item in rows]


def _row_from_record(record: dict[str, Any]) -> BenchmarkRow:
    return BenchmarkRow(
        item_id=str(record["item_id"]),
        task_id=str(record["task_id"]),
        lane=str(record["lane"]),
        repo_remote=str(record["repo_remote"]),
        repo_commit=str(record["repo_commit"]),
        task_statement=str(record["task_statement"]),
        source_refs=tuple(str(item) for item in record["source_refs"]),
        target_paths=tuple(str(item) for item in record["target_paths"]),
        acceptance_command=tuple(str(item) for item in record["acceptance_command"]),
        acceptance_cwd=str(record["acceptance_cwd"]),
        timeout_seconds=int(record["timeout_seconds"]),
        required_capabilities=tuple(str(item) for item in record["required_capabilities"]),
        required_env={str(key): str(value) for key, value in dict(record["required_env"]).items()},
        metadata=dict(record["metadata"]),
        raw=dict(record),
    )


def _submission_from_record(record: dict[str, Any]) -> SubmissionRow:
    return SubmissionRow(
        item_id=str(record["item_id"]),
        candidate_id=str(record["candidate_id"]),
        patch=str(record["patch"]),
        metadata=dict(record["metadata"]),
        raw=dict(record),
    )


def curate_rows(records: Sequence[Mapping[str, Any]]) -> list[BenchmarkRow]:
    normalized = [_row_from_record(_prepare_public_record(record)[0]) for record in records]
    duplicates = _duplicates([row.item_id for row in normalized])
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate item_id values are not allowed: {joined}")
    return sorted(normalized, key=lambda row: (row.item_id, row.task_id))


def curate_private_task_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    private_records: list[dict[str, Any]] = []
    for record in records:
        normalized, private_source_refs, private_metadata = _prepare_public_record(record)
        private_record = build_private_task_record(
            record,
            item_id=str(normalized["item_id"]),
            task_id=str(normalized["task_id"]),
            private_source_refs=private_source_refs,
            private_metadata=private_metadata,
        )
        if private_record is not None:
            private_records.append(private_record)
    duplicates = _duplicates([str(record["item_id"]) for record in private_records])
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate private item_id values are not allowed: {joined}")
    return sorted(
        private_records,
        key=lambda record: (str(record["item_id"]), str(record["task_id"])),
    )


def curate_submissions(records: Sequence[Mapping[str, Any]]) -> list[SubmissionRow]:
    normalized = [
        _submission_from_record(normalize_submission_record(record)) for record in records
    ]
    duplicates = _duplicates(
        [f"{submission.item_id}:{submission.candidate_id}" for submission in normalized]
    )
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(
            f"duplicate (item_id, candidate_id) submission pairs are not allowed: {joined}"
        )
    return sorted(normalized, key=lambda row: (row.item_id, row.candidate_id))


def load_rows(path: Path) -> list[BenchmarkRow]:
    return curate_rows(_load_raw_records(path))


def load_private_rows(path: Path) -> list[dict[str, Any]]:
    rows = _load_raw_records(path)
    if not rows:
        return []
    if all("repo_remote" in row and "task_statement" in row for row in rows):
        return curate_private_task_records(rows)
    loaded = [dict(_require_mapping(row, field=str(path))) for row in rows]
    for row in loaded:
        if "gold_patch" in row and "gold_patch_sha256" not in row:
            row["gold_patch_sha256"] = _sha256_text(str(row["gold_patch"]))
    return loaded


def load_submissions(path: Path) -> list[SubmissionRow]:
    return curate_submissions(_load_raw_records(path))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_canonical_json(record) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def rows_sha256(rows: Sequence[BenchmarkRow]) -> str:
    payload = [_canonical_row(row) for row in sorted(rows, key=lambda item: item.item_id)]
    return _sha256_text(_canonical_json(payload))


def split_rows(
    rows: Sequence[BenchmarkRow],
    *,
    seed: int,
    heldout_fraction: float,
) -> tuple[list[BenchmarkRow], list[BenchmarkRow]]:
    if not rows:
        raise ValueError("cannot split an empty benchmark index")
    if heldout_fraction < 0.0 or heldout_fraction > 1.0:
        raise ValueError("heldout_fraction must be in [0, 1]")
    if len(rows) == 1:
        return list(rows), []
    ordered = sorted(
        rows,
        key=lambda row: (_split_digest(seed=seed, item_id=row.item_id), row.item_id),
    )
    if heldout_fraction == 0.0:
        heldout_count = 0
    elif heldout_fraction == 1.0:
        heldout_count = len(ordered)
    else:
        heldout_count = round(len(ordered) * heldout_fraction)
        heldout_count = max(1, min(len(ordered) - 1, heldout_count))
    heldout = sorted(ordered[:heldout_count], key=lambda row: row.item_id)
    public_dev = sorted(ordered[heldout_count:], key=lambda row: row.item_id)
    return public_dev, heldout


def build_index_manifest(
    rows: Sequence[BenchmarkRow],
    *,
    source_path: Path,
    source_sha256: str,
) -> dict[str, Any]:
    lane_counts = _count_values([row.lane for row in rows])
    return {
        "schema_version": SCHEMA_VERSION,
        "row_count": len(rows),
        "lane_counts": lane_counts,
        "repo_remotes": sorted({row.repo_remote for row in rows}),
        "item_ids": [row.item_id for row in rows],
        "index_sha256": rows_sha256(rows),
        "source_path": str(source_path),
        "source_sha256": source_sha256,
    }


def build_split_manifest(
    *,
    all_rows: Sequence[BenchmarkRow],
    public_dev: Sequence[BenchmarkRow],
    heldout_test: Sequence[BenchmarkRow],
    seed: int,
    heldout_fraction: float,
    index_path: Path,
    index_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "heldout_fraction": heldout_fraction,
        "index_path": str(index_path),
        "index_sha256": index_sha256,
        "row_count": len(all_rows),
        "public_dev_count": len(public_dev),
        "heldout_test_count": len(heldout_test),
        "public_dev_sha256": rows_sha256(public_dev) if public_dev else None,
        "heldout_test_sha256": rows_sha256(heldout_test) if heldout_test else None,
        "public_dev_item_ids": [row.item_id for row in public_dev],
        "heldout_test_item_ids": [row.item_id for row in heldout_test],
    }


def _canonical_row(row: BenchmarkRow) -> dict[str, Any]:
    return {
        "schema_version": row.raw["schema_version"],
        "item_id": row.item_id,
        "task_id": row.task_id,
        "lane": row.lane,
        "repo_remote": row.repo_remote,
        "repo_commit": row.repo_commit,
        "task_statement": row.task_statement,
        "source_refs": list(row.source_refs),
        "target_paths": list(row.target_paths),
        "acceptance_command": list(row.acceptance_command),
        "acceptance_cwd": row.acceptance_cwd,
        "timeout_seconds": row.timeout_seconds,
        "required_capabilities": list(row.required_capabilities),
        "required_env": dict(row.required_env),
        "metadata": dict(row.metadata),
    }


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
            continue
        seen.add(value)
    return list(duplicates)


def _split_digest(*, seed: int, item_id: str) -> str:
    return _sha256_text(f"{seed}:{item_id}")


def _count_values(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
