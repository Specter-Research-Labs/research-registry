from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

from analysis.viz_server import VizHandler


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_handler(logs_dir: Path) -> VizHandler:
    handler = object.__new__(VizHandler)
    handler.logs_dir = logs_dir
    handler.viz_dir = logs_dir
    handler.fonts_dir = logs_dir
    handler.pkg_dir = logs_dir
    handler.recent_only = False
    handler.include_run_meta = True
    return handler


def test_handle_dashboard_provider_all_returns_multi_provider_payload(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    run_dir = logs_dir / "run-a"
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": "run-a",
            "multi_provider": True,
            "theorem_selection": {"selected_theorems": ["t1", "t2"]},
        },
    )
    _write_json(run_dir / "run_status.json", {"status": "completed"})
    _write_json(run_dir / "providers_summary.json", {"providers": [{"provider": "deepseek"}]})
    _write_json(
        run_dir / "providers_theorem_summary.json",
        {"theorems": [{"name": "t1", "provider": "deepseek"}]},
    )

    captured: dict[str, object] = {}
    handler = _make_handler(logs_dir)
    handler._send_json = (
        lambda payload, status=HTTPStatus.OK: captured.setdefault("payload", payload)
    )
    handler._send_error = lambda status, message: captured.setdefault("error", (status, message))

    handler._handle_dashboard("run-a", "all")

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["multi_provider"] is True
    assert payload["status"] == {"status": "completed"}
    assert payload["providers_summary"] == {"providers": [{"provider": "deepseek"}]}
    assert payload["providers_theorem_summary"] == {
        "theorems": [{"name": "t1", "provider": "deepseek"}]
    }
    assert payload["errors"] == []


def test_handle_dashboard_v2_missing_summary_returns_not_found(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    run_dir = logs_dir / "run-b"
    _write_json(run_dir / "run_config.json", {"run_id": "run-b", "provider": "deepseek"})

    captured: dict[str, object] = {}
    handler = _make_handler(logs_dir)
    handler._send_json = (
        lambda payload, status=HTTPStatus.OK: captured.setdefault("payload", payload)
    )
    handler._send_error = lambda status, message: captured.setdefault("error", (status, message))

    handler._handle_dashboard_v2("run-b", None)

    assert captured["error"] == (HTTPStatus.NOT_FOUND, "Missing summary.json.gz")
