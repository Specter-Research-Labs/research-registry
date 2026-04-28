from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from leantree import utils
from leantree.repl_adapter.interaction import LeanProcess


def test_resolve_tool_binary_falls_back_to_elan_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    lake = home / ".elan" / "bin" / "lake"
    lake.parent.mkdir(parents=True)
    lake.write_text("", encoding="utf-8")
    lake.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(utils.shutil, "which", lambda _: None)

    assert utils.resolve_tool_binary("lake") == lake

def test_lean_process_start_async_uses_resolved_lake_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class _FakeStream:
        async def readline(self) -> bytes:
            return b""

    class _FakeProc:
        def __init__(self) -> None:
            self.stdin = object()
            self.stdout = object()
            self.stderr = _FakeStream()

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs["cwd"]
        return _FakeProc()

    async def run_start() -> None:
        proc = LeanProcess(tmp_path / "repl", tmp_path / "project")
        await proc.start_async()
        if proc._stderr_task is not None:
            await proc._stderr_task

    monkeypatch.setattr(utils, "require_tool_binary", lambda name: Path("/tmp/fake-lake"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    asyncio.run(run_start())

    assert captured["cmd"] == ("/tmp/fake-lake", "env", str(tmp_path / "repl"))
    assert captured["cwd"] == str(tmp_path / "project")
