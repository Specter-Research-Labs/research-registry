from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lean_sorry_repos_benchmark import SCHEMA_VERSION
from lean_sorry_repos_benchmark.adapters import (
    MockAdapter,
    OllamaAdapter,
    OpenAIAdapter,
    classify_generation_error,
    generation_error_domain,
)
from lean_sorry_repos_benchmark.data import BenchmarkRow, load_rows, select_rows, selected_rows_hash
from lean_sorry_repos_benchmark.paths import resolve_artifact_root
from lean_sorry_repos_benchmark.replay import (
    RepoReplayConfig,
    RepoReplayProfileSet,
    RepoReplayVerifier,
    load_repo_replay_profile_set,
    resolve_repo_replay_policy,
)
from lean_sorry_repos_benchmark.scoring import (
    aggregate,
    aggregate_verification_pass_at_k,
    aggregate_verification_pass_at_k_confidence_intervals,
    bootstrap_rate_confidence_interval,
    bounded_pass_at_k_values,
    tactic_contains_sorry,
    tactic_nonempty,
    tactic_valid,
)
from lean_sorry_repos_benchmark.split_artifacts import (
    SplitConfig,
    assert_leak_fraction,
    build_checksum_manifest,
    build_contamination_report,
    build_heldout_commitments,
    build_split_manifest,
    generate_frozen_split,
    index_sha256,
    validate_release_visibility,
    validate_split_config,
    write_rows_jsonl,
)
from lean_sorry_repos_benchmark.verification import (
    SyntheticLeanVerifier,
    SyntheticVerificationConfig,
    VerificationResult,
    verification_error_domain,
)

