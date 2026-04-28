from __future__ import annotations

import copy
import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


JsonValue = Any


def _stable_seed(base_seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _normalize_distribution(
    distribution: Mapping[Any, float],
    *,
    label: str,
) -> dict[Any, float]:
    if not distribution:
        raise ValueError(f"{label} distribution must be non-empty")
    total = 0.0
    normalized: dict[Any, float] = {}
    for key, weight in distribution.items():
        value = float(weight)
        if value < 0:
            raise ValueError(f"{label} distribution weights must be >= 0")
        if value == 0:
            continue
        normalized[key] = value
        total += value
    if total <= 0:
        raise ValueError(f"{label} distribution must have positive total mass")
    for key in list(normalized):
        normalized[key] = normalized[key] / total
    return normalized


def _sample_from_distribution(
    distribution: Mapping[Any, float],
    *,
    label: str,
    rng: random.Random,
) -> Any:
    normalized = _normalize_distribution(distribution, label=label)
    threshold = rng.random()
    cumulative = 0.0
    last_key: Any | None = None
    for key, probability in normalized.items():
        cumulative += probability
        last_key = key
        if threshold <= cumulative:
            return key
    if last_key is None:
        raise RuntimeError(f"{label} distribution sampling failed")
    return last_key


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        raise ValueError("mean over empty collection")
    return sum(items) / len(items)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("quantile over empty collection")
    if q < 0.0 or q > 1.0:
        raise ValueError(f"quantile q must be in [0, 1] (got {q})")

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = q * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]

    weight = position - lower
    return (1 - weight) * sorted_values[lower] + weight * sorted_values[upper]


@dataclass(frozen=True)
class PairedTrial:
    agent_cost: float
    agent_solved: bool
    blind_cost: float
    blind_solved: bool
    agent_observed_cost: float | None = None
    blind_observed_cost: float | None = None
    trial_seed: int | None = None
    initial_state: JsonValue | None = None
    agent_stop_reason: str | None = None
    blind_stop_reason: str | None = None


@dataclass(frozen=True)
class PolicySpec:
    name: str
    operator_semantics: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("policy name must be non-empty")
        if not self.operator_semantics.strip():
            raise ValueError("operator_semantics must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "operator_semantics": self.operator_semantics,
            "description": self.description,
        }


@dataclass(frozen=True)
class OperatorCostSpec:
    default_cost: float = 1.0
    per_operator: tuple[tuple[str, float], ...] = ()
    description: str | None = None
    state_dependent: bool = False

    def __post_init__(self) -> None:
        default_cost = float(self.default_cost)
        if default_cost < 0:
            raise ValueError(f"default_cost must be >= 0 (got {default_cost})")
        normalized: list[tuple[str, float]] = []
        seen: set[str] = set()
        for operator_name, cost in self.per_operator:
            name = str(operator_name)
            if not name.strip():
                raise ValueError("operator cost keys must be non-empty")
            value = float(cost)
            if value < 0:
                raise ValueError(f"operator cost must be >= 0 (got {value})")
            if name in seen:
                raise ValueError(f"duplicate operator cost entry for {name!r}")
            seen.add(name)
            normalized.append((name, value))

        object.__setattr__(self, "default_cost", default_cost)
        object.__setattr__(self, "per_operator", tuple(normalized))

    @classmethod
    def from_payload(cls, raw: float | int | Mapping[str, Any]) -> OperatorCostSpec:
        if isinstance(raw, (float, int)):
            return cls(default_cost=float(raw))
        if not isinstance(raw, Mapping):
            raise ValueError("w must be a number or an object")

        by_operator_raw = raw.get("by_operator", {})
        if not isinstance(by_operator_raw, Mapping):
            raise ValueError("w.by_operator must be an object")
        by_operator = tuple(
            (str(operator_name), float(cost))
            for operator_name, cost in by_operator_raw.items()
        )
        return cls(
            default_cost=float(raw.get("default", 1.0)),
            per_operator=by_operator,
            description=(
                str(raw["description"]) if raw.get("description") is not None else None
            ),
            state_dependent=bool(raw.get("state_dependent", False)),
        )

    @property
    def by_operator(self) -> dict[str, float]:
        return dict(self.per_operator)

    def cost_for_operator(self, operator_name: str) -> float:
        return self.by_operator.get(operator_name, self.default_cost)

    def to_dict(self, *, unit: str) -> dict[str, Any]:
        return {
            "default": self.default_cost,
            "by_operator": self.by_operator,
            "description": self.description,
            "state_dependent": self.state_dependent,
            "unit": unit,
        }


@dataclass(frozen=True)
class ProblemExecutor:
    initial_state_sampler: Callable[[random.Random], Any] | None = None
    initial_state_distribution: Callable[[], Mapping[Any, float]] | None = None
    is_goal: Callable[[Any], bool] | None = None
    applicable_operators: Callable[[Any], Sequence[Any]] | None = None
    apply_operator: Callable[[Any, Any, random.Random], Any] | None = None
    transition_distribution: Callable[[Any, Any], Mapping[Any, float]] | None = None
    enumerate_states: Callable[[], Sequence[Any]] | None = None
    evaluate: Callable[[Any], float] | None = None
    operator_cost: Callable[[Any, Any, Any], float] | None = None
    horizon_increment: Callable[[Any, Any, Any], float] | None = None
    state_serializer: Callable[[Any], JsonValue] = repr
    operator_serializer: Callable[[Any], str] = str

    def __post_init__(self) -> None:
        if self.initial_state_sampler is None and self.initial_state_distribution is None:
            raise ValueError(
                "executor must provide initial_state_sampler or initial_state_distribution"
            )
        if self.is_goal is None:
            raise ValueError("executor must provide is_goal")
        if self.applicable_operators is None:
            raise ValueError("executor must provide applicable_operators")
        if self.apply_operator is None and self.transition_distribution is None:
            raise ValueError("executor must provide apply_operator or transition_distribution")


