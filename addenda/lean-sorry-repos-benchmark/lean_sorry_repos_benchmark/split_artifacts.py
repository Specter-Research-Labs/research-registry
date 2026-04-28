from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from lean_sorry_repos_benchmark.data import BenchmarkRow

_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_WHITESPACE_PATTERN = re.compile(r"\s+", flags=re.UNICODE)
_LICENSE_POLICY_VALUES = {"any", "open_only"}
_RELEASE_VISIBILITY_VALUES = {"full", "public"}


@dataclass(frozen=True)
class SplitConfig:
    seed: int
    repo_holdout_fraction: float
    near_dup_jaccard_threshold: float
    max_leak_fraction: float
    license_policy: str = "any"
    char_ngram_jaccard_threshold: float = 0.85
    char_ngram_size: int = 5


@dataclass(frozen=True)
class ExactOverlap:
    test_item_id: str
    dev_item_id: str
    goal_sha256: str


@dataclass(frozen=True)
class NearDuplicateOverlap:
    test_item_id: str
    dev_item_id: str
    jaccard: float


@dataclass(frozen=True)
class CharNgramOverlap:
    test_item_id: str
    dev_item_id: str
    jaccard: float


@dataclass(frozen=True)
class LicenseCounts:
    policy: str
    input_total_rows: int
    input_open_rows: int
    input_non_open_or_unknown_rows: int
    selected_rows_after_policy: int
    excluded_by_policy_rows: int
    selected_open_rows: int
    selected_non_open_or_unknown_rows: int
    public_dev_open_rows: int
    heldout_test_open_rows_before_drop: int
    heldout_test_open_rows_after_drop: int


@dataclass(frozen=True)
class FrozenSplit:
    public_dev: list[BenchmarkRow]
    heldout_test: list[BenchmarkRow]
    heldout_test_before_drop_count: int
    dropped_test_item_ids: list[str]
    exact_overlaps: list[ExactOverlap]
    near_duplicate_overlaps: list[NearDuplicateOverlap]
    char_ngram_overlaps: list[CharNgramOverlap]
    license_counts: LicenseCounts

    @property
    def leak_fraction(self) -> float:
        if self.heldout_test_before_drop_count == 0:
            return 0.0
        return len(self.dropped_test_item_ids) / self.heldout_test_before_drop_count


def validate_split_config(config: SplitConfig) -> None:
    validate_license_policy(config.license_policy)
    _validate_fraction(
        name="repo_holdout_fraction",
        value=config.repo_holdout_fraction,
        min_inclusive=False,
        max_inclusive=False,
    )
    _validate_fraction(
        name="near_dup_jaccard_threshold",
        value=config.near_dup_jaccard_threshold,
        min_inclusive=True,
        max_inclusive=True,
    )
    _validate_fraction(
        name="max_leak_fraction",
        value=config.max_leak_fraction,
        min_inclusive=True,
        max_inclusive=True,
    )
    _validate_fraction(
        name="char_ngram_jaccard_threshold",
        value=config.char_ngram_jaccard_threshold,
        min_inclusive=True,
        max_inclusive=True,
    )
    if config.char_ngram_size <= 0:
        raise ValueError("char_ngram_size must be > 0")


def validate_license_policy(license_policy: str) -> None:
    if license_policy in _LICENSE_POLICY_VALUES:
        return
    choices = ", ".join(sorted(_LICENSE_POLICY_VALUES))
    raise ValueError(f"license_policy must be one of: {choices}")


def validate_release_visibility(release_visibility: str) -> None:
    if release_visibility in _RELEASE_VISIBILITY_VALUES:
        return
    choices = ", ".join(sorted(_RELEASE_VISIBILITY_VALUES))
    raise ValueError(f"release_visibility must be one of: {choices}")


def holdout_score(repo_remote: str, *, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{repo_remote}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def is_heldout_test_repo(repo_remote: str, *, seed: int, repo_holdout_fraction: float) -> bool:
    return holdout_score(repo_remote, seed=seed) < repo_holdout_fraction


def normalized_goal_tokens(goal_text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(goal_text)}


def token_jaccard(left: set[str], right: set[str]) -> float:
    return _set_jaccard(left, right)


def normalized_char_ngrams(goal_text: str, *, n: int) -> set[str]:
    normalized = _WHITESPACE_PATTERN.sub(" ", goal_text.casefold().strip())
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[idx : idx + n] for idx in range(0, len(normalized) - n + 1)}


def char_ngram_jaccard(left: set[str], right: set[str]) -> float:
    return _set_jaccard(left, right)


