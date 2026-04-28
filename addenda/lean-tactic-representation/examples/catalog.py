from __future__ import annotations

from core.model import (
    And,
    Apply,
    Atom,
    Constructor,
    Exact,
    Example,
    Hypothesis,
    Obligation,
    Program,
    Rule,
)


def _atom(name: str, *args: str) -> Atom:
    return Atom(name=name, args=args)


def get_examples() -> dict[str, Example]:
    examples = [
        Example(
            name="exact_atom",
            description="Direct closure by matching a hypothesis against the target.",
            root=Obligation(
                goal_id="g0",
                context=(Hypothesis("h", _atom("P")),),
                target=_atom("P"),
            ),
            rules=(),
            program=Program(step=Exact("h")),
        ),
        Example(
            name="constructor_and",
            description="Independent branching through conjunction introduction.",
            root=Obligation(
                goal_id="g0",
                context=(Hypothesis("hp", _atom("P")), Hypothesis("hq", _atom("Q"))),
                target=And(_atom("P"), _atom("Q")),
            ),
            rules=(),
            program=Program(
                step=Constructor(),
                children=(Program(step=Exact("hp")), Program(step=Exact("hq"))),
            ),
        ),
        Example(
            name="apply_mk_pair",
            description="Independent premises introduced by applying a rule with two arguments.",
            root=Obligation(
                goal_id="g0",
                context=(Hypothesis("hp", _atom("P")), Hypothesis("hq", _atom("Q"))),
                target=And(_atom("P"), _atom("Q")),
            ),
            rules=(
                Rule(
                    name="mkPair",
                    premises=(_atom("P"), _atom("Q")),
                    conclusion=And(_atom("P"), _atom("Q")),
                ),
            ),
            program=Program(
                step=Apply("mkPair"),
                children=(Program(step=Exact("hp")), Program(step=Exact("hq"))),
            ),
        ),
        Example(
            name="apply_coupled_pack",
            description=(
                "Coupled premises introduced by applying a rule with a shared metavariable."
            ),
            root=Obligation(
                goal_id="g0",
                context=(
                    Hypothesis("hp", _atom("P", "k")),
                    Hypothesis("hq", _atom("Q", "k")),
                ),
                target=_atom("R"),
            ),
            rules=(
                Rule(
                    name="pack",
                    premises=(_atom("P", "?w"), _atom("Q", "?w")),
                    conclusion=_atom("R"),
                ),
            ),
            program=Program(
                step=Apply("pack"),
                children=(Program(step=Exact("hp")), Program(step=Exact("hq"))),
            ),
        ),
        Example(
            name="nested_constructor_apply",
            description=(
                "Two-step tree program with constructor at the root and apply on one branch."
            ),
            root=Obligation(
                goal_id="g0",
                context=(Hypothesis("ha", _atom("A")), Hypothesis("hq", _atom("Q"))),
                target=And(_atom("P"), _atom("Q")),
            ),
            rules=(
                Rule(
                    name="proveP",
                    premises=(_atom("A"),),
                    conclusion=_atom("P"),
                ),
            ),
            program=Program(
                step=Constructor(),
                children=(
                    Program(
                        step=Apply("proveP"),
                        children=(Program(step=Exact("ha")),),
                    ),
                    Program(step=Exact("hq")),
                ),
            ),
        ),
    ]
    return {example.name: example for example in examples}


def get_example(name: str) -> Example:
    examples = get_examples()
    if name not in examples:
        known = ", ".join(sorted(examples))
        raise KeyError(f"unknown example {name!r}; known examples: {known}")
    return examples[name]
