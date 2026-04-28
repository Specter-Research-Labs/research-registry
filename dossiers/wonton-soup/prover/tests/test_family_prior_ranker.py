import json
from pathlib import Path

from prover.rankers import FamilyPriorModel, family_prior_ranker


class _Node:
    def __init__(self, goal_features):
        self.goal_features = goal_features


def test_family_prior_ranker_reorders_by_model_score(tmp_path: Path) -> None:
    # Two families: simplify, other. Feature_dim=2.
    model_path = tmp_path / "model.json"
    payload = {
        "schema_version": 1,
        "model": "family_prior_logreg",
        "families": ["simplify", "other"],
        "feature_dim": 2,
        "scaler": {"mean": [0.0, 0.0], "std": [1.0, 1.0]},
        "weights": [[10.0, 0.0], [-10.0, 0.0]],
        "bias": [0.0, 0.0],
        "meta": {},
    }
    model_path.write_text(json.dumps(payload))

    model = FamilyPriorModel.load(model_path)
    ranker = family_prior_ranker(model, alpha=1.0)

    node = _Node(goal_features=[1.0, 0.0])
    ranked = ranker([("simp", 0.1), ("exact h", 0.9)], iteration=0, node=node)
    assert [t for t, _ in ranked] == ["simp", "exact h"]