def _set_jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def generate_frozen_split(rows: Sequence[BenchmarkRow], *, config: SplitConfig) -> FrozenSplit:
    validate_split_config(config)
    ordered_rows = sorted(rows, key=lambda row: row.item_id)
    selected_rows = _apply_license_policy(ordered_rows, license_policy=config.license_policy)

    public_dev_rows: list[BenchmarkRow] = []
    heldout_test_rows_before_drop: list[BenchmarkRow] = []
    for row in selected_rows:
        if is_heldout_test_repo(
            row.repo_remote,
            seed=config.seed,
            repo_holdout_fraction=config.repo_holdout_fraction,
        ):
            heldout_test_rows_before_drop.append(row)
        else:
            public_dev_rows.append(row)

    exact_overlaps, exact_contaminated = _detect_exact_overlaps(
        public_dev_rows,
        heldout_test_rows_before_drop,
    )
    near_overlaps, near_contaminated = _detect_near_duplicate_overlaps(
        public_dev_rows,
        heldout_test_rows_before_drop,
        threshold=config.near_dup_jaccard_threshold,
    )
    char_ngram_overlaps, char_ngram_contaminated = _detect_char_ngram_overlaps(
        public_dev_rows,
        heldout_test_rows_before_drop,
        threshold=config.char_ngram_jaccard_threshold,
        n=config.char_ngram_size,
    )
    contaminated_item_ids = exact_contaminated | near_contaminated | char_ngram_contaminated
    dropped_test_item_ids = sorted(contaminated_item_ids)

    heldout_test_rows = [
        row for row in heldout_test_rows_before_drop if row.item_id not in contaminated_item_ids
    ]
    license_counts = _build_license_counts(
        input_rows=ordered_rows,
        selected_rows=selected_rows,
        public_dev_rows=public_dev_rows,
        heldout_test_rows_before_drop=heldout_test_rows_before_drop,
        heldout_test_rows_after_drop=heldout_test_rows,
        policy=config.license_policy,
    )
    return FrozenSplit(
        public_dev=public_dev_rows,
        heldout_test=heldout_test_rows,
        heldout_test_before_drop_count=len(heldout_test_rows_before_drop),
        dropped_test_item_ids=dropped_test_item_ids,
        exact_overlaps=exact_overlaps,
        near_duplicate_overlaps=near_overlaps,
        char_ngram_overlaps=char_ngram_overlaps,
        license_counts=license_counts,
    )


def assert_leak_fraction(split: FrozenSplit, *, max_leak_fraction: float) -> None:
    _validate_fraction(
        name="max_leak_fraction",
        value=max_leak_fraction,
        min_inclusive=True,
        max_inclusive=True,
    )
    if split.leak_fraction > max_leak_fraction:
        raise ValueError(
            "Leak fraction exceeds threshold: "
            f"leak_fraction={split.leak_fraction:.6f}, "
            f"max_leak_fraction={max_leak_fraction:.6f}, "
            f"contaminated_test_rows={len(split.dropped_test_item_ids)}, "
            f"heldout_test_rows_before_drop={split.heldout_test_before_drop_count}"
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_sha256(index_path: Path) -> str:
    return file_sha256(index_path)


def write_rows_jsonl(path: Path, rows: Sequence[BenchmarkRow]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.raw, sort_keys=True) + "\n")


