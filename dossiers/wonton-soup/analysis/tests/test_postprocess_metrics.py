from __future__ import annotations

from typing import Any

from analysis import postprocess_metrics
from prover.proof import ProofGraph


class _FakeGoalSigTed:
    tree_errors: dict[str, str] = {}

    def tree(self, _sig: str) -> object:
        return object()

    def normalized_distance(self, _left: str, _right: str) -> float:
        return 0.0


def _graph() -> ProofGraph:
    graph = ProofGraph.for_search_trace(backend="lean")
    graph.add_node("root", goal_type="True", goal_sig="root")
    graph.add_expansion("root", "trivial", [], [], [])
    return graph


def test_compute_soft_search_graph_ged_passes_timeout(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_graph_edit_distance(*_args: object, **kwargs: object) -> float:
        captured.update(kwargs)
        return 0.0

    monkeypatch.setattr(postprocess_metrics.nx, "graph_edit_distance", fake_graph_edit_distance)

    result = postprocess_metrics.compute_soft_search_graph_ged(
        _graph(),
        _graph(),
        goal_sig_ted=_FakeGoalSigTed(),  # type: ignore[arg-type]
        timeout_sec=0.25,
    )

    assert result["value"] == 0.0
    assert captured["timeout"] == 0.25


def test_compute_soft_search_graph_ged_marks_timeout_invalid(monkeypatch) -> None:
    def fake_graph_edit_distance(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(postprocess_metrics.nx, "graph_edit_distance", fake_graph_edit_distance)

    result = postprocess_metrics.compute_soft_search_graph_ged(
        _graph(),
        _graph(),
        goal_sig_ted=_FakeGoalSigTed(),  # type: ignore[arg-type]
        timeout_sec=0.25,
    )

    assert result["value"] is None
    assert result["valid"] is False
    assert "timeout" in result["validity_notes"][0]


def test_postprocess_params_reads_soft_ged_env(monkeypatch) -> None:
    monkeypatch.setenv("WONTON_POSTPROCESS_MAX_SOFT_GED_NODES", "8")
    monkeypatch.setenv("WONTON_POSTPROCESS_MAX_SOFT_GED_EDGES", "16")
    monkeypatch.setenv("WONTON_POSTPROCESS_SOFT_GED_TIMEOUT_SEC", "0.5")
    monkeypatch.setenv("WONTON_POSTPROCESS_MAX_NOVELTY_PAIRS", "32")
    monkeypatch.setenv("WONTON_POSTPROCESS_MAX_PATH_DP_CELLS", "64")
    monkeypatch.setenv("WONTON_POSTPROCESS_ROOT_GOAL_MODE", "skip")

    params = postprocess_metrics.PostprocessParams()

    assert params.max_soft_ged_nodes == 8
    assert params.max_soft_ged_edges == 16
    assert params.soft_ged_timeout_sec == 0.5
    assert params.max_novelty_pairs == 32
    assert params.max_path_dp_cells == 64
    assert params.root_goal_mode == "skip"


def test_postprocess_params_rejects_invalid_soft_ged_env(monkeypatch) -> None:
    monkeypatch.setenv("WONTON_POSTPROCESS_MAX_SOFT_GED_NODES", "-1")

    try:
        postprocess_metrics.PostprocessParams()
    except ValueError as exc:
        assert "WONTON_POSTPROCESS_MAX_SOFT_GED_NODES" in str(exc)
    else:
        raise AssertionError("expected invalid env override to raise")


def test_compute_goal_novelty_zero_max_pairs_skips_goal_distances() -> None:
    graph = _graph()
    intervention = ProofGraph.for_search_trace(backend="lean")
    intervention.add_node("root", goal_type="True", goal_sig="root")
    intervention.add_expansion("root", "intro", ["child"], [], [])
    intervention.add_node("child", goal_type="False", goal_sig="child")

    result = postprocess_metrics.compute_goal_novelty(
        graph,
        intervention,
        goal_sig_ted=_FakeGoalSigTed(),  # type: ignore[arg-type]
        max_pairs=0,
    )

    assert result["valid"] is False
    assert result["validity_notes"] == ["skipped: max_pairs=0"]
    assert result["novel_goal_count"] == 1