_RETRY_DOMAINS = {"infra", "model"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_run_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    fallback = root / "artifacts"
    out_root = resolve_artifact_root(fallback)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return out_root / "runs" / f"proposal-{stamp}"


def _build_prompt(goal_text: str) -> str:
    return (
        "You are helping with Lean 4 proof development.\n"
        "Given this proof state, propose exactly one next tactic.\n"
        "Return only the tactic line, no prose.\n\n"
        f"{goal_text}\n"
    )


def _sample_seed(*, base_seed: int, item_id: str, sample_index: int) -> int:
    payload = f"{base_seed}:{item_id}:{sample_index}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) % 2_147_483_647


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _confidence_level(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a float in (0,1)") from exc
    if parsed <= 0.0 or parsed >= 1.0:
        raise argparse.ArgumentTypeError("value must be in (0,1)")
    return parsed


def _parse_csv_tokens(value: str, *, field: str) -> list[str]:
    tokens = [token.strip().lower() for token in value.split(",") if token.strip()]
    if not tokens:
        raise ValueError(f"{field} must include at least one value")
    return tokens


def _parse_retry_domains(value: str) -> set[str]:
    domains: set[str] = set()
    for token in _parse_csv_tokens(value, field="--generation-retry-domains"):
        if token == "all":
            domains.update(_RETRY_DOMAINS)
            continue
        if token not in _RETRY_DOMAINS:
            allowed = ", ".join(sorted([*_RETRY_DOMAINS, "all"]))
            raise ValueError(
                f"--generation-retry-domains includes unsupported value {token!r}; "
                f"expected one of: {allowed}"
            )
        domains.add(token)
    return domains


def _parse_retry_kinds(value: str) -> set[str] | None:
    if not value.strip():
        return None
    return set(_parse_csv_tokens(value, field="--generation-retry-kinds"))


def _sorted_domain_counts(counts: dict[str, int]) -> dict[str, int]:
    return {domain: int(counts.get(domain, 0)) for domain in sorted(_RETRY_DOMAINS)}


def _sorted_domain_kind_counts(
    counts: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    return {
        domain: dict(sorted(counts.get(domain, {}).items()))
        for domain in sorted(_RETRY_DOMAINS)
    }


def _increment_counter(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _increment_domain_kind_counter(
    *,
    counter: dict[str, dict[str, int]],
    domain: str,
    kind: str,
) -> None:
    bucket = counter.setdefault(domain, {})
    bucket[kind] = bucket.get(kind, 0) + 1


def _should_retry_generation_error(
    *,
    retry_count: int,
    error_kind: str | None,
    error_domain: str | None,
    retry_domains: set[str],
    retry_kinds: set[str] | None,
) -> bool:
    if retry_count <= 0:
        return False
    if error_kind is None or error_domain is None:
        return False
    if error_domain not in retry_domains:
        return False
    if retry_kinds is None:
        return True
    return error_kind in retry_kinds


def _release_readiness(
    *,
    selected_items: int,
    selected_samples: int,
    min_selected_items: int,
    min_selected_samples: int,
) -> dict[str, Any]:
    selected_items_ready = selected_items >= min_selected_items
    selected_samples_ready = selected_samples >= min_selected_samples
    ready = selected_items_ready and selected_samples_ready
    failed_requirements: list[str] = []
    if not selected_items_ready:
        failed_requirements.append(
            "selected_items_below_minimum:"
            f" {selected_items} < {min_selected_items}"
        )
    if not selected_samples_ready:
        failed_requirements.append(
            "selected_samples_below_minimum:"
            f" {selected_samples} < {min_selected_samples}"
        )
    return {
        "ready": ready,
        "selected_items_ready": selected_items_ready,
        "selected_samples_ready": selected_samples_ready,
        "failed_requirements": failed_requirements,
    }


def _select_rows_for_shard(
    rows: list[BenchmarkRow],
    *,
    shard_count: int,
    shard_index: int,
) -> list[BenchmarkRow]:
    if shard_count == 1:
        return rows
    selected: list[BenchmarkRow] = []
    for row in rows:
        digest = hashlib.sha256(row.item_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:16], 16) % shard_count
        if bucket == shard_index:
            selected.append(row)
    return selected


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--index", required=True, type=Path, help="Path to benchmark index JSONL.")
    parser.add_argument(
        "--adapter",
        choices=["mock", "ollama", "openai"],
        default="mock",
        help="Inference adapter.",
    )
    parser.add_argument("--model", default="mock-v1", help="Model identifier.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output run directory (default routes via SPECTER_ARTIFACT_ROOT or local artifacts/).",
    )
    parser.add_argument(
        "--split-policy",
        choices=["all", "repo_holdout"],
        default="all",
        help="Subset selection policy.",
    )
    parser.add_argument("--repo-holdout-fraction", type=float, default=0.2)
    parser.add_argument(
        "--goal-slice",
        choices=["all", "core_easy", "non_core_easy"],
        default="all",
        help="Goal difficulty slice filter.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument(
        "--shard-count",
        type=_non_negative_int,
        default=1,
        help="Number of deterministic item-id shards to partition selected rows into.",
    )
    parser.add_argument(
        "--shard-index",
        type=_non_negative_int,
        default=0,
        help="0-based shard index selected from --shard-count shards.",
    )
    parser.add_argument(
        "--samples-per-item",
        type=int,
        default=1,
        help="Number of inference samples generated per selected item.",
    )
    parser.add_argument(
        "--generation-retry-count",
        type=_non_negative_int,
        default=0,
        help="Number of retries after a generation error.",
    )
    parser.add_argument(
        "--generation-retry-domains",
        default="infra",
        help=(
            "Comma-separated generation error domains eligible for retry "
            "(infra, model, all)."
        ),
    )
    parser.add_argument(
        "--generation-retry-kinds",
        default="",
        help=(
            "Comma-separated generation error kinds eligible for retry. "
            "Empty means all kinds within --generation-retry-domains."
        ),
    )
    parser.add_argument(
        "--pass-at-k",
        type=int,
        nargs="+",
        default=[1, 5, 10],
        help="Verification pass@k list; values are clamped to --samples-per-item.",
    )
    parser.add_argument(
        "--bootstrap-iters",
        type=_non_negative_int,
        default=2000,
        help="Bootstrap iterations for confidence intervals; 0 disables resampling.",
    )
    parser.add_argument(
        "--bootstrap-confidence-level",
        type=_confidence_level,
        default=0.95,
        help="Confidence level for bootstrap confidence intervals.",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=None,
        help="Bootstrap seed (default reuses --seed).",
    )
    parser.add_argument(
        "--min-release-selected-items",
        type=_non_negative_int,
        default=0,
        help="Minimum selected items required for release reporting readiness.",
    )
    parser.add_argument(
        "--min-release-selected-samples",
        type=_non_negative_int,
        default=0,
        help="Minimum selected samples required for release reporting readiness.",
    )
    parser.add_argument("--max-tactic-chars", type=int, default=120)
    parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--ollama-temperature", type=float, default=0.0)
    parser.add_argument("--ollama-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--ollama-num-predict", type=int, default=64)
    parser.add_argument(
        "--openai-endpoint",
        default="https://api.openai.com/v1/chat/completions",
        help="OpenAI-compatible chat completions endpoint URL.",
    )
    parser.add_argument(
        "--openai-api-key",
        default=None,
        help="OpenAI-compatible API key (prefer env var over CLI argument).",
    )
    parser.add_argument(
        "--openai-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable name used when --openai-api-key is unset.",
    )
    parser.add_argument("--openai-temperature", type=float, default=0.0)
    parser.add_argument("--openai-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--openai-max-tokens", type=int, default=64)
    parser.add_argument(
        "--openai-organization",
        default=None,
        help="Optional OpenAI organization header value.",
    )
    parser.add_argument(
        "--verification-mode",
        choices=["none", "synthetic", "repo_replay"],
        default="none",
        help="Verification strategy for generated tactics.",
    )
    parser.add_argument(
        "--lean-cmd",
        default="lean",
        help="Lean command used by synthetic verification (supports shell-style tokens).",
    )
    parser.add_argument(
        "--lean-timeout-seconds",
        type=float,
        default=20.0,
        help="Wall-clock timeout per Lean verification attempt.",
    )
    parser.add_argument(
        "--lean-error-kind",
        default="warning",
        help="Lean message kind promoted to error during verification (empty to disable).",
    )
    parser.add_argument(
        "--lean-import",
        action="append",
        default=[],
        help="Module imported in synthetic verification script (repeatable).",
    )
    parser.add_argument(
        "--lean-workdir",
        type=Path,
        default=None,
        help="Working directory used to run Lean verification command.",
    )
    parser.add_argument(
        "--repo-replay-cache-dir",
        type=Path,
        default=None,
        help="Repository cache directory for replay verification.",
    )
    parser.add_argument(
        "--repo-replay-lean-cmd",
        default="lake env lean",
        help="Lean invocation command for replay verification.",
    )
    parser.add_argument(
        "--repo-replay-timeout-seconds",
        type=float,
        default=120.0,
        help="Timeout for replay Lean command per attempt.",
    )
    parser.add_argument(
        "--repo-replay-cold-start-timeout-seconds",
        type=float,
        default=240.0,
        help="Timeout for first replay Lean invocation per repo@commit.",
    )
    parser.add_argument(
        "--repo-replay-git-timeout-seconds",
        type=float,
        default=180.0,
        help="Timeout for git clone/fetch/checkout operations.",
    )
    parser.add_argument(
        "--repo-replay-prepare-cmd",
        default="lake build",
        help="Preparation command run once per repo@commit (set empty string to disable).",
    )
    parser.add_argument(
        "--repo-replay-prepare-timeout-seconds",
        type=float,
        default=900.0,
        help="Timeout for replay preparation command.",
    )
    parser.add_argument(
        "--repo-replay-profile-config",
        type=Path,
        default=None,
        help="Optional JSON config defining per-repo replay profiles.",
    )
    parser.add_argument(
        "--repo-replay-profile-strict",
        action="store_true",
        help="Fail if a selected row does not match exactly one replay profile.",
    )


def _add_split_artifacts_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--index", required=True, type=Path, help="Path to input index JSONL.")
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory for split artifacts and manifests.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Seed used in repo holdout hashing.")
    parser.add_argument(
        "--repo-holdout-fraction",
        type=float,
        default=0.2,
        help="Fraction of repos assigned to heldout_test using hash(seed, repo_remote).",
    )
    parser.add_argument(
        "--near-dup-jaccard-threshold",
        type=float,
        default=0.9,
        help="Normalized token Jaccard threshold for near-duplicate leakage detection.",
    )
    parser.add_argument(
        "--max-leak-fraction",
        type=float,
        default=0.0,
        help="Fail if contaminated heldout_test fraction exceeds this value.",
    )
    parser.add_argument(
        "--license-policy",
        choices=["any", "open_only"],
        default="any",
        help="Row filtering policy by repo license openness.",
    )
    parser.add_argument(
        "--char-ngram-jaccard-threshold",
        type=float,
        default=0.85,
        help="Character n-gram Jaccard threshold for leakage detection.",
    )
    parser.add_argument(
        "--release-visibility",
        choices=["full", "public"],
        default="full",
        help="Artifact release mode; public omits heldout_test content.",
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lean-sorry-repos-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the Lean sorry proposal benchmark.",
        description="Run a local-model proposal benchmark over Lean sorry goal states.",
    )
    _add_run_args(run_parser)

    split_parser = subparsers.add_parser(
        "split-artifacts",
        help="Generate frozen public_dev/heldout_test split artifacts.",
        description="Generate frozen public_dev/heldout_test split artifacts from an index.jsonl.",
    )
    _add_split_artifacts_args(split_parser)
    return parser.parse_args(argv)


def split_artifacts_main(args: argparse.Namespace) -> int:
    config = SplitConfig(
        seed=args.seed,
        repo_holdout_fraction=args.repo_holdout_fraction,
        near_dup_jaccard_threshold=args.near_dup_jaccard_threshold,
        max_leak_fraction=args.max_leak_fraction,
        license_policy=args.license_policy,
        char_ngram_jaccard_threshold=args.char_ngram_jaccard_threshold,
    )
    validate_split_config(config)
    validate_release_visibility(args.release_visibility)

    rows = load_rows(args.index)
    split = generate_frozen_split(rows, config=config)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    public_dev_path = out_dir / "public_dev.jsonl"
    heldout_test_path = out_dir / "heldout_test.jsonl"
    heldout_commitments_path = out_dir / "heldout_test_commitments.json"
    report_path = out_dir / "contamination_report.json"
    manifest_path = out_dir / "split_manifest.json"
    checksums_path = out_dir / "artifact_checksums.json"

    write_rows_jsonl(public_dev_path, split.public_dev)
    if args.release_visibility == "full":
        write_rows_jsonl(heldout_test_path, split.heldout_test)

    source_sha256 = index_sha256(args.index)
    heldout_commitments = build_heldout_commitments(split)
    heldout_commitments_path.write_text(
        json.dumps(heldout_commitments, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    contamination_report = build_contamination_report(
        index_path=args.index,
        source_sha256=source_sha256,
        config=config,
        split=split,
        release_visibility=args.release_visibility,
    )
    split_manifest = build_split_manifest(
        index_path=args.index,
        source_sha256=source_sha256,
        config=config,
        split=split,
        release_visibility=args.release_visibility,
    )
    report_path.write_text(
        json.dumps(contamination_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(split_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_files = [public_dev_path, heldout_commitments_path, manifest_path, report_path]
    if args.release_visibility == "full":
        artifact_files.append(heldout_test_path)
    checksum_manifest = build_checksum_manifest(root_dir=out_dir, files=artifact_files)
    checksums_path.write_text(
        json.dumps(checksum_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    try:
        assert_leak_fraction(split, max_leak_fraction=config.max_leak_fraction)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"public_dev_rows={len(split.public_dev)}")
    print(f"heldout_test_rows={len(split.heldout_test)}")
    print(f"dropped_contaminated_test_rows={len(split.dropped_test_item_ids)}")
    print(f"leak_fraction={split.leak_fraction:.6f}")
    print(f"public_dev={public_dev_path}")
    if args.release_visibility == "full":
        print(f"heldout_test={heldout_test_path}")
    else:
        print("heldout_test=omitted (release_visibility=public)")
    print(f"heldout_test_commitments={heldout_commitments_path}")
    print(f"split_manifest={manifest_path}")
    print(f"contamination_report={report_path}")
    print(f"artifact_checksums={checksums_path}")
    return 0


def _run_main(args: argparse.Namespace) -> int:
    if args.shard_count <= 0:
        raise SystemExit("--shard-count must be >= 1")
    if args.shard_index >= args.shard_count:
        raise SystemExit("--shard-index must be in [0, --shard-count)")
    try:
        generation_retry_domains = _parse_retry_domains(args.generation_retry_domains)
        generation_retry_kinds = _parse_retry_kinds(args.generation_retry_kinds)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        pass_at_k_values = bounded_pass_at_k_values(
            configured_values=args.pass_at_k,
            samples_per_item=args.samples_per_item,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    rows = load_rows(args.index)
    unsharded = select_rows(
        rows,
        split_policy=args.split_policy,
        seed=args.seed,
        repo_holdout_fraction=args.repo_holdout_fraction,
        goal_slice=args.goal_slice,
        max_items=args.max_items,
    )
    selected = _select_rows_for_shard(
        unsharded,
        shard_count=args.shard_count,
        shard_index=args.shard_index,
    )
    if not selected:
        if args.shard_count > 1:
            raise SystemExit(
                "No rows selected after shard filtering; adjust --shard-count/--shard-index "
                "or selection config."
            )
        raise SystemExit("No rows selected; adjust split/max-items configuration.")
    bootstrap_seed = args.seed if args.bootstrap_seed is None else args.bootstrap_seed
    selected_rows_pre_shard = len(unsharded)
    selected_item_count = len(selected)
    selected_sample_count = selected_item_count * args.samples_per_item
    release_readiness = _release_readiness(
        selected_items=selected_item_count,
        selected_samples=selected_sample_count,
        min_selected_items=args.min_release_selected_items,
        min_selected_samples=args.min_release_selected_samples,
    )

    if args.adapter == "mock":
        adapter = MockAdapter(model=args.model)
    elif args.adapter == "ollama":
        adapter = OllamaAdapter(
            model=args.model,
            endpoint=args.ollama_endpoint,
            temperature=args.ollama_temperature,
            timeout_seconds=args.ollama_timeout_seconds,
            num_predict=args.ollama_num_predict,
        )
    else:
        env_name = args.openai_api_key_env.strip()
        api_key = args.openai_api_key
        if api_key is None:
            api_key = os.getenv(env_name, "") if env_name else ""
        api_key = api_key.strip()
        if not api_key:
            source = (
                f"--openai-api-key or env var {env_name}"
                if env_name
                else "--openai-api-key"
            )
            raise SystemExit(f"Missing API key for --adapter openai; provide {source}.")
        adapter = OpenAIAdapter(
            model=args.model,
            endpoint=args.openai_endpoint,
            api_key=api_key,
            temperature=args.openai_temperature,
            timeout_seconds=args.openai_timeout_seconds,
            max_tokens=args.openai_max_tokens,
            organization=args.openai_organization,
        )

    verifier: SyntheticLeanVerifier | None = None
    replay_profile_set: RepoReplayProfileSet | None = None
    replay_verifiers: dict[str, RepoReplayVerifier] = {}
    replay_verifier_rows: dict[str, list[BenchmarkRow]] = {}
    replay_profile_id_by_item: dict[str, str | None] = {}
    replay_verifier_key_by_item: dict[str, str] = {}
    replay_profile_match_counts: dict[str, int] = {}
    replay_preflight_repo_targets = 0
    replay_preflight_profile_targets = 0
    replay_profile_config_path: str | None = None
    if args.verification_mode == "synthetic":
        verifier = SyntheticLeanVerifier(
            SyntheticVerificationConfig(
                lean_cmd=args.lean_cmd,
                timeout_seconds=args.lean_timeout_seconds,
                imports=tuple(args.lean_import),
                error_kind=args.lean_error_kind.strip() or None,
                workdir=args.lean_workdir,
            )
        )
    elif args.verification_mode == "repo_replay":
        root = Path(__file__).resolve().parents[1]
        default_cache_dir = root / "artifacts" / "repo-replay-cache"
        replay_cache_dir = args.repo_replay_cache_dir or default_cache_dir
        prepare_cmd = args.repo_replay_prepare_cmd.strip() or None
        base_replay_config = RepoReplayConfig(
            cache_dir=replay_cache_dir,
            lean_cmd=args.repo_replay_lean_cmd,
            timeout_seconds=args.repo_replay_timeout_seconds,
            cold_start_timeout_seconds=args.repo_replay_cold_start_timeout_seconds,
            git_timeout_seconds=args.repo_replay_git_timeout_seconds,
            prepare_cmd=prepare_cmd,
            prepare_timeout_seconds=args.repo_replay_prepare_timeout_seconds,
        )
        if args.repo_replay_profile_config is not None:
            try:
                replay_profile_set = load_repo_replay_profile_set(args.repo_replay_profile_config)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            replay_profile_config_path = str(args.repo_replay_profile_config)
        for row in selected:
            try:
                resolved = resolve_repo_replay_policy(
                    row=row,
                    base_config=base_replay_config,
                    profile_set=replay_profile_set,
                    strict=args.repo_replay_profile_strict,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            profile_id = resolved.profile_id
            profile_label = profile_id if profile_id is not None else "default"
            replay_profile_match_counts[profile_label] = (
                replay_profile_match_counts.get(profile_label, 0) + 1
            )
            verifier_key = (
                "__default__" if profile_id is None else f"profile:{resolved.profile_id}"
            )
            replay_profile_id_by_item[row.item_id] = profile_id
            replay_verifier_key_by_item[row.item_id] = verifier_key
            replay_verifier_rows.setdefault(verifier_key, []).append(row)
            if verifier_key not in replay_verifiers:
                replay_verifiers[verifier_key] = RepoReplayVerifier(resolved.config)

        replay_preflight_repo_targets = len(
            {(row.repo_remote, row.repo_commit) for row in selected}
        )
        replay_preflight_profile_targets = len(
            {
                (replay_verifier_key_by_item[row.item_id], row.repo_remote, row.repo_commit)
                for row in selected
            }
        )
        preflight_failures: list[tuple[str | None, str, str, str]] = []
        for verifier_key, replay_verifier in replay_verifiers.items():
            preflight_errors = replay_verifier.prepare_rows(replay_verifier_rows[verifier_key])
            profile_id = (
                None
                if verifier_key == "__default__"
                else verifier_key.removeprefix("profile:")
            )
            for (remote, commit), error in preflight_errors.items():
                preflight_failures.append((profile_id, remote, commit, error))
        if preflight_failures:
            failures = sorted(
                preflight_failures,
                key=lambda item: (item[1], item[2], item[0] or ""),
            )

            def _preview_line(item: tuple[str | None, str, str, str]) -> str:
                profile_id, remote, commit, error = item
                prefix = (
                    f"[profile={profile_id}] "
                    if profile_id is not None
                    else "[profile=default] "
                )
                return f"{prefix}{remote}@{commit}: {error}"

            preview = [_preview_line(item) for item in failures[:3]]
            more = f"\n... and {len(failures) - 3} more" if len(failures) > 3 else ""
            raise SystemExit(
                "Repo replay preflight failed for "
                f"{len(failures)} repo@commit targets:\n"
                + "\n".join(preview)
                + more
            )

    out_dir = args.out_dir if args.out_dir is not None else _default_run_dir()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise SystemExit(
            f"Cannot create out-dir: {out_dir}\n"
            "Use --out-dir to point to a writable location, or fix SPECTER_ARTIFACT_ROOT."
        ) from exc
    attempts_path = out_dir / "attempts.jsonl"
    summary_path = out_dir / "summary.json"

    generation_error_count = 0
    generation_error_kinds: dict[str, int] = {}
    generation_error_domains: dict[str, int] = {}
    generation_error_kinds_by_domain: dict[str, dict[str, int]] = {}
    generation_observed_error_count = 0
    generation_observed_error_kinds: dict[str, int] = {}
    generation_observed_error_domains: dict[str, int] = {}
    generation_observed_error_kinds_by_domain: dict[str, dict[str, int]] = {}
    generation_retry_attempt_count = 0
    generation_retry_success_count = 0
    generation_retry_exhausted_count = 0
    generation_retry_attempted_domains: dict[str, int] = {}
    generation_retry_attempted_kinds: dict[str, int] = {}
    nonempty_count = 0
    valid_count = 0
    contains_sorry_count = 0
    latencies_ms: list[int] = []
    verification_attempted_count = 0
    verification_success_count = 0
    verification_error_count = 0
    verification_latencies_ms: list[int] = []
    verification_error_kinds: dict[str, int] = {}
    verification_error_domains: dict[str, int] = {}
    verification_error_kinds_by_domain: dict[str, dict[str, int]] = {}
    verification_success_by_item: list[list[bool]] = []
    verification_success_total_outcomes: list[bool] = []
    verification_success_attempted_outcomes: list[bool] = []

    with attempts_path.open("w", encoding="utf-8") as handle:
        for row in selected:
            prompt = _build_prompt(row.goal_text)
            prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            item_verification_success: list[bool] = []
            for sample_index in range(args.samples_per_item):
                sample_seed = _sample_seed(
                    base_seed=args.seed,
                    item_id=row.item_id,
                    sample_index=sample_index,
                )
                generation_error_kind: str | None = None
                generation_error_domain_value: str | None = None
                generation_attempt_count = 0
                generation_retry_count = 0
                generation_total_latency_ms = 0
                result = adapter.infer(
                    row,
                    prompt,
                    sample_index=sample_index,
                    sample_seed=sample_seed,
                )
                while True:
                    generation_attempt_count += 1
                    generation_total_latency_ms += result.latency_ms
                    generation_error_kind = None
                    generation_error_domain_value = None
                    if result.error is not None:
                        generation_error_kind = classify_generation_error(result.error)
                        generation_error_domain_value = generation_error_domain(
                            generation_error_kind
                        )
                        generation_observed_error_count += 1
                        _increment_counter(generation_observed_error_kinds, generation_error_kind)
                        _increment_counter(
                            generation_observed_error_domains,
                            generation_error_domain_value,
                        )
                        _increment_domain_kind_counter(
                            counter=generation_observed_error_kinds_by_domain,
                            domain=generation_error_domain_value,
                            kind=generation_error_kind,
                        )
                        should_retry = _should_retry_generation_error(
                            retry_count=args.generation_retry_count - generation_retry_count,
                            error_kind=generation_error_kind,
                            error_domain=generation_error_domain_value,
                            retry_domains=generation_retry_domains,
                            retry_kinds=generation_retry_kinds,
                        )
                        if should_retry:
                            generation_retry_count += 1
                            generation_retry_attempt_count += 1
                            _increment_counter(
                                generation_retry_attempted_domains,
                                generation_error_domain_value,
                            )
                            _increment_counter(
                                generation_retry_attempted_kinds,
                                generation_error_kind,
                            )
                            result = adapter.infer(
                                row,
                                prompt,
                                sample_index=sample_index,
                                sample_seed=sample_seed,
                            )
                            continue
                    break

                generation_recovered_after_retry = (
                    generation_retry_count > 0 and result.error is None
                )
                if generation_recovered_after_retry:
                    generation_retry_success_count += 1
                elif generation_retry_count > 0:
                    generation_retry_exhausted_count += 1

                nonempty = tactic_nonempty(result.tactic)
                contains_sorry = tactic_contains_sorry(result.tactic)
                valid = tactic_valid(result.tactic, max_chars=args.max_tactic_chars)
                if result.error is not None:
                    generation_error_count += 1
                    if generation_error_kind is None or generation_error_domain_value is None:
                        raise RuntimeError("error classification missing for non-null error")
                    _increment_counter(generation_error_kinds, generation_error_kind)
                    _increment_counter(generation_error_domains, generation_error_domain_value)
                    _increment_domain_kind_counter(
                        counter=generation_error_kinds_by_domain,
                        domain=generation_error_domain_value,
                        kind=generation_error_kind,
                    )
                if nonempty:
                    nonempty_count += 1
                if contains_sorry:
                    contains_sorry_count += 1
                if valid:
                    valid_count += 1
                latencies_ms.append(result.latency_ms)

                verification = VerificationResult(
                    attempted=False,
                    success=False,
                    error=None,
                    error_kind=None,
                    exit_code=None,
                    latency_ms=0,
                )
                should_verify = result.error is None and nonempty and not contains_sorry
                if should_verify:
                    if verifier is not None:
                        verification = verifier.verify(
                            goal_text=row.goal_text,
                            tactic=result.tactic,
                        )
                    elif replay_verifiers:
                        verifier_key = replay_verifier_key_by_item[row.item_id]
                        verification = replay_verifiers[verifier_key].verify(
                            row=row,
                            tactic=result.tactic,
                        )
                verification_success = verification.attempted and verification.success
                item_verification_success.append(verification_success)
                verification_success_total_outcomes.append(verification_success)
                verification_error_domain_value = verification_error_domain(verification.error_kind)
                if verification.attempted:
                    verification_attempted_count += 1
                    verification_success_attempted_outcomes.append(verification.success)
                    verification_latencies_ms.append(verification.latency_ms)
                    if verification.success:
                        verification_success_count += 1
                    elif verification.error is not None:
                        verification_error_count += 1
                        if verification.error_kind is not None:
                            key = verification.error_kind
                            _increment_counter(verification_error_kinds, key)
                        if verification_error_domain_value is not None:
                            _increment_counter(
                                verification_error_domains,
                                verification_error_domain_value,
                            )
                            if verification.error_kind is not None:
                                _increment_domain_kind_counter(
                                    counter=verification_error_kinds_by_domain,
                                    domain=verification_error_domain_value,
                                    kind=verification.error_kind,
                                )

                attempt = {
                    "schema_version": SCHEMA_VERSION,
                    "timestamp": _utc_now(),
                    "adapter": adapter.adapter_name,
                    "model": adapter.model_name,
                    "item_id": row.item_id,
                    "sample_index": sample_index,
                    "sample_seed": sample_seed,
                    "repo_remote": row.repo_remote,
                    "repo_commit": row.repo_commit,
                    "repo_lean_version": row.repo_lean_version,
                    "location_path": row.location_path,
                    "location_start_line": row.location_start_line,
                    "location_start_column": row.location_start_column,
                    "location_end_line": row.location_end_line,
                    "location_end_column": row.location_end_column,
                    "repo_replay_profile_id": (
                        replay_profile_id_by_item.get(row.item_id)
                        if args.verification_mode == "repo_replay"
                        else None
                    ),
                    "source_url": row.source_url,
                    "goal_sha256": row.goal_sha256,
                    "prompt_sha256": prompt_sha,
                    "tactic": result.tactic,
                    "tactic_nonempty": nonempty,
                    "tactic_valid": valid,
                    "tactic_contains_sorry": contains_sorry,
                    "generation_attempt_count": generation_attempt_count,
                    "generation_retry_count": generation_retry_count,
                    "generation_retried": generation_retry_count > 0,
                    "generation_recovered_after_retry": generation_recovered_after_retry,
                    "generation_latency_ms": result.latency_ms,
                    "generation_total_latency_ms": generation_total_latency_ms,
                    "generation_error": result.error,
                    "generation_error_kind": generation_error_kind,
                    "generation_error_domain": generation_error_domain_value,
                    "latency_ms": result.latency_ms,
                    "error": result.error,
                    "error_kind": generation_error_kind,
                    "error_domain": generation_error_domain_value,
                    "verification_mode": args.verification_mode,
                    "verification_attempted": verification.attempted,
                    "verification_success": (
                        verification.success if verification.attempted else None
                    ),
                    "verification_latency_ms": (
                        verification.latency_ms if verification.attempted else None
                    ),
                    "verification_exit_code": verification.exit_code,
                    "verification_error_kind": verification.error_kind,
                    "verification_error_domain": verification_error_domain_value,
                    "verification_error": verification.error,
                    "goal_bucket": row.goal_bucket,
                }
                handle.write(json.dumps(attempt, sort_keys=True) + "\n")
            verification_success_by_item.append(item_verification_success)

    metrics = aggregate(
        generation_error_count=generation_error_count,
        nonempty_count=nonempty_count,
        valid_count=valid_count,
        contains_sorry_count=contains_sorry_count,
        latencies_ms=latencies_ms,
    )
    verification_pass_at_k = aggregate_verification_pass_at_k(
        verification_success_by_item=verification_success_by_item,
        ks=pass_at_k_values,
    )
    verification_pass_at_k_success_count = {
        str(k): int(verification_pass_at_k[k]["success_count"]) for k in pass_at_k_values
    }
    verification_pass_at_k_success_rate = {
        str(k): float(verification_pass_at_k[k]["success_rate"]) for k in pass_at_k_values
    }
    verification_success_rate_total_ci = bootstrap_rate_confidence_interval(
        outcomes=verification_success_total_outcomes,
        seed=bootstrap_seed,
        iters=args.bootstrap_iters,
        confidence_level=args.bootstrap_confidence_level,
    )
    verification_success_rate_attempted_ci = bootstrap_rate_confidence_interval(
        outcomes=verification_success_attempted_outcomes,
        seed=bootstrap_seed + 1,
        iters=args.bootstrap_iters,
        confidence_level=args.bootstrap_confidence_level,
    )
    verification_pass_at_k_success_rate_ci_raw = (
        aggregate_verification_pass_at_k_confidence_intervals(
            verification_success_by_item=verification_success_by_item,
            ks=pass_at_k_values,
            seed=bootstrap_seed + 2,
            iters=args.bootstrap_iters,
            confidence_level=args.bootstrap_confidence_level,
        )
    )
    verification_pass_at_k_success_rate_ci = {
        str(k): verification_pass_at_k_success_rate_ci_raw[k] for k in pass_at_k_values
    }
    selected_core_easy_rows = len([row for row in selected if row.goal_bucket == "core_easy"])
    generation_error_domains_sorted = _sorted_domain_counts(generation_error_domains)
    generation_observed_error_domains_sorted = _sorted_domain_counts(
        generation_observed_error_domains
    )
    verification_error_domains_sorted = _sorted_domain_counts(verification_error_domains)
    generation_error_kinds_by_domain_sorted = _sorted_domain_kind_counts(
        generation_error_kinds_by_domain
    )
    generation_observed_error_kinds_by_domain_sorted = _sorted_domain_kind_counts(
        generation_observed_error_kinds_by_domain
    )
    verification_error_kinds_by_domain_sorted = _sorted_domain_kind_counts(
        verification_error_kinds_by_domain
    )
    verification_attempted_den = max(verification_attempted_count, 1)
    verification_total_den = max(selected_sample_count, 1)
    verification_metrics: dict[str, object] = {
        "verification_attempted_count": verification_attempted_count,
        "verification_attempted_rate": verification_attempted_count / verification_total_den,
        "verification_success_count": verification_success_count,
        "verification_success_rate_total": verification_success_count / verification_total_den,
        "verification_success_rate_attempted": (
            verification_success_count / verification_attempted_den
        ),
        "verification_error_count": verification_error_count,
        "verification_error_rate_attempted": verification_error_count / verification_attempted_den,
        "verification_error_kinds": dict(sorted(verification_error_kinds.items())),
        "verification_error_domains": verification_error_domains_sorted,
        "verification_error_kinds_by_domain": verification_error_kinds_by_domain_sorted,
        "verification_latency_ms_mean": (
            sum(verification_latencies_ms) / len(verification_latencies_ms)
            if verification_latencies_ms
            else 0.0
        ),
        "verification_success_rate_total_ci": verification_success_rate_total_ci,
        "verification_success_rate_attempted_ci": verification_success_rate_attempted_ci,
        "verification_pass_at_k_ks": pass_at_k_values,
        "verification_pass_at_k_success_count": verification_pass_at_k_success_count,
        "verification_pass_at_k_success_rate": verification_pass_at_k_success_rate,
        "verification_pass_at_k_success_rate_ci": verification_pass_at_k_success_rate_ci,
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "benchmark_kind": "goal_to_tactic_proposal_v1",
        "adapter": adapter.adapter_name,
        "model": adapter.model_name,
        "index_path": str(args.index),
        "selected_rows_hash": selected_rows_hash(selected),
        "selection": {
            "split_policy": args.split_policy,
            "repo_holdout_fraction": args.repo_holdout_fraction,
            "goal_slice": args.goal_slice,
            "seed": args.seed,
            "max_items": args.max_items,
            "shard_count": args.shard_count,
            "shard_index": args.shard_index,
            "selected_rows_pre_shard": selected_rows_pre_shard,
            "samples_per_item": args.samples_per_item,
            "selected_rows": selected_item_count,
            "selected_core_easy_rows": selected_core_easy_rows,
        },
        "release_reporting": {
            "min_selected_items_required": args.min_release_selected_items,
            "min_selected_samples_required": args.min_release_selected_samples,
            "selected_items": selected_item_count,
            "selected_samples": selected_sample_count,
            "selected_items_ready": release_readiness["selected_items_ready"],
            "selected_samples_ready": release_readiness["selected_samples_ready"],
            "ready": release_readiness["ready"],
            "failed_requirements": release_readiness["failed_requirements"],
        },
        "runtime_reliability": {
            "generation_retry_policy": {
                "retry_count": args.generation_retry_count,
                "retry_domains": sorted(generation_retry_domains),
                "retry_kinds": (
                    sorted(generation_retry_kinds) if generation_retry_kinds is not None else None
                ),
            },
            "generation_retry_metrics": {
                "retry_attempt_count": generation_retry_attempt_count,
                "retry_success_count": generation_retry_success_count,
                "retry_exhausted_count": generation_retry_exhausted_count,
                "retry_attempted_domains": _sorted_domain_counts(
                    generation_retry_attempted_domains
                ),
                "retry_attempted_kinds": dict(sorted(generation_retry_attempted_kinds.items())),
            },
        },
        "inference": (
            {
                "ollama_endpoint": args.ollama_endpoint,
                "ollama_temperature": args.ollama_temperature,
                "ollama_timeout_seconds": args.ollama_timeout_seconds,
                "ollama_num_predict": args.ollama_num_predict,
            }
            if adapter.adapter_name == "ollama"
            else (
                {
                    "openai_endpoint": args.openai_endpoint,
                    "openai_api_key_env": args.openai_api_key_env,
                    "openai_temperature": args.openai_temperature,
                    "openai_timeout_seconds": args.openai_timeout_seconds,
                    "openai_max_tokens": args.openai_max_tokens,
                    "openai_organization": args.openai_organization,
                }
                if adapter.adapter_name == "openai"
                else {}
            )
        ),
        "verification": {
            "mode": args.verification_mode,
            "lean_cmd": args.lean_cmd if args.verification_mode == "synthetic" else None,
            "lean_timeout_seconds": (
                args.lean_timeout_seconds if args.verification_mode == "synthetic" else None
            ),
            "lean_error_kind": (
                args.lean_error_kind if args.verification_mode == "synthetic" else None
            ),
            "lean_imports": args.lean_import if args.verification_mode == "synthetic" else [],
            "lean_workdir": (
                str(args.lean_workdir)
                if args.verification_mode == "synthetic" and args.lean_workdir is not None
                else None
            ),
            "repo_replay": (
                {
                    "cache_dir": str(
                        args.repo_replay_cache_dir
                        or Path(__file__).resolve().parents[1] / "artifacts" / "repo-replay-cache"
                    ),
                    "lean_cmd": args.repo_replay_lean_cmd,
                    "timeout_seconds": args.repo_replay_timeout_seconds,
                    "cold_start_timeout_seconds": args.repo_replay_cold_start_timeout_seconds,
                    "git_timeout_seconds": args.repo_replay_git_timeout_seconds,
                    "prepare_cmd": args.repo_replay_prepare_cmd.strip() or None,
                    "prepare_timeout_seconds": args.repo_replay_prepare_timeout_seconds,
                    "profile_config_path": replay_profile_config_path,
                    "profile_strict": args.repo_replay_profile_strict,
                    "profile_schema_version": (
                        replay_profile_set.schema_version
                        if replay_profile_set is not None
                        else None
                    ),
                    "profiles_loaded": (
                        [profile.profile_id for profile in replay_profile_set.profiles]
                        if replay_profile_set is not None
                        else []
                    ),
                    "profile_match_counts": dict(sorted(replay_profile_match_counts.items())),
                    "preflight_repo_targets": replay_preflight_repo_targets,
                    "preflight_profile_targets": replay_preflight_profile_targets,
                    "preflight_error_count": 0,
                }
                if args.verification_mode == "repo_replay"
                else None
            ),
            "pass_at_k_requested": args.pass_at_k,
            "pass_at_k_effective": pass_at_k_values,
            "statistical": {
                "method": "bootstrap_percentile",
                "bootstrap_iters": args.bootstrap_iters,
                "confidence_level": args.bootstrap_confidence_level,
                "bootstrap_seed": bootstrap_seed,
            },
            "metrics": verification_metrics,
            "note": (
                "Synthetic verification checks a reconstructed goal script with Lean. "
                "It is stricter than text-only proxies but not equivalent to verifying in each "
                "original repository context."
                if args.verification_mode == "synthetic"
                else (
                    "Repo replay verification checks tactic insertion against source files at "
                    "repo@commit and executes Lean in that repository context."
                    if args.verification_mode == "repo_replay"
                    else "Verification disabled."
                )
            ),
        },
        "scoring": {
            "max_tactic_chars": args.max_tactic_chars,
            "metrics": metrics.as_dict(),
            "generation_error_kinds": dict(sorted(generation_error_kinds.items())),
            "generation_error_domains": generation_error_domains_sorted,
            "generation_error_kinds_by_domain": generation_error_kinds_by_domain_sorted,
            "generation_observed_error_count": generation_observed_error_count,
            "generation_observed_error_kinds": dict(
                sorted(generation_observed_error_kinds.items())
            ),
            "generation_observed_error_domains": generation_observed_error_domains_sorted,
            "generation_observed_error_kinds_by_domain": (
                generation_observed_error_kinds_by_domain_sorted
            ),
            "note": "Proposal-level proxy metrics over raw model outputs.",
        },
        "outputs": {
            "attempts_jsonl": str(attempts_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"adapter={adapter.adapter_name}")
    print(f"model={adapter.model_name}")
    print(f"selected_rows={len(selected)}")
    print(f"attempts={attempts_path}")
    print(f"summary={summary_path}")
    print(f"valid_rate={metrics.as_dict()['valid_rate']:.4f}")
    print(
        "verification_success_rate_attempted="
        f"{verification_metrics['verification_success_rate_attempted']:.4f}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "split-artifacts":
        return split_artifacts_main(args)
    return _run_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