@dataclass(frozen=True)
class ProblemSpace:
    S: str
    operators: tuple[str, ...]
    C: tuple[str, ...]
    E: str
    H: float
    H_unit: str
    w: float | OperatorCostSpec = 1.0
    w_unit: str | None = None
    S_init: str | None = None
    S_goal: str | None = None
    executor: ProblemExecutor | None = None

    def __post_init__(self) -> None:
        if not self.S.strip():
            raise ValueError("S must be non-empty")
        if not self.E.strip():
            raise ValueError("E must be non-empty")
        if self.H <= 0:
            raise ValueError(f"H must be > 0 (got {self.H})")
        if not self.H_unit.strip():
            raise ValueError("H_unit must be non-empty")

        operators = tuple(self.operators)
        constraints = tuple(self.C)
        if not operators:
            raise ValueError("O must contain at least one operator descriptor")
        if any(not op.strip() for op in operators):
            raise ValueError("all O entries must be non-empty")
        if any(not c.strip() for c in constraints):
            raise ValueError("all C entries must be non-empty")

        if isinstance(self.w, OperatorCostSpec):
            cost_spec = self.w
        else:
            cost_spec = OperatorCostSpec(default_cost=float(self.w))

        unknown_operators = [
            operator_name
            for operator_name in cost_spec.by_operator
            if operator_name not in operators
        ]
        if unknown_operators:
            raise ValueError(
                "operator costs reference unknown operators: "
                + ", ".join(sorted(unknown_operators))
            )

        object.__setattr__(self, "operators", operators)
        object.__setattr__(self, "C", constraints)
        object.__setattr__(self, "_cost_spec", cost_spec)

    @property
    def cost_spec(self) -> OperatorCostSpec:
        return getattr(self, "_cost_spec")

    @property
    def effective_w_unit(self) -> str:
        return self.w_unit if self.w_unit is not None else self.H_unit

    @property
    def is_executable(self) -> bool:
        return self.executor is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "P": {
                "S": self.S,
                "O": list(self.operators),
                "C": list(self.C),
                "E": self.E,
                "H": float(self.H),
            },
            "S_init": self.S_init,
            "S_goal": self.S_goal,
            "H": float(self.H),
            "H_unit": self.H_unit,
            "w": self.cost_spec.to_dict(unit=self.effective_w_unit),
            "executable": self.is_executable,
        }

    def _require_executor(self) -> ProblemExecutor:
        if self.executor is None:
            raise ValueError("problem_space is descriptive only; no executor is attached")
        return self.executor

    def serialize_state(self, state: Any) -> JsonValue:
        executor = self._require_executor()
        return executor.state_serializer(state)

    def serialize_operator(self, operator: Any) -> str:
        executor = self._require_executor()
        return executor.operator_serializer(operator)

    def sample_initial_state(self, *, rng: random.Random) -> Any:
        executor = self._require_executor()
        if executor.initial_state_sampler is not None:
            return executor.initial_state_sampler(rng)
        distribution = executor.initial_state_distribution
        if distribution is None:
            raise ValueError("executor does not define an initial-state source")
        return _sample_from_distribution(
            distribution(),
            label="initial_state",
            rng=rng,
        )

    def get_initial_state_distribution(self) -> dict[Any, float]:
        executor = self._require_executor()
        if executor.initial_state_distribution is None:
            raise ValueError("executor does not define initial_state_distribution")
        return _normalize_distribution(
            executor.initial_state_distribution(),
            label="initial_state",
        )

    def is_goal_state(self, state: Any) -> bool:
        executor = self._require_executor()
        if executor.is_goal is None:
            raise ValueError("executor does not define is_goal")
        return bool(executor.is_goal(state))

    def applicable_operator_set(self, state: Any) -> tuple[Any, ...]:
        executor = self._require_executor()
        if executor.applicable_operators is None:
            raise ValueError("executor does not define applicable_operators")
        return tuple(executor.applicable_operators(state))

    def evaluate_state(self, state: Any) -> float | None:
        executor = self._require_executor()
        if executor.evaluate is None:
            return None
        return float(executor.evaluate(state))

    def apply_operator_once(
        self,
        state: Any,
        operator: Any,
        *,
        rng: random.Random,
    ) -> Any:
        executor = self._require_executor()
        if executor.apply_operator is None:
            raise ValueError("executor does not define apply_operator")
        return executor.apply_operator(state, operator, rng)

    def transition_kernel(self, state: Any, operator: Any) -> dict[Any, float]:
        executor = self._require_executor()
        if executor.transition_distribution is not None:
            return _normalize_distribution(
                executor.transition_distribution(state, operator),
                label="transition",
            )
        if executor.apply_operator is None:
            raise ValueError("executor does not define transition dynamics")
        next_state = executor.apply_operator(state, operator, random.Random(0))
        return {next_state: 1.0}

    def operator_cost_for_transition(self, state: Any, operator: Any, next_state: Any) -> float:
        executor = self.executor
        if executor is not None and executor.operator_cost is not None:
            cost = float(executor.operator_cost(state, operator, next_state))
        else:
            operator_name = str(operator)
            if executor is not None:
                operator_name = executor.operator_serializer(operator)
            cost = self.cost_spec.cost_for_operator(operator_name)
        if cost < 0:
            raise ValueError(f"operator cost must be >= 0 (got {cost})")
        return cost

    def horizon_increment_for_transition(
        self,
        state: Any,
        operator: Any,
        next_state: Any,
    ) -> float:
        executor = self.executor
        if executor is not None and executor.horizon_increment is not None:
            increment = float(executor.horizon_increment(state, operator, next_state))
        else:
            increment = 1.0
        if increment <= 0:
            raise ValueError(f"horizon increment must be > 0 (got {increment})")
        return increment

    def enumerate_all_states(self) -> tuple[Any, ...]:
        executor = self._require_executor()
        if executor.enumerate_states is None:
            raise ValueError("executor does not define enumerate_states")
        return tuple(executor.enumerate_states())