def build_contamination_report(
    *,
    index_path: Path,
    source_sha256: str,
    config: SplitConfig,
    split: FrozenSplit,
    release_visibility: str = "full",
) -> dict[str, object]:
    validate_release_visibility(release_visibility)
    residual_exact_overlaps, _ = _detect_exact_overlaps(split.public_dev, split.heldout_test)
    residual_near_overlaps, _ = _detect_near_duplicate_overlaps(
        split.public_dev,
        split.heldout_test,
        threshold=config.near_dup_jaccard_threshold,
    )
    residual_char_ngram_overlaps, _ = _detect_char_ngram_overlaps(
        split.public_dev,
        split.heldout_test,
        threshold=config.char_ngram_jaccard_threshold,
        n=config.char_ngram_size,
    )
    exact_overlap_rows = {pair.test_item_id for pair in split.exact_overlaps}
    near_overlap_rows = {pair.test_item_id for pair in split.near_duplicate_overlaps}
    char_ngram_overlap_rows = {pair.test_item_id for pair in split.char_ngram_overlaps}
    residual_overlap_rows = {pair.test_item_id for pair in residual_exact_overlaps}
    residual_overlap_rows.update(pair.test_item_id for pair in residual_near_overlaps)
    residual_overlap_rows.update(pair.test_item_id for pair in residual_char_ngram_overlaps)

    residual_leak_fraction = 0.0
    if split.heldout_test:
        residual_leak_fraction = len(residual_overlap_rows) / len(split.heldout_test)

    return {
        "schema_version": 2,
        "source": {
            "index_path": str(index_path),
            "index_sha256": source_sha256,
        },
        "config": {
            "seed": config.seed,
            "repo_holdout_fraction": config.repo_holdout_fraction,
            "near_dup_jaccard_threshold": config.near_dup_jaccard_threshold,
            "char_ngram_jaccard_threshold": config.char_ngram_jaccard_threshold,
            "char_ngram_size": config.char_ngram_size,
            "license_policy": config.license_policy,
            "max_leak_fraction": config.max_leak_fraction,
        },
        "release": {
            "visibility": release_visibility,
            "includes_heldout_test_content": release_visibility == "full",
        },
        "counts": {
            "public_dev_rows": len(split.public_dev),
            "heldout_test_rows_before_drop": split.heldout_test_before_drop_count,
            "dropped_contaminated_test_rows": len(split.dropped_test_item_ids),
            "heldout_test_rows_after_drop": len(split.heldout_test),
            "exact_overlap_pairs": len(split.exact_overlaps),
            "near_duplicate_pairs": len(split.near_duplicate_overlaps),
            "char_ngram_pairs": len(split.char_ngram_overlaps),
            "exact_overlap_test_rows": len(exact_overlap_rows),
            "near_duplicate_test_rows": len(near_overlap_rows),
            "char_ngram_test_rows": len(char_ngram_overlap_rows),
            "residual_overlap_pairs_exact": len(residual_exact_overlaps),
            "residual_overlap_pairs_near_duplicate": len(residual_near_overlaps),
            "residual_overlap_pairs_char_ngram": len(residual_char_ngram_overlaps),
            "residual_overlap_test_rows": len(residual_overlap_rows),
        },
        "license_counts": _license_counts_payload(split.license_counts),
        "fractions": {
            "leak_fraction": split.leak_fraction,
            "residual_leak_fraction": residual_leak_fraction,
        },
        "dropped_test_item_ids": split.dropped_test_item_ids,
        "exact_overlaps": [
            {
                "test_item_id": pair.test_item_id,
                "dev_item_id": pair.dev_item_id,
                "goal_sha256": pair.goal_sha256,
            }
            for pair in split.exact_overlaps
        ],
        "near_duplicate_overlaps": [
            {
                "test_item_id": pair.test_item_id,
                "dev_item_id": pair.dev_item_id,
                "jaccard": pair.jaccard,
            }
            for pair in split.near_duplicate_overlaps
        ],
        "char_ngram_overlaps": [
            {
                "test_item_id": pair.test_item_id,
                "dev_item_id": pair.dev_item_id,
                "jaccard": pair.jaccard,
            }
            for pair in split.char_ngram_overlaps
        ],
    }


def build_split_manifest(
    *,
    index_path: Path,
    source_sha256: str,
    config: SplitConfig,
    split: FrozenSplit,
    release_visibility: str = "full",
) -> dict[str, object]:
    validate_release_visibility(release_visibility)
    row_hashes: dict[str, list[dict[str, str]]] = {
        "public_dev": _row_hash_items(split.public_dev),
    }
    if release_visibility == "full":
        row_hashes["heldout_test"] = _row_hash_items(split.heldout_test)

    return {
        "schema_version": 2,
        "source": {
            "index_path": str(index_path),
            "index_sha256": source_sha256,
        },
        "config": {
            "seed": config.seed,
            "repo_holdout_fraction": config.repo_holdout_fraction,
            "near_dup_jaccard_threshold": config.near_dup_jaccard_threshold,
            "char_ngram_jaccard_threshold": config.char_ngram_jaccard_threshold,
            "char_ngram_size": config.char_ngram_size,
            "license_policy": config.license_policy,
            "max_leak_fraction": config.max_leak_fraction,
        },
        "release": {
            "visibility": release_visibility,
            "includes_heldout_test_content": release_visibility == "full",
        },
        "counts": {
            "public_dev_rows": len(split.public_dev),
            "heldout_test_rows": len(split.heldout_test),
            "heldout_test_rows_before_drop": split.heldout_test_before_drop_count,
            "dropped_contaminated_test_rows": len(split.dropped_test_item_ids),
            "heldout_test_commitment_count": len(split.heldout_test),
        },
        "license_counts": _license_counts_payload(split.license_counts),
        "heldout_test_commitments": build_heldout_commitments(split),
        "row_hashes": row_hashes,
    }


