from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lean_sorry_repos_benchmark.cli import main as benchmark_main
from lean_sorry_repos_benchmark.paths import resolve_artifact_root

SUITE_SCHEMA_VERSION = 1
_ALLOWED_ADAPTERS = {"mock", "ollama", "openai"}
_RESERVED_ARGS = frozenset({"--adapter", "--model", "--out-dir"})
_PROTOCOL_CRITICAL_RUN_ARGS = frozenset(
    {
        "--index",
        "--split-policy",
        "--repo-holdout-fraction",
        "--goal-slice",
        "--seed",
        "--samples-per-item",
        "--pass-at-k",
        "--verification-mode",
    }
)
_RUN_RESERVED_ARGS = _RESERVED_ARGS | _PROTOCOL_CRITICAL_RUN_ARGS


@dataclass(frozen=True)
class SuiteRunSpec:
    name: str
    adapter: str
    model: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class SuiteConfig:
    schema_version: int
    common_args: tuple[str, ...]
    runs: tuple[SuiteRunSpec, ...]


@dataclass(frozen=True)
class SuiteRunResult:
    name: str
    adapter: str
    model: str
    run_dir: str
    status: str
    exit_code: int
    selected_rows: int | None
    valid_rate: float | None
    verification_success_rate_attempted: float | None
    verification_success_rate_attempted_ci: dict[str, float] | None
    verification_pass_at_k_success_rate: dict[str, float]
    verification_pass_at_k_success_rate_ci: dict[str, dict[str, float] | None]
    generation_error_count: int | None
    generation_error_kinds: dict[str, int]
    verification_error_count: int | None
    infra_failure_kind: str | None
    infra_failure_reason: str | None
    failure_domain: str | None
    failure_reason: str | None
    attempts_jsonl: str | None
    summary_json: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_suite_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    fallback = root / "artifacts"
    out_root = resolve_artifact_root(fallback)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return out_root / "suites" / f"proposal-suite-{stamp}"


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a benchmark suite over multiple model specs and write aggregate leaderboard files."
        )
    )
    parser.add_argument("--config", required=True, type=Path, help="Path to suite config JSON.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output suite directory "
            "(default routes via SPECTER_ARTIFACT_ROOT or local artifacts/)."
        ),
    )
    parser.add_argument(
        "--max-parallel-runs",
        type=_parse_positive_int,
        default=1,
        help="Maximum number of suite runs to execute in parallel (default: 1).",
    )
    return parser.parse_args(argv)


def _parse_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 1") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be an integer >= 1")
    return parsed