@dataclass(frozen=True)
class ExecutablePolicy:
    spec: PolicySpec
    choose_operator: Callable[[ProblemSpace, Any, random.Random], Any]
    operator_distribution: Callable[[ProblemSpace, Any], Mapping[Any, float]] | None = None

    def sample_operator(self, problem_space: ProblemSpace, state: Any, rng: random.Random) -> Any:
        return self.choose_operator(problem_space, state, rng)

    def get_operator_distribution(
        self,
        problem_space: ProblemSpace,
        state: Any,
    ) -> dict[Any, float]:
        if self.operator_distribution is None:
            raise ValueError(
                f"policy {self.spec.name!r} does not define operator_distribution"
            )
        return _normalize_distribution(
            self.operator_distribution(problem_space, state),
            label=f"{self.spec.name}.operator_distribution",
        )


@dataclass(frozen=True)
class TraceStep:
    step_index: int
    state_before: JsonValue
    operator: str
    state_after: JsonValue
    step_cost: float
    cumulative_cost: float
    horizon_used: float
    evaluation_after: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "state_before": self.state_before,
            "operator": self.operator,
            "state_after": self.state_after,
            "step_cost": self.step_cost,
            "cumulative_cost": self.cumulative_cost,
            "horizon_used": self.horizon_used,
            "evaluation_after": self.evaluation_after,
        }


@dataclass(frozen=True)
class PolicyRun:
    policy: PolicySpec
    seed: int
    solved: bool
    total_cost: float
    horizon_used: float
    steps: int
    stop_reason: str
    initial_state: JsonValue
    final_state: JsonValue
    trace: tuple[TraceStep, ...] = ()

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        out = {
            "policy": self.policy.to_dict(),
            "seed": self.seed,
            "solved": self.solved,
            "total_cost": self.total_cost,
            "horizon_used": self.horizon_used,
            "steps": self.steps,
            "stop_reason": self.stop_reason,
            "initial_state": self.initial_state,
            "final_state": self.final_state,
        }
        if include_trace:
            out["trace"] = [step.to_dict() for step in self.trace]
        return out


@dataclass(frozen=True)
class PairedRun:
    trial_index: int
    trial_seed: int
    initial_state: JsonValue
    agent: PolicyRun
    blind: PolicyRun

    def to_paired_trial(self) -> PairedTrial:
        return PairedTrial(
            agent_cost=self.agent.total_cost,
            agent_solved=self.agent.solved,
            blind_cost=self.blind.total_cost,
            blind_solved=self.blind.solved,
            agent_observed_cost=self.agent.total_cost,
            blind_observed_cost=self.blind.total_cost,
            trial_seed=self.trial_seed,
            initial_state=self.initial_state,
            agent_stop_reason=self.agent.stop_reason,
            blind_stop_reason=self.blind.stop_reason,
        )

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        return {
            "trial_index": self.trial_index,
            "trial_seed": self.trial_seed,
            "initial_state": self.initial_state,
            "agent": self.agent.to_dict(include_trace=include_trace),
            "blind": self.blind.to_dict(include_trace=include_trace),
        }


def k_log10_ratio(*, tau_blind: float, tau_agent: float) -> float:
    if tau_blind <= 0 or tau_agent <= 0:
        raise ValueError(f"taus must be > 0 (tau_blind={tau_blind}, tau_agent={tau_agent})")
    return math.log10(tau_blind / tau_agent)


def _observed_cost(trial: PairedTrial, *, side: str, problem_space: ProblemSpace) -> float:
    if side == "agent":
        solved = trial.agent_solved
        cost = float(trial.agent_cost)
        observed = trial.agent_observed_cost
    elif side == "blind":
        solved = trial.blind_solved
        cost = float(trial.blind_cost)
        observed = trial.blind_observed_cost
    else:
        raise ValueError(f"unknown side: {side}")

    if solved:
        return cost
    if observed is not None:
        return float(observed)
    return float(problem_space.H)


def _resolve_problem_space(
    *,
    problem_space: ProblemSpace | None,
    H: float | None,
    H_unit: str | None,
    w: float | Mapping[str, Any] | None,
    w_unit: str | None,
) -> ProblemSpace:
    if problem_space is None:
        if H is None:
            raise ValueError("H is required when problem_space is not provided")
        if H_unit is None:
            raise ValueError("H_unit is required when problem_space is not provided")
        effective_w = (
            OperatorCostSpec(default_cost=1.0)
            if w is None
            else OperatorCostSpec.from_payload(w)
        )
        return ProblemSpace(
            S="unspecified_state_space",
            operators=("unspecified_operator",),
            C=(),
            E="unspecified_evaluation",
            H=float(H),
            H_unit=H_unit,
            w=effective_w,
            w_unit=w_unit,
        )

    if H is not None and not math.isclose(float(H), float(problem_space.H)):
        raise ValueError("H conflicts with problem_space.H")
    if H_unit is not None and H_unit.strip() != problem_space.H_unit:
        raise ValueError("H_unit conflicts with problem_space.H_unit")
    if w is not None:
        requested = OperatorCostSpec.from_payload(w)
        if requested != problem_space.cost_spec:
            raise ValueError("w conflicts with problem_space.w")
    if w_unit is not None and w_unit != problem_space.effective_w_unit:
        raise ValueError("w_unit conflicts with problem_space.w_unit")
    return problem_space


