from __future__ import annotations

import pytest

from tt_lenia.ttlang_runtime import run_ttlang_kernel


def test_run_ttlang_kernel_suppresses_normal_stdout(capsys, monkeypatch):
    monkeypatch.delenv("LENIA_TT_SHOW_TTLANG_COMPILE", raising=False)

    def kernel():
        print("generated kernel source")
        return 7

    assert run_ttlang_kernel(kernel) == 7
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_ttlang_kernel_replays_stdout_on_failure(capsys, monkeypatch):
    monkeypatch.delenv("LENIA_TT_SHOW_TTLANG_COMPILE", raising=False)

    def kernel():
        print("generated kernel source")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_ttlang_kernel(kernel)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "generated kernel source" in captured.err


def test_run_ttlang_kernel_honors_verbose_env(capsys, monkeypatch):
    monkeypatch.setenv("LENIA_TT_SHOW_TTLANG_COMPILE", "1")

    def kernel():
        print("generated kernel source")

    run_ttlang_kernel(kernel)
    captured = capsys.readouterr()
    assert "generated kernel source" in captured.out
    assert captured.err == ""
