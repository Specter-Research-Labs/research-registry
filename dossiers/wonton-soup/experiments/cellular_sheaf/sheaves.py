from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from prover.goal_cache import GoalCache
from prover.goal_features import FEATURE_DIM
from prover.mcts import TACTIC_FAMILIES

NUM_FAMILIES = len(TACTIC_FAMILIES)
MIN_EDGES_FOR_REGRESSION = 5


@dataclass
class EquivalenceSheaf:
    """Measures consistency of tactic success rates across goal signature occurrences.

    The core idea: if a goal signature truly captures the "essence" of a goal state,
    then the same tactic family should succeed at roughly the same rate across all
    occurrences of that signature. High variance suggests the signature is missing
    important information.

    Terminology note: This is not a sheaf in the mathematical sense (no presheaf
    structure or gluing axiom). The name reflects the conceptual goal of measuring
    how well local data (per-occurrence success rates) agrees globally.
    """

    cache: GoalCache

    @classmethod
    def from_cache(cls, cache: GoalCache) -> EquivalenceSheaf:
        return cls(cache=cache)

    def consistency(self, min_occurrences: int = 2, min_attempts: int = 3) -> float:
        """Compute overall consistency score across all signatures and tactic families.

        Returns a value in [0, 1]:
          - 1.0 = perfectly consistent (same success rate everywhere)
          - 0.0 = maximum variance (opposite outcomes at different occurrences)

        The score is 1 - (weighted average variance), where each signature-family
        pair contributes proportionally to its total attempt count.

        Higher consistency suggests goal signatures capture meaningful structure.
        Lower consistency may indicate signatures are too coarse or that context
        beyond the goal type matters for tactic success.
        """
        total_weighted_var, total_weight = 0.0, 0.0

        for entry in self.cache.entries.values():
            for family in range(NUM_FAMILIES):
                occ_rates = []
                occ_weights = []

                for occ in entry.occurrences.values():
                    outcomes = occ.outcomes.get(family, [])
                    if len(outcomes) > 0:
                        rate = sum(outcomes) / len(outcomes)
                        occ_rates.append(rate)
                        occ_weights.append(len(outcomes))

                n_occs = len(occ_rates)
                total_attempts = sum(occ_weights)

                if n_occs >= min_occurrences or total_attempts >= min_attempts:
                    if n_occs > 1:
                        weights = np.array(occ_weights, dtype=np.float64)
                        rates = np.array(occ_rates, dtype=np.float64)
                        mean = np.average(rates, weights=weights)
                        variance = np.average((rates - mean) ** 2, weights=weights)
                        total_weighted_var += variance * total_attempts
                        total_weight += total_attempts

        return 1.0 - total_weighted_var / total_weight if total_weight > 0 else 1.0

    def inconsistent_sigs(self, threshold: float = 0.2) -> list[tuple[str, int, float]]:
        """Find signature-family pairs with high variance in success rates.

        Returns list of (signature, family_index, variance) tuples where
        variance > threshold. These represent cases where the same goal
        signature has very different tactic success rates in different contexts.
        """
        results = []
        for sig, entry in self.cache.entries.items():
            for family in range(NUM_FAMILIES):
                occ_rates = []
                occ_weights = []
                for occ in entry.occurrences.values():
                    outcomes = occ.outcomes.get(family, [])
                    if outcomes:
                        occ_rates.append(sum(outcomes) / len(outcomes))
                        occ_weights.append(len(outcomes))

                if len(occ_rates) >= 2:
                    weights = np.array(occ_weights, dtype=np.float64)
                    rates = np.array(occ_rates, dtype=np.float64)
                    mean = np.average(rates, weights=weights)
                    variance = np.average((rates - mean) ** 2, weights=weights)
                    if variance > threshold:
                        results.append((sig, family, float(variance)))
        return results

    def per_sig_feasibility(self) -> dict[str, dict[int, float]]:
        """Compute smoothed success rate for each signature-family pair.

        Uses Laplace smoothing: (successes + 1) / (attempts + 2) to handle
        sparse data gracefully. Returns {signature: {family_index: rate}}.
        """
        result = {}
        for sig, entry in self.cache.entries.items():
            family_rates = {}
            for family in range(NUM_FAMILIES):
                total_success = 0
                total_attempts = 0
                for occ in entry.occurrences.values():
                    outcomes = occ.outcomes.get(family, [])
                    total_success += sum(outcomes)
                    total_attempts += len(outcomes)
                if total_attempts > 0:
                    family_rates[family] = (total_success + 1) / (total_attempts + 2)
            if family_rates:
                result[sig] = family_rates
        return result


