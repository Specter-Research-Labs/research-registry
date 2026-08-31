from __future__ import annotations

import argparse
import json
import sys

from core.compiler_artifacts import (
    CompilerError,
    compiler_summary,
    run_compiler,
    run_compiler_pipeline,
)
from core.engine import execute_program
from core.lean_artifacts import LeanBridgeError, lean_summary, run_lean_request
from examples.catalog import get_example, get_examples
from render import render_example_json, render_example_tree


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lean-tactic-representation",
        description="Structured tactic compiler and kernel-checked Lean executor.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("examples", help="List built-in toy examples")

    show = sub.add_parser("show", help="Run and render one toy example")
    show.add_argument("name")
    show.add_argument("--format", choices=("tree", "json"), default="tree")

    check = sub.add_parser("check", help="Check one toy example")
    check.add_argument("name")
    check.add_argument("--format", choices=("text", "json"), default="text")

    for command, help_text in (
        ("compile", "Compile a sequential source program"),
        ("compile-run", "Compile, execute independently, and compare"),
        ("lean-run", "Execute a lowered request and kernel-check it"),
    ):
        lane = sub.add_parser(command, help=help_text)
        lane.add_argument("input")
        lane.add_argument("--format", choices=("summary", "json"), default="summary")
        lane.add_argument("--no-build", action="store_true")
    return parser.parse_args(argv)


def _toy_check(name: str) -> tuple[dict[str, object], int]:
    example = get_example(name)
    node = execute_program(example.program, example.root, example.rules)
    rows = list(_flatten_invariants(node))
    failed = [row for row in rows if not row.passed]
    return {
        "example": example.name,
        "invariant_count": len(rows),
        "failed_count": len(failed),
        "failed": [{"name": row.name, "detail": row.detail} for row in failed],
    }, 0 if not failed else 1


def _flatten_invariants(node):
    yield from node.invariants
    for child in node.child_nodes:
        yield from _flatten_invariants(child)


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.cmd == "examples":
            for name, example in sorted(get_examples().items()):
                print(f"{name}: {example.description}")
            return 0
        if args.cmd == "show":
            example = get_example(args.name)
            node = execute_program(example.program, example.root, example.rules)
            print(
                render_example_json(example, node)
                if args.format == "json"
                else render_example_tree(example, node)
            )
            return 0
        if args.cmd == "check":
            payload, code = _toy_check(args.name)
            if args.format == "json":
                _print(payload)
            else:
                print(f"example={payload['example']}")
                print(f"invariants={payload['invariant_count']}")
                print(f"failed={payload['failed_count']}")
            return code

        build = not args.no_build
        if args.cmd == "compile":
            response = run_compiler(args.input, build=build)
            payload = response if args.format == "json" else {
                "request_id": response["compilation"]["target_request"]["request_id"],
                "instructions": response["compilation"]["instruction_count"],
            }
        elif args.cmd == "compile-run":
            response = run_compiler_pipeline(args.input, build=build)
            payload = response if args.format == "json" else compiler_summary(response)
        elif args.cmd == "lean-run":
            response = run_lean_request(args.input, build=build)
            payload = response if args.format == "json" else lean_summary(response)
        else:
            raise SystemExit(f"unknown command: {args.cmd}")
        _print(payload)
        return 0
    except (CompilerError, LeanBridgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
