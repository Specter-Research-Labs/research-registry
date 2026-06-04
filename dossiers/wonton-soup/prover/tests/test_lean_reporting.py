from types import SimpleNamespace

from orchestrator import lean_reporting
from prover.proof import ProofGraph


def _graph(name: str) -> ProofGraph:
    graph = ProofGraph()
    graph.graph.add_node(name, goal_sig=name)
    return graph


def test_compute_pairwise_ged_respects_variant_cap(monkeypatch) -> None:
    monkeypatch.setenv("WONTON_SUMMARY_MAX_PAIRWISE_GED_VARIANTS", "0")
    monkeypatch.setattr(
        lean_reporting._lean_runner,
        "_canonical_graph_edit_distance",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GED should be skipped")),
    )
    result = SimpleNamespace(
        theorem=SimpleNamespace(name="t"),
        wild_type=SimpleNamespace(graph=_graph("wild")),
        interventions=[
            SimpleNamespace(
                intervention=SimpleNamespace(name="block_simp"),
                intervention_run=SimpleNamespace(graph=_graph("block_simp")),
            )
        ],
    )

    ged = lean_reporting.compute_pairwise_ged(result)

    assert ged["ged_matrix"]["wild_type"]["wild_type"] == 0.0
    assert ged["ged_matrix"]["wild_type"]["block_simp"] is None
    assert ged["ged_matrix"]["block_simp"]["wild_type"] is None
    assert ged["ged_policy"]["skip_reason"] == "variant_count>0"
    assert ged["ged_policy"]["skipped_pairs"] == 2