def _parse_str_list(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array of strings")
    out: list[str] = []
    for idx, token in enumerate(value):
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{field}[{idx}] must be a non-empty string")
        out.append(token)
    return tuple(out)


def _has_flag(args: tuple[str, ...], flag: str) -> bool:
    prefix = f"{flag}="
    return any(token == flag or token.startswith(prefix) for token in args)


def _assert_no_reserved_args(
    args: tuple[str, ...],
    *,
    field: str,
    reserved_args: frozenset[str] = _RESERVED_ARGS,
) -> None:
    for reserved in sorted(reserved_args):
        if _has_flag(args, reserved):
            raise ValueError(f"{field} must not include {reserved}; suite runner sets it per run")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("suite config must be a JSON object")
    return payload


def load_suite_config(path: Path) -> SuiteConfig:
    payload = _load_json_object(path)
    schema_version = payload.get("schema_version", SUITE_SCHEMA_VERSION)
    if not isinstance(schema_version, int):
        raise ValueError("schema_version must be an integer")
    if schema_version != SUITE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version={schema_version}; expected {SUITE_SCHEMA_VERSION}"
        )

    common_args = _parse_str_list(payload.get("common_args"), field="common_args")
    _assert_no_reserved_args(common_args, field="common_args")
    if not _has_flag(common_args, "--index"):
        raise ValueError("common_args must include --index so each run benchmarks the same corpus")

    runs_obj = payload.get("runs")
    if not isinstance(runs_obj, list) or not runs_obj:
        raise ValueError("runs must be a non-empty array")

    runs: list[SuiteRunSpec] = []
    seen_names: set[str] = set()
    for idx, run_obj in enumerate(runs_obj):
        if not isinstance(run_obj, dict):
            raise ValueError(f"runs[{idx}] must be an object")
        adapter = run_obj.get("adapter")
        model = run_obj.get("model")
        if adapter not in _ALLOWED_ADAPTERS:
            raise ValueError(f"runs[{idx}].adapter must be one of {sorted(_ALLOWED_ADAPTERS)}")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"runs[{idx}].model must be a non-empty string")
        raw_name = run_obj.get("name")
        if raw_name is None:
            name = f"{adapter}:{model}"
        elif isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip()
        else:
            raise ValueError(f"runs[{idx}].name must be a non-empty string when provided")
        if name in seen_names:
            raise ValueError(f"duplicate run name: {name}")
        seen_names.add(name)

        args_value = run_obj.get("args", [])
        run_args = _parse_str_list(args_value, field=f"runs[{idx}].args")
        _assert_no_reserved_args(
            run_args,
            field=f"runs[{idx}].args",
            reserved_args=_RUN_RESERVED_ARGS,
        )
        runs.append(
            SuiteRunSpec(
                name=name,
                adapter=adapter,
                model=model.strip(),
                args=run_args,
            )
        )

    return SuiteConfig(
        schema_version=schema_version,
        common_args=common_args,
        runs=tuple(runs),
    )


def classify_model_error(error: str) -> str:
    lower = error.lower()
    if "timeout after" in lower:
        return "timeout"
    if lower.startswith("http "):
        return "http_error"
    if "connection refused" in lower or "failed to establish a new connection" in lower:
        return "endpoint_unreachable"
    if "name or service not known" in lower or "nodename nor servname provided" in lower:
        return "dns_error"
    if "invalid json response" in lower or "missing response field" in lower:
        return "invalid_response"
    return "other"


def _collect_model_error_kinds(attempts_path: Path) -> tuple[int, dict[str, int]]:
    if not attempts_path.exists():
        return 0, {}
    total = 0
    kinds: dict[str, int] = {}
    with attempts_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{attempts_path}: invalid JSON at line {line_no}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{attempts_path}: expected object at line {line_no}")
            error = payload.get("error")
            if not isinstance(error, str) or not error.strip():
                continue
            total += 1
            kind = classify_model_error(error)
            kinds[kind] = kinds.get(kind, 0) + 1
    return total, dict(sorted(kinds.items()))


def _normalize_exit(code: object) -> tuple[int, str | None]:
    if code is None:
        return 0, None
    if isinstance(code, int):
        return code, None if code == 0 else f"benchmark exited with code {code}"
    message = str(code).strip()
    return 1, message or "benchmark exited with non-integer status"


