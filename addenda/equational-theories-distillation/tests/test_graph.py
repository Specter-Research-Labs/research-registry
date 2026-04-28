from graph import ImplicationGraph, decode_rle


def test_decode_rle_reconstructs_expected_bytes() -> None:
    assert decode_rle([7, 2, 6, 1, 3, 3], expected_length=6) == bytes([7, 7, 6, 3, 3, 3])


def test_graph_status_uses_one_based_law_ids() -> None:
    graph = ImplicationGraph(law_count=2, statuses=bytes([7, 6, 2, 3]), equivalence_classes=())

    assert graph.status(1, 1) == 7
    assert graph.status(1, 2) == 6
    assert graph.status(2, 1) == 2
    assert graph.status(2, 2) == 3
