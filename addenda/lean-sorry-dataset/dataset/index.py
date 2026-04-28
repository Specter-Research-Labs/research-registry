from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from constants import SCHEMA_VERSION

_NOASSERTION = {"", "NONE", "NOASSERTION"}


@dataclass(frozen=True)
class BuildConfig:
    include_goal_text: bool
    resolve_github_license: bool
    require_open_license: bool
    strict: bool
    github_token: str | None = None


@dataclass(frozen=True)
class BuildStats:
    source_sorries: int
    rows_written: int
    rows_invalid: int
    rows_skipped_non_open_license: int
    unique_repos: int
    unique_item_ids: int
    license_lookup_errors: dict[str, str]
    by_lean_version: dict[str, int]
    by_license: dict[str, int]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_snapshot(snapshot: str) -> tuple[dict[str, Any], bytes]:
    if snapshot.startswith("http://") or snapshot.startswith("https://"):
        request = urllib.request.Request(snapshot, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request) as resp:  # noqa: S310 - explicit URLs only
            raw = resp.read()
    else:
        raw = Path(snapshot).read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("snapshot must decode to a JSON object")
    return payload, raw


def extract_sorries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sorries = payload.get("sorries")
    if not isinstance(sorries, list):
        raise ValueError("snapshot missing `sorries` list")
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(sorries):
        if not isinstance(row, dict):
            raise ValueError(f"sorry index {idx} is not a JSON object")
        out.append(row)
    return out


def _coerce_int(raw: Any, field: str, idx: int) -> int:
    if isinstance(raw, int):
        return raw
    raise ValueError(f"invalid `{field}` at index {idx}: expected int")


def _coerce_str(raw: Any, field: str, idx: int) -> str:
    if isinstance(raw, str) and raw:
        return raw
    raise ValueError(f"invalid `{field}` at index {idx}: expected non-empty string")


def _normalise_remote(remote: str) -> str:
    if remote.endswith(".git"):
        return remote[:-4]
    return remote.rstrip("/")


def github_repo_slug(remote: str) -> str | None:
    patterns = [
        r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, remote)
        if match is None:
            continue
        owner = match.group("owner")
        repo = match.group("repo")
        return f"{owner}/{repo}"
    return None


def is_open_license(spdx_id: str | None) -> bool:
    if spdx_id is None:
        return False
    return spdx_id.strip().upper() not in _NOASSERTION