def _resolve_policies(
    *,
    agent_policy: str,
    blind_policy: str,
    agent_policy_spec: PolicySpec | None,
    blind_policy_spec: PolicySpec | None,
) -> tuple[str, str, dict[str, Any] | None]:
    if (agent_policy_spec is None) ^ (blind_policy_spec is None):
        raise ValueError("agent_policy_spec and blind_policy_spec must be provided together")

    if agent_policy_spec is None or blind_policy_spec is None:
        if not agent_policy.strip() or not blind_policy.strip():
            raise ValueError("policy names must be non-empty")
        return agent_policy, blind_policy, None

    if agent_policy_spec.operator_semantics != blind_policy_spec.operator_semantics:
        raise ValueError(
            "agent and blind policies must share operator semantics in the same problem space"
        )
    return (
        agent_policy_spec.name,
        blind_policy_spec.name,
        {
            "shared_operator_semantics": agent_policy_spec.operator_semantics,
            "agent_spec": agent_policy_spec.to_dict(),
            "blind_spec": blind_policy_spec.to_dict(),
        },
    )


def _kaplan_meier_summary(
    observations: Sequence[tuple[float, bool]],
) -> dict[str, Any]:
    if not observations:
        raise ValueError("kaplan_meier_summary requires non-empty observations")

    ordered = sorted(observations, key=lambda item: item[0])
    n_at_risk = len(ordered)
    survival = 1.0
    cursor = 0
    points: list[dict[str, Any]] = []
    while cursor < len(ordered):
        time = ordered[cursor][0]
        events = 0
        censored = 0
        while cursor < len(ordered) and ordered[cursor][0] == time:
            if ordered[cursor][1]:
                events += 1
            else:
                censored += 1
            cursor += 1
        if events > 0:
            survival *= 1.0 - (events / n_at_risk)
        points.append(
            {
                "time": time,
                "n_at_risk": n_at_risk,
                "events": events,
                "censored": censored,
                "survival": survival,
            }
        )
        n_at_risk -= events + censored

    median = None
    for point in points:
        if point["survival"] <= 0.5:
            median = point["time"]
            break
    return {
        "n": len(observations),
        "events": sum(1 for _, solved in observations if solved),
        "censored": sum(1 for _, solved in observations if not solved),
        "median_if_identifiable": median,
        "points": points,
    }


def _bootstrap_sample(
    trials: Sequence[PairedTrial],
    *,
    problem_space: ProblemSpace,
    rng: random.Random,
) -> tuple[float, float, float, float | None]:
    resampled = [trials[rng.randrange(len(trials))] for _ in range(len(trials))]

    agent_observed = [
        _observed_cost(t, side="agent", problem_space=problem_space) for t in resampled
    ]
    blind_observed = [
        _observed_cost(t, side="blind", problem_space=problem_space) for t in resampled
    ]
    both_solved_agent: list[float] = []
    both_solved_blind: list[float] = []
    for trial in resampled:
        if trial.agent_solved and trial.blind_solved:
            both_solved_agent.append(float(trial.agent_cost))
            both_solved_blind.append(float(trial.blind_cost))

    tau_agent_restricted = _mean(agent_observed)
    tau_blind_restricted = _mean(blind_observed)
    k_restricted = k_log10_ratio(
        tau_blind=tau_blind_restricted,
        tau_agent=tau_agent_restricted,
    )

    k_both = None
    if both_solved_agent and both_solved_blind:
        tau_agent_mean_both = _mean(both_solved_agent)
        tau_blind_mean_both = _mean(both_solved_blind)
        if tau_agent_mean_both > 0 and tau_blind_mean_both > 0:
            k_both = k_log10_ratio(
                tau_blind=tau_blind_mean_both,
                tau_agent=tau_agent_mean_both,
            )

    return tau_agent_restricted, tau_blind_restricted, k_restricted, k_both


