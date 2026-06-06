from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from corpus import artifacts as corpus_artifacts
from corpus.lean.harder_theorems import CORPUS_HARD
from corpus.lean.research import CORPUS_RESEARCH
from corpus.lean.theorems import (
    CORPUS,
    CORPUS_EXPANDED,
    CORPUS_MATHLIB,
    CORPUS_MINIF2F,
    CORPUS_PROVERBENCH,
    DEEPSEEK_CORPUS,
    Theorem,
)
from prover import FilteredTacticProvider
from prover.goal_signature import GoalSignatureConfig
from prover.providers import (
    BFSProverTacticProvider,
    DeepSeekTacticProvider,
    InternLMStepProverTacticProvider,
    ReProverTacticProvider,
    TacticProvider,
)
from prover.providers.base import GoalAwareTacticProvider

EASY_TACTICS = {"simp", "simp_all", "omega", "decide", "native_decide", "rfl"}
PROVIDER_CHOICES = ("reprover", "deepseek", "bfs", "internlm", "heuristic")

_CORPUS_MAP = {
    "easy": CORPUS,
    "hard": CORPUS_HARD,
    "expanded": CORPUS_EXPANDED,
    "deepseek": DEEPSEEK_CORPUS,
    "proverbench": CORPUS_PROVERBENCH,
    "mathlib": CORPUS_MATHLIB,
    "minif2f": CORPUS_MINIF2F,
    "research": CORPUS_RESEARCH,
}
_LEAN_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")


def _load_named_corpus(corpus: str) -> tuple[list[Theorem], dict[str, Any], None]:
    if corpus not in _CORPUS_MAP:
        raise ValueError(f"Unknown corpus: {corpus}")
    theorems = list(_CORPUS_MAP[corpus])
    return theorems, {"name": corpus, "total_theorems": len(theorems)}, None


def _manifest_items_entry(manifest: dict[str, Any], root_dir: Path) -> tuple[Path, str, int]:
    items_file = manifest.get("items_file", "items.jsonl")
    if not isinstance(items_file, str) or not items_file:
        raise ValueError(f"Invalid items_file in manifest: {root_dir}")
    items_path = root_dir / items_file
    if not items_path.exists():
        raise ValueError(f"Items not found: {items_path}")

    items_sha256 = manifest.get("items_sha256")
    if not isinstance(items_sha256, str) or not items_sha256:
        raise ValueError(f"Missing items_sha256 in manifest for: {root_dir}")

    total_items = (manifest.get("counts") or {}).get("items_total")
    if not isinstance(total_items, int) or total_items < 0:
        raise ValueError(f"Missing items_total in manifest for: {root_dir}")

    return items_path, items_sha256, total_items


