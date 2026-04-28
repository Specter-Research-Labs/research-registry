from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from atp.coq.runner import _escape_sentence, exec_sentence
from atp.coq.serapi import SerapiSession, extract_feedback_strings
from atp.coq.source import PROOF_END_RE, THEOREM_RE, strip_attributes, strip_leading_comments
from atp.sexp import sexpr_to_string
from prover.proof import ProofGraph
from prover.providers.base import normalize_tactic, tactic_family
from prover.tactic_ir import (
    CONTINUATION_KIND_BRANCH,
    CONTINUATION_KIND_CHAIN,
    CONTINUATION_KIND_SOLVE,
    EFFECT_BRANCHES_GOALS,
    EFFECT_CLOSES_GOALS,
    EFFECT_COMPLETES_TERM,
    EFFECT_OPENS_GOALS,
    EFFECT_REFINES_TERM,
    EFFECT_SPAWNS_GOALS,
    EFFECT_TRANSFORMS_GOALS,
    GOAL_COUPLING_NONE,
    GOAL_COUPLING_UNKNOWN,
)


@dataclass(frozen=True)
class CoqGoalTrace:
    goal_id: str | None
    goal_type: str
    hypotheses: tuple[str, ...]
    goal_sig: str

    def serialize(self) -> dict[str, object]:
        return {
            "goalId": self.goal_id,
            "goalType": self.goal_type,
            "hypotheses": list(self.hypotheses),
            "goalSig": self.goal_sig,
        }


@dataclass(frozen=True)
class CoqGoalState:
    focused: tuple[CoqGoalTrace, ...] = ()
    background: tuple[CoqGoalTrace, ...] = ()
    shelved: tuple[CoqGoalTrace, ...] = ()
    given_up: tuple[CoqGoalTrace, ...] = ()

    def serialize(self) -> dict[str, object]:
        return {
            "focused": [goal.serialize() for goal in self.focused],
            "background": [goal.serialize() for goal in self.background],
            "shelved": [goal.serialize() for goal in self.shelved],
            "givenUp": [goal.serialize() for goal in self.given_up],
        }

    def open_goals(self) -> tuple[CoqGoalTrace, ...]:
        return (*self.focused, *self.background, *self.shelved, *self.given_up)

    def open_goal_count(self) -> int:
        return len(self.open_goals())

    def state_sig(self) -> str:
        payload = "|".join(goal.goal_sig for goal in self.open_goals())
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CoqProcessStep:
    index: int
    sentence: str
    command_kind: str
    command_norm: str
    goals_before: CoqGoalState | None
    goals_after: CoqGoalState | None
    proof_term_before: str | None
    proof_term_after: str | None
    action_metadata: dict[str, object] = field(default_factory=dict)

    def serialize(self) -> dict[str, object]:
        return {
            "index": self.index,
            "sentence": self.sentence,
            "commandKind": self.command_kind,
            "commandNorm": self.command_norm,
            "goalsBefore": self.goals_before.serialize() if self.goals_before else None,
            "goalsAfter": self.goals_after.serialize() if self.goals_after else None,
            "proofTermBefore": self.proof_term_before,
            "proofTermAfter": self.proof_term_after,
            "actionMetadata": deepcopy(self.action_metadata),
        }


@dataclass(frozen=True)
class CoqProcessTrace:
    theorem: str
    source_path: str | None
    trace_source: str
    trace_completeness: str
    steps: tuple[CoqProcessStep, ...]

    def serialize(self) -> dict[str, object]:
        return {
            "theorem": self.theorem,
            "sourcePath": self.source_path,
            "traceSource": self.trace_source,
            "traceCompleteness": self.trace_completeness,
            "steps": [step.serialize() for step in self.steps],
        }


def _query_opts(state_id: int | None = None) -> str:
    if state_id is None:
        return "()"
    return f"((sid {state_id}))"