def build_heldout_commitments(split: FrozenSplit) -> dict[str, object]:
    row_sha256 = sorted(_row_sha256(row) for row in split.heldout_test)
    commitment_payload = "\n".join(row_sha256)
    return {
        "heldout_test_rows_after_drop": len(split.heldout_test),
        "heldout_test_rows_before_drop": split.heldout_test_before_drop_count,
        "dropped_contaminated_test_rows": len(split.dropped_test_item_ids),
        "row_sha256": row_sha256,
        "row_sha256_set_sha256": hashlib.sha256(commitment_payload.encode("utf-8")).hexdigest(),
    }


def build_checksum_manifest(*, root_dir: Path, files: Sequence[Path]) -> dict[str, object]:
    root_resolved = root_dir.resolve()
    file_entries: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for path in files:
        path_resolved = path.resolve()
        try:
            rel = path_resolved.relative_to(root_resolved).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"artifact path must be within root_dir: root_dir={root_dir}, path={path}"
            ) from exc
        if rel in seen_paths:
            continue
        seen_paths.add(rel)
        stat = path.stat()
        file_entries.append(
            {
                "path": rel,
                "sha256": file_sha256(path),
                "size_bytes": stat.st_size,
            }
        )

    file_entries.sort(key=lambda entry: str(entry["path"]))
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "files": file_entries,
    }


def _detect_exact_overlaps(
    dev_rows: Sequence[BenchmarkRow],
    heldout_rows: Sequence[BenchmarkRow],
) -> tuple[list[ExactOverlap], set[str]]:
    dev_rows_by_sha: dict[str, list[BenchmarkRow]] = {}
    for row in dev_rows:
        goal_sha256 = row.goal_sha256
        if goal_sha256 is None:
            continue
        dev_rows_by_sha.setdefault(goal_sha256, []).append(row)

    overlaps: list[ExactOverlap] = []
    contaminated_test_item_ids: set[str] = set()
    for test_row in heldout_rows:
        goal_sha256 = test_row.goal_sha256
        if goal_sha256 is None:
            continue
        for dev_row in dev_rows_by_sha.get(goal_sha256, []):
            overlaps.append(
                ExactOverlap(
                    test_item_id=test_row.item_id,
                    dev_item_id=dev_row.item_id,
                    goal_sha256=goal_sha256,
                )
            )
            contaminated_test_item_ids.add(test_row.item_id)

    overlaps.sort(key=lambda pair: (pair.test_item_id, pair.dev_item_id, pair.goal_sha256))
    return overlaps, contaminated_test_item_ids


def _detect_near_duplicate_overlaps(
    dev_rows: Sequence[BenchmarkRow],
    heldout_rows: Sequence[BenchmarkRow],
    *,
    threshold: float,
) -> tuple[list[NearDuplicateOverlap], set[str]]:
    dev_tokens: list[tuple[BenchmarkRow, set[str]]] = [
        (row, normalized_goal_tokens(row.goal_text)) for row in dev_rows
    ]

    overlaps: list[NearDuplicateOverlap] = []
    contaminated_test_item_ids: set[str] = set()
    for test_row in heldout_rows:
        test_tokens = normalized_goal_tokens(test_row.goal_text)
        for dev_row, dev_goal_tokens in dev_tokens:
            score = token_jaccard(test_tokens, dev_goal_tokens)
            if score < threshold:
                continue
            overlaps.append(
                NearDuplicateOverlap(
                    test_item_id=test_row.item_id,
                    dev_item_id=dev_row.item_id,
                    jaccard=score,
                )
            )
            contaminated_test_item_ids.add(test_row.item_id)

    overlaps.sort(key=lambda pair: (pair.test_item_id, pair.dev_item_id, -pair.jaccard))
    return overlaps, contaminated_test_item_ids


def _detect_char_ngram_overlaps(
    dev_rows: Sequence[BenchmarkRow],
    heldout_rows: Sequence[BenchmarkRow],
    *,
    threshold: float,
    n: int,
) -> tuple[list[CharNgramOverlap], set[str]]:
    dev_char_ngrams: list[tuple[BenchmarkRow, set[str]]] = [
        (row, normalized_char_ngrams(row.goal_text, n=n)) for row in dev_rows
    ]

    overlaps: list[CharNgramOverlap] = []
    contaminated_test_item_ids: set[str] = set()
    for test_row in heldout_rows:
        test_char_ngrams = normalized_char_ngrams(test_row.goal_text, n=n)
        for dev_row, dev_row_char_ngrams in dev_char_ngrams:
            score = char_ngram_jaccard(test_char_ngrams, dev_row_char_ngrams)
            if score < threshold:
                continue
            overlaps.append(
                CharNgramOverlap(
                    test_item_id=test_row.item_id,
                    dev_item_id=dev_row.item_id,
                    jaccard=score,
                )
            )
            contaminated_test_item_ids.add(test_row.item_id)

    overlaps.sort(key=lambda pair: (pair.test_item_id, pair.dev_item_id, -pair.jaccard))
    return overlaps, contaminated_test_item_ids


