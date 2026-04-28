from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from prover.goal_features import FEATURE_DIM, extract_features
from prover.goal_signature import GoalSignatureConfig, compute_goal_signature


@dataclass
class OccurrenceRecord:
    mvar_id: str
    outcomes: dict[int, list[bool]] = field(default_factory=dict)


@dataclass
class GoalEntry:
    sig: str
    type_expr: dict | None
    hyp_exprs: list[dict | None]
    _features: np.ndarray | None = None
    occurrences: dict[str, OccurrenceRecord] = field(default_factory=dict)

    def get_features(self) -> np.ndarray:
        if self._features is None:
            self._features = extract_features(self.type_expr, len(self.hyp_exprs))
        return self._features


class GoalCache:
    def __init__(self, sig_config: GoalSignatureConfig):
        self.entries: dict[str, GoalEntry] = {}
        self.mvar_to_sig: dict[str, str] = {}
        self.sig_config = sig_config

    def add_goal(
        self,
        mvar_id: str,
        type_str: str,
        type_expr: dict | None,
        hyp_types: list[str],
        hyp_exprs: list[dict | None],
    ) -> str:
        sig = compute_goal_signature(
            type_str=type_str,
            type_expr=type_expr,
            hyp_types=hyp_types,
            hyp_exprs=hyp_exprs,
            config=self.sig_config,
        )
        self.mvar_to_sig[mvar_id] = sig

        if sig not in self.entries:
            self.entries[sig] = GoalEntry(
                sig=sig,
                type_expr=type_expr,
                hyp_exprs=hyp_exprs,
            )

        if mvar_id not in self.entries[sig].occurrences:
            self.entries[sig].occurrences[mvar_id] = OccurrenceRecord(mvar_id=mvar_id)

        return sig

    def record_outcome(self, mvar_id: str, family: int, success: bool):
        sig = self.mvar_to_sig.get(mvar_id)
        if sig is None or sig not in self.entries:
            return
        occ = self.entries[sig].occurrences.get(mvar_id)
        if occ is None:
            return
        if family not in occ.outcomes:
            occ.outcomes[family] = []
        occ.outcomes[family].append(success)

    def get_sig(self, mvar_id: str) -> str | None:
        return self.mvar_to_sig.get(mvar_id)

    def get_features(self, sig: str) -> np.ndarray:
        entry = self.entries.get(sig)
        if entry is None:
            return np.zeros(FEATURE_DIM, dtype=np.float32)
        return entry.get_features()

    def save(self, path: Path):
        data = {
            "sig_scheme": self.sig_config.scheme,
            "sig_stats": {
                "ast_missing": self.sig_config.stats.ast_missing,
            },
            "mvar_to_sig": self.mvar_to_sig,
            "entries": {
                sig: {
                    "sig": entry.sig,
                    "type_expr": entry.type_expr,
                    "hyp_exprs": entry.hyp_exprs,
                    "occurrences": {
                        mvar_id: {
                            "mvar_id": occ.mvar_id,
                            "outcomes": {str(k): v for k, v in occ.outcomes.items()},
                        }
                        for mvar_id, occ in entry.occurrences.items()
                    },
                }
                for sig, entry in self.entries.items()
            },
        }
        gz_path = path.with_suffix(path.suffix + ".gz")
        with gzip.open(gz_path, "wt") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: Path, sig_config: GoalSignatureConfig | None = None) -> GoalCache:
        gz_path = path.with_suffix(path.suffix + ".gz")
        if gz_path.exists():
            with gzip.open(gz_path, "rt") as f:
                data = json.load(f)
        elif path.exists():
            with open(path) as f:
                data = json.load(f)
        else:
            raise FileNotFoundError(f"No {path} or {gz_path} found")
        return cls._from_data(data, sig_config)

    @classmethod
    def _from_data(cls, data: dict, sig_config: GoalSignatureConfig | None = None) -> GoalCache:
        if sig_config is None:
            scheme = data.get("sig_scheme", "text")
            sig_config = GoalSignatureConfig(
                scheme=scheme,
            )
            stats = data.get("sig_stats", {})
            sig_config.stats.ast_missing = stats.get("ast_missing", 0)

        cache = cls(sig_config)
        cache.mvar_to_sig = data.get("mvar_to_sig", {})

        for sig, entry_data in data.get("entries", {}).items():
            occurrences = {}
            for mvar_id, occ_data in entry_data.get("occurrences", {}).items():
                occurrences[mvar_id] = OccurrenceRecord(
                    mvar_id=occ_data["mvar_id"],
                    outcomes={int(k): v for k, v in occ_data.get("outcomes", {}).items()},
                )

            cache.entries[sig] = GoalEntry(
                sig=entry_data["sig"],
                type_expr=entry_data.get("type_expr"),
                hyp_exprs=entry_data.get("hyp_exprs", []),
                occurrences=occurrences,
            )

        return cache
