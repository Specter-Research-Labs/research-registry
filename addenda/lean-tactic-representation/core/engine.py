from __future__ import annotations

from dataclasses import asdict
from itertools import combinations

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
    Hypothesis,
    HypRef,
    Interface,
    InvariantResult,
    Obligation,
    OpticStep,
    PrimitiveStep,
    Program,
    Proposition,
    ResidualBuilder,
    Rule,
    Witness,
    is_meta_symbol,
)


class InterpreterError(ValueError):
    pass


def rule_map(rules: tuple[Rule, ...]) -> dict[str, Rule]:
    return {rule.name: rule for rule in rules}


def lookup_hypothesis(context: tuple[Hypothesis, ...], name: str) -> Hypothesis:
    for hypothesis in context:
        if hypothesis.name == name:
            return hypothesis
    raise InterpreterError(f"unknown hypothesis: {name}")


def collect_holes(witness: Witness) -> tuple[str, ...]:
    if isinstance(witness, Hole):
        return (witness.goal_id,)
    if isinstance(witness, HypRef):
        return ()
    if isinstance(witness, AndIntro):
        return collect_holes(witness.left) + collect_holes(witness.right)
    if isinstance(witness, App):
        holes: list[str] = []
        for arg in witness.args:
            holes.extend(collect_holes(arg))
        return tuple(holes)
    raise TypeError(f"unsupported witness: {type(witness)!r}")


def fill_holes(witness: Witness, assignments: dict[str, Witness]) -> Witness:
    if isinstance(witness, Hole):
        if witness.goal_id not in assignments:
            raise InterpreterError(f"missing witness for hole {witness.goal_id}")
        return assignments[witness.goal_id]
    if isinstance(witness, HypRef):
        return witness
    if isinstance(witness, AndIntro):
        return AndIntro(
            left=fill_holes(witness.left, assignments),
            right=fill_holes(witness.right, assignments),
        )
    if isinstance(witness, App):
        return App(
            rule_name=witness.rule_name,
            args=tuple(fill_holes(arg, assignments) for arg in witness.args),
        )
    raise TypeError(f"unsupported witness: {type(witness)!r}")


def proposition_free_metas(prop: Proposition) -> set[str]:
    if isinstance(prop, Atom):
        return {arg for arg in prop.args if is_meta_symbol(arg)}
    if isinstance(prop, And):
        return proposition_free_metas(prop.left) | proposition_free_metas(prop.right)
    raise TypeError(f"unsupported proposition: {type(prop)!r}")


def instantiate_proposition(prop: Proposition, substitution: dict[str, str]) -> Proposition:
    if isinstance(prop, Atom):
        return Atom(
            name=prop.name,
            args=tuple(substitution.get(arg, arg) for arg in prop.args),
        )
    if isinstance(prop, And):
        return And(
            left=instantiate_proposition(prop.left, substitution),
            right=instantiate_proposition(prop.right, substitution),
        )
    raise TypeError(f"unsupported proposition: {type(prop)!r}")


def unify_propositions(
    pattern: Proposition,
    actual: Proposition,
    substitution: dict[str, str] | None = None,
) -> dict[str, str]:
    subst = {} if substitution is None else dict(substitution)
    if isinstance(pattern, Atom) and isinstance(actual, Atom):
        if pattern.name != actual.name or len(pattern.args) != len(actual.args):
            raise InterpreterError(f"cannot unify {pattern!r} with {actual!r}")
        for pattern_arg, actual_arg in zip(pattern.args, actual.args, strict=True):
            if is_meta_symbol(pattern_arg):
                bound = subst.get(pattern_arg)
                if bound is None:
                    subst[pattern_arg] = actual_arg
                elif bound != actual_arg:
                    raise InterpreterError(
                        "metavariable "
                        f"{pattern_arg} cannot unify with both {bound} and {actual_arg}"
                    )
            elif pattern_arg != actual_arg:
                raise InterpreterError(f"cannot unify {pattern_arg} with {actual_arg}")
        return subst
    if isinstance(pattern, And) and isinstance(actual, And):
        left_subst = unify_propositions(pattern.left, actual.left, subst)
        return unify_propositions(pattern.right, actual.right, left_subst)
    raise InterpreterError(f"cannot unify {pattern!r} with {actual!r}")


