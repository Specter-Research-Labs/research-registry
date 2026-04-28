from __future__ import annotations

import argparse
import json
import signal
import urllib.error
import urllib.request
import warnings
from contextlib import contextmanager
from typing import cast


@contextmanager
def time_limit(seconds: int):
    def on_alarm(_signum: int, _frame) -> None:
        raise TimeoutError(f"operation timed out after {seconds} seconds")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def main() -> None:
    args = parse_args()
    payload, exit_code = probe_backend(args)
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor-url", required=True)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--user", default="guest")
    parser.add_argument("--secret", default="guestpass")
    parser.add_argument("--connect-timeout-s", type=int, default=20)
    return parser.parse_args()


def probe_backend(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )
    from flybrainlab import Client

    probe_status = probe_processor_http_status(args.processor_url)
    if probe_status == 404:
        return (
            {
                "status": "error",
                "processor_url": args.processor_url,
                "message": (
                    f"processor url probe returned 404 for {args.processor_url}. "
                    "This is not a live FFBO processor websocket."
                ),
            },
            1,
        )
    client = None
    try:
        with time_limit(args.connect_timeout_s):
            client = Client(
                url=args.processor_url,
                ssl=args.processor_url.startswith("wss://"),
                user=args.user,
                secret=args.secret,
                dataset=args.dataset,
                debug=False,
                log_level="error",
            )
        server_info = client.rpc("ffbo.processor.server_information")
        datasets = sorted(valid_datasets(server_info))
        payload = {
            "status": "ok",
            "processor_url": args.processor_url,
            "dataset": args.dataset,
            "datasets": datasets,
            "na_count": len(server_info.get("na", {})),
            "nlp_count": len(server_info.get("nlp", {})),
            "nk_count": len(server_info.get("nk", {})),
            "execution_supported": len(server_info.get("nk", {})) > 0,
        }
        if args.dataset is None and len(datasets) == 1:
            payload["dataset"] = datasets[0]
        return payload, 0
    except Exception as exc:
        message = str(exc)
        datasets = extract_datasets_from_error(message)
        status = "dataset_required" if datasets else "error"
        payload = {
            "status": status,
            "processor_url": args.processor_url,
            "dataset": args.dataset,
            "datasets": list(datasets),
            "message": message,
        }
        return payload, 2 if datasets else 1
    finally:
        if client is not None:
            try:
                client.client.stop()
            except Exception:
                pass


def valid_datasets(server_info: dict[str, object]) -> tuple[str, ...]:
    by_name: dict[str, dict[str, int]] = {}
    for server_type in ("na", "nlp"):
        servers = server_info.get(server_type, {})
        if not isinstance(servers, dict):
            continue
        for config in servers.values():
            if not isinstance(config, dict):
                continue
            config_map = cast(dict[str, object], config)
            dataset_value = config_map.get("dataset", "default")
            dataset = str(dataset_value)
            entry = by_name.setdefault(dataset, {"na": 0, "nlp": 0})
            entry[server_type] += 1
    return tuple(
        dataset
        for dataset, counts in by_name.items()
        if counts["na"] > 0 and counts["nlp"] > 0
    )


def extract_datasets_from_error(message: str) -> tuple[str, ...]:
    marker = "Available datasets on the FFBO processor are the following:\n"
    if marker not in message:
        return ()
    tail = message.split(marker, 1)[1]
    datasets: list[str] = []
    for raw_line in tail.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(". Please choose"):
            break
        if line.startswith("- "):
            datasets.append(line[2:])
    return tuple(datasets)


def probe_processor_http_status(processor_url: str) -> int | None:
    if processor_url.startswith("wss://"):
        http_url = "https://" + processor_url.removeprefix("wss://")
    elif processor_url.startswith("ws://"):
        http_url = "http://" + processor_url.removeprefix("ws://")
    else:
        return None
    request = urllib.request.Request(http_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except (TimeoutError, urllib.error.URLError):
        return None


if __name__ == "__main__":
    main()
