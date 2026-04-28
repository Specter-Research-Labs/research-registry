from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

import numpy as np


def _qd24_genotype(payload: dict[str, Any]) -> np.ndarray:
    elite = payload.get("elite")
    genotype = elite.get("genotype") if isinstance(elite, dict) else None
    if not isinstance(genotype, list) or not genotype:
        raise SystemExit("qd24 payload elite.genotype must be a non-empty list")
    return np.asarray(genotype, dtype=np.float64)


def _qd24_set_genotype(
    payload: dict[str, Any],
    genotype: np.ndarray,
    *,
    cell_seed: int,
) -> dict[str, Any]:
    mutated = copy.deepcopy(payload)
    elite = mutated.get("elite")
    if not isinstance(elite, dict):
        raise SystemExit("qd24 payload is missing elite")
    elite["genotype"] = genotype.astype(float).tolist()
    elite["cell"] = int(cell_seed)
    elite["descriptor"] = []
    elite["centroid"] = []
    elite["generation"] = -1
    return mutated


@dataclass(frozen=True)
class QD24ChartConfig:
    name: str
    transform: str
    genotype_size: int
    n_kernel: int
    n_channel: int
    n_params_size: int
    n_params: int
    embryo_size: int
    iso_sigma: float
    line_sigma: float
    epsilon: float
    per_gene_scale: np.ndarray


def qd24_chart_config(
    payload: dict[str, Any],
    *,
    iso_sigma: float = 0.005,
    line_sigma: float = 0.05,
    epsilon: float = 1e-4,
    transform: str = "identity",
) -> QD24ChartConfig:
    genotype = _qd24_genotype(payload)
    base = payload.get("base")
    if not isinstance(base, dict):
        raise SystemExit("qd24 payload is missing base")
    n_params_size = base.get("n_params_size")
    if not isinstance(n_params_size, int) or n_params_size <= 0:
        raise SystemExit("qd24 payload base.n_params_size must be a positive integer")
    pattern = payload.get("pattern")
    kernels = pattern.get("kernels") if isinstance(pattern, dict) else None
    cells = pattern.get("cells") if isinstance(pattern, dict) else None
    if not isinstance(kernels, list) or not kernels:
        raise SystemExit("qd24 payload pattern.kernels must be a non-empty list")
    if not isinstance(cells, list) or not cells:
        raise SystemExit("qd24 payload pattern.cells must be a non-empty list")
    n_kernel = len(kernels)
    n_channel = len(cells)
    n_params = n_params_size * n_kernel
    if genotype.size <= n_params:
        raise SystemExit("qd24 genotype is too short for the declared parameter block")
    cells_size = int(genotype.size - n_params)
    embryo_area = cells_size / max(n_channel, 1)
    embryo_size = int(round(math.sqrt(embryo_area)))
    if embryo_size * embryo_size * n_channel != cells_size:
        raise SystemExit("qd24 genotype cell block is not a square embryo")
    if iso_sigma <= 0.0:
        raise SystemExit("iso_sigma must be positive")
    if transform not in {"identity", "bounded_logit"}:
        raise SystemExit(f"Unsupported qd24 chart transform: {transform}")
    if transform == "bounded_logit" and (
        float(genotype.min()) <= 0.0 or float(genotype.max()) >= 1.0
    ):
        raise SystemExit(
            "bounded_logit chart requires all qd24 genes "
            "to lie strictly inside (0, 1)"
        )
    per_gene_scale = np.full(genotype.shape, iso_sigma, dtype=np.float64)
    return QD24ChartConfig(
        name=f"qd24_{transform}_mutscale_v1",
        transform=transform,
        genotype_size=int(genotype.size),
        n_kernel=n_kernel,
        n_channel=n_channel,
        n_params_size=n_params_size,
        n_params=n_params,
        embryo_size=embryo_size,
        iso_sigma=float(iso_sigma),
        line_sigma=float(line_sigma),
        epsilon=float(epsilon),
        per_gene_scale=per_gene_scale,
    )


def encode_qd24_payload(payload: dict[str, Any], config: QD24ChartConfig) -> np.ndarray:
    genotype = _qd24_genotype(payload)
    if genotype.size != config.genotype_size:
        raise SystemExit("qd24 genotype size does not match chart config")
    if config.transform == "identity":
        return genotype / config.per_gene_scale
    clipped = np.clip(genotype, config.epsilon, 1.0 - config.epsilon)
    return np.log(clipped / (1.0 - clipped)) / config.per_gene_scale


def decode_qd24_payload(
    template_payload: dict[str, Any],
    chart_coordinates: np.ndarray,
    config: QD24ChartConfig,
    *,
    cell_seed: int,
) -> dict[str, Any]:
    if chart_coordinates.shape != (config.genotype_size,):
        raise SystemExit("qd24 chart coordinate shape does not match chart config")
    if config.transform == "identity":
        genotype = chart_coordinates * config.per_gene_scale
    else:
        logits = chart_coordinates * config.per_gene_scale
        genotype = 1.0 / (1.0 + np.exp(-logits))
        genotype = np.clip(genotype, config.epsilon, 1.0 - config.epsilon)
    return _qd24_set_genotype(template_payload, genotype, cell_seed=cell_seed)


def interpolate_qd24_payload_chart(
    payload_a: dict[str, Any],
    payload_b: dict[str, Any],
    alpha: float,
    config: QD24ChartConfig,
    *,
    cell_seed: int,
) -> dict[str, Any]:
    chart_a = encode_qd24_payload(payload_a, config)
    chart_b = encode_qd24_payload(payload_b, config)
    if chart_a.shape != chart_b.shape:
        raise SystemExit("qd24 chart endpoints have mismatched shapes")
    chart = (1.0 - alpha) * chart_a + alpha * chart_b
    return decode_qd24_payload(payload_a, chart, config, cell_seed=cell_seed)


def pair_direction_qd24_chart(
    payload_a: dict[str, Any],
    payload_b: dict[str, Any],
    config: QD24ChartConfig,
) -> np.ndarray:
    chart_a = encode_qd24_payload(payload_a, config)
    chart_b = encode_qd24_payload(payload_b, config)
    direction = chart_b - chart_a
    norm = float(np.linalg.norm(direction))
    if norm == 0.0:
        raise SystemExit("qd24 pair direction has zero norm in chart coordinates")
    return direction / norm


def perturb_qd24_payload_chart(
    template_payload: dict[str, Any],
    *,
    base_payload: dict[str, Any],
    config: QD24ChartConfig,
    direction: np.ndarray,
    step_size: float,
    cell_seed: int,
) -> dict[str, Any]:
    base_chart = encode_qd24_payload(base_payload, config)
    if direction.shape != base_chart.shape:
        raise SystemExit("qd24 perturbation direction shape does not match chart config")
    return decode_qd24_payload(
        template_payload,
        base_chart + step_size * direction,
        config,
        cell_seed=cell_seed,
    )
