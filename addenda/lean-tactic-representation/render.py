from __future__ import annotations

import json

from core.engine import example_to_json_ready
from core.model import (
    And,
    AndIntro,
    App,
    Apply,
    Atom,
    Constructor,
    Coupling,
    Decomposition,
    Exact,
    Example,
    ExecutionNode,
    Hole,
    HypRef,
    Interface,
    OpticStep,
    PrimitiveStep,
    Program,
    Proposition,
    Witness,
)


def render_proposition(prop: Proposition) -> str:
    if isinstance(prop, Atom):
        if not prop.args:
            return prop.name
        return f"{prop.name}({', '.join(prop.args)})"
    if isinstance(prop, And):
        return f"({render_proposition(prop.left)} ∧ {render_proposition(prop.right)})"
    raise TypeError(f"unsupported proposition: {type(prop)!r}")


def render_witness(witness: Witness) -> str:
    if isinstance(witness, HypRef):
        return witness.name
    if isinstance(witness, Hole):
        return f"?{witness.goal_id}"
    if isinstance(witness, AndIntro):
        return f"And.intro({render_witness(witness.left)}, {render_witness(witness.right)})"
    if isinstance(witness, App):
        args = ", ".join(render_witness(arg) for arg in witness.args)
        return f"{witness.rule_name}({args})"
    raise TypeError(f"unsupported witness: {type(witness)!r}")


def render_step(step: PrimitiveStep) -> str:
    if isinstance(step, Exact):
        return f"exact {step.hypothesis_name}"
    if isinstance(step, Constructor):
        return "constructor"
    if isinstance(step, Apply):
        return f"apply {step.rule_name}"
    raise TypeError(f"unsupported step: {type(step)!r}")


def render_program(program: Program, indent: str = "") -> list[str]:
    lines = [f"{indent}{render_step(program.step)}"]
    for child in program.children:
        lines.extend(render_program(child, indent=indent + "  "))
    return lines


def render_interface(interface: Interface) -> str:
    if not interface.obligations:
        return "[]"
    parts = [
        f"{obligation.goal_id}: {render_proposition(obligation.target)}"
        for obligation in interface.obligations
    ]
    return "[" + ", ".join(parts) + "]"


def render_coupling(coupling: Coupling) -> str:
    shared = ", ".join(coupling.shared_metavars) if coupling.shared_metavars else "-"
    edges = ", ".join(f"{left}<->{right}" for left, right in coupling.dependency_edges) or "-"
    return f"kind={coupling.kind} shared=[{shared}] edges=[{edges}]"


def render_decomposition(decomposition: Decomposition, indent: str = "") -> list[str]:
    return [
        f"{indent}source: {render_interface(decomposition.parent_interface)}",
        f"{indent}target: {render_interface(decomposition.child_interface)}",
        f"{indent}coupling: {render_coupling(decomposition.coupling)}",
        f"{indent}before: {render_witness(decomposition.partial_term_before)}",
        f"{indent}after: {render_witness(decomposition.partial_term_after)}",
    ]


def render_optic_step(optic_step: OpticStep, indent: str = "") -> list[str]:
    lines = [
        f"{indent}primitive: {render_step(optic_step.step)}",
        f"{indent}decomposition:",
        *render_decomposition(optic_step.decomposition, indent=indent + "  "),
        f"{indent}residue: {render_witness(optic_step.residue.template)}",
        f"{indent}residue_order: {list(optic_step.residue.child_order)}",
        f"{indent}certificates: {list(optic_step.certificates)}",
    ]
    return lines


def render_execution(node: ExecutionNode, indent: str = "") -> list[str]:
    lines = [
        f"{indent}{node.obligation.goal_id}: {render_proposition(node.obligation.target)}",
        f"{indent}  optic:",
    ]
    lines.extend(render_optic_step(node.optic_step, indent=indent + "    "))
    lines.append(f"{indent}  invariants:")
    for invariant in node.invariants:
        status = "PASS" if invariant.passed else "FAIL"
        lines.append(f"{indent}    [{status}] {invariant.name}: {invariant.detail}")
    lines.append(f"{indent}  witness: {render_witness(node.final_witness)}")
    for child in node.child_nodes:
        lines.extend(render_execution(child, indent=indent + "  "))
    return lines


def render_example_tree(example: Example, node: ExecutionNode) -> str:
    lines = [
        f"example={example.name}",
        f"description={example.description}",
        f"root={example.root.goal_id}: {render_proposition(example.root.target)}",
        "program:",
        *render_program(example.program, indent="  "),
        "execution:",
        *render_execution(node, indent="  "),
    ]
    return "\n".join(lines)


def render_example_json(example: Example, node: ExecutionNode) -> str:
    return json.dumps(example_to_json_ready(example, node), indent=2, sort_keys=True)