def paper_k_from_paired_trials(
    trials: Sequence[PairedTrial],
    *,
    H: float | None = None,
    H_unit: str | None = None,
    agent_policy: str = "agent",
    blind_policy: str = "blind_uniform",
    w: float | Mapping[str, Any] | None = None,
    w_unit: str | None = None,
    problem_space: ProblemSpace | None = None,
    agent_policy_spec: PolicySpec | None = None,
    blind_policy_spec: PolicySpec | None = None,
    schema_version: int = 2,
    bootstrap_samples: int = 0,
    bootstrap_ci_level: float = 0.95,
    bootstrap_seed: int | None = None,
) -> dict[str, Any]:
    if not trials:
        raise ValueError("trials must be non-empty")
    if bootstrap_samples < 0:
        raise ValueError(f"bootstrap_samples must be >= 0 (got {bootstrap_samples})")
    if bootstrap_ci_level <= 0 or bootstrap_ci_level >= 1:
        raise ValueError(
            f"bootstrap_ci_level must be in (0, 1) (got {bootstrap_ci_level})"
        )

    ps = _resolve_problem_space(
        problem_space=problem_space,
        H=H,
        H_unit=H_unit,
        w=w,
        w_unit=w_unit,
    )
    effective_agent_policy, effective_blind_policy, policy_meta = _resolve_policies(
        agent_policy=agent_policy,
        blind_policy=blind_policy,
        agent_policy_spec=agent_policy_spec,
        blind_policy_spec=blind_policy_spec,
    )

    agent_observed: list[float] = []
    blind_observed: list[float] = []
    both_solved_agent: list[float] = []
    both_solved_blind: list[float] = []
    n_agent_solved = 0
    n_blind_solved = 0
    n_both_solved = 0

    for trial in trials:
        if trial.agent_cost < 0 or trial.blind_cost < 0:
            raise ValueError("costs must be >= 0")

        agent_cost_observed = _observed_cost(trial, side="agent", problem_space=ps)
        blind_cost_observed = _observed_cost(trial, side="blind", problem_space=ps)
        if agent_cost_observed < 0 or blind_cost_observed < 0:
            raise ValueError("observed costs must be >= 0")

        agent_observed.append(agent_cost_observed)
        blind_observed.append(blind_cost_observed)
        if trial.agent_solved:
            n_agent_solved += 1
        if trial.blind_solved:
            n_blind_solved += 1
        if trial.agent_solved and trial.blind_solved:
            n_both_solved += 1
            both_solved_agent.append(float(trial.agent_cost))
            both_solved_blind.append(float(trial.blind_cost))

    tau_agent_restricted = _mean(agent_observed)
    tau_blind_restricted = _mean(blind_observed)
    k_restricted = k_log10_ratio(
        tau_blind=tau_blind_restricted,
        tau_agent=tau_agent_restricted,
    )

    tau_agent_mean_both = None
    tau_blind_mean_both = None
    k_both = None
    if both_solved_agent and both_solved_blind:
        tau_agent_mean_both = _mean(both_solved_agent)
        tau_blind_mean_both = _mean(both_solved_blind)
        if tau_agent_mean_both > 0 and tau_blind_mean_both > 0:
            k_both = k_log10_ratio(
                tau_blind=tau_blind_mean_both,
                tau_agent=tau_agent_mean_both,
            )

    uncertainty: dict[str, Any] = {
        "bootstrap_samples": int(bootstrap_samples),
        "bootstrap_ci_level": float(bootstrap_ci_level),
        "bootstrap_seed": bootstrap_seed,
        "K_restricted_mean_ci": None,
        "K_lower_bound_censored_at_H_ci": None,
        "K_conditional_both_solved_ci": None,
        "tau_agent_restricted_mean_ci": None,
        "tau_blind_restricted_mean_ci": None,
        "tau_agent_mean_censored_ci": None,
        "tau_blind_mean_censored_ci": None,
    }
    if bootstrap_samples > 0:
        rng = random.Random(bootstrap_seed)
        alpha = (1.0 - bootstrap_ci_level) / 2.0

        boot_tau_agent: list[float] = []
        boot_tau_blind: list[float] = []
        boot_k_restricted: list[float] = []
        boot_k_both: list[float] = []
        for _ in range(bootstrap_samples):
            tau_agent_boot, tau_blind_boot, k_restricted_boot, k_both_boot = _bootstrap_sample(
                trials,
                problem_space=ps,
                rng=rng,
            )
            boot_tau_agent.append(tau_agent_boot)
            boot_tau_blind.append(tau_blind_boot)
            boot_k_restricted.append(k_restricted_boot)
            if k_both_boot is not None:
                boot_k_both.append(k_both_boot)

        boot_tau_agent.sort()
        boot_tau_blind.sort()
        boot_k_restricted.sort()

        restricted_ci = [
            _quantile(boot_k_restricted, alpha),
            _quantile(boot_k_restricted, 1.0 - alpha),
        ]
        uncertainty["K_restricted_mean_ci"] = restricted_ci
        uncertainty["K_lower_bound_censored_at_H_ci"] = restricted_ci

        agent_ci = [
            _quantile(boot_tau_agent, alpha),
            _quantile(boot_tau_agent, 1.0 - alpha),
        ]
        blind_ci = [
            _quantile(boot_tau_blind, alpha),
            _quantile(boot_tau_blind, 1.0 - alpha),
        ]
        uncertainty["tau_agent_restricted_mean_ci"] = agent_ci
        uncertainty["tau_blind_restricted_mean_ci"] = blind_ci
        uncertainty["tau_agent_mean_censored_ci"] = agent_ci
        uncertainty["tau_blind_mean_censored_ci"] = blind_ci

        if boot_k_both:
            boot_k_both.sort()
            uncertainty["K_conditional_both_solved_ci"] = [
                _quantile(boot_k_both, alpha),
                _quantile(boot_k_both, 1.0 - alpha),
            ]

    agent_observations = list(
        zip(agent_observed, [trial.agent_solved for trial in trials], strict=True)
    )
    blind_observations = list(
        zip(blind_observed, [trial.blind_solved for trial in trials], strict=True)
    )

    out = {
        "schema_version": int(schema_version),
        "K": {
            "restricted_mean_at_stop": k_restricted,
            "lower_bound_censored_at_H": k_restricted,
            "conditional_on_both_solved": k_both,
        },
        "problem_space": {**ps.to_dict()},
        "policies": {
            "agent": effective_agent_policy,
            "blind": effective_blind_policy,
        },
        "tau": {
            "agent_restricted_mean": tau_agent_restricted,
            "blind_restricted_mean": tau_blind_restricted,
            "agent_mean_censored": tau_agent_restricted,
            "blind_mean_censored": tau_blind_restricted,
            "agent_mean_both_solved": tau_agent_mean_both,
            "blind_mean_both_solved": tau_blind_mean_both,
        },
        "solve_rates": {
            "agent": n_agent_solved / len(trials),
            "blind": n_blind_solved / len(trials),
            "both_solved": n_both_solved / len(trials),
        },
        "counts": {
            "trials": len(trials),
            "agent_solved": n_agent_solved,
            "blind_solved": n_blind_solved,
            "both_solved": n_both_solved,
        },
        "censoring": {
            "estimand": "restricted_mean_cost_up_to_observed_stop",
            "agent_censored_fraction": 1.0 - (n_agent_solved / len(trials)),
            "blind_censored_fraction": 1.0 - (n_blind_solved / len(trials)),
            "agent_kaplan_meier": _kaplan_meier_summary(agent_observations),
            "blind_kaplan_meier": _kaplan_meier_summary(blind_observations),
        },
        "notes": [
            "restricted_mean_at_stop is a horizon-limited lower bound on the full expected cost",
            "conditional_on_both_solved is computed on the paired subset where both policies solve",
        ],
        "uncertainty": uncertainty,
    }

    if policy_meta is not None:
        out["policies"]["shared_operator_semantics"] = policy_meta["shared_operator_semantics"]
        out["policies"]["agent_spec"] = policy_meta["agent_spec"]
        out["policies"]["blind_spec"] = policy_meta["blind_spec"]
    return out


