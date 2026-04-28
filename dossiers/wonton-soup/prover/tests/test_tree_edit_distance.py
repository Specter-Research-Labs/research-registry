from prover.tree_edit_distance import OrderedTree, normalized_tree_edit_distance, tree_edit_distance


def test_tree_edit_distance_unit_cost_contracts():
    t = OrderedTree("a", (OrderedTree("b"), OrderedTree("c")))
    assert tree_edit_distance(t, t) == 0
    assert normalized_tree_edit_distance(t, t) == 0.0

    t1 = OrderedTree("a", (OrderedTree("b"),))
    t2 = OrderedTree("a", (OrderedTree("b"), OrderedTree("c")))
    assert tree_edit_distance(t1, t2) == 1
    assert tree_edit_distance(t2, t1) == 1

    t1 = OrderedTree("a", (OrderedTree("b"),))
    t2 = OrderedTree("a", (OrderedTree("c"),))
    assert tree_edit_distance(t1, t2) == 1