def _classify_infra_error(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "permission_error"
    if isinstance(exc, FileNotFoundError):
        return "missing_file"
    if isinstance(exc, ValueError):
        return "invalid_output"
    return "exception"


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _safe_ci(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    low = _safe_float(value.get("low"))
    high = _safe_float(value.get("high"))
    if low is None or high is None:
        return None
    return {"low": low, "high": high}


def _nested_get(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "run"


def _result_failure(
    *,
    spec: SuiteRunSpec,
    run_dir: Path,
    exit_code: int,
    infra_kind: str,
    infra_reason: str,
) -> SuiteRunResult:
    return SuiteRunResult(
        name=spec.name,
        adapter=spec.adapter,
        model=spec.model,
        run_dir=str(run_dir),
        status="failed",
        exit_code=exit_code,
        selected_rows=None,
        valid_rate=None,
        verification_success_rate_attempted=None,
        verification_success_rate_attempted_ci=None,
        verification_pass_at_k_success_rate={},
        verification_pass_at_k_success_rate_ci={},
        generation_error_count=None,
        generation_error_kinds={},
        verification_error_count=None,
        infra_failure_kind=infra_kind,
        infra_failure_reason=infra_reason,
        failure_domain="infra",
        failure_reason=infra_reason,
        attempts_jsonl=None,
        summary_json=None,
    )


def _run_one(spec: SuiteRunSpec, *, common_args: tuple[str, ...], run_dir: Path) -> SuiteRunResult:
    argv = [
        *common_args,
        "--adapter",
        spec.adapter,
        "--model",
        spec.model,
        "--out-dir",
        str(run_dir),
        *spec.args,
    ]
    try:
        rc = benchmark_main(argv)
    except SystemExit as exc:
        exit_code, reason = _normalize_exit(exc.code)
        message = reason or "benchmark raised SystemExit"
        return _result_failure(
            spec=spec,
            run_dir=run_dir,
            exit_code=exit_code,
            infra_kind="benchmark_exit",
            infra_reason=message,
        )
    except Exception as exc:
        return _result_failure(
            spec=spec,
            run_dir=run_dir,
            exit_code=1,
            infra_kind=_classify_infra_error(exc),
            infra_reason=str(exc) or exc.__class__.__name__,
        )
    if rc != 0:
        return _result_failure(
            spec=spec,
            run_dir=run_dir,
            exit_code=rc,
            infra_kind="benchmark_exit",
            infra_reason=f"benchmark returned non-zero exit code {rc}",
        )

    summary_path = run_dir / "summary.json"
    attempts_path = run_dir / "attempts.jsonl"
    if not summary_path.exists():
        return _result_failure(
            spec=spec,
            run_dir=run_dir,
            exit_code=1,
            infra_kind="missing_summary",
            infra_reason=f"missing benchmark summary: {summary_path}",
        )

    try:
        summary_obj = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary_obj, dict):
            raise ValueError("summary.json must contain an object")
        counted_errors, error_kinds = _collect_model_error_kinds(attempts_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return _result_failure(
            spec=spec,
            run_dir=run_dir,
            exit_code=1,
            infra_kind="invalid_summary",
            infra_reason=str(exc),
        )

    selected_rows = _safe_int(_nested_get(summary_obj, ("selection", "selected_rows")))
    valid_rate = _safe_float(_nested_get(summary_obj, ("scoring", "metrics", "valid_rate")))
    verification_success_rate = _safe_float(
        _nested_get(summary_obj, ("verification", "metrics", "verification_success_rate_attempted"))
    )
    verification_success_rate_ci = _safe_ci(
        _nested_get(
            summary_obj,
            ("verification", "metrics", "verification_success_rate_attempted_ci"),
        )
    )
    pass_at_k_raw = _nested_get(
        summary_obj,
        ("verification", "metrics", "verification_pass_at_k_success_rate"),
    )
    pass_at_k_ci_raw = _nested_get(
        summary_obj,
        ("verification", "metrics", "verification_pass_at_k_success_rate_ci"),
    )
    verification_pass_at_k_success_rate: dict[str, float] = {}
    verification_pass_at_k_success_rate_ci: dict[str, dict[str, float] | None] = {}
    if isinstance(pass_at_k_raw, dict):
        for key, value in pass_at_k_raw.items():
            if isinstance(key, str) and isinstance(value, int | float):
                verification_pass_at_k_success_rate[key] = float(value)
    if isinstance(pass_at_k_ci_raw, dict):
        for key, value in pass_at_k_ci_raw.items():
            if isinstance(key, str):
                verification_pass_at_k_success_rate_ci[key] = _safe_ci(value)
    verification_pass_at_k_success_rate = dict(
        sorted(verification_pass_at_k_success_rate.items(), key=lambda item: int(item[0]))
    )
    verification_pass_at_k_success_rate_ci = dict(
        sorted(verification_pass_at_k_success_rate_ci.items(), key=lambda item: int(item[0]))
    )
    generation_error_count = _safe_int(
        _nested_get(summary_obj, ("scoring", "metrics", "generation_error_count"))
    )
    verification_error_count = _safe_int(
        _nested_get(summary_obj, ("verification", "metrics", "verification_error_count"))
    )
    if generation_error_count is None:
        generation_error_count = counted_errors

    failure_domain: str | None = None
    failure_reason: str | None = None
    if generation_error_count > 0:
        failure_domain = "model"
        failure_reason = f"{generation_error_count} generation errors"

    return SuiteRunResult(
        name=spec.name,
        adapter=spec.adapter,
        model=spec.model,
        run_dir=str(run_dir),
        status="success",
        exit_code=0,
        selected_rows=selected_rows,
        valid_rate=valid_rate,
        verification_success_rate_attempted=verification_success_rate,
        verification_success_rate_attempted_ci=verification_success_rate_ci,
        verification_pass_at_k_success_rate=verification_pass_at_k_success_rate,
        verification_pass_at_k_success_rate_ci=verification_pass_at_k_success_rate_ci,
        generation_error_count=generation_error_count,
        generation_error_kinds=error_kinds,
        verification_error_count=verification_error_count,
        infra_failure_kind=None,
        infra_failure_reason=None,
        failure_domain=failure_domain,
        failure_reason=failure_reason,
        attempts_jsonl=str(attempts_path) if attempts_path.exists() else None,
        summary_json=str(summary_path),
    )


def run_suite(
    config: SuiteConfig, *, out_dir: Path, max_parallel_runs: int = 1
) -> list[SuiteRunResult]:
    if max_parallel_runs < 1:
        raise ValueError("max_parallel_runs must be >= 1")
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    indexed_runs: list[tuple[int, SuiteRunSpec, Path]] = []
    for order_idx, spec in enumerate(config.runs):
        run_dir = runs_dir / f"{order_idx + 1:02d}-{_slug(spec.name)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        indexed_runs.append((order_idx, spec, run_dir))

    if max_parallel_runs == 1 or len(indexed_runs) <= 1:
        results: list[SuiteRunResult] = []
        for _, spec, run_dir in indexed_runs:
            results.append(_run_one(spec, common_args=config.common_args, run_dir=run_dir))
        return results

    ordered_results: list[SuiteRunResult | None] = [None] * len(indexed_runs)
    with ThreadPoolExecutor(max_workers=max_parallel_runs) as executor:
        futures: dict[Future[SuiteRunResult], int] = {}
        for idx, spec, run_dir in indexed_runs:
            future = executor.submit(
                _run_one,
                spec,
                common_args=config.common_args,
                run_dir=run_dir,
            )
            futures[future] = idx
        for future in as_completed(futures):
            idx = futures[future]
            ordered_results[idx] = future.result()

    results = []
    for idx, result in enumerate(ordered_results):
        if result is None:
            raise RuntimeError(f"missing suite result at index {idx}")
        results.append(result)
    return results


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def _fmt_rate_with_ci(value: float | None, ci: dict[str, float] | None) -> str:
    if value is None:
        return "-"
    if ci is None:
        return _fmt_rate(value)
    return f"{value:.4f} [{ci['low']:.4f}, {ci['high']:.4f}]"


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_summary_markdown(results: list[SuiteRunResult]) -> str:
    run_count = len(results)
    success_count = sum(1 for row in results if row.status == "success")
    infra_failure_count = sum(1 for row in results if row.failure_domain == "infra")
    model_error_run_count = sum(1 for row in results if row.failure_domain == "model")
    lines = [
        "# Benchmark Suite Summary",
        "",
        f"- runs: {run_count}",
        f"- success: {success_count}",
        f"- infra_failures: {infra_failure_count}",
        f"- runs_with_model_errors: {model_error_run_count}",
        "",
        "| run | adapter | model | status | selected_rows | valid_rate | "
        "verification_success_rate_attempted | pass@k | model_errors | infra_failure |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in results:
        model_errors = "-"
        if row.generation_error_count is not None:
            model_errors = str(row.generation_error_count)
            if row.generation_error_kinds:
                kinds = ", ".join(f"{k}:{v}" for k, v in sorted(row.generation_error_kinds.items()))
                model_errors = f"{model_errors} ({kinds})"
        infra_failure = "-"
        if row.infra_failure_kind is not None:
            infra_failure = row.infra_failure_kind
            if row.infra_failure_reason:
                infra_failure = f"{infra_failure}: {row.infra_failure_reason}"
        pass_at_k_text = "-"
        if row.verification_pass_at_k_success_rate:
            entries: list[str] = []
            for key, value in row.verification_pass_at_k_success_rate.items():
                ci = row.verification_pass_at_k_success_rate_ci.get(key)
                if ci is None:
                    entries.append(f"{key}:{value:.4f}")
                else:
                    entries.append(
                        f"{key}:{value:.4f} [{ci['low']:.4f}, {ci['high']:.4f}]"
                    )
            pass_at_k_text = ", ".join(entries)
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row.name),
                    _md_cell(row.adapter),
                    _md_cell(row.model),
                    _md_cell(row.status),
                    str(row.selected_rows) if row.selected_rows is not None else "-",
                    _fmt_rate(row.valid_rate),
                    _fmt_rate_with_ci(
                        row.verification_success_rate_attempted,
                        row.verification_success_rate_attempted_ci,
                    ),
                    _md_cell(pass_at_k_text),
                    _md_cell(model_errors),
                    _md_cell(infra_failure),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _result_to_dict(result: SuiteRunResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["generation_error_kinds"] = dict(sorted(result.generation_error_kinds.items()))
    return payload


def _write_suite_outputs(
    *,
    out_dir: Path,
    config_path: Path,
    config: SuiteConfig,
    results: list[SuiteRunResult],
) -> tuple[Path, Path, Path]:
    jsonl_path = out_dir / "suite_results.jsonl"
    summary_json_path = out_dir / "suite_results.json"
    summary_md_path = out_dir / "suite_summary.md"

    records = [_result_to_dict(result) for result in results]
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    run_count = len(results)
    success_count = sum(1 for row in results if row.status == "success")
    infra_failure_count = sum(1 for row in results if row.failure_domain == "infra")
    model_error_run_count = sum(1 for row in results if row.failure_domain == "model")

    payload = {
        "suite_schema_version": SUITE_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "config_path": str(config_path),
        "suite_out_dir": str(out_dir),
        "run_count": run_count,
        "success_count": success_count,
        "infra_failure_count": infra_failure_count,
        "model_error_run_count": model_error_run_count,
        "config": {
            "schema_version": config.schema_version,
            "common_args": list(config.common_args),
            "runs": [asdict(run) for run in config.runs],
        },
        "outputs": {
            "suite_results_jsonl": str(jsonl_path),
            "suite_summary_md": str(summary_md_path),
        },
        "runs": records,
    }
    summary_json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(render_summary_markdown(results), encoding="utf-8")
    return jsonl_path, summary_json_path, summary_md_path


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    config = load_suite_config(args.config)
    out_dir = args.out_dir if args.out_dir is not None else _default_suite_dir()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise SystemExit(
            f"Cannot create out-dir: {out_dir}\n"
            "Use --out-dir to point to a writable location, or fix SPECTER_ARTIFACT_ROOT."
        ) from exc

    results = run_suite(
        config,
        out_dir=out_dir,
        max_parallel_runs=args.max_parallel_runs,
    )
    jsonl_path, summary_json_path, summary_md_path = _write_suite_outputs(
        out_dir=out_dir,
        config_path=args.config,
        config=config,
        results=results,
    )
    infra_failure_count = sum(1 for row in results if row.failure_domain == "infra")
    model_error_run_count = sum(1 for row in results if row.failure_domain == "model")
    print(f"runs={len(results)}")
    print(f"infra_failures={infra_failure_count}")
    print(f"runs_with_model_errors={model_error_run_count}")
    print(f"suite_results_jsonl={jsonl_path}")
    print(f"suite_results_json={summary_json_path}")
    print(f"suite_summary_md={summary_md_path}")
    return 2 if infra_failure_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
