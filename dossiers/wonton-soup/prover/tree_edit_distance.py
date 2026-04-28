from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderedTree:
    """A minimal ordered rooted tree.

    This is intentionally tiny: labels are strings and children are ordered.
    """

    label: str
    children: tuple["OrderedTree", ...] = ()


def _postorder_labels_and_leftmost(root: OrderedTree) -> tuple[list[str], list[int]]:
    """Return (labels, leftmost_leaf_index) for nodes in postorder.

    We assign nodes an index by postorder (children first, then node). For each node i,
    leftmost[i] is the postorder index of the leftmost leaf in i's subtree.
    """

    labels: list[str] = []
    leftmost: list[int] = []

    # Frame: (node, next_child_index, leftmost_leaf_of_first_child)
    stack: list[tuple[OrderedTree, int, int | None]] = [(root, 0, None)]
    while stack:
        node, child_idx, first_leftmost = stack[-1]
        if child_idx < len(node.children):
            child = node.children[child_idx]
            stack[-1] = (node, child_idx + 1, first_leftmost)
            stack.append((child, 0, None))
            continue

        idx = len(labels)
        labels.append(node.label)
        lm = idx if first_leftmost is None else first_leftmost
        leftmost.append(lm)

        stack.pop()
        if stack and stack[-1][2] is None:
            # This was the first child of the parent; propagate its leftmost leaf.
            parent, parent_child_idx, _ = stack[-1]
            stack[-1] = (parent, parent_child_idx, lm)

    return labels, leftmost


def _keyroots(leftmost: list[int]) -> list[int]:
    # In postorder, leftmost is non-decreasing. Keyroots are the last occurrence of each
    # leftmost value.
    n = len(leftmost)
    roots: list[int] = []
    for i in range(n):
        if i == n - 1 or leftmost[i] != leftmost[i + 1]:
            roots.append(i)
    return roots


def tree_edit_distance(t1: OrderedTree, t2: OrderedTree) -> int:
    """Zhang–Shasha ordered tree edit distance with unit costs.

    Costs:
    - insert node: 1
    - delete node: 1
    - substitute node: 0 if labels match else 1

    Returns the minimum edit cost to transform t1 into t2.
    """

    labels1, l1 = _postorder_labels_and_leftmost(t1)
    labels2, l2 = _postorder_labels_and_leftmost(t2)
    n1 = len(labels1)
    n2 = len(labels2)

    if n1 == 0:
        return n2
    if n2 == 0:
        return n1

    td = [[0 for _ in range(n2)] for _ in range(n1)]
    kr1 = _keyroots(l1)
    kr2 = _keyroots(l2)

    for i in kr1:
        i0 = l1[i]
        for j in kr2:
            j0 = l2[j]

            m = i - i0 + 2
            n = j - j0 + 2
            fd = [[0 for _ in range(n)] for _ in range(m)]

            for di in range(1, m):
                fd[di][0] = fd[di - 1][0] + 1
            for dj in range(1, n):
                fd[0][dj] = fd[0][dj - 1] + 1

            for di in range(1, m):
                node_i = i0 + di - 1
                for dj in range(1, n):
                    node_j = j0 + dj - 1
                    if l1[node_i] == i0 and l2[node_j] == j0:
                        subst = 0 if labels1[node_i] == labels2[node_j] else 1
                        best = fd[di - 1][dj] + 1
                        best = min(best, fd[di][dj - 1] + 1)
                        best = min(best, fd[di - 1][dj - 1] + subst)
                        fd[di][dj] = best
                        td[node_i][node_j] = best
                    else:
                        di1 = l1[node_i] - i0
                        dj1 = l2[node_j] - j0
                        best = fd[di - 1][dj] + 1
                        best = min(best, fd[di][dj - 1] + 1)
                        best = min(best, fd[di1][dj1] + td[node_i][node_j])
                        fd[di][dj] = best

    return td[n1 - 1][n2 - 1]


def normalized_tree_edit_distance(t1: OrderedTree, t2: OrderedTree) -> float:
    """Return TED normalized to [0, 1] via dist / (|t1| + |t2|)."""

    labels1, _ = _postorder_labels_and_leftmost(t1)
    labels2, _ = _postorder_labels_and_leftmost(t2)
    denom = len(labels1) + len(labels2)
    if denom == 0:
        return 0.0
    return tree_edit_distance(t1, t2) / denom