@dataclass
class TacticTransformSheaf:
    """Models how tactics transform goal features in a predictable way.

    For each tactic family, fits a linear transformation M_t such that:
        feature(child_goal) ≈ M_t @ feature(parent_goal)

    If tactics have consistent, predictable effects on goal structure,
    these transformations will fit well (low residual). High residual
    suggests tactics have context-dependent effects not captured by features.

    Key metrics:
      - residual_energy: Average squared prediction error across all edges.
        Lower = tactics behave predictably. Typical range: 5-50 for standardized features.
      - per_family_residual: Error broken down by tactic family.
        Identifies which tactics are most/least predictable.
      - intervention_delta: How much worse the fit is for intervention edges
        vs wild-type. Positive = interventions produce less predictable transitions.

    Terminology note: Not a true sheaf (no restriction maps or gluing).
    The name reflects modeling local transformations that should compose.
    """

    edges: list[tuple[str, str, int]]
    transform_maps: dict[int, np.ndarray]
    feature_dim: int
    feature_mean: np.ndarray | None
    feature_std: np.ndarray | None
    ridge_alpha: float = 0.1

    @classmethod
    def from_edges(
        cls,
        edges: list[tuple[str, str, int]],
        cache: GoalCache,
        feature_dim: int = FEATURE_DIM,
        ridge_alpha: float = 0.1,
    ) -> TacticTransformSheaf:
        all_sigs = set()
        for p, c, _ in edges:
            all_sigs.add(p)
            all_sigs.add(c)

        if not all_sigs:
            return cls(
                edges=edges,
                transform_maps={},
                feature_dim=feature_dim,
                feature_mean=None,
                feature_std=None,
                ridge_alpha=ridge_alpha,
            )

        features = np.stack([cache.get_features(s) for s in all_sigs])
        mean = features.mean(axis=0)
        std = features.std(axis=0)
        std = np.where(std < 1e-6, 1.0, std)

        sheaf = cls(
            edges=edges,
            transform_maps={},
            feature_dim=feature_dim,
            feature_mean=mean,
            feature_std=std,
            ridge_alpha=ridge_alpha,
        )
        sheaf._fit_transforms(cache)
        return sheaf

    def _standardize(self, x: np.ndarray) -> np.ndarray:
        if self.feature_mean is None or self.feature_std is None:
            return x
        return (x - self.feature_mean) / self.feature_std

    def _fit_transforms(self, cache: GoalCache):
        for family in range(NUM_FAMILIES):
            family_edges = [(p, c) for p, c, f in self.edges if f == family]
            if len(family_edges) < MIN_EDGES_FOR_REGRESSION:
                self.transform_maps[family] = np.eye(self.feature_dim)
                continue

            X = np.stack([self._standardize(cache.get_features(p)) for p, _ in family_edges])
            Y = np.stack([self._standardize(cache.get_features(c)) for _, c in family_edges])

            XtX = X.T @ X
            reg = self.ridge_alpha * np.eye(self.feature_dim)
            try:
                self.transform_maps[family] = np.linalg.solve(XtX + reg, X.T @ Y).T
            except np.linalg.LinAlgError:
                self.transform_maps[family] = np.eye(self.feature_dim)

    def residual_energy(self, cache: GoalCache) -> float:
        """Average squared prediction error across all edges.

        For each (parent, child, family) edge, computes:
            error = ||feature(child) - M_family @ feature(parent)||^2

        Lower values indicate tactics transform goals predictably.
        """
        total, count = 0.0, 0
        for parent_sig, child_sig, family in self.edges:
            x_p = self._standardize(cache.get_features(parent_sig))
            x_c = self._standardize(cache.get_features(child_sig))
            M_t = self.transform_maps.get(family, np.eye(self.feature_dim))
            pred = M_t @ x_p
            total += np.sum((x_c - pred) ** 2)
            count += 1
        return total / count if count > 0 else 0.0

    def per_family_residual(self, cache: GoalCache) -> dict[int, float]:
        """Residual energy broken down by tactic family.

        Returns {family_index: average_squared_error}. High values indicate
        that tactic family has inconsistent/unpredictable effects on goal features.
        """
        result = {}
        for family in range(NUM_FAMILIES):
            family_edges = [(p, c) for p, c, f in self.edges if f == family]
            if not family_edges:
                continue
            total = 0.0
            for parent_sig, child_sig in family_edges:
                x_p = self._standardize(cache.get_features(parent_sig))
                x_c = self._standardize(cache.get_features(child_sig))
                M_t = self.transform_maps.get(family, np.eye(self.feature_dim))
                pred = M_t @ x_p
                total += np.sum((x_c - pred) ** 2)
            result[family] = total / len(family_edges)
        return result

    def intervention_delta(
        self,
        intervention_edges: list[tuple[str, str, int]],
        cache: GoalCache,
    ) -> float:
        """Difference in residual energy between intervention and wild-type edges.

        Positive value = intervention edges fit worse than wild-type
        Negative value = intervention edges fit better (unusual)
        Zero = no difference

        Large positive deltas suggest interventions force the search into
        less predictable territory (novel tactic combinations).
        """
        if not intervention_edges:
            return 0.0
        total, count = 0.0, 0
        for parent_sig, child_sig, family in intervention_edges:
            x_p = self._standardize(cache.get_features(parent_sig))
            x_c = self._standardize(cache.get_features(child_sig))
            M_t = self.transform_maps.get(family, np.eye(self.feature_dim))
            pred = M_t @ x_p
            total += np.sum((x_c - pred) ** 2)
            count += 1
        intervention_residual = total / count if count > 0 else 0.0
        baseline = self.residual_energy(cache)
        return intervention_residual - baseline
