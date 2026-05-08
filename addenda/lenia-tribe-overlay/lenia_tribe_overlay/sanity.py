from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import paths
from .probes import probe_set
from .tribe_client import TribeClient, TribePrediction

VARIANCE_FLOOR = 1e-4


class SanityFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class SanityReport:
    checkpoint_revision: str
    timestamp: str
    n_voxels: int
    per_class_mean: dict[str, float]
    per_class_std: dict[str, float]
    across_stimulus_variance: float
    per_stimulus_mean: dict[str, float]

    def to_json(self) -> str:
        return json.dumps(
            {
                "checkpoint_revision": self.checkpoint_revision,
                "timestamp": self.timestamp,
                "n_voxels": self.n_voxels,
                "per_class_mean": self.per_class_mean,
                "per_class_std": self.per_class_std,
                "per_stimulus_mean": self.per_stimulus_mean,
                "across_stimulus_variance": self.across_stimulus_variance,
                "result": "pass",
            },
            indent=2,
            sort_keys=True,
        )


def _activations(predictions: list[TribePrediction]) -> np.ndarray:
    return np.stack([p.voxels for p in predictions], axis=0)


def run_gate(client: TribeClient, seed: int = 0) -> SanityReport:
    """Model-level sanity gate.

    invariant: this gate only checks model-level health (does TRIBE produce
    differentiated whole-cortex predictions for visually distinct probes?).
    Region-specific claims, including bio-motion engagement, belong to the
    experiment proper because they require an ROI mask. Conflating the two
    led to a false-negative on a 7-stimulus probe set where the bio-motion
    signal was hidden under the whole-cortex average.
    """
    stimuli = list(probe_set(seed=seed))
    predictions = [client.predict(s) for s in stimuli]
    activations = _activations(predictions)

    per_stimulus_mean_arr = activations.mean(axis=1)
    across_var = float(per_stimulus_mean_arr.var())
    per_stimulus_mean = {
        stim.name: float(per_stimulus_mean_arr[i]) for i, stim in enumerate(stimuli)
    }
    if across_var < VARIANCE_FLOOR:
        raise SanityFailure(
            "across-stimulus variance collapse: "
            f"var={across_var:.3e} < floor={VARIANCE_FLOOR:.3e}. "
            "TRIBE produced near-identical whole-cortex predictions for visually "
            "distinct probes; the dossier's premise is broken on this checkpoint. "
            f"per-stimulus means: {per_stimulus_mean}"
        )

    by_class: dict[str, list[float]] = {}
    for stim, pred in zip(stimuli, predictions):
        by_class.setdefault(stim.stimulus_class, []).append(float(pred.voxels.mean()))
    per_class_mean = {k: float(np.mean(v)) for k, v in by_class.items()}
    per_class_std = {k: float(np.std(v)) for k, v in by_class.items()}

    return SanityReport(
        checkpoint_revision=client.checkpoint_revision,
        timestamp=datetime.now(UTC).isoformat(),
        n_voxels=client.n_voxels,
        per_class_mean=per_class_mean,
        per_class_std=per_class_std,
        across_stimulus_variance=across_var,
        per_stimulus_mean=per_stimulus_mean,
    )


def write_report(report: SanityReport) -> Path:
    out_dir = paths.ensure(paths.artifact_root() / "sanity")
    revision_slug = report.checkpoint_revision.replace("/", "_")
    fname = f"{revision_slug}.{report.timestamp.replace(':', '-')}.json"
    out = out_dir / fname
    out.write_text(report.to_json())
    return out


def _load_client_from_args(args: argparse.Namespace) -> TribeClient:
    if args.fake:
        from .tribe_fake import FakeTribeClient

        return FakeTribeClient(seed=args.seed)
    from .tribe_real import RealTribeClient

    return RealTribeClient(device=args.device)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the TRIBE sanity gate.")
    parser.add_argument("--fake", action="store_true", help="use the fake client for development")
    parser.add_argument("--device", default="auto", help="torch device for the real client")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    client = _load_client_from_args(args)
    report = run_gate(client, seed=args.seed)
    out = write_report(report)
    print(f"sanity gate passed; report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
