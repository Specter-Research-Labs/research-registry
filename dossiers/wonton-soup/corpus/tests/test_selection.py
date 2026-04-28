from corpus.selection import select_items


def test_select_items_head_sorts_by_id():
    items = [{"id": "b"}, {"id": "a"}, {"id": "c"}]
    selected, meta = select_items(items, lambda x: x["id"], offset=0, limit=None)
    assert [x["id"] for x in selected] == ["a", "b", "c"]
    assert meta.method == "head"


def test_select_items_head_offset_and_limit():
    items = [{"id": "b"}, {"id": "a"}, {"id": "c"}, {"id": "d"}]
    selected, meta = select_items(items, lambda x: x["id"], offset=1, limit=2)
    assert [x["id"] for x in selected] == ["b", "c"]
    assert meta.method == "head"
    assert meta.offset == 1
    assert meta.limit == 2


def test_select_items_hash_sample_is_order_invariant():
    items = [{"id": "b"}, {"id": "a"}, {"id": "c"}, {"id": "d"}]
    selected1, meta1 = select_items(items, lambda x: x["id"], sample=2, seed=123)
    selected2, meta2 = select_items(list(reversed(items)), lambda x: x["id"], sample=2, seed=123)
    assert [x["id"] for x in selected1] == [x["id"] for x in selected2]
    assert meta1.method == "hash_sample"
    assert meta2.method == "hash_sample"


def test_select_items_hash_sample_offset_window():
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}, {"id": "e"}]
    sel0, _ = select_items(items, lambda x: x["id"], sample=2, seed=7, offset=0)
    sel1, _ = select_items(items, lambda x: x["id"], sample=2, seed=7, offset=1)
    assert [x["id"] for x in sel0][1:] == [x["id"] for x in sel1][:1]


def test_select_items_rejects_negative_offset_and_limit():
    items = [{"id": "a"}]
    try:
        select_items(items, lambda x: x["id"], offset=-1)
    except ValueError as e:
        assert "offset must be >= 0" in str(e)
    else:
        raise AssertionError("expected ValueError for negative offset")

    try:
        select_items(items, lambda x: x["id"], limit=-1)
    except ValueError as e:
        assert "limit must be >= 0" in str(e)
    else:
        raise AssertionError("expected ValueError for negative limit")


def test_select_items_rejects_sampling_without_seed_and_with_limit():
    items = [{"id": "a"}, {"id": "b"}]
    try:
        select_items(items, lambda x: x["id"], sample=1, seed=None)
    except ValueError as e:
        assert "--seed is required when --sample is set" in str(e)
    else:
        raise AssertionError("expected ValueError when sampling without seed")

    try:
        select_items(items, lambda x: x["id"], sample=1, seed=123, limit=1)
    except ValueError as e:
        assert "Use --sample or --limit, not both" in str(e)
    else:
        raise AssertionError("expected ValueError when using sample+limit")