def _query_goals(session: SerapiSession, state_id: int | None = None) -> CoqGoalState | None:
    responses = session.send(f"(Query {_query_opts(state_id)} Goals)")
    return extract_goal_state(responses)


def _query_show_proof(session: SerapiSession, state_id: int | None = None) -> str | None:
    command = _escape_sentence("Show Proof.")
    responses = session.send(f'(Query {_query_opts(state_id)} (Vernac "{command}"))')
    messages = [
        message.strip()
        for message in extract_feedback_strings(responses)
        if message.strip()
    ]
    if not messages:
        return None
    return messages[-1]


def _normalize_command(sentence: str) -> str:
    text = strip_leading_comments(strip_attributes(sentence)).strip()
    if text.endswith("."):
        text = text[:-1]
    return normalize_tactic(text)


def _classify_sentence(sentence: str) -> str:
    normalized = strip_leading_comments(strip_attributes(sentence)).strip()
    if THEOREM_RE.match(normalized):
        return "theorem_decl"
    if normalized.startswith("Proof"):
        return "proof_open"
    if PROOF_END_RE.match(normalized):
        return "proof_end"
    return "tactic"


def _goal_ref(goal: CoqGoalTrace) -> str:
    return goal.goal_id or goal.goal_sig


def _goal_refs(state: CoqGoalState | None) -> set[str]:
    if state is None:
        return set()
    return {_goal_ref(goal) for goal in state.open_goals()}


def _derive_action_metadata(
    sentence: str,
    *,
    command_kind: str,
    goals_before: CoqGoalState | None,
    goals_after: CoqGoalState | None,
    proof_term_before: str | None,
    proof_term_after: str | None,
) -> dict[str, object]:
    before_refs = _goal_refs(goals_before)
    after_refs = _goal_refs(goals_after)
    before_open = len(before_refs)
    after_open = len(after_refs)
    focused_after = len(goals_after.focused) if goals_after is not None else 0
    effect_flags: list[str] = []
    if command_kind == "tactic":
        effect_flags.append(EFFECT_TRANSFORMS_GOALS)
    if after_open > before_open:
        effect_flags.extend([EFFECT_OPENS_GOALS, EFFECT_SPAWNS_GOALS])
    if focused_after > 1:
        effect_flags.append(EFFECT_BRANCHES_GOALS)
    if after_open < before_open:
        effect_flags.append(EFFECT_CLOSES_GOALS)
    if proof_term_before != proof_term_after and command_kind == "tactic":
        effect_flags.append(EFFECT_REFINES_TERM)
    if before_open > 0 and after_open == 0:
        effect_flags.extend([EFFECT_CLOSES_GOALS, EFFECT_COMPLETES_TERM])

    if before_open > 0 and after_open == 0:
        continuation_kind = CONTINUATION_KIND_SOLVE
    elif focused_after > 1:
        continuation_kind = CONTINUATION_KIND_BRANCH
    else:
        continuation_kind = CONTINUATION_KIND_CHAIN

    goal_coupling = GOAL_COUPLING_UNKNOWN if focused_after > 1 else GOAL_COUPLING_NONE
    tactic_norm = _normalize_command(sentence)
    return {
        "command_kind": command_kind,
        "tactic_family": tactic_family(tactic_norm),
        "branch_arity": focused_after,
        "continuation_kind": continuation_kind,
        "goal_coupling": goal_coupling,
        "effect_flags": sorted(set(effect_flags)),
        "goals_before": sorted(before_refs),
        "goals_after": sorted(after_refs),
        "goals_closed": sorted(before_refs - after_refs),
        "goals_opened": sorted(after_refs - before_refs),
        "open_goal_count_before": before_open,
        "open_goal_count_after": after_open,
    }


