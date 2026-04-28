from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from core import (
    OperatorCostSpec,
    PairedTrial,
    PolicySpec,
    ProblemSpace,
    paper_k_from_paired_trials,
)


class SchemaError(ValueError):
    pass


CANONICAL_ROW_KEYS = (
    "name",
    "description",
    "K_restricted_mean_at_stop",
    "agent_restricted_mean",
    "blind_restricted_mean",
    "agent_solve_rate",
    "blind_solve_rate",
    "repeats",
    "seed",
    "mean_wall_sec",
    "min_wall_sec",
    "max_wall_sec",
    "exact_supported",
)


def _schema_error(path: str, message: str) -> SchemaError:
    return SchemaError(f"{path}: {message}")


def _require_object(raw: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise _schema_error(path, "must be an object")
    return raw


def _require_list(raw: Any, *, path: str) -> list[Any]:
    if not isinstance(raw, list):
        raise _schema_error(path, "must be an array")
    return raw


def _require_str(raw: Any, *, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise _schema_error(path, "must be a non-empty string")
    return raw


def _require_number(raw: Any, *, path: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise _schema_error(path, "must be a number")
    return float(raw)


def _require_int(raw: Any, *, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _schema_error(path, "must be an integer")
    return raw


def _require_bool(raw: Any, *, path: str) -> bool:
    if not isinstance(raw, bool):
        raise _schema_error(path, "must be a boolean")
    return raw


def _parse_trial(raw: Any, *, path: str) -> PairedTrial:
    obj = _require_object(raw, path=path)
    return PairedTrial(
        agent_cost=_require_number(obj["agent_cost"], path=f"{path}.agent_cost"),
        agent_solved=_require_bool(obj["agent_solved"], path=f"{path}.agent_solved"),
        blind_cost=_require_number(obj["blind_cost"], path=f"{path}.blind_cost"),
        blind_solved=_require_bool(obj["blind_solved"], path=f"{path}.blind_solved"),
        agent_observed_cost=(
            None
            if obj.get("agent_observed_cost") is None
            else _require_number(obj["agent_observed_cost"], path=f"{path}.agent_observed_cost")
        ),
        blind_observed_cost=(
            None
            if obj.get("blind_observed_cost") is None
            else _require_number(obj["blind_observed_cost"], path=f"{path}.blind_observed_cost")
        ),
        trial_seed=(
            None
            if obj.get("trial_seed") is None
            else _require_int(obj["trial_seed"], path=f"{path}.trial_seed")
        ),
        initial_state=obj.get("initial_state"),
        agent_stop_reason=(
            None
            if obj.get("agent_stop_reason") is None
            else _require_str(obj["agent_stop_reason"], path=f"{path}.agent_stop_reason")
        ),
        blind_stop_reason=(
            None
            if obj.get("blind_stop_reason") is None
            else _require_str(obj["blind_stop_reason"], path=f"{path}.blind_stop_reason")
        ),
    )


def _parse_operator_cost(raw: Any, *, path: str) -> float | Mapping[str, Any]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    obj = _require_object(raw, path=path)
    if "unit" in obj:
        _require_str(obj["unit"], path=f"{path}.unit")
    default = obj.get("default", 1.0)
    by_operator = obj.get("by_operator", {})
    if default is not None:
        _require_number(default, path=f"{path}.default")
    if not isinstance(by_operator, Mapping):
        raise _schema_error(f"{path}.by_operator", "must be an object")
    for operator_name, cost in by_operator.items():
        _require_str(operator_name, path=f"{path}.by_operator key")
        _require_number(cost, path=f"{path}.by_operator[{operator_name!r}]")
    if "description" in obj and obj["description"] is not None:
        _require_str(obj["description"], path=f"{path}.description")
    if "state_dependent" in obj:
        _require_bool(obj["state_dependent"], path=f"{path}.state_dependent")
    return obj


def _parse_problem_space(raw: Any, *, path: str) -> ProblemSpace | None:
    if raw is None:
        return None
    obj = _require_object(raw, path=path)

    w_raw = obj.get("w", 1.0)
    if w_raw is None:
        w_value: float | OperatorCostSpec = 1.0
    elif isinstance(w_raw, Mapping):
        w_value = OperatorCostSpec.from_payload(_parse_operator_cost(w_raw, path=f"{path}.w"))
    else:
        w_value = _require_number(w_raw, path=f"{path}.w")

    w_unit = obj.get("w_unit")
    if w_unit is not None:
        _require_str(w_unit, path=f"{path}.w_unit")
    elif isinstance(w_raw, Mapping) and w_raw.get("unit") is not None:
        w_unit = _require_str(w_raw["unit"], path=f"{path}.w.unit")

    for key in ("S", "O", "E", "H", "H_unit"):
        if key not in obj:
            raise _schema_error(f"{path}.{key}", "is required")

    return ProblemSpace(
        S=_require_str(obj["S"], path=f"{path}.S"),
        operators=tuple(
            _require_str(x, path=f"{path}.O[{i}]")
            for i, x in enumerate(_require_list(obj["O"], path=f"{path}.O"))
        ),
        C=tuple(
            _require_str(x, path=f"{path}.C[{i}]")
            for i, x in enumerate(_require_list(obj.get("C", []), path=f"{path}.C"))
        ),
        E=_require_str(obj["E"], path=f"{path}.E"),
        H=_require_number(obj["H"], path=f"{path}.H"),
        H_unit=_require_str(obj["H_unit"], path=f"{path}.H_unit"),
        w=w_value,
        w_unit=(None if w_unit is None else str(w_unit)),
        S_init=(None if obj.get("S_init") is None else str(obj["S_init"])),
        S_goal=(None if obj.get("S_goal") is None else str(obj["S_goal"])),
    )


def _parse_policy_spec(raw: Any, *, path: str) -> PolicySpec | None:
    if raw is None:
        return None
    obj = _require_object(raw, path=path)
    return PolicySpec(
        name=_require_str(obj["name"], path=f"{path}.name"),
        operator_semantics=_require_str(obj["operator_semantics"], path=f"{path}.operator_semantics"),
        description=(
            None
            if obj.get("description") is None
            else _require_str(obj["description"], path=f"{path}.description")
        ),
    )


@dataclass(frozen=True)
class ComputeRequest:
    name: str | None
    trials: tuple[PairedTrial, ...]
    problem_space: ProblemSpace | None
    H: float | None
    H_unit: str | None
    w: float | Mapping[str, Any] | None
    w_unit: str | None
    agent_policy: str
    blind_policy: str
    agent_policy_spec: PolicySpec | None
    blind_policy_spec: PolicySpec | None
    schema_version: int
    bootstrap_samples: int
    bootstrap_ci_level: float
    bootstrap_seed: int | None

    def execute(self) -> dict[str, Any]:
        result = paper_k_from_paired_trials(
            self.trials,
            H=self.H,
            H_unit=self.H_unit,
            agent_policy=self.agent_policy,
            blind_policy=self.blind_policy,
            w=self.w,
            w_unit=self.w_unit,
            problem_space=self.problem_space,
            agent_policy_spec=self.agent_policy_spec,
            blind_policy_spec=self.blind_policy_spec,
            schema_version=self.schema_version,
            bootstrap_samples=self.bootstrap_samples,
            bootstrap_ci_level=self.bootstrap_ci_level,
            bootstrap_seed=self.bootstrap_seed,
        )
        if self.name is not None:
            result["name"] = self.name
        return result


def parse_compute_request(raw: Any, *, path: str = "input") -> ComputeRequest:
    obj = _require_object(raw, path=path)
    if "trials" not in obj:
        raise _schema_error(f"{path}.trials", "is required")
    trials_raw = _require_list(obj["trials"], path=f"{path}.trials")
    if not trials_raw:
        raise _schema_error(f"{path}.trials", "must be non-empty")

    problem_space = _parse_problem_space(obj.get("problem_space"), path=f"{path}.problem_space")
    agent_policy_spec = _parse_policy_spec(obj.get("agent_policy_spec"), path=f"{path}.agent_policy_spec")
    blind_policy_spec = _parse_policy_spec(obj.get("blind_policy_spec"), path=f"{path}.blind_policy_spec")

    h_value = obj.get("H")
    h_unit_value = obj.get("H_unit")
    w_value = obj.get("w")
    w_unit_value = obj.get("w_unit")
    if h_value is not None:
        h_value = _require_number(h_value, path=f"{path}.H")
    if h_unit_value is not None:
        h_unit_value = _require_str(h_unit_value, path=f"{path}.H_unit")
    if w_unit_value is not None:
        w_unit_value = _require_str(w_unit_value, path=f"{path}.w_unit")
    if w_value is not None:
        w_value = _parse_operator_cost(w_value, path=f"{path}.w")
        if w_unit_value is None and isinstance(w_value, Mapping) and w_value.get("unit") is not None:
            w_unit_value = _require_str(w_value["unit"], path=f"{path}.w.unit")

    bootstrap_samples = int(obj.get("bootstrap_samples", 0))
    if bootstrap_samples < 0:
        raise _schema_error(f"{path}.bootstrap_samples", "must be >= 0")
    bootstrap_ci_level = float(obj.get("bootstrap_ci_level", 0.95))
    if bootstrap_ci_level <= 0 or bootstrap_ci_level >= 1:
        raise _schema_error(f"{path}.bootstrap_ci_level", "must be in (0, 1)")

    return ComputeRequest(
        name=(None if obj.get("name") is None else _require_str(obj["name"], path=f"{path}.name")),
        trials=tuple(_parse_trial(item, path=f"{path}.trials[{i}]") for i, item in enumerate(trials_raw)),
        problem_space=problem_space,
        H=h_value,
        H_unit=h_unit_value,
        w=w_value,
        w_unit=w_unit_value,
        agent_policy=_require_str(obj.get("agent_policy", "agent"), path=f"{path}.agent_policy"),
        blind_policy=_require_str(obj.get("blind_policy", "blind_uniform"), path=f"{path}.blind_policy"),
        agent_policy_spec=agent_policy_spec,
        blind_policy_spec=blind_policy_spec,
        schema_version=int(obj.get("schema_version", 2)),
        bootstrap_samples=bootstrap_samples,
        bootstrap_ci_level=bootstrap_ci_level,
        bootstrap_seed=(
            None
            if obj.get("bootstrap_seed") is None
            else _require_int(obj["bootstrap_seed"], path=f"{path}.bootstrap_seed")
        ),
    )


def load_compute_request(path: Path) -> ComputeRequest:
    return parse_compute_request(json.loads(path.read_text(encoding="utf-8")), path=str(path))


@dataclass(frozen=True)
class SweepCase:
    name: str
    request: ComputeRequest


def load_json_documents(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise SchemaError(f"{path}: input is empty")
    if path.suffix == ".jsonl":
        documents: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            documents.append(dict(_require_object(json.loads(stripped), path=f"{path}:{line_number}")))
        if not documents:
            raise SchemaError(f"{path}: no JSONL documents found")
        return documents
    loaded = json.loads(raw)
    if isinstance(loaded, list):
        return [dict(_require_object(item, path=f"{path}[{index}]")) for index, item in enumerate(loaded)]
    obj = _require_object(loaded, path=str(path))
    if "cases" in obj:
        return [dict(_require_object(item, path=f"{path}.cases[{index}]")) for index, item in enumerate(_require_list(obj["cases"], path=f"{path}.cases"))]
    return [dict(obj)]


def load_sweep_cases(path: Path) -> list[SweepCase]:
    cases: list[SweepCase] = []
    for index, document in enumerate(load_json_documents(path)):
        request = parse_compute_request(document, path=f"{path}[{index}]")
        cases.append(SweepCase(name=str(document.get("name", f"case-{index}")), request=request))
    return cases


def coerce_summary_row(result: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "K_restricted_mean_at_stop": float(result["K"]["restricted_mean_at_stop"]),
        "agent_restricted_mean": float(result["tau"]["agent_restricted_mean"]),
        "blind_restricted_mean": float(result["tau"]["blind_restricted_mean"]),
        "agent_solve_rate": float(result["solve_rates"]["agent"]),
        "blind_solve_rate": float(result["solve_rates"]["blind"]),
    }


def _canonicalize_row(document: Mapping[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in CANONICAL_ROW_KEYS:
        if key in document:
            ordered[key] = document[key]
    for key, value in document.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def load_report_rows(path: Path) -> list[dict[str, Any]]:
    documents = load_json_documents(path)
    rows: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        if "K_restricted_mean_at_stop" in document:
            rows.append(_canonicalize_row(document))
            continue
        request = parse_compute_request(document, path=f"{path}[{index}]")
        rows.append(coerce_summary_row(request.execute(), name=request.name or f"case-{index}"))
    return rows


def aggregate_rows(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        raise SchemaError("report rows must be non-empty")

    numeric_keys: list[str] = []
    for key, value in rows[0].items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if all(
            key in row and isinstance(row[key], (int, float)) and not isinstance(row[key], bool)
            for row in rows
        ):
            numeric_keys.append(key)

    return {key: sum(float(row[key]) for row in rows) / len(rows) for key in numeric_keys}


def format_rows(
    rows: list[Mapping[str, Any]],
    *,
    output_format: str,
    aggregate: Mapping[str, float] | None = None,
) -> str:
    if output_format == "jsonl":
        return "\n".join(json.dumps(dict(row), sort_keys=True) for row in rows) + "\n"
    if output_format == "csv":
        fieldnames = list(rows[0].keys())
        sio = StringIO()
        writer = csv.DictWriter(sio, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return sio.getvalue()
    if output_format == "markdown":
        headers = list(rows[0].keys())
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
        if aggregate is not None:
            lines.append("")
            lines.append("## Aggregate")
            for key, value in aggregate.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) + "\n"
    raise SchemaError(f"unsupported output format: {output_format}")


def write_text(path: Path | None, text: str) -> None:
    if path is None:
        print(text, end="")
        return
    path.write_text(text, encoding="utf-8")