def paper_k_from_expectations(
    *,
    tau_agent: float,
    tau_blind: float,
    H: float | None = None,
    H_unit: str | None = None,
    agent_policy: str = "agent",
    blind_policy: str = "blind_uniform",
    w: float | Mapping[str, Any] | None = None,
    w_unit: str | None = None,
    problem_space: ProblemSpace | None = None,
    agent_policy_spec: PolicySpec | None = None,
    blind_policy_spec: PolicySpec | None = None,
    schema_version: int = 2,
) -> dict[str, Any]:
    trial = PairedTrial(
        agent_cost=float(tau_agent),
        agent_solved=True,
        blind_cost=float(tau_blind),
        blind_solved=True,
        agent_observed_cost=float(tau_agent),
        blind_observed_cost=float(tau_blind),
    )
    out = paper_k_from_paired_trials(
        [trial],
        H=H,
        H_unit=H_unit,
        agent_policy=agent_policy,
        blind_policy=blind_policy,
        w=w,
        w_unit=w_unit,
        problem_space=problem_space,
        agent_policy_spec=agent_policy_spec,
        blind_policy_spec=blind_policy_spec,
        schema_version=schema_version,
    )
    out["notes"].append("computed directly from expected costs (single-trial expectation encoding)")
    return out


def run_policy(
    problem_space: ProblemSpace,
    policy: ExecutablePolicy,
    *,
    initial_state: Any,
    seed: int,
    record_trace: bool = False,
    max_trace_steps: int = 25,
) -> PolicyRun:
    if not problem_space.is_executable:
        raise ValueError("problem_space must be executable to run a policy")

    rng = random.Random(seed)
    state = copy.deepcopy(initial_state)
    initial_state_json = problem_space.serialize_state(copy.deepcopy(initial_state))

    if problem_space.is_goal_state(state):
        return PolicyRun(
            policy=policy.spec,
            seed=seed,
            solved=True,
            total_cost=0.0,
            horizon_used=0.0,
            steps=0,
            stop_reason="already_at_goal",
            initial_state=initial_state_json,
            final_state=problem_space.serialize_state(state),
            trace=(),
        )

    trace: list[TraceStep] = []
    total_cost = 0.0
    horizon_used = 0.0
    steps = 0
    stop_reason = "horizon_exhausted"
    solved = False

    while True:
        operators = problem_space.applicable_operator_set(state)
        if not operators:
            stop_reason = "no_applicable_operator"
            break

        operator = policy.sample_operator(problem_space, state, rng)
        if operator not in operators:
            raise ValueError(
                f"policy {policy.spec.name!r} selected an operator outside the admissible set"
            )

        next_state = problem_space.apply_operator_once(state, operator, rng=rng)
        increment = problem_space.horizon_increment_for_transition(state, operator, next_state)
        if horizon_used + increment > problem_space.H + 1e-12:
            stop_reason = "horizon_exhausted"
            break

        step_cost = problem_space.operator_cost_for_transition(state, operator, next_state)
        total_cost += step_cost
        horizon_used += increment
        steps += 1

        if record_trace and len(trace) < max_trace_steps:
            trace.append(
                TraceStep(
                    step_index=steps,
                    state_before=problem_space.serialize_state(state),
                    operator=problem_space.serialize_operator(operator),
                    state_after=problem_space.serialize_state(next_state),
                    step_cost=step_cost,
                    cumulative_cost=total_cost,
                    horizon_used=horizon_used,
                    evaluation_after=problem_space.evaluate_state(next_state),
                )
            )

        state = next_state
        if problem_space.is_goal_state(state):
            solved = True
            stop_reason = "goal_reached"
            break
        if horizon_used >= problem_space.H - 1e-12:
            stop_reason = "horizon_exhausted"
            break

    return PolicyRun(
        policy=policy.spec,
        seed=seed,
        solved=solved,
        total_cost=total_cost,
        horizon_used=horizon_used,
        steps=steps,
        stop_reason=stop_reason,
        initial_state=initial_state_json,
        final_state=problem_space.serialize_state(state),
        trace=tuple(trace),
    )


def run_paired_trial(
    problem_space: ProblemSpace,
    agent_policy: ExecutablePolicy,
    blind_policy: ExecutablePolicy,
    *,
    trial_index: int,
    trial_seed: int,
    record_trace: bool = False,
    max_trace_steps: int = 25,
) -> PairedRun:
    init_rng = random.Random(_stable_seed(trial_seed, "initial_state"))
    initial_state = problem_space.sample_initial_state(rng=init_rng)
    initial_state_json = problem_space.serialize_state(copy.deepcopy(initial_state))

    agent_run = run_policy(
        problem_space,
        agent_policy,
        initial_state=copy.deepcopy(initial_state),
        seed=_stable_seed(trial_seed, "agent"),
        record_trace=record_trace,
        max_trace_steps=max_trace_steps,
    )
    blind_run = run_policy(
        problem_space,
        blind_policy,
        initial_state=copy.deepcopy(initial_state),
        seed=_stable_seed(trial_seed, f"blind:{blind_policy.spec.name}"),
        record_trace=record_trace,
        max_trace_steps=max_trace_steps,
    )
    return PairedRun(
        trial_index=trial_index,
        trial_seed=trial_seed,
        initial_state=initial_state_json,
        agent=agent_run,
        blind=blind_run,
    )


