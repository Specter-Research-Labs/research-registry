from __future__ import annotations

from dataclasses import dataclass


def is_meta_symbol(symbol: str) -> bool:
    return symbol.startswith("?")


@dataclass(frozen=True)
class Atom:
    name: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class And:
    left: "Proposition"
    right: "Proposition"


Proposition = Atom | And


@dataclass(frozen=True)
class Hypothesis:
    name: str
    proposition: Proposition


@dataclass(frozen=True)
class Rule:
    name: str
    premises: tuple[Proposition, ...]
    conclusion: Proposition


@dataclass(frozen=True)
class Obligation:
    goal_id: str
    context: tuple[Hypothesis, ...]
    target: Proposition


@dataclass(frozen=True)
class Interface:
    obligations: tuple[Obligation, ...]


@dataclass(frozen=True)
class HypRef:
    name: str


@dataclass(frozen=True)
class AndIntro:
    left: "Witness"
    right: "Witness"


@dataclass(frozen=True)
class App:
    rule_name: str
    args: tuple["Witness", ...]


@dataclass(frozen=True)
class Hole:
    goal_id: str


Witness = HypRef | AndIntro | App | Hole


@dataclass(frozen=True)
class ResidualBuilder:
    template: Witness
    child_order: tuple[str, ...]


@dataclass(frozen=True)
class Coupling:
    child_ids: tuple[str, ...]
    shared_metavars: tuple[str, ...]
    dependency_edges: tuple[tuple[str, str], ...]
    kind: str


@dataclass(frozen=True)
class Exact:
    hypothesis_name: str


@dataclass(frozen=True)
class Constructor:
    pass


@dataclass(frozen=True)
class Apply:
    rule_name: str


PrimitiveStep = Exact | Constructor | Apply


@dataclass(frozen=True)
class Program:
    step: PrimitiveStep
    children: tuple["Program", ...] = ()


@dataclass(frozen=True)
class Decomposition:
    parent_interface: Interface
    child_interface: Interface
    coupling: Coupling
    partial_term_before: Witness
    partial_term_after: Witness


@dataclass(frozen=True)
class OpticStep:
    step: PrimitiveStep
    decomposition: Decomposition
    residue: ResidualBuilder
    certificates: tuple[str, ...]


@dataclass(frozen=True)
class InvariantResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ExecutionNode:
    obligation: Obligation
    program: Program
    optic_step: OpticStep
    child_nodes: tuple["ExecutionNode", ...]
    final_witness: Witness
    final_type: Proposition
    invariants: tuple[InvariantResult, ...]


@dataclass(frozen=True)
class Example:
    name: str
    description: str
    root: Obligation
    rules: tuple[Rule, ...]
    program: Program
