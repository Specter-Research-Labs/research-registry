from __future__ import annotations

import argparse
import gzip
import json
import re
import webbrowser
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from analysis.logs import read_json_auto
from analysis.run_metadata import (
    RunSnapshot,
    build_run_label,
    build_run_meta,
    load_optional_json_mapping,
    load_run_config,
    load_run_snapshot,
    providers_from_config,
    status_tag_from_run_status,
)
from analysis.viz_payloads import (
    build_dashboard_payload,
    build_dashboard_payload_v2,
)
from runtime_paths import resolve_logs_root as _resolve_runtime_logs_root


def resolve_logs_dir(logs_dir: str | None) -> Path:
    if logs_dir is None or logs_dir == "logs":
        return _resolve_runtime_logs_root().resolve()
    return Path(logs_dir).resolve()


def resolve_fonts_dir(viz_path: Path, fonts_dir: str | None) -> Path:
    if fonts_dir:
        return Path(fonts_dir).resolve()
    candidates = [viz_path, *viz_path.parents]
    for parent in candidates:
        candidate = (parent / "site" / "fonts").resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Fonts directory not found. Pass --fonts-dir or add site/fonts near {viz_path}"
    )


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _run_name_date(value: str) -> date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    if match is not None:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    match = re.search(r"(\d{8})", value)
    if match is not None:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _run_created_date(run_dir: Path, run_config: dict[str, Any] | None) -> date | None:
    if run_config:
        created_at = run_config.get("created_at")
        if isinstance(created_at, str):
            parsed = _parse_iso_date(created_at)
            if parsed is not None:
                return parsed
    summary_path = run_dir / "summary.json.gz"
    if summary_path.exists():
        try:
            return datetime.fromtimestamp(summary_path.stat().st_mtime).date()
        except OSError:
            return None
    return None


class VizHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        logs_dir: Path,
        viz_dir: Path,
        fonts_dir: Path,
        pkg_dir: Path,
        recent_only: bool,
        include_run_meta: bool,
        **kwargs,
    ):
        self.logs_dir = logs_dir
        self.viz_dir = viz_dir
        self.fonts_dir = fonts_dir
        self.pkg_dir = pkg_dir
        self.recent_only = recent_only
        self.include_run_meta = include_run_meta
        super().__init__(*args, directory=str(viz_dir), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api()
            return
        if self.path.startswith("/fonts/"):
            self._handle_fonts()
            return
        if self.path.startswith("/pkg/"):
            self._handle_pkg()
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _handle_fonts(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2 or parts[0] != "fonts":
            self._send_error(HTTPStatus.NOT_FOUND, "Unknown font path")
            return
        if not self.fonts_dir.exists():
            self._send_error(HTTPStatus.NOT_FOUND, f"Fonts directory not found: {self.fonts_dir}")
            return
        if any(not self._is_safe_segment(part) for part in parts[1:]):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid font path")
            return
        filename = "/".join(parts[1:])
        target = self.fonts_dir / filename
        try:
            resolved = target.resolve()
        except OSError:
            self._send_error(HTTPStatus.NOT_FOUND, f"Font not found: {filename}")
            return
        try:
            resolved.relative_to(self.fonts_dir.resolve())
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid font path")
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, f"Font not found: {filename}")
            return
        if resolved.suffix.lower() not in {".woff2", ".woff"}:
            self._send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Unsupported font type")
            return
        try:
            with resolved.open("rb") as handle:
                data = handle.read()
        except OSError as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Failed to read font: {exc}")
            return
        content_type = self.guess_type(str(resolved)) or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _handle_pkg(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2 or parts[0] != "pkg":
            self._send_error(HTTPStatus.NOT_FOUND, "Unknown pkg path")
            return
        if not self.pkg_dir.exists():
            self._send_error(HTTPStatus.NOT_FOUND, f"Pkg directory not found: {self.pkg_dir}")
            return
        if any(not self._is_safe_segment(part) for part in parts[1:]):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid pkg path")
            return
        filename = "/".join(parts[1:])
        target = self.pkg_dir / filename
        try:
            resolved = target.resolve()
        except OSError:
            self._send_error(HTTPStatus.NOT_FOUND, f"Pkg file not found: {filename}")
            return
        try:
            resolved.relative_to(self.pkg_dir.resolve())
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid pkg path")
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, f"Pkg file not found: {filename}")
            return
        try:
            with resolved.open("rb") as handle:
                data = handle.read()
        except OSError as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Failed to read pkg file: {exc}")
            return
        content_type = self.guess_type(str(resolved)) or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _handle_api(self) -> None:
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        provider = query.get("provider", [None])[0]
        if provider is not None:
            provider = unquote(provider)

        if parts == ["api", "runs"]:
            self._handle_runs()
            return

        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "run":
            run_name = unquote(parts[2])

            if parts[3:] == ["theorems"]:
                self._handle_theorems(run_name, provider)
                return

            if parts[3:] == ["dashboard"]:
                self._handle_dashboard(run_name, provider)
                return
            if parts[3:] == ["dashboard_v2"]:
                self._handle_dashboard_v2(run_name, provider)
                return

            if len(parts) >= 5 and parts[3] == "theorem":
                theorem_name = unquote(parts[4])
                if parts[5:] == []:
                    self._handle_theorem_index(run_name, theorem_name, provider)
                    return
                if len(parts) >= 7 and parts[5] == "file":
                    filename = unquote("/".join(parts[6:]))
                    self._handle_file(run_name, theorem_name, filename, provider)
                    return

            if len(parts) >= 5 and parts[3] == "file":
                filename = unquote("/".join(parts[4:]))
                self._handle_file(run_name, None, filename, provider)
                return

        self._send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def _handle_runs(self) -> None:
        if not self.logs_dir.exists():
            self._send_error(HTTPStatus.NOT_FOUND, f"Logs directory not found: {self.logs_dir}")
            return

        runs: list[str] = []
        run_labels: dict[str, str] = {}
        providers_by_run: dict[str, list[str]] = {}
        run_meta: dict[str, dict[str, Any]] = {}
        cutoff = date.today() - timedelta(days=6) if self.recent_only else None
        for run_dir in self.logs_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            summary_path = run_dir / "summary.json.gz"
            if (self.include_run_meta or self.recent_only) and not summary_path.exists():
                continue
            run_snapshot = load_run_snapshot(
                run_dir,
                include_run_config=self.include_run_meta,
                include_summary_aggregates=self.recent_only,
            )
            run_config = run_snapshot.config
            if self.recent_only:
                created_at = _run_created_date(run_dir, run_config)
                if created_at is not None and cutoff is not None and created_at < cutoff:
                    continue
            run_name = run_dir.name
            runs.append(run_name)
            if not self.include_run_meta:
                continue
            providers_by_run[run_name] = (
                providers_from_config(run_config) if run_config else []
            )
            label = self._run_label(run_name, run_dir, run_snapshot)
            if label:
                run_labels[run_name] = label
            meta = self._run_meta(run_snapshot)
            if meta:
                run_meta[run_name] = meta

        runs.sort(
            key=lambda name: (
                (run_date := _run_name_date(name)) is not None,
                run_date or date.min,
                name,
            ),
            reverse=True,
        )
        latest = self._load_latest_run()
        latest_id = latest.get("run_id") if latest else None
        default_run = latest_id if isinstance(latest_id, str) and latest_id in runs else None
        if default_run is None:
            default_run = runs[0] if runs else None
        payload = {
            "runs": runs,
            "run_labels": run_labels,
            "providers_by_run": providers_by_run,
            "run_meta": run_meta,
            "default_run": default_run,
        }
        self._send_json(payload)

    def _load_latest_run(self) -> dict[str, Any] | None:
        latest_path = self.logs_dir / "latest_run.json"
        data = load_optional_json_mapping(latest_path)
        if data is None:
            return None
        run_id = data.get("run_id")
        if not isinstance(run_id, str):
            return None
        run_dir = self.logs_dir / run_id
        if not run_dir.exists():
            return None
        return data

    def _run_meta(self, run_snapshot: RunSnapshot) -> dict[str, Any] | None:
        return build_run_meta(
            run_snapshot.aggregates,
            run_snapshot.config,
            run_snapshot.status,
            theorem_count=run_snapshot.theorem_count,
        )

    def _run_label(
        self, run_name: str, run_dir: Path, run_snapshot: RunSnapshot
    ) -> str | None:
        run_config = run_snapshot.config
        status_data = run_snapshot.status
        status_tag = status_tag_from_run_status(status_data)

        def _with_status(label: str) -> str:
            return f"{label} | {status_tag}" if status_tag else label

        if run_config:
            return build_run_label(
                run_name,
                run_config,
                status_data,
                theorem_count=run_snapshot.theorem_count,
                style="viz",
            )

        log_path = run_dir / "corpus.log"
        lines: list[str] = []
        if log_path.exists():
            try:
                with log_path.open("r", encoding="utf-8") as handle:
                    lines = [handle.readline().strip() for _ in range(6)]
            except OSError:
                lines = []
        lines = [line for line in lines if line]
        if lines:
            start_pattern = re.compile(
                r"Starting corpus run with (?P<count>\d+) theorems "
                r"\((?P<mode>[^)]+)\), budget_tiers=\[(?P<tiers>[^\]]+)\] "
                r"\(total=(?P<total>\d+)\), workers=(?P<workers>\d+)"
            )
            single_pattern = re.compile(r"Running single theorem: (?P<theorem>.+)")
            limited_pattern = re.compile(r"Limited to (?P<count>\d+) theorems")

            for line in lines:
                match = start_pattern.search(line)
                if match:
                    count = match.group("count")
                    mode = match.group("mode").strip()
                    tiers = match.group("tiers").replace(" ", "")
                    workers = match.group("workers")
                    return _with_status(
                        f"{run_name} | {mode} | {count} thm | tiers {tiers} | wk {workers}"
                    )

            for line in lines:
                match = single_pattern.search(line)
                if match:
                    theorem = match.group("theorem").strip()
                    return _with_status(f"{run_name} | single {theorem}")

            for line in lines:
                match = limited_pattern.search(line)
                if match:
                    count = match.group("count")
                    return _with_status(f"{run_name} | limited {count} thm")

        return _with_status(run_name)

    def _handle_theorems(self, run_name: str, provider: str | None) -> None:
        if not self._is_safe_segment(run_name):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid run name")
            return
        base_dir = self._resolve_run(run_name)
        if base_dir is None:
            return
        if provider == "all":
            run_config = load_run_config(base_dir)
            selected = []
            if run_config:
                selection = run_config.get("theorem_selection", {})
                if isinstance(selection, dict):
                    selected = selection.get("selected_theorems") or []
            if not selected:
                self._send_json({"run": run_name, "theorems": []})
                return
            self._send_json({"run": run_name, "theorems": selected})
            return

        run_dir = self._resolve_run_with_provider(run_name, provider)
        if run_dir is None:
            return

        theorems = [d.name for d in run_dir.iterdir() if d.is_dir()]
        theorems.sort()
        self._send_json({"run": run_name, "theorems": theorems})

    def _handle_theorem_index(self, run_name: str, theorem_name: str, provider: str | None) -> None:
        if not self._is_safe_segment(run_name) or not self._is_safe_segment(theorem_name):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid path segment")
            return
        if provider == "all":
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "Theorem index not available for provider=all. Select a provider.",
            )
            return
        run_dir = self._resolve_run_with_provider(run_name, provider)
        if run_dir is None:
            return

        theorem_dir = run_dir / theorem_name
        if not theorem_dir.exists() or not theorem_dir.is_dir():
            self._send_error(HTTPStatus.NOT_FOUND, f"Theorem not found: {theorem_name}")
            return

        variant_files: dict[str, dict[str, str]] = {}
        extra_files: dict[str, str | None] = {
            "ged_matrix": None,
            "attractor_clusters": None,
            "basin_analysis": None,
        }

        kinds = [
            "history",
            "mcts_tree",
            "mcts_trace",
            "graph",
            "metrics",
            "comparison",
            "assembly",
            "proof_term",
        ]
        for file in theorem_dir.iterdir():
            if not file.is_file():
                continue
            name = file.name
            if name in {"ged_matrix.json", "ged_matrix.json.gz"}:
                extra_files["ged_matrix"] = name
                continue
            if name in {"attractor_clusters.json", "attractor_clusters.json.gz"}:
                extra_files["attractor_clusters"] = name
                continue
            if name in {"basin_analysis.json", "basin_analysis.json.gz"}:
                extra_files["basin_analysis"] = name
                continue

            for kind in kinds:
                if kind == "mcts_trace":
                    suffix = f"_{kind}.jsonl"
                    suffix_gz = f"{suffix}.gz"
                else:
                    suffix = f"_{kind}.json"
                    suffix_gz = f"{suffix}.gz"
                if name.endswith(suffix):
                    variant = name[: -len(suffix)]
                elif name.endswith(suffix_gz):
                    variant = name[: -len(suffix_gz)]
                else:
                    continue
                if variant not in variant_files:
                    variant_files[variant] = {}
                variant_files[variant][kind] = name
                break

        def variant_sort(name: str) -> tuple[int, str]:
            return (0, name) if name == "wild_type" else (1, name)

        variants = sorted(variant_files.keys(), key=variant_sort)
        self._send_json(
            {
                "run": run_name,
                "theorem": theorem_name,
                "variants": variants,
                "variant_files": variant_files,
                "extra_files": extra_files,
            }
        )

    def _handle_file(
        self,
        run_name: str,
        theorem_name: str | None,
        filename: str,
        provider: str | None,
    ) -> None:
        if not self._is_safe_segment(run_name):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid run name")
            return
        if provider == "all" and theorem_name is not None:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "Theorem files not available for provider=all. Select a provider.",
            )
            return
        run_dir = self._resolve_run_with_provider(run_name, provider)
        if run_dir is None:
            return

        if theorem_name and not self._is_safe_segment(theorem_name):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid theorem name")
            return

        if "/" in filename or "\\" in filename:
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid filename")
            return

        if theorem_name:
            target = run_dir / theorem_name / filename
        else:
            target = run_dir / filename

        target = self._resolve_in_logs(target)
        if target is None or not target.exists():
            self._send_error(HTTPStatus.NOT_FOUND, f"File not found: {filename}")
            return
        is_jsonl = target.name.endswith(".jsonl") or target.name.endswith(".jsonl.gz")
        if is_jsonl:
            try:
                data = self._load_text(target)
            except OSError as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Failed to read file: {exc}")
                return
            self._send_text(data, content_type="application/x-ndjson; charset=utf-8")
            return
        if target.suffix not in {".json", ".gz"}:
            self._send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Only JSON files are supported")
            return

        try:
            data = self._load_json(target)
        except json.JSONDecodeError as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Invalid JSON: {exc}")
            return
        except OSError as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Failed to read file: {exc}")
            return

        self._send_json(data)

    def _handle_dashboard(self, run_name: str, provider: str | None) -> None:
        self._handle_dashboard_common(run_name, provider, version="v1")

    def _handle_dashboard_v2(self, run_name: str, provider: str | None) -> None:
        self._handle_dashboard_common(run_name, provider, version="v2")

    def _handle_dashboard_common(
        self,
        run_name: str,
        provider: str | None,
        *,
        version: str,
    ) -> None:
        if not self._is_safe_segment(run_name):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid run name")
            return
        if provider == "all":
            if version == "v2":
                self._send_error(
                    HTTPStatus.BAD_REQUEST,
                    "Dashboard v2 does not support provider=all.",
                )
                return
            base_dir = self._resolve_run(run_name)
            if base_dir is None:
                return
            payload = self._dashboard_payload(run_name, base_dir, include_summary=False)
            if payload is None:
                return
            errors = payload["errors"]
            payload["multi_provider"] = True
            payload["providers_summary"] = self._load_json_payload(
                base_dir / "providers_summary.json",
                required=False,
                errors=errors,
            )
            payload["providers_theorem_summary"] = self._load_json_payload(
                base_dir / "providers_theorem_summary.json",
                required=False,
                errors=errors,
            )
            self._send_json(payload)
            return

        run_dir = self._resolve_run_with_provider(run_name, provider)
        if run_dir is None:
            return

        payload = self._dashboard_payload(
            run_name,
            run_dir,
            include_summary=True,
            require_summary=version == "v2",
        )
        if payload is None:
            return
        summary = payload.pop("_summary", None)
        if version == "v2":
            payload = build_dashboard_payload_v2(
                summary,
                run_dir,
                payload["config"],
                payload["status"],
            )
        elif summary:
            payload.update(build_dashboard_payload(summary, run_dir))
        self._send_json(payload)

    def _load_json(self, path: Path) -> Any:
        return read_json_auto(path)

    def _load_json_payload(
        self,
        path: Path,
        *,
        required: bool,
        errors: list[str] | None = None,
    ) -> Any | None:
        if not path.exists():
            if required:
                self._send_error(HTTPStatus.NOT_FOUND, f"Missing {path.name}")
            elif errors is not None:
                errors.append(f"Missing {path.name}")
            return None
        try:
            return self._load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            if required:
                self._send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    f"Failed to read {path.name}: {exc}",
                )
            elif errors is not None:
                errors.append(f"Failed to read {path.name}: {exc}")
            return None

    def _dashboard_payload(
        self,
        run_name: str,
        run_dir: Path,
        *,
        include_summary: bool = True,
        require_summary: bool = False,
    ) -> dict[str, Any] | None:
        errors: list[str] = []
        summary = None
        if include_summary:
            summary = self._load_json_payload(
                run_dir / "summary.json.gz",
                required=require_summary,
                errors=None if require_summary else errors,
            )
            if require_summary and summary is None:
                return None
        run_snapshot = load_run_snapshot(
            run_dir,
            include_run_config=True,
            include_summary_aggregates=False,
        )
        if run_snapshot.config is None:
            errors.append("Missing run_config.json")
        return {
            "run": run_name,
            "status": run_snapshot.status,
            "config": run_snapshot.config,
            "errors": errors,
            "_summary": summary,
        }

    def _load_text(self, path: Path) -> str:
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return handle.read()
        with path.open("r", encoding="utf-8") as handle:
            return handle.read()

    def _resolve_run(self, run_name: str) -> Path | None:
        if not self.logs_dir.exists():
            self._send_error(HTTPStatus.NOT_FOUND, f"Logs directory not found: {self.logs_dir}")
            return None

        run_dir = self.logs_dir / run_name
        if not run_dir.exists() or not run_dir.is_dir():
            self._send_error(HTTPStatus.NOT_FOUND, f"Run not found: {run_name}")
            return None
        return run_dir

    def _resolve_run_with_provider(self, run_name: str, provider: str | None) -> Path | None:
        run_dir = self._resolve_run(run_name)
        if run_dir is None:
            return None
        if not provider or provider == "all":
            return run_dir
        if not self._is_safe_segment(provider):
            self._send_error(HTTPStatus.BAD_REQUEST, "Invalid provider name")
            return None
        provider_dir = run_dir / f"provider={provider}"
        if provider_dir.exists() and provider_dir.is_dir():
            return provider_dir
        run_config = load_run_config(run_dir)
        if run_config and not run_config.get("multi_provider"):
            single_provider = run_config.get("provider")
            if single_provider == provider:
                return run_dir
        self._send_error(HTTPStatus.NOT_FOUND, f"Provider not found: {provider}")
        return None

    def _resolve_in_logs(self, target: Path) -> Path | None:
        try:
            resolved = target.resolve()
        except OSError:
            return None
        try:
            resolved.relative_to(self.logs_dir.resolve())
        except ValueError:
            return None
        return resolved

    def _is_safe_segment(self, name: str) -> bool:
        if not name:
            return False
        if "/" in name or "\\" in name:
            return False
        if ".." in name:
            return False
        return True

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(
        self,
        payload: str,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)