def replay_theorem_block(
    session: SerapiSession,
    *,
    theorem: str,
    source_path: str | None,
    prelude_sentences: list[str],
    block_sentences: list[str],
) -> CoqProcessTrace:
    for sentence in prelude_sentences:
        exec_sentence(session, sentence)

    goals_before = _query_goals(session)
    proof_before = _query_show_proof(session)
    steps: list[CoqProcessStep] = []
    trace_completeness = "script"
    for index, sentence in enumerate(block_sentences):
        state_id = exec_sentence(session, sentence)
        goals_after = _query_goals(session, state_id)
        proof_after = _query_show_proof(session, state_id)
        command_kind = _classify_sentence(sentence)
        action_metadata = _derive_action_metadata(
            sentence,
            command_kind=command_kind,
            goals_before=goals_before,
            goals_after=goals_after,
            proof_term_before=proof_before,
            proof_term_after=proof_after,
        )
        steps.append(
            CoqProcessStep(
                index=index,
                sentence=sentence,
                command_kind=command_kind,
                command_norm=_normalize_command(sentence),
                goals_before=goals_before,
                goals_after=goals_after,
                proof_term_before=proof_before,
                proof_term_after=proof_after,
                action_metadata=action_metadata,
            )
        )
        goals_before = goals_after
        proof_before = proof_after

    if not steps:
        trace_completeness = "empty"
    elif steps[-1].goals_after is not None and steps[-1].goals_after.open_goal_count() > 0:
        trace_completeness = "partial"

    return CoqProcessTrace(
        theorem=theorem,
        source_path=source_path,
        trace_source="serapi_replay",
        trace_completeness=trace_completeness,
        steps=tuple(steps),
    )


def process_trace_to_graph(trace: CoqProcessTrace) -> ProofGraph:
    graph = ProofGraph.for_search_trace(backend="coq", provenance="process_replay")
    current_node_id: str | None = None
    next_state_idx = 0

    def add_state_node(state: CoqGoalState) -> str:
        nonlocal next_state_idx
        node_id = f"state:{next_state_idx}"
        next_state_idx += 1
        primary_goal = state.focused[0].goal_type if state.focused else "<pending>"
        graph.add_node(
            node_id,
            goal_type=primary_goal,
            depth=next_state_idx - 1,
            goal_sig=state.state_sig(),
            node_kind="proof_state",
            focused_goal_count=len(state.focused),
            background_goal_count=len(state.background),
            shelved_goal_count=len(state.shelved),
            given_up_goal_count=len(state.given_up),
        )
        return node_id

    for step in trace.steps:
        goals_before = step.goals_before
        goals_after = step.goals_after
        if step.command_kind in {"theorem_decl", "proof_open"}:
            if (
                current_node_id is None
                and goals_after is not None
                and goals_after.open_goal_count() > 0
            ):
                current_node_id = add_state_node(goals_after)
            continue
        if (
            current_node_id is None
            and goals_before is not None
            and goals_before.open_goal_count() > 0
        ):
            current_node_id = add_state_node(goals_before)
        if current_node_id is None:
            continue

        action_metadata = deepcopy(step.action_metadata)
        tactic_norm = step.command_norm
        family = action_metadata.get("tactic_family")
        edge_role = f"fam:{family}" if isinstance(family, str) and family else "fam:other"

        if (
            goals_after is not None
            and goals_after.open_goal_count() > 0
            and step.command_kind == "tactic"
        ):
            next_node_id = add_state_node(goals_after)
            graph.graph.add_edge(
                current_node_id,
                next_node_id,
                tactic=step.sentence,
                tactic_norm=tactic_norm,
                edge_role=edge_role,
                action_kind="tactic_step",
                order=step.index + 1,
                **action_metadata,
            )
            current_node_id = next_node_id
            continue

        if step.command_kind == "tactic" and (
            goals_after is None or goals_after.open_goal_count() == 0
        ):
            terminal_payload = {
                "is_terminal": True,
                "terminal_tactic": step.sentence,
                "terminal_tactic_norm": tactic_norm,
                "terminal_edge_role": edge_role,
                "terminal_action_kind": "tactic_step",
                "terminal_branch_arity": 0,
                "terminal_expanded_child_count": 0,
            }
            for key, value in action_metadata.items():
                terminal_payload[f"terminal_{key}"] = deepcopy(value)
            graph.update_node(current_node_id, **terminal_payload)

    return graph