def _exact_policy_state_tables(
    problem_space: ProblemSpace,
    policy: ExecutablePolicy,
) -> dict[Any, dict[str, list[float]]]:
    if not problem_space.is_executable:
        raise ValueError("exact finite-horizon metrics require an executable problem_space")
    states = problem_space.enumerate_all_states()
    if not states:
        raise ValueError("exact finite-horizon metrics require a non-empty state set")

    horizon = int(problem_space.H)
    if not math.isclose(problem_space.H, float(horizon)):
        raise ValueError("exact finite-horizon metrics require integer-valued H")

    tables: dict[Any, dict[str, list[float]]] = {}
    for state in states:
        tables[state] = {
            "solve_prob": [0.0] * (horizon + 1),
            "restricted_cost": [0.0] * (horizon + 1),
            "solve_cost_mass": [0.0] * (horizon + 1),
        }

    for remaining in range(horizon + 1):
        for state in states:
            record = tables[state]
            if problem_space.is_goal_state(state):
                record["solve_prob"][remaining] = 1.0
                record["restricted_cost"][remaining] = 0.0
                record["solve_cost_mass"][remaining] = 0.0
                continue
            if remaining == 0:
                continue

            try:
                operator_distribution = policy.get_operator_distribution(problem_space, state)
            except ValueError:
                operator_distribution = {}
            if not operator_distribution:
                continue

            solve_prob = 0.0
            restricted_cost = 0.0
            solve_cost_mass = 0.0
            for operator, p_operator in operator_distribution.items():
                transition_distribution = problem_space.transition_kernel(state, operator)
                for next_state, p_next in transition_distribution.items():
                    increment = problem_space.horizon_increment_for_transition(
                        state,
                        operator,
                        next_state,
                    )
                    if not math.isclose(increment, round(increment)):
                        raise ValueError(
                            "exact finite-horizon metrics require integer horizon increments"
                        )
                    increment_int = int(round(increment))
                    if increment_int > remaining:
                        continue

                    next_remaining = remaining - increment_int
                    step_cost = problem_space.operator_cost_for_transition(state, operator, next_state)
                    next_record = tables[next_state]
                    probability = p_operator * p_next
                    solve_prob += probability * next_record["solve_prob"][next_remaining]
                    restricted_cost += probability * (
                        step_cost + next_record["restricted_cost"][next_remaining]
                    )
                    solve_cost_mass += probability * (
                        step_cost * next_record["solve_prob"][next_remaining]
                        + next_record["solve_cost_mass"][next_remaining]
                    )

            record["solve_prob"][remaining] = solve_prob
            record["restricted_cost"][remaining] = restricted_cost
            record["solve_cost_mass"][remaining] = solve_cost_mass

    return tables


def exact_finite_horizon_metrics(
    problem_space: ProblemSpace,
    agent_policy: ExecutablePolicy,
    blind_policy: ExecutablePolicy,
) -> dict[str, Any]:
    initial_distribution = problem_space.get_initial_state_distribution()
    horizon = int(problem_space.H)

    agent_tables = _exact_policy_state_tables(problem_space, agent_policy)
    blind_tables = _exact_policy_state_tables(problem_space, blind_policy)

    agent_tau = 0.0
    blind_tau = 0.0
    agent_solve_prob = 0.0
    blind_solve_prob = 0.0
    both_solve_prob = 0.0
    agent_both_cost_mass = 0.0
    blind_both_cost_mass = 0.0

    for state, probability in initial_distribution.items():
        agent_record = agent_tables[state]
        blind_record = blind_tables[state]
        agent_q = agent_record["solve_prob"][horizon]
        blind_q = blind_record["solve_prob"][horizon]
        agent_tau += probability * agent_record["restricted_cost"][horizon]
        blind_tau += probability * blind_record["restricted_cost"][horizon]
        agent_solve_prob += probability * agent_q
        blind_solve_prob += probability * blind_q
        both_solve_prob += probability * agent_q * blind_q
        agent_both_cost_mass += probability * agent_record["solve_cost_mass"][horizon] * blind_q
        blind_both_cost_mass += probability * blind_record["solve_cost_mass"][horizon] * agent_q

    tau_agent_mean_both = None
    tau_blind_mean_both = None
    k_both = None
    if both_solve_prob > 0:
        tau_agent_mean_both = agent_both_cost_mass / both_solve_prob
        tau_blind_mean_both = blind_both_cost_mass / both_solve_prob
        if tau_agent_mean_both > 0 and tau_blind_mean_both > 0:
            k_both = k_log10_ratio(
                tau_blind=tau_blind_mean_both,
                tau_agent=tau_agent_mean_both,
            )

    return {
        "K": {
            "restricted_mean_at_H_exact": k_log10_ratio(
                tau_blind=blind_tau,
                tau_agent=agent_tau,
            ),
            "conditional_on_both_solved_exact": k_both,
        },
        "tau": {
            "agent_restricted_mean_exact": agent_tau,
            "blind_restricted_mean_exact": blind_tau,
            "agent_mean_both_solved_exact": tau_agent_mean_both,
            "blind_mean_both_solved_exact": tau_blind_mean_both,
        },
        "solve_rates": {
            "agent_exact": agent_solve_prob,
            "blind_exact": blind_solve_prob,
            "both_solved_exact": both_solve_prob,
        },
        "notes": [
            "exact finite-horizon metrics use the executable problem graph and policy distributions",
        ],
    }


