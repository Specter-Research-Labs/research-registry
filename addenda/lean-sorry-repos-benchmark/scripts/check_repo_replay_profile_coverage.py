from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from lean_sorry_repos_benchmark.data import load_rows  # noqa: E402
from lean_sorry_repos_benchmark.paths import resolve_runtime_dir  # noqa: E402
from lean_sorry_repos_benchmark.replay import (  # noqa: E402
    RepoReplayConfig,
    load_repo_replay_profile_set,
    resolve_repo_replay_policy,
)


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether replay profiles cover selected rows under strict matching.",
    )
    parser.add_argument("--index", required=True, type=Path, help="Input index JSONL.")
    parser.add_argument(
        "--profile-config",
        required=True,
        type=Path,
        help="Replay profile config JSON path.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional max number of sorted rows to check.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    rows = load_rows(args.index)
    if args.max_items is not None:
        rows = rows[: args.max_items]
    profile_set = load_repo_replay_profile_set(args.profile_config)
    base_config = RepoReplayConfig(
        cache_dir=resolve_runtime_dir(
            "lean-sorry-replay-profile-coverage",
            Path("/tmp/lean-sorry-replay-profile-coverage"),
        ),
        lean_cmd="lake env lean",
        timeout_seconds=120.0,
        cold_start_timeout_seconds=240.0,
        git_timeout_seconds=180.0,
        prepare_cmd="lake build",
        prepare_timeout_seconds=900.0,
        max_error_chars=400,
    )
    counts: Counter[str] = Counter()
    for row in rows:
        resolved = resolve_repo_replay_policy(
            row=row,
            base_config=base_config,
            profile_set=profile_set,
            strict=True,
        )
        profile_id = resolved.profile_id
        if profile_id is None:
            raise RuntimeError("strict coverage should not resolve to default profile")
        counts[profile_id] += 1
    print(f"checked_rows={len(rows)}")
    print(f"matched_profiles={len(counts)}")
    for profile_id, count in sorted(counts.items()):
        print(f"profile={profile_id} rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