def infer_witness_type(
    witness: Witness,
    *,
    context: tuple[Hypothesis, ...],
    rules: dict[str, Rule],
) -> Proposition:
    if isinstance(witness, Hole):
        raise InterpreterError(f"cannot infer type for open hole {witness.goal_id}")
    if isinstance(witness, HypRef):
        return lookup_hypothesis(context, witness.name).proposition
    if isinstance(witness, AndIntro):
        return And(
            left=infer_witness_type(witness.left, context=context, rules=rules),
            right=infer_witness_type(witness.right, context=context, rules=rules),
        )
    if isinstance(witness, App):
        if witness.rule_name not in rules:
            raise InterpreterError(f"unknown rule: {witness.rule_name}")
        rule = rules[witness.rule_name]
        if len(rule.premises) != len(witness.args):
            raise InterpreterError(
                f"rule {rule.name} expects {len(rule.premises)} args, got {len(witness.args)}"
            )
        substitution: dict[str, str] = {}
        for premise, arg in zip(rule.premises, witness.args, strict=True):
            arg_type = infer_witness_type(arg, context=context, rules=rules)
            substitution = unify_propositions(premise, arg_type, substitution)
        return instantiate_proposition(rule.conclusion, substitution)
    raise TypeError(f"unsupported witness: {type(witness)!r}")


def _make_child_goal_id(parent_goal_id: str, index: int) -> str:
    return f"{parent_goal_id}.{index}"


def _build_coupling(child_obligations: tuple[Obligation, ...]) -> Coupling:
    child_ids = tuple(child.goal_id for child in child_obligations)
    meta_to_children: dict[str, list[str]] = {}
    for child in child_obligations:
        for meta in proposition_free_metas(child.target):
            meta_to_children.setdefault(meta, []).append(child.goal_id)

    shared_metavars = tuple(sorted(meta for meta, ids in meta_to_children.items() if len(ids) > 1))
    edge_set: set[tuple[str, str]] = set()
    for ids in meta_to_children.values():
        if len(ids) < 2:
            continue
        for left, right in combinations(sorted(ids), 2):
            edge_set.add((left, right))

    dependency_edges = tuple(sorted(edge_set))
    if len(child_ids) <= 1:
        kind = "none"
    elif shared_metavars or dependency_edges:
        kind = "coupled"
    else:
        kind = "independent"
    return Coupling(
        child_ids=child_ids,
        shared_metavars=shared_metavars,
        dependency_edges=dependency_edges,
        kind=kind,
    )


def _singleton_interface(obligation: Obligation) -> Interface:
    return Interface(obligations=(obligation,))