def compare_policies_in_problem_space(
    problem_space: ProblemSpace,
    agent_policy: ExecutablePolicy,
    blind_policy: ExecutablePolicy,
    *,
    trials: int,
    seed: int,
    blind_policy_family: Mapping[str, ExecutablePolicy] | None = None,
    bootstrap_samples: int = 0,
    bootstrap_ci_level: float = 0.95,
    exact: bool = True,
    provenance_limit: int = 5,
    trace_trials: int = 0,
    max_trace_steps: int = 25,
) -> dict[str, Any]:
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if provenance_limit < 0:
        raise ValueError("provenance_limit must be >= 0")
    if trace_trials < 0:
        raise ValueError("trace_trials must be >= 0")

    all_blinds: dict[str, ExecutablePolicy] = {blind_policy.spec.name: blind_policy}
    if blind_policy_family is not None:
        for label, policy in blind_policy_family.items():
            if label in all_blinds and all_blinds[label] is not policy:
                raise ValueError(f"duplicate blind policy label: {label}")
            all_blinds[label] = policy

    paired_runs_by_label: dict[str, list[PairedRun]] = {label: [] for label in all_blinds}
    trial_summaries: list[dict[str, Any]] = []

    for trial_index in range(trials):
        trial_seed = _stable_seed(seed, f"trial:{trial_index}")
        init_rng = random.Random(_stable_seed(trial_seed, "initial_state"))
        initial_state = problem_space.sample_initial_state(rng=init_rng)
        initial_state_json = problem_space.serialize_state(copy.deepcopy(initial_state))

        record_trace = trial_index < trace_trials
        agent_run = run_policy(
            problem_space,
            agent_policy,
            initial_state=copy.deepcopy(initial_state),
            seed=_stable_seed(trial_seed, "agent"),
            record_trace=record_trace,
            max_trace_steps=max_trace_steps,
        )

        trial_summary = {
            "trial_index": trial_index,
            "trial_seed": trial_seed,
            "initial_state": initial_state_json,
            "agent_stop_reason": agent_run.stop_reason,
        }

        for label, policy in all_blinds.items():
            blind_run = run_policy(
                problem_space,
                policy,
                initial_state=copy.deepcopy(initial_state),
                seed=_stable_seed(trial_seed, f"blind:{label}"),
                record_trace=record_trace,
                max_trace_steps=max_trace_steps,
            )
            paired_runs_by_label[label].append(
                PairedRun(
                    trial_index=trial_index,
                    trial_seed=trial_seed,
                    initial_state=initial_state_json,
                    agent=agent_run,
                    blind=blind_run,
                )
            )
            trial_summary[f"blind_stop_reason:{label}"] = blind_run.stop_reason
        trial_summaries.append(trial_summary)

    primary_label = blind_policy.spec.name
    primary_runs = paired_runs_by_label[primary_label]
    result = paper_k_from_paired_trials(
        [paired_run.to_paired_trial() for paired_run in primary_runs],
        problem_space=problem_space,
        agent_policy_spec=agent_policy.spec,
        blind_policy_spec=blind_policy.spec,
        bootstrap_samples=bootstrap_samples,
        bootstrap_ci_level=bootstrap_ci_level,
        bootstrap_seed=seed,
    )
    result["execution"] = {
        "seed": seed,
        "paired_initial_states": True,
        "trials": trials,
        "provenance_head": trial_summaries[:provenance_limit],
    }
    if trace_trials > 0:
        result["execution"]["trace_head"] = [
            paired_run.to_dict(include_trace=True) for paired_run in primary_runs[:trace_trials]
        ]

    if len(all_blinds) > 1:
        baseline_results: dict[str, Any] = {}
        k_values: list[float] = []
        for label, policy in all_blinds.items():
            baseline_result = paper_k_from_paired_trials(
                [paired_run.to_paired_trial() for paired_run in paired_runs_by_label[label]],
                problem_space=problem_space,
                agent_policy_spec=agent_policy.spec,
                blind_policy_spec=policy.spec,
                bootstrap_samples=bootstrap_samples,
                bootstrap_ci_level=bootstrap_ci_level,
                bootstrap_seed=_stable_seed(seed, f"bootstrap:{label}"),
            )
            baseline_results[label] = {
                "blind_policy": policy.spec.to_dict(),
                "K_restricted_mean_at_stop": baseline_result["K"]["restricted_mean_at_stop"],
                "solve_rate_blind": baseline_result["solve_rates"]["blind"],
            }
            k_values.append(baseline_result["K"]["restricted_mean_at_stop"])
        result["baseline_sensitivity"] = {
            "primary_blind_policy": primary_label,
            "baselines": baseline_results,
            "K_range": [min(k_values), max(k_values)],
            "K_spread": max(k_values) - min(k_values),
        }

    if exact:
        try:
            result["exact"] = exact_finite_horizon_metrics(
                problem_space,
                agent_policy,
                blind_policy,
            )
        except ValueError as exc:
            result["exact"] = {"unsupported": str(exc)}

    return result


def compose_problem_spaces(
    *problem_spaces: ProblemSpace,
    name: str | None = None,
    horizon_mode: str = "product",
    cost_mode: str = "product",
) -> ProblemSpace:
    if len(problem_spaces) < 2:
        raise ValueError("compose_problem_spaces requires at least two factors")
    if horizon_mode not in {"product", "sum"}:
        raise ValueError("horizon_mode must be 'product' or 'sum'")
    if cost_mode not in {"product", "sum"}:
        raise ValueError("cost_mode must be 'product' or 'sum'")

    h_values = [space.H for space in problem_spaces]
    w_values = [space.cost_spec.default_cost for space in problem_spaces]
    composite_h = math.prod(h_values) if horizon_mode == "product" else sum(h_values)
    composite_w = math.prod(w_values) if cost_mode == "product" else sum(w_values)

    return ProblemSpace(
        S=name if name is not None else " x ".join(space.S for space in problem_spaces),
        operators=tuple(
            f"stage_{index}:{operator_name}"
            for index, space in enumerate(problem_spaces, start=1)
            for operator_name in space.operators
        ),
        C=tuple(
            f"factor_{index}:{constraint}"
            for index, space in enumerate(problem_spaces, start=1)
            for constraint in space.C
        ),
        E=f"{cost_mode}_composition_of(" + ", ".join(space.E for space in problem_spaces) + ")",
        H=float(composite_h),
        H_unit="composite_unit",
        w=OperatorCostSpec(
            default_cost=float(composite_w),
            description=f"{cost_mode} cost composition over stage factors",
        ),
        w_unit="composite_cost",
        S_init="product_initial_state",
        S_goal="product_goal_state",
    )


def compare_composite_k(
    *stage_results: Mapping[str, Any],
    composite_result: Mapping[str, Any],
) -> dict[str, Any]:
    if not stage_results:
        raise ValueError("compare_composite_k requires at least one stage result")
    sum_stages = sum(float(result["K"]["restricted_mean_at_stop"]) for result in stage_results)
    composite_k = float(composite_result["K"]["restricted_mean_at_stop"])
    return {
        "K_sum_stages": sum_stages,
        "K_composite": composite_k,
        "delta": abs(composite_k - sum_stages),
    }