def _load_artifact_corpus(
    *,
    corpus_artifact: str,
    corpus_build_id: str | None,
    corpus_derived: str | None,
) -> tuple[list[Theorem], dict[str, Any], dict[str, Any]]:
    ref = corpus_artifacts.resolve_build_dir(
        "lean",
        corpus_artifact,
        build_id=corpus_build_id,
    )
    source_dir = ref.build_dir
    manifest = corpus_artifacts.load_manifest(source_dir)

    derived_build_id: str | None = None
    if corpus_derived:
        parts = [part for part in corpus_derived.strip().split("/") if part]
        if any(part in {".", ".."} for part in parts) or any("\\" in part for part in parts):
            raise ValueError(f"Invalid derived selector: {corpus_derived!r}")
        derived_root = source_dir / "derived"
        for part in parts:
            derived_root = derived_root / part
        if not derived_root.exists():
            raise ValueError(f"Derived path not found: {derived_root}")
        current = derived_root / "CURRENT"
        if current.exists():
            derived_build_id = current.read_text().strip()
            if not derived_build_id:
                raise ValueError(f"Empty CURRENT pointer: {current}")
            source_dir = derived_root / derived_build_id
        else:
            source_dir = derived_root
        manifest = corpus_artifacts.load_manifest(source_dir)

    items_path, items_sha256, total_items = _manifest_items_entry(manifest, source_dir)

    theorems: list[Theorem] = []
    for obj in corpus_artifacts.iter_jsonl(items_path):
        item_id = obj.get("item_id")
        payload = obj.get("payload")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"Invalid item_id in {items_path}")
        if not _LEAN_IDENT_RE.match(item_id):
            raise ValueError(
                f"Lean corpus item_id must be a valid identifier (got {item_id!r}). "
                "Use display_name for original names."
            )
        if not isinstance(payload, dict):
            raise ValueError(f"Missing payload for item {item_id!r} in {items_path}")
        statement = payload.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(f"Missing payload.statement for item {item_id!r} in {items_path}")
        theorems.append(Theorem(name=item_id, statement=statement))

    corpus_label = f"artifact:{corpus_artifact}@{ref.build_id}"
    if corpus_derived:
        suffix = f"@{derived_build_id}" if derived_build_id is not None else ""
        corpus_label = f"{corpus_label}:derived/{corpus_derived}{suffix}"

    corpus_meta = {
        "name": corpus_label,
        "total_theorems": total_items,
        "items_loaded": len(theorems),
        "items_path": str(items_path),
    }
    corpus_artifact_ref = {
        "corpus_id": corpus_artifact,
        "build_id": ref.build_id,
        "items_sha256": items_sha256,
        "derived": corpus_derived,
        "derived_build_id": derived_build_id,
    }
    return theorems, corpus_meta, corpus_artifact_ref


def load_corpus(corpus: str) -> tuple[list[Theorem], dict[str, Any], dict[str, Any] | None]:
    if not corpus.startswith("lean:"):
        return _load_named_corpus(corpus)

    ref = corpus_artifacts.parse_corpus_ref(corpus)
    if ref.backend != "lean":
        raise ValueError(f"Invalid Lean corpus ref (expected backend=lean): {corpus!r}")
    return _load_artifact_corpus(
        corpus_artifact=ref.corpus_id,
        corpus_build_id=ref.build_id,
        corpus_derived=ref.derived,
    )


def create_provider(
    provider_name: str,
    device: str | None,
    use_sampling: bool,
    goal_sig_config: GoalSignatureConfig,
    block_easy: bool = False,
    *,
    deepseek_num_samples: int | None = None,
    deepseek_model_path: str | None = None,
    deepseek_backend: str = "mlx",
    bfs_num_samples: int | None = None,
    internlm_num_samples: int | None = None,
) -> TacticProvider:
    if provider_name == "reprover":
        base = ReProverTacticProvider(
            device=device,
            use_sampling=use_sampling,
            temperature=0.7,
            top_p=0.9,
        )
    elif provider_name == "deepseek":
        if deepseek_num_samples is None:
            base = DeepSeekTacticProvider(
                model_path=deepseek_model_path,
                backend=deepseek_backend,
                device=device,
            )
        else:
            base = DeepSeekTacticProvider(
                model_path=deepseek_model_path,
                backend=deepseek_backend,
                device=device,
                num_samples=deepseek_num_samples,
            )
    elif provider_name == "bfs":
        kwargs = {
            "device": device,
            "use_sampling": use_sampling,
            "temperature": 0.7,
            "top_p": 0.9,
        }
        if bfs_num_samples is None:
            base = BFSProverTacticProvider(**kwargs)
        else:
            base = BFSProverTacticProvider(num_samples=bfs_num_samples, **kwargs)
    elif provider_name == "internlm":
        kwargs = {
            "device": device,
            "use_sampling": use_sampling,
            "temperature": 0.7,
            "top_p": 0.9,
        }
        if internlm_num_samples is None:
            base = InternLMStepProverTacticProvider(**kwargs)
        else:
            base = InternLMStepProverTacticProvider(
                num_samples=internlm_num_samples,
                **kwargs,
            )
    elif provider_name == "heuristic":
        base = GoalAwareTacticProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

    if block_easy:
        return FilteredTacticProvider(
            base,
            blocked=EASY_TACTICS,
            goal_sig_config=goal_sig_config,
        )
    return base