def execute_step(step: PrimitiveStep, obligation: Obligation, rules: dict[str, Rule]) -> OpticStep:
    partial_term_before: Witness = Hole(obligation.goal_id)
    parent_interface = _singleton_interface(obligation)

    if isinstance(step, Exact):
        hypothesis = lookup_hypothesis(obligation.context, step.hypothesis_name)
        try:
            unify_propositions(obligation.target, hypothesis.proposition)
        except InterpreterError as exc:
            raise InterpreterError(
                f"exact {step.hypothesis_name} has type {hypothesis.proposition!r}, "
                f"expected {obligation.target!r}"
            ) from exc
        partial_term_after = HypRef(step.hypothesis_name)
        coupling = Coupling(child_ids=(), shared_metavars=(), dependency_edges=(), kind="none")
        return OpticStep(
            step=step,
            decomposition=Decomposition(
                parent_interface=parent_interface,
                child_interface=Interface(obligations=()),
                coupling=coupling,
                partial_term_before=partial_term_before,
                partial_term_after=partial_term_after,
            ),
            residue=ResidualBuilder(template=partial_term_after, child_order=()),
            certificates=("hypothesis_target_match",),
        )

    if isinstance(step, Constructor):
        target = obligation.target
        if not isinstance(target, And):
            raise InterpreterError(f"constructor expects conjunction goal, got {target!r}")
        children = (
            Obligation(
                goal_id=_make_child_goal_id(obligation.goal_id, 1),
                context=obligation.context,
                target=target.left,
            ),
            Obligation(
                goal_id=_make_child_goal_id(obligation.goal_id, 2),
                context=obligation.context,
                target=target.right,
            ),
        )
        partial_term_after = AndIntro(Hole(children[0].goal_id), Hole(children[1].goal_id))
        return OpticStep(
            step=step,
            decomposition=Decomposition(
                parent_interface=parent_interface,
                child_interface=Interface(obligations=children),
                coupling=_build_coupling(children),
                partial_term_before=partial_term_before,
                partial_term_after=partial_term_after,
            ),
            residue=ResidualBuilder(
                template=partial_term_after,
                child_order=tuple(child.goal_id for child in children),
            ),
            certificates=("conjunction_split",),
        )

    if isinstance(step, Apply):
        if step.rule_name not in rules:
            raise InterpreterError(f"unknown rule: {step.rule_name}")
        rule = rules[step.rule_name]
        substitution = unify_propositions(rule.conclusion, obligation.target)
        premises = tuple(
            instantiate_proposition(premise, substitution) for premise in rule.premises
        )
        children = tuple(
            Obligation(
                goal_id=_make_child_goal_id(obligation.goal_id, index),
                context=obligation.context,
                target=premise,
            )
            for index, premise in enumerate(premises, start=1)
        )
        partial_term_after = App(
            rule_name=step.rule_name,
            args=tuple(Hole(child.goal_id) for child in children),
        )
        return OpticStep(
            step=step,
            decomposition=Decomposition(
                parent_interface=parent_interface,
                child_interface=Interface(obligations=children),
                coupling=_build_coupling(children),
                partial_term_before=partial_term_before,
                partial_term_after=partial_term_after,
            ),
            residue=ResidualBuilder(
                template=partial_term_after,
                child_order=tuple(child.goal_id for child in children),
            ),
            certificates=("rule_conclusion_unified",),
        )

    raise TypeError(f"unsupported step: {type(step)!r}")


def check_optic_step(optic_step: OpticStep, rules: dict[str, Rule]) -> tuple[InvariantResult, ...]:
    parent_ids = tuple(
        obligation.goal_id for obligation in optic_step.decomposition.parent_interface.obligations
    )
    child_ids = tuple(
        obligation.goal_id for obligation in optic_step.decomposition.child_interface.obligations
    )
    hole_ids = collect_holes(optic_step.residue.template)
    results = [
        InvariantResult(
            name="optic_parent_interface_is_singleton",
            passed=len(parent_ids) == 1,
            detail=f"parent_ids={list(parent_ids)}",
        ),
        InvariantResult(
            name="optic_child_ids_unique",
            passed=len(set(child_ids)) == len(child_ids),
            detail=f"child_ids={list(child_ids)}",
        ),
        InvariantResult(
            name="residue_holes_match_child_interface",
            passed=tuple(sorted(hole_ids)) == tuple(sorted(child_ids)),
            detail=f"holes={list(hole_ids)} children={list(child_ids)}",
        ),
        InvariantResult(
            name="coupling_child_ids_match_interface",
            passed=optic_step.decomposition.coupling.child_ids == child_ids,
            detail=(
                f"coupling_child_ids={list(optic_step.decomposition.coupling.child_ids)} "
                f"children={list(child_ids)}"
            ),
        ),
    ]

    if len(child_ids) <= 1:
        expected_kind = "none"
    elif (
        optic_step.decomposition.coupling.shared_metavars
        or optic_step.decomposition.coupling.dependency_edges
    ):
        expected_kind = "coupled"
    else:
        expected_kind = "independent"
    results.append(
        InvariantResult(
            name="coupling_kind_matches_structure",
            passed=optic_step.decomposition.coupling.kind == expected_kind,
            detail=(
                f"kind={optic_step.decomposition.coupling.kind} "
                f"shared={list(optic_step.decomposition.coupling.shared_metavars)} "
                f"edges={list(optic_step.decomposition.coupling.dependency_edges)}"
            ),
        )
    )

    if isinstance(optic_step.step, Exact):
        arity_ok = len(child_ids) == 0
        arity_detail = f"exact_children={len(child_ids)}"
    elif isinstance(optic_step.step, Constructor):
        arity_ok = len(child_ids) == 2
        arity_detail = f"constructor_children={len(child_ids)}"
    elif isinstance(optic_step.step, Apply):
        expected = len(rules[optic_step.step.rule_name].premises)
        arity_ok = len(child_ids) == expected
        arity_detail = f"apply_children={len(child_ids)} expected={expected}"
    else:
        arity_ok = False
        arity_detail = "unknown step kind"
    results.append(
        InvariantResult(
            name="optic_arity_matches_primitive",
            passed=arity_ok,
            detail=arity_detail,
        )
    )
    return tuple(results)