def lookup_repo_license(
    slug: str,
    *,
    github_token: str | None,
) -> tuple[str | None, str | None, str | None]:
    url = f"https://api.github.com/repos/{slug}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return None, None, f"http {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, None, str(exc.reason)
    if not isinstance(payload, dict):
        return None, None, "invalid API payload"
    license_obj = payload.get("license")
    if not isinstance(license_obj, dict):
        return None, None, "license missing"
    spdx_id = license_obj.get("spdx_id")
    if isinstance(spdx_id, str):
        spdx = spdx_id
    else:
        spdx = None
    html_url = payload.get("html_url")
    return spdx, html_url if isinstance(html_url, str) else None, None


def _fallback_source_url(
    *,
    remote: str,
    commit: str,
    path: str,
    start_line: int,
) -> str:
    clean = _normalise_remote(remote)
    quoted_path = urllib.parse.quote(path)
    return f"{clean}/blob/{commit}/{quoted_path}#L{start_line}"


def _item_id(
    *,
    remote: str,
    commit: str,
    path: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
) -> str:
    parts = [
        remote,
        commit,
        path,
        str(start_line),
        str(start_column),
        str(end_line),
        str(end_column),
    ]
    return _sha256_text("\n".join(parts))


def build_index_rows(
    *,
    sorries: list[dict[str, Any]],
    config: BuildConfig,
    license_resolver: Callable[[str], tuple[str | None, str | None, str | None]] | None = None,
) -> tuple[list[dict[str, Any]], BuildStats]:
    rows: list[dict[str, Any]] = []
    rows_invalid = 0
    rows_skipped_non_open_license = 0
    license_lookup_errors: dict[str, str] = {}

    license_cache: dict[str, tuple[str | None, str | None, str | None]] = {}
    resolve = config.resolve_github_license
    resolver = license_resolver
    active_resolver: Callable[[str], tuple[str | None, str | None, str | None]] | None = None
    if resolve:
        if resolver is None:

            def _resolver(slug: str) -> tuple[str | None, str | None, str | None]:
                return lookup_repo_license(slug, github_token=config.github_token)

            active_resolver = _resolver
        else:
            active_resolver = resolver

    for idx, sorry in enumerate(sorries):
        try:
            repo = sorry.get("repo")
            location = sorry.get("location")
            debug_info = sorry.get("debug_info")
            metadata = sorry.get("metadata")
            if not isinstance(repo, dict) or not isinstance(location, dict):
                raise ValueError("missing repo/location object")

            remote_raw = _coerce_str(repo.get("remote"), "repo.remote", idx)
            remote = _normalise_remote(remote_raw)
            branch = _coerce_str(repo.get("branch"), "repo.branch", idx)
            commit = _coerce_str(repo.get("commit"), "repo.commit", idx)
            lean_version = _coerce_str(repo.get("lean_version"), "repo.lean_version", idx)
            path = _coerce_str(location.get("path"), "location.path", idx)
            start_line = _coerce_int(location.get("start_line"), "location.start_line", idx)
            start_column = _coerce_int(location.get("start_column"), "location.start_column", idx)
            end_line = _coerce_int(location.get("end_line"), "location.end_line", idx)
            end_column = _coerce_int(location.get("end_column"), "location.end_column", idx)

            goal_text: str | None = None
            source_url: str | None = None
            if isinstance(debug_info, dict):
                goal = debug_info.get("goal")
                url = debug_info.get("url")
                if isinstance(goal, str):
                    goal_text = goal
                if isinstance(url, str):
                    source_url = url

            blame_email_hash: str | None = None
            blame_date: str | None = None
            inclusion_date: str | None = None
            if isinstance(metadata, dict):
                email_hash = metadata.get("blame_email_hash")
                if isinstance(email_hash, str):
                    blame_email_hash = email_hash
                raw_blame_date = metadata.get("blame_date")
                if isinstance(raw_blame_date, str):
                    blame_date = raw_blame_date
                raw_inclusion_date = metadata.get("inclusion_date")
                if isinstance(raw_inclusion_date, str):
                    inclusion_date = raw_inclusion_date

            repo_slug = github_repo_slug(remote)
            repo_license_spdx: str | None = None
            repo_license_url: str | None = None
            repo_license_open: bool | None = None

            if resolve:
                if repo_slug is None:
                    repo_license_open = None
                else:
                    if repo_slug not in license_cache:
                        if active_resolver is None:
                            raise RuntimeError(
                                "resolver must be set when license resolution is enabled"
                            )
                        license_cache[repo_slug] = active_resolver(repo_slug)
                    spdx_id, repo_html_url, license_error = license_cache[repo_slug]
                    repo_license_spdx = spdx_id
                    repo_license_url = repo_html_url
                    if license_error is not None and repo_slug not in license_lookup_errors:
                        license_lookup_errors[repo_slug] = license_error
                    repo_license_open = is_open_license(spdx_id)
                if config.require_open_license and repo_license_open is not True:
                    rows_skipped_non_open_license += 1
                    continue

            if source_url is None:
                source_url = _fallback_source_url(
                    remote=remote,
                    commit=commit,
                    path=path,
                    start_line=start_line,
                )

            row = {
                "schema_version": SCHEMA_VERSION,
                "item_id": _item_id(
                    remote=remote,
                    commit=commit,
                    path=path,
                    start_line=start_line,
                    start_column=start_column,
                    end_line=end_line,
                    end_column=end_column,
                ),
                "repo_remote": remote,
                "repo_slug": repo_slug,
                "repo_branch": branch,
                "repo_commit": commit,
                "repo_lean_version": lean_version,
                "repo_license_spdx": repo_license_spdx,
                "repo_license_url": repo_license_url,
                "repo_license_open": repo_license_open,
                "location_path": path,
                "location_start_line": start_line,
                "location_start_column": start_column,
                "location_end_line": end_line,
                "location_end_column": end_column,
                "source_url": source_url,
                "goal_sha256": _sha256_text(goal_text) if goal_text is not None else None,
                "goal_text": goal_text if config.include_goal_text else None,
                "blame_email_hash": blame_email_hash,
                "blame_date": blame_date,
                "inclusion_date": inclusion_date,
            }
            rows.append(row)
        except ValueError:
            if config.strict:
                raise
            rows_invalid += 1

    rows.sort(
        key=lambda row: (
            row["repo_remote"],
            row["repo_commit"],
            row["location_path"],
            row["location_start_line"],
            row["location_start_column"],
            row["location_end_line"],
            row["location_end_column"],
        )
    )

    deduped: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for row in rows:
        item_id = row["item_id"]
        if item_id in seen_item_ids:
            continue
        deduped.append(row)
        seen_item_ids.add(item_id)

    by_lean_version: dict[str, int] = {}
    by_license: dict[str, int] = {}
    for row in deduped:
        lean_version = row["repo_lean_version"]
        by_lean_version[lean_version] = by_lean_version.get(lean_version, 0) + 1
        license_key = (
            row["repo_license_spdx"] if row["repo_license_spdx"] is not None else "unresolved"
        )
        by_license[license_key] = by_license.get(license_key, 0) + 1

    stats = BuildStats(
        source_sorries=len(sorries),
        rows_written=len(deduped),
        rows_invalid=rows_invalid,
        rows_skipped_non_open_license=rows_skipped_non_open_license,
        unique_repos=len({row["repo_remote"] for row in deduped}),
        unique_item_ids=len(seen_item_ids),
        license_lookup_errors=license_lookup_errors,
        by_lean_version=dict(sorted(by_lean_version.items())),
        by_license=dict(sorted(by_license.items())),
    )
    return deduped, stats


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_manifest(
    *,
    path: Path,
    source_snapshot: str,
    source_snapshot_sha256: str,
    config: BuildConfig,
    stats: BuildStats,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "source_snapshot": source_snapshot,
        "source_snapshot_sha256": source_snapshot_sha256,
        "config": {
            "include_goal_text": config.include_goal_text,
            "resolve_github_license": config.resolve_github_license,
            "require_open_license": config.require_open_license,
            "strict": config.strict,
        },
        "stats": {
            "source_sorries": stats.source_sorries,
            "rows_written": stats.rows_written,
            "rows_invalid": stats.rows_invalid,
            "rows_skipped_non_open_license": stats.rows_skipped_non_open_license,
            "unique_repos": stats.unique_repos,
            "unique_item_ids": stats.unique_item_ids,
            "by_lean_version": stats.by_lean_version,
            "by_license": stats.by_license,
            "license_lookup_errors": stats.license_lookup_errors,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
