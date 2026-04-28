from __future__ import annotations

import argparse

from core.engine import execute_program
from examples.catalog import get_example, get_examples
from render import render_example_json, render_example_tree


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lean-tactic-representation",
        description="Toy interpreter and visualizer for algebraic tactic-calculus fragments.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("examples", help="List built-in examples")

    show = sub.add_parser("show", help="Run and render one example")
    show.add_argument("name", help="Example name")
    show.add_argument(
        "--format",
        choices=("tree", "json"),
        default="tree",
        help="Render format",
    )

    check = sub.add_parser("check", help="Run one example and report invariant status")
    check.add_argument("name", help="Example name")
    check.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Render format",
    )

    return parser.parse_args(argv)


def _cmd_examples() -> int:
    for name, example in sorted(get_examples().items()):
        print(f"{name}: {example.description}")
    return 0


def _cmd_show(name: str, fmt: str) -> int:
    example = get_example(name)
    node = execute_program(example.program, example.root, example.rules)
    if fmt == "json":
        print(render_example_json(example, node))
    else:
        print(render_example_tree(example, node))
    return 0


def _cmd_check(name: str, fmt: str) -> int:
    example = get_example(name)
    node = execute_program(example.program, example.root, example.rules)
    invariant_rows = [*node.invariants]
    for child in node.child_nodes:
        invariant_rows.extend(_flatten_invariants(child))
    failed = [row for row in invariant_rows if not row.passed]
    payload = {
        "example": example.name,
        "invariant_count": len(invariant_rows),
        "failed_count": len(failed),
        "failed": [
            {
                "name": row.name,
                "detail": row.detail,
            }
            for row in failed
        ],
    }
    if fmt == "json":
        import json

        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"example={example.name}")
        print(f"invariants={len(invariant_rows)}")
        print(f"failed={len(failed)}")
        for row in failed:
            print(f"FAIL {row.name}: {row.detail}")
    return 0 if not failed else 1


def _flatten_invariants(node) -> list:
    rows = list(node.invariants)
    for child in node.child_nodes:
        rows.extend(_flatten_invariants(child))
    return rows


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.cmd == "examples":
        return _cmd_examples()
    if args.cmd == "show":
        return _cmd_show(args.name, args.format)
    if args.cmd == "check":
        return _cmd_check(args.name, args.format)
    raise SystemExit(f"unknown command: {args.cmd}")
