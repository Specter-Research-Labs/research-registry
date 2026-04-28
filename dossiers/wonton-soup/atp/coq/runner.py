from __future__ import annotations

from dataclasses import dataclass

from atp.coq.serapi import SerapiConfig, SerapiSession, extract_added_state


@dataclass(frozen=True)
class CoqConfig:
    serapi: SerapiConfig = SerapiConfig()
    doc_name: str = "coqdoc"


def _escape_sentence(sentence: str) -> str:
    return sentence.replace("\\", "\\\\").replace('"', '\\"')


def exec_sentence(session: SerapiSession, sentence: str) -> int | None:
    sent = sentence.strip()
    if not sent:
        return None
    responses = session.send(f'(Add () "{_escape_sentence(sent)}")')
    state_id = extract_added_state(responses)
    if state_id is not None:
        session.send(f"(Exec {state_id})")
    return state_id


def _exec_sentences(session: SerapiSession, sentences: list[str]) -> None:
    for sentence in sentences:
        exec_sentence(session, sentence)
