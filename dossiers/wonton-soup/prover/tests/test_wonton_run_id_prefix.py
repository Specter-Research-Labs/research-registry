from __future__ import annotations

import wonton


class _FakeDateTime:
    @classmethod
    def now(cls):
        class _Now:
            def strftime(self, fmt: str) -> str:
                if fmt == "%Y-%m-%d":
                    return "2000-01-02"
                if fmt == "%Y-%m-%d-%H%M%S":
                    return "2000-01-02-030405"
                raise AssertionError(f"Unexpected strftime format: {fmt}")

        return _Now()


def test_build_run_id_date_prefix_policy(monkeypatch) -> None:
    monkeypatch.setattr(wonton, "datetime", _FakeDateTime)
    cases = {
        "research-deepseek-50-123": "2000-01-02-research-deepseek-50-123",
        "corpus-2020-01-01-000000": "corpus-2020-01-01-000000",
        "1999-12-31-research-1": "1999-12-31-research-1",
        "foo/bar": "2000-01-02-foo/bar",
    }

    for run_id, expected in cases.items():
        assert wonton._build_run_id(run_id) == expected