def run_server(
    host: str,
    port: int,
    logs_dir: str,
    viz_dir: str,
    open_browser: bool,
    fonts_dir: str | None,
    recent_only: bool,
    include_run_meta: bool,
) -> None:
    logs_path = resolve_logs_dir(logs_dir)
    viz_path = Path(viz_dir).resolve()
    fonts_path = resolve_fonts_dir(viz_path, fonts_dir)
    pkg_path = (viz_path.parent / "pkg").resolve()

    if not logs_path.exists():
        raise FileNotFoundError(f"Logs directory not found: {logs_path}")
    if not viz_path.exists():
        raise FileNotFoundError(f"Viz directory not found: {viz_path}")
    if not fonts_path.exists():
        raise FileNotFoundError(f"Fonts directory not found: {fonts_path}")

    def handler(*args, **kwargs):
        return VizHandler(
            *args,
            logs_dir=logs_path,
            viz_dir=viz_path,
            fonts_dir=fonts_path,
            pkg_dir=pkg_path,
            recent_only=recent_only,
            include_run_meta=include_run_meta,
            **kwargs,
        )
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"

    print(f"Serving Wonton-Soup viz at {url}")
    print(f"Logs: {logs_path}")
    print(f"Viz: {viz_path}")
    print(f"Fonts: {fonts_path}")
    print(f"Pkg: {pkg_path}")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Wonton-Soup visualization UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Path to logs directory (default: ./logs or $SPECTER_LOG_ROOT)",
    )
    parser.add_argument(
        "--viz-dir", default="viz", help="Path to viz directory (default: ./viz)"
    )
    parser.add_argument(
        "--fonts-dir",
        default=None,
        help="Path to fonts directory (default: auto-detect site/fonts)",
    )
    parser.add_argument(
        "--recent-only",
        action="store_true",
        help="Limit /api/runs to the last 7 days by created date.",
    )
    parser.add_argument(
        "--include-run-meta",
        action="store_true",
        help="Read per-run config/status/summary metadata for /api/runs (slower on remote mounts).",
    )
    parser.add_argument("--open", action="store_true", help="Open browser after start")
    args = parser.parse_args()

    run_server(
        args.host,
        args.port,
        args.logs_dir,
        args.viz_dir,
        args.open,
        args.fonts_dir,
        args.recent_only,
        args.include_run_meta,
    )


if __name__ == "__main__":
    main()
