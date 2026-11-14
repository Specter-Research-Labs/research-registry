"""K search efficiency: log10(tau_blind / tau_agent) over a solved variant's steps.

tau_blind is the expected attempt count of a blind searcher that, at each
solution step, draws uniformly from the step's candidate tactics
(`blind_uniform_candidate`) or from their distinct tactic families
(`blind_uniform_family`). Callers differ only in where p(success | goal_sig,
family) comes from: the run's own goal cache (postprocess) or a lake reference
(score-k).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from analysis.logs import SolutionStepExtraction
from prover.k import k_log10_ratio
from prover.providers.base import normalize_tactic, tactic_family

PSuccess = Callable[[str, str], float]
ObservedFamilies = Callable[[str], list[str]]

BLIND_CANDIDATE = "blind_uniform_candidate"
BLIND_FAMILY = "blind_uniform_family"
METRICS = ("any_success", "used_operator")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _tau_blind(
    ext: SolutionStepExtraction,
    *,
    p_success: PSuccess,
    null_model: str,
    metric: str,
    observed_families: ObservedFamilies | None,
) -> tuple[float | None, list[str]]:
    tau_blind = 0.0
    notes: list[str] = []
    for spec in ext.step_specs:
        it = spec["iteration"]
        sig = spec["goal_sig"]
        used_fam = spec["tactic_family"]
        candidates = ext.candidates_by_iter.get(it)
        if candidates:
            fams = [tactic_family(normalize_tactic(c)) for c in candidates]
        elif null_model == BLIND_FAMILY and observed_families is not None:
            fams = observed_families(sig)
            if not fams:
                notes.append(f"missing_candidates_and_no_observed_fams: iteration={it}")
                return None, notes
            notes.append(f"fallback_operator_alphabet: observed_families iteration={it}")
        else:
            notes.append(f"missing_candidates: iteration={it}")
            return None, notes

        if null_model == BLIND_CANDIDATE:
            alphabet = fams
        elif null_model == BLIND_FAMILY:
            alphabet = sorted(set(fams))
        else:
            raise ValueError(f"Unknown null model: {null_model}")

        if metric == "any_success":
            p_step = _mean([p_success(sig, fam) for fam in alphabet])
        elif metric == "used_operator":
            used_count = alphabet.count(used_fam)
            if used_count <= 0:
                where = "candidates" if null_model == BLIND_CANDIDATE else "families"
                notes.append(f"used_family_missing_from_{where}: iteration={it}")
                return None, notes
            p_step = (used_count / len(alphabet)) * p_success(sig, used_fam)
        else:
            raise ValueError(f"Unknown K metric: {metric}")

        if p_step <= 0.0:
            notes.append(f"invalid_step_probability: iteration={it} p={p_step!r}")
            return None, notes
        tau_blind += 1.0 / p_step
    return tau_blind, notes


def compute_k(
    ext: SolutionStepExtraction,
    *,
    p_success: PSuccess,
    null_models: tuple[str, ...],
    observed_families: ObservedFamilies | None,
) -> dict[str, Any]:
    """K entry for one variant.

    The primary value is `any_success` under the first valid null model in
    `null_models`, or under the last one when none is valid; picking a later
    one is recorded as `primary_fallback` in the validity notes.
    """
    if not ext.valid:
        return {"schema_version": 1, "valid": False, "validity_notes": ext.validity_notes}
    assert ext.tau_agent is not None
    tau_agent = ext.tau_agent

    variants: dict[str, dict[str, dict[str, Any]]] = {metric: {} for metric in METRICS}
    for metric in METRICS:
        for null_model in null_models:
            tau_blind, notes = _tau_blind(
                ext,
                p_success=p_success,
                null_model=null_model,
                metric=metric,
                observed_families=observed_families,
            )
            if tau_blind is None:
                variants[metric][null_model] = {
                    "tau_blind": None,
                    "K": None,
                    "valid": False,
                    "validity_notes": notes,
                }
                continue
            k_value = k_log10_ratio(tau_blind=tau_blind, tau_agent=tau_agent)
            variants[metric][null_model] = {
                "tau_blind": round(float(tau_blind), 6),
                "K": round(float(k_value), 6),
                "valid": True,
                "validity_notes": notes,
            }

    notes = list(ext.validity_notes)
    primary_null = next(
        (m for m in null_models if variants["any_success"][m]["valid"]), null_models[-1]
    )
    if primary_null != null_models[0]:
        notes.append(f"primary_fallback: used {primary_null} due to trace/candidate issues")
    primary = variants["any_success"][primary_null]
    # Partial step maps are invalid so that a partial tau_blind is never scored
    # against the full tau_agent.
    complete = ext.expected_steps == len(ext.step_specs)
    return {
        "schema_version": 1,
        "valid": bool(primary["valid"]) and complete,
        "validity_notes": notes,
        "w_unit": "tactic_attempt",
        "tau_agent": int(tau_agent),
        "primary": {
            "metric": "any_success",
            "null_model": primary_null,
            "tau_blind": primary["tau_blind"],
            "K": primary["K"],
        },
        "variants": variants,
        "steps": {
            "count": len(ext.step_specs),
            "expected": ext.expected_steps,
            "dropped": ext.dropped_steps,
        },
    }
