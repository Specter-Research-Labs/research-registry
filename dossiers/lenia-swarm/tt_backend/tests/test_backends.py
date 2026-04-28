from __future__ import annotations

import pytest

from tt_lenia import backends


def test_make_runtime_engine_routes_tt_to_spectral_ttlang_path(monkeypatch):
    calls: list[tuple[object, object]] = []

    class FakeEngine:
        def __init__(self, *args, **kwargs):
            calls.append((kwargs.get("front_half_mode"), kwargs.get("reintegration_mode")))

    monkeypatch.setattr(backends, "TTFlowLeniaEngine", FakeEngine)

    backends.make_runtime_engine("tt", object(), object(), device="mesh")

    assert calls == [("dft_ttlang", "ttlang")]


def test_make_runtime_engine_rejects_non_canonical_backend():
    with pytest.raises(ValueError, match="Expected 'tt'"):
        backends.make_runtime_engine("not-tt", object(), object(), device="mesh")


def test_uses_ttnn_runtime_only_matches_canonical_tt():
    assert backends.uses_ttnn_runtime("tt") is True
    assert backends.uses_ttnn_runtime("not-tt") is False