def execute_program(
    program: Program,
    obligation: Obligation,
    rules: tuple[Rule, ...],
) -> ExecutionNode:
    indexed_rules = rule_map(rules)
    optic_step = execute_step(program.step, obligation, indexed_rules)
    child_obligations = optic_step.decomposition.child_interface.obligations
    child_count = len(child_obligations)
    if len(program.children) != child_count:
        raise InterpreterError(
            f"program child count {len(program.children)} does not match step arity {child_count}"
        )

    child_nodes = tuple(
        execute_program(child_program, child_obligation, rules)
        for child_program, child_obligation in zip(
            program.children,
            child_obligations,
            strict=True,
        )
    )
    assignments = {
        child.obligation.goal_id: child.final_witness
        for child in child_nodes
    }
    final_witness = fill_holes(optic_step.residue.template, assignments)
    final_type = infer_witness_type(final_witness, context=obligation.context, rules=indexed_rules)
    final_type_subst: dict[str, str] | None
    try:
        final_type_subst = unify_propositions(obligation.target, final_type)
        final_type_ok = True
    except InterpreterError:
        final_type_subst = None
        final_type_ok = False
    invariants = list(check_optic_step(optic_step, indexed_rules))
    invariants.append(
        InvariantResult(
            name="optic_reassembles_parent_target",
            passed=final_type_ok,
            detail=(
                f"inferred={final_type!r} target={obligation.target!r} "
                f"subst={final_type_subst if final_type_subst is not None else {}}"
            ),
        )
    )
    if not final_type_ok:
        raise InterpreterError(
            f"final witness has type {final_type!r}, expected {obligation.target!r}"
        )
    return ExecutionNode(
        obligation=obligation,
        program=program,
        optic_step=optic_step,
        child_nodes=child_nodes,
        final_witness=final_witness,
        final_type=final_type,
        invariants=tuple(invariants),
    )


def example_to_json_ready(example: Example, node: ExecutionNode) -> dict[str, object]:
    return {
        "example": example.name,
        "description": example.description,
        "root": asdict(example.root),
        "rules": [asdict(rule) for rule in example.rules],
        "program": asdict(example.program),
        "execution": _execution_node_to_dict(node),
    }


def _execution_node_to_dict(node: ExecutionNode) -> dict[str, object]:
    return {
        "obligation": asdict(node.obligation),
        "program": asdict(node.program),
        "optic_step": asdict(node.optic_step),
        "child_nodes": [_execution_node_to_dict(child) for child in node.child_nodes],
        "final_witness": asdict(node.final_witness),
        "final_type": asdict(node.final_type),
        "invariants": [asdict(invariant) for invariant in node.invariants],
    }