def _row_hash_items(rows: Sequence[BenchmarkRow]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for row in rows:
        items.append(
            {
                "item_id": row.item_id,
                "row_sha256": _row_sha256(row),
            }
        )
    return items


def _row_sha256(row: BenchmarkRow) -> str:
    payload = json.dumps(row.raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_license_policy(
    rows: Sequence[BenchmarkRow], *, license_policy: str
) -> list[BenchmarkRow]:
    validate_license_policy(license_policy)
    if license_policy == "any":
        return list(rows)
    return [row for row in rows if _repo_license_open(row)]


def _repo_license_open(row: BenchmarkRow) -> bool:
    value = row.raw.get("repo_license_open")
    if value is None:
        return False
    if type(value) is not bool:
        raise ValueError(
            "repo_license_open must be a boolean or null: "
            f"item_id={row.item_id}, actual_type={type(value).__name__}"
        )
    return value


def _build_license_counts(
    *,
    input_rows: Sequence[BenchmarkRow],
    selected_rows: Sequence[BenchmarkRow],
    public_dev_rows: Sequence[BenchmarkRow],
    heldout_test_rows_before_drop: Sequence[BenchmarkRow],
    heldout_test_rows_after_drop: Sequence[BenchmarkRow],
    policy: str,
) -> LicenseCounts:
    input_total_rows = len(input_rows)
    input_open_rows = _count_open_rows(input_rows)
    input_non_open_rows = input_total_rows - input_open_rows
    selected_open_rows = _count_open_rows(selected_rows)
    selected_total_rows = len(selected_rows)
    public_dev_open_rows = _count_open_rows(public_dev_rows)
    heldout_open_before_drop = _count_open_rows(heldout_test_rows_before_drop)
    heldout_open_after_drop = _count_open_rows(heldout_test_rows_after_drop)

    return LicenseCounts(
        policy=policy,
        input_total_rows=input_total_rows,
        input_open_rows=input_open_rows,
        input_non_open_or_unknown_rows=input_non_open_rows,
        selected_rows_after_policy=selected_total_rows,
        excluded_by_policy_rows=input_total_rows - selected_total_rows,
        selected_open_rows=selected_open_rows,
        selected_non_open_or_unknown_rows=selected_total_rows - selected_open_rows,
        public_dev_open_rows=public_dev_open_rows,
        heldout_test_open_rows_before_drop=heldout_open_before_drop,
        heldout_test_open_rows_after_drop=heldout_open_after_drop,
    )


def _count_open_rows(rows: Sequence[BenchmarkRow]) -> int:
    return sum(1 for row in rows if _repo_license_open(row))


def _license_counts_payload(license_counts: LicenseCounts) -> dict[str, object]:
    return {
        "policy": license_counts.policy,
        "input_total_rows": license_counts.input_total_rows,
        "input_open_rows": license_counts.input_open_rows,
        "input_non_open_or_unknown_rows": license_counts.input_non_open_or_unknown_rows,
        "selected_rows_after_policy": license_counts.selected_rows_after_policy,
        "excluded_by_policy_rows": license_counts.excluded_by_policy_rows,
        "selected_open_rows": license_counts.selected_open_rows,
        "selected_non_open_or_unknown_rows": license_counts.selected_non_open_or_unknown_rows,
        "public_dev_open_rows": license_counts.public_dev_open_rows,
        "heldout_test_open_rows_before_drop": license_counts.heldout_test_open_rows_before_drop,
        "heldout_test_open_rows_after_drop": license_counts.heldout_test_open_rows_after_drop,
    }


def _validate_fraction(
    *,
    name: str,
    value: float,
    min_inclusive: bool,
    max_inclusive: bool,
) -> None:
    valid_min = value >= 0.0 if min_inclusive else value > 0.0
    valid_max = value <= 1.0 if max_inclusive else value < 1.0
    if valid_min and valid_max:
        return
    lower = "[0" if min_inclusive else "(0"
    upper = "1]" if max_inclusive else "1)"
    raise ValueError(f"{name} must be in {lower}, {upper}")