def _field_value(fields: list[Any], key: str) -> Any | None:
    for item in fields:
        if not isinstance(item, list) or len(item) < 2:
            continue
        if item[0] == key:
            if len(item) == 2:
                return item[1]
            return item[1:]
    return None


def _looks_like_goal_fields(node: Any) -> bool:
    if not isinstance(node, list) or not node:
        return False
    keys = {
        item[0]
        for item in node
        if isinstance(item, list) and item and isinstance(item[0], str)
    }
    return "info" in keys and "ty" in keys


def _collect_goal_field_nodes(node: Any) -> list[list[Any]]:
    if _looks_like_goal_fields(node):
        return [node]
    if not isinstance(node, list):
        return []
    out: list[list[Any]] = []
    for child in node:
        out.extend(_collect_goal_field_nodes(child))
    return out


def _stringify_goal_part(node: Any) -> str:
    if isinstance(node, list):
        return sexpr_to_string(node)
    return str(node)


def _goal_signature(goal_type: str, hypotheses: tuple[str, ...]) -> str:
    payload = "\n".join([goal_type, *hypotheses])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _goal_from_fields(fields: list[Any]) -> CoqGoalTrace:
    goal_info_raw = _field_value(fields, "info")
    goal_id_raw = None
    if isinstance(goal_info_raw, list):
        evar_raw = _field_value(goal_info_raw, "evar")
        if isinstance(evar_raw, list):
            goal_id_raw = next(
                (
                    token
                    for token in reversed(evar_raw)
                    if isinstance(token, str) and token.isdigit()
                ),
                None,
            )
        elif evar_raw is not None:
            goal_id_raw = str(evar_raw)
    goal_type_raw = _field_value(fields, "ty")
    hyps_raw = _field_value(fields, "hyp")
    hypotheses: tuple[str, ...]
    if isinstance(hyps_raw, list):
        hypotheses = tuple(_stringify_goal_part(item) for item in hyps_raw)
    elif hyps_raw is None:
        hypotheses = ()
    else:
        hypotheses = (_stringify_goal_part(hyps_raw),)
    goal_type = _stringify_goal_part(goal_type_raw) if goal_type_raw is not None else "<unknown>"
    goal_id = None if goal_id_raw is None else str(goal_id_raw)
    return CoqGoalTrace(
        goal_id=goal_id,
        goal_type=goal_type,
        hypotheses=hypotheses,
        goal_sig=_goal_signature(goal_type, hypotheses),
    )


def extract_goal_state(responses: list[Any]) -> CoqGoalState | None:
    def visit(node: Any) -> CoqGoalState | None:
        if isinstance(node, list) and node:
            if node[0] == "CoqGoal":
                fields = node[1] if len(node) > 1 and isinstance(node[1], list) else node[1:]
                focused = tuple(
                    _goal_from_fields(goal_fields)
                    for goal_fields in _collect_goal_field_nodes(_field_value(fields, "goals"))
                )
                background = tuple(
                    _goal_from_fields(goal_fields)
                    for goal_fields in _collect_goal_field_nodes(_field_value(fields, "stack"))
                )
                shelved = tuple(
                    _goal_from_fields(goal_fields)
                    for goal_fields in _collect_goal_field_nodes(_field_value(fields, "shelf"))
                )
                given_up = tuple(
                    _goal_from_fields(goal_fields)
                    for goal_fields in _collect_goal_field_nodes(_field_value(fields, "given_up"))
                )
                return CoqGoalState(
                    focused=focused,
                    background=background,
                    shelved=shelved,
                    given_up=given_up,
                )
            for child in node:
                found = visit(child)
                if found is not None:
                    return found
        return None

    return visit(responses)
