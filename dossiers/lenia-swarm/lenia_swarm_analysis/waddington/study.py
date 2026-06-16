"""Reproducible specification for the Waddington landscape study.

Four track1-harvest rules share one initial-condition family (single patch), so the only thing
that differs is the rule (the pegs under Waddington's sheet). For each we replay a deterministic
seeded subset of the discovered specimens with per-step descriptor capture, giving developmental
trajectories through the 16-axis terminal morphospace. The seed selection is the stable hash order
of each export record's creatureId, so the study reruns identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DOSSIER_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = DOSSIER_ROOT / "artifacts" / "flow-universe-runs" / "track1-20260520"
STUDY_ROOT = DOSSIER_ROOT / "artifacts" / "waddington"
WAREHOUSE_DB = STUDY_ROOT / "waddington.duckdb"


@dataclass(frozen=True)
class RuleConfig:
    config_hash: str
    label: str
    shard_glob: str


CONFIGS: tuple[RuleConfig, ...] = (
    RuleConfig("203dd0e350e7", "2c10-r7-10", "track1b-2c10-r7-10-initshift-8192-s*"),
    RuleConfig("4cf7f1476e03", "2c20", "track1b-2c20-harvest-8192-s*"),
    RuleConfig("658e1861c83a", "2c10-r17-20", "track1b-2c10-r17-20-initshift-8192-s*"),
    RuleConfig("a54410e453b4", "3c15", "track1b-3c15-harvest-8192-s*"),
)

SPECIMENS_PER_CONFIG = 8000
TRACE_INTERVAL = 25

INPUTS_DIR = STUDY_ROOT / "inputs"
REPLAY_DIR = STUDY_ROOT / "replay"
FIGURES_DIR = STUDY_ROOT / "figures"

# Uniform-random-genotype control: same rules, but genotypes sampled uniformly over the full
# Flow-Lenia parameter ranges (not the search-discovered, filter-passing set). Maps the unfiltered
# outcome distribution including the diffuse "soup" the harvest filtered away, isolating the
# survivorship + discovery bias in the main study.
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "R": (2.0, 25.0),
    "r": (0.2, 1.0),
    "b": (0.001, 1.0),
    "w": (0.01, 0.5),
    "a": (0.0, 1.0),
    "m": (0.05, 0.5),
    "s": (0.001, 0.2),
    "h": (0.0, 1.0),
}
RANDOM_SPECIMENS_PER_CONFIG = 5000
RANDOM_ROOT = STUDY_ROOT / "random"
RANDOM_SCOUT_DIR = RANDOM_ROOT / "scout"
RANDOM_REPLAY_DIR = RANDOM_ROOT / "replay"


def input_index_path(config_hash: str) -> Path:
    return INPUTS_DIR / f"{config_hash}.jsonl"


def replay_run_path(config_hash: str) -> Path:
    return REPLAY_DIR / config_hash


def random_scout_path(config_hash: str) -> Path:
    return RANDOM_SCOUT_DIR / config_hash


def random_replay_path(config_hash: str) -> Path:
    return RANDOM_REPLAY_DIR / config_hash


# Perturbation/canalization control: ablate a square patch of the creature's state mid-development
# (zero_state_patch) and measure whether it returns to its attractor. Tests Waddington canalization
# directly: does geometric valley depth predict dynamical recovery? Requires profile=experimental.
PERTURB_ROOT = STUDY_ROOT / "perturb"
PERTURB_STEP = 300
PERTURB_SIZE = 48
PERTURB_SPECIMENS_PER_CONFIG = 1500


def perturb_scout_path(variant: str, config_hash: str) -> Path:
    return PERTURB_ROOT / variant / "scout" / config_hash


def perturb_replay_path(variant: str, config_hash: str) -> Path:
    return PERTURB_ROOT / variant / "replay" / config_hash
