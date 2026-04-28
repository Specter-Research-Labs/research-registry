#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


RUNNER_VERSION = "0.1.0"
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_HEARTBEAT_SECONDS = 10.0
DEFAULT_CANCEL_GRACE_SECONDS = 15.0
DEFAULT_REPORT_RETRIES = 12
DEFAULT_REPORT_RETRY_SECONDS = 2.0
RESULT_PREFIX = "SPECTER_RESULT_JSON="

SCRIPT_PATH = Path(__file__).resolve()
OPS_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
DEFAULT_ENV_PATH = OPS_ROOT / ".env.runner"


class RunnerError(RuntimeError):
    pass


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RunnerError(f"missing required environment variable: {name}")
    return value.strip()


def maybe_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def split_csv(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def detect_capabilities() -> list[str]:
    capabilities: set[str] = set()
    command_capabilities = {
        "python3": "python",
        "nix": "nix",
        "uv": "uv",
        "docker": "docker",
        "typst": "typst",
        "xcodebuild": "xcode",
        "ffmpeg": "ffmpeg",
        "claude": "claude_cli",
        "gemini": "gemini_cli",
        "codex": "codex_cli",
        "gh": "gh",
        "git": "git",
        "jq": "jq",
        "pandoc": "pandoc",
        "rsync": "rsync",
        "ssh": "ssh",
    }
    for command, capability in command_capabilities.items():
        if shutil.which(command):
            capabilities.add(capability)

    if platform.system() == "Darwin":
        capabilities.add("macos")
    if platform.machine().lower() in {"arm64", "aarch64"}:
        capabilities.add("apple_silicon")

    capabilities.update(split_csv(maybe_env("RUNNER_EXTRA_CAPABILITIES")))
    return sorted(capabilities)


def resolve_runtime_root() -> Path:
    if "SPECTER_RUNTIME_ROOT" in os.environ:
        raw = os.environ.get("SPECTER_RUNTIME_ROOT", "")
        if not raw.strip():
            raise RunnerError("SPECTER_RUNTIME_ROOT is set but empty")
        return Path(raw).expanduser().resolve() / "specter-dispatch"
    return REPO_ROOT / "tmp" / "specter-dispatch"


def runner_identity() -> tuple[str, str]:
    host = socket.gethostname().split(".")[0]
    runner_id = maybe_env("RUNNER_ID") or host
    display_name = maybe_env("RUNNER_DISPLAY_NAME") or host
    return runner_id, display_name


def resolve_job_cwd(raw: Any) -> Path:
    if not isinstance(raw, str):
        raise RunnerError("job cwd must be a string")
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def read_tail(path: Path, max_lines: int = 20) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def extract_structured_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        if not line.startswith(RESULT_PREFIX):
            continue
        payload = line[len(RESULT_PREFIX) :]
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RunnerError(f"invalid structured result JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RunnerError("structured result payload must be a JSON object")
        return parsed
    return None


def create_connection_with_fallback(
    address: tuple[str, int],
    timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
    *,
    all_errors: bool = False,
) -> socket.socket:
    host, port = address
    errors: list[OSError] = []
    addrinfo = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    ordered = sorted(
        addrinfo,
        key=lambda item: 0 if item[0] == socket.AF_INET else 1,
    )
    for family, socktype, proto, _, sockaddr in ordered:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            errors.append(exc)
            if sock is not None:
                sock.close()
    if all_errors and len(errors) > 1:
        raise ExceptionGroup("dispatch connection failed", errors)
    if errors:
        raise errors[-1]
    raise OSError(f"no addresses resolved for {host}:{port}")


class DispatchHTTPConnection(http.client.HTTPConnection):
    _create_connection = staticmethod(create_connection_with_fallback)


class DispatchHTTPSConnection(http.client.HTTPSConnection):
    _create_connection = staticmethod(create_connection_with_fallback)


class DispatchHTTPHandler(request.HTTPHandler):
    def http_open(self, req: request.Request):
        return self.do_open(DispatchHTTPConnection, req)


class DispatchHTTPSHandler(request.HTTPSHandler):
    def __init__(self) -> None:
        super().__init__(context=ssl.create_default_context())

    def https_open(self, req: request.Request):
        return self.do_open(DispatchHTTPSConnection, req)


class DispatchClient:
    def __init__(self, base_url: str, shared_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.shared_secret = shared_secret
        self.opener = request.build_opener(
            DispatchHTTPHandler(),
            DispatchHTTPSHandler(),
        )

    def _request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "authorization": f"Bearer {self.shared_secret}",
                "content-type": "application/json",
                "user-agent": f"specter-dispatch-runner/{RUNNER_VERSION}",
            },
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RunnerError(f"{path} failed with {exc.code}: {detail}") from exc
        except error.URLError as exc:
            reason = exc.reason if exc.reason is not None else exc
            raise RunnerError(f"{path} failed: {reason}") from exc

    def register(self, runner_id: str, display_name: str, capabilities: list[str], concurrency_limit: int) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runner/register",
            {
                "runnerId": runner_id,
                "displayName": display_name,
                "version": RUNNER_VERSION,
                "capabilities": capabilities,
                "concurrencyLimit": concurrency_limit,
            },
        )

    def claim(self, runner_id: str) -> dict[str, Any]:
        return self._request("POST", "/runner/claim", {"runnerId": runner_id})

    def heartbeat(self, runner_id: str, job_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runner/heartbeat",
            {"runnerId": runner_id, "jobId": job_id},
        )

    def complete(self, runner_id: str, job_id: str, summary: str, exit_code: int | None, result: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runner/complete",
            {
                "runnerId": runner_id,
                "jobId": job_id,
                "summary": summary,
                "exitCode": exit_code,
                "result": result,
            },
        )

    def fail(self, runner_id: str, job_id: str, summary: str, exit_code: int | None, result: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runner/fail",
            {
                "runnerId": runner_id,
                "jobId": job_id,
                "summary": summary,
                "exitCode": exit_code,
                "result": result,
            },
        )

    def cancelled(self, runner_id: str, job_id: str, summary: str, exit_code: int | None, result: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runner/cancelled",
            {
                "runnerId": runner_id,
                "jobId": job_id,
                "summary": summary,
                "exitCode": exit_code,
                "result": result,
            },
        )


class SpecterRunner:
    def __init__(self, client: DispatchClient, poll_seconds: float, heartbeat_seconds: float, cancel_grace_seconds: float, once: bool) -> None:
        self.client = client
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.cancel_grace_seconds = cancel_grace_seconds
        self.once = once
        self.stop_requested = False
        self.runtime_root = resolve_runtime_root()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.runner_id, self.display_name = runner_identity()
        self.capabilities = detect_capabilities()
        self.concurrency_limit = 1

    def post_terminal_update(
        self,
        reporter: Any,
        job_id: str,
        summary: str,
        exit_code: int | None,
        result: dict[str, Any],
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, DEFAULT_REPORT_RETRIES + 1):
            try:
                reporter(
                    self.runner_id,
                    job_id,
                    summary,
                    exit_code,
                    result,
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(
                    f"runner terminal report attempt {attempt}/{DEFAULT_REPORT_RETRIES} failed for {job_id}: {exc}",
                    file=sys.stderr,
                )
                if attempt < DEFAULT_REPORT_RETRIES:
                    time.sleep(DEFAULT_REPORT_RETRY_SECONDS)
        if last_error is not None:
            raise RunnerError(f"unable to report terminal job state for {job_id}: {last_error}")

    def request_stop(self, _signum: int, _frame: Any) -> None:
        self.stop_requested = True

    def register(self) -> None:
        self.client.register(
            self.runner_id,
            self.display_name,
            self.capabilities,
            self.concurrency_limit,
        )

    def job_runtime_dir(self, job_id: str) -> Path:
        return self.runtime_root / "jobs" / job_id

    def run_job(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        argv = [str(part) for part in job["argv"]]
        cwd = resolve_job_cwd(job["cwd"])
        job_dir = self.job_runtime_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = job_dir / "stdout.log"
        stderr_path = job_dir / "stderr.log"
        meta_path = job_dir / "job.json"
        meta_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

        started = time.monotonic()
        cancel_requested = False
        termination_started_at: float | None = None

        env = os.environ.copy()
        env["SPECTER_ZULIP_JOB_ID"] = job_id

        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            next_heartbeat = time.monotonic() + self.heartbeat_seconds

            while True:
                return_code = process.poll()
                now = time.monotonic()
                if return_code is not None:
                    break

                if now >= next_heartbeat:
                    try:
                        heartbeat = self.client.heartbeat(self.runner_id, job_id)
                    except RunnerError as exc:
                        print(
                            f"runner heartbeat failed for {job_id}: {exc}",
                            file=sys.stderr,
                        )
                    else:
                        cancel_requested = bool(heartbeat.get("cancelRequested"))
                    next_heartbeat = now + self.heartbeat_seconds

                if (cancel_requested or self.stop_requested) and termination_started_at is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    termination_started_at = now

                if termination_started_at is not None and now - termination_started_at >= self.cancel_grace_seconds:
                    os.killpg(process.pid, signal.SIGKILL)
                    termination_started_at = None

                time.sleep(min(self.poll_seconds, 1.0))

        finished = time.monotonic()
        duration_seconds = round(finished - started, 3)
        stderr_tail = read_tail(stderr_path)
        result = {
            "durationSeconds": duration_seconds,
            "cwd": str(cwd),
            "argv": argv,
            "stdoutPath": str(stdout_path),
            "stderrPath": str(stderr_path),
            "jobDir": str(job_dir),
        }

        if cancel_requested or self.stop_requested:
            summary = f"Cancelled after {duration_seconds:.1f}s."
            if stderr_tail:
                result["stderrTail"] = stderr_tail
            self.post_terminal_update(
                self.client.cancelled,
                job_id,
                summary,
                process.returncode,
                result,
            )
            return

        expects_structured_result = bool(
            isinstance(job.get("args"), dict)
            and job["args"].get("expectsStructuredResult") is True
        )
        try:
            structured_result = extract_structured_result(stdout_path)
        except RunnerError as exc:
            result["stdoutTail"] = read_tail(stdout_path)
            summary = f"Failed to parse structured result after {duration_seconds:.1f}s: {exc}"
            self.client.fail(
                self.runner_id,
                job_id,
                summary,
                process.returncode,
                result,
            )
            return

        if expects_structured_result and structured_result is None:
            result["stdoutTail"] = read_tail(stdout_path)
            summary = (
                f"Expected a structured publish result after {duration_seconds:.1f}s, "
                "but the command did not emit one."
            )
            self.client.fail(
                self.runner_id,
                job_id,
                summary,
                process.returncode,
                result,
            )
            return

        if structured_result is not None:
            result.update(structured_result)

        if process.returncode == 0:
            summary = f"Succeeded in {duration_seconds:.1f}s."
            self.post_terminal_update(
                self.client.complete,
                job_id,
                summary,
                process.returncode,
                result,
            )
            return

        if stderr_tail:
            result["stderrTail"] = stderr_tail
        summary = f"Failed with exit code {process.returncode} after {duration_seconds:.1f}s."
        self.post_terminal_update(
            self.client.fail,
            job_id,
            summary,
            process.returncode,
            result,
        )

    def loop(self) -> int:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        while not self.stop_requested:
            try:
                self.register()
                claim = self.client.claim(self.runner_id)
                job = claim.get("job")
                if not job:
                    if self.once:
                        return 0
                    time.sleep(self.poll_seconds)
                    continue
                self.run_job(job)
                if self.once:
                    return 0
            except RunnerError as exc:
                print(f"runner error: {exc}", file=sys.stderr)
                if self.once:
                    return 1
                time.sleep(max(self.poll_seconds, 5.0))
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Specter compute worker.")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="Path to the runner env file.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the dispatch base URL.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Register, claim at most one job, and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file).expanduser())
    if args.base_url:
        os.environ["DISPATCH_BASE_URL"] = args.base_url

    client = DispatchClient(
        require_env("DISPATCH_BASE_URL"),
        require_env("RUNNER_SHARED_SECRET"),
    )
    poll_seconds = float(maybe_env("RUNNER_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    heartbeat_seconds = float(
        maybe_env("RUNNER_HEARTBEAT_SECONDS") or DEFAULT_HEARTBEAT_SECONDS
    )
    cancel_grace_seconds = float(
        maybe_env("RUNNER_CANCEL_GRACE_SECONDS") or DEFAULT_CANCEL_GRACE_SECONDS
    )
    runner = SpecterRunner(
        client=client,
        poll_seconds=poll_seconds,
        heartbeat_seconds=heartbeat_seconds,
        cancel_grace_seconds=cancel_grace_seconds,
        once=args.once,
    )
    return runner.loop()


if __name__ == "__main__":
    raise SystemExit(main())
