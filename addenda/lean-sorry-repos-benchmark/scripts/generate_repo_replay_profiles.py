from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from lean_sorry_repos_benchmark.data import load_rows  # noqa: E402


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "profile"


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate repo replay profile config from benchmark rows.",
    )
    parser.add_argument("--index", required=True, type=Path, help="Input index JSONL.")
    parser.add_argument("--out", required=True, type=Path, help="Output profile config JSON path.")
    parser.add_argument(
        "--group-by",
        choices=["repo_remote", "repo_remote_and_lean_version"],
        default="repo_remote_and_lean_version",
        help="Grouping key for profile generation.",
    )
    parser.add_argument("--lean-cmd", default="lake env lean")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--cold-start-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--git-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--prepare-cmd", default="lake build")
    parser.add_argument("--prepare-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--max-error-chars", type=int, default=400)
    return parser.parse_args(argv)


def _build_profile_id(
    *,
    repo_remote: str,
    repo_lean_version: str | None,
    used_ids: set[str],
) -> str:
    remote_slug = _slug(repo_remote.removesuffix(".git").split("/")[-1])
    if repo_lean_version is None:
        base = f"{remote_slug}-default"
    else:
        base = f"{remote_slug}-{_slug(repo_lean_version)}"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    rows = load_rows(args.index)
    if not rows:
        raise SystemExit("no rows found")

    if args.group_by == "repo_remote_and_lean_version":
        by_remote_versions: dict[str, set[str | None]] = {}
        for row in rows:
            by_remote_versions.setdefault(row.repo_remote, set()).add(row.repo_lean_version)
        mixed = [
            remote
            for remote, versions in by_remote_versions.items()
            if None in versions and len(versions) > 1
        ]
        if mixed:
            preview = ", ".join(sorted(mixed)[:5])
            more = f" (+{len(mixed) - 5} more)" if len(mixed) > 5 else ""
            raise SystemExit(
                "cannot group by repo_remote_and_lean_version when a repo mixes missing and "
                f"present lean versions: {preview}{more}"
            )

    grouped: dict[tuple[str, str | None], int] = Counter()
    for row in rows:
        lean_key = (
            row.repo_lean_version
            if args.group_by == "repo_remote_and_lean_version"
            else None
        )
        grouped[(row.repo_remote, lean_key)] += 1

    used_ids: set[str] = set()
    profiles: list[dict[str, object]] = []
    for (repo_remote, repo_lean_version), count in sorted(grouped.items()):
        profile_id = _build_profile_id(
            repo_remote=repo_remote,
            repo_lean_version=repo_lean_version,
            used_ids=used_ids,
        )
        match: dict[str, str] = {"repo_remote": repo_remote}
        if repo_lean_version is not None:
            match["repo_lean_version"] = repo_lean_version
        prepare_cmd = args.prepare_cmd.strip() or None
        profile = {
            "id": profile_id,
            "match": match,
            "overrides": {
                "lean_cmd": args.lean_cmd,
                "timeout_seconds": args.timeout_seconds,
                "cold_start_timeout_seconds": args.cold_start_timeout_seconds,
                "git_timeout_seconds": args.git_timeout_seconds,
                "prepare_cmd": prepare_cmd,
                "prepare_timeout_seconds": args.prepare_timeout_seconds,
                "max_error_chars": args.max_error_chars,
            },
            "row_count": count,
        }
        profiles.append(profile)

    payload = {
        "schema_version": 1,
        "profiles": [
            {"id": p["id"], "match": p["match"], "overrides": p["overrides"]}
            for p in profiles
        ],
        "metadata": {
            "generated_from_index": str(args.index),
            "group_by": args.group_by,
            "row_count": len(rows),
            "repo_count": len({row.repo_remote for row in rows}),
            "profile_count": len(profiles),
            "top_profiles_by_rows": [
                {"id": p["id"], "row_count": int(p["row_count"])}
                for p in sorted(
                    profiles,
                    key=lambda item: int(item["row_count"]),
                    reverse=True,
                )[:10]
            ],
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"rows={len(rows)}")
    print(f"repos={len({row.repo_remote for row in rows})}")
    print(f"profiles={len(profiles)}")
    print(f"profile_config={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
