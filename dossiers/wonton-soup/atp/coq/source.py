from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from atp.coq.sentences import split_coq_sentences

THEOREM_RE = re.compile(
    r"^(?:Global|Local)?\s*"
    r"(Theorem|Lemma|Corollary|Proposition|Fact|Remark|Example)\s+"
    r"([A-Za-z_][A-Za-z0-9_']*)\b"
)
MODULE_START_RE = re.compile(r"^Module\s+(?:Type\s+)?([A-Za-z_][A-Za-z0-9_']*)\b")
SECTION_START_RE = re.compile(r"^Section\s+([A-Za-z_][A-Za-z0-9_']*)\b")
END_RE = re.compile(r"^End\s+([A-Za-z_][A-Za-z0-9_']*)\b")
PROOF_END_RE = re.compile(r"^(Qed|Defined|Admitted|Abort)\b")


@dataclass(frozen=True)
class CoqTheoremBlock:
    qualname: str
    prelude_sentences: tuple[str, ...]
    block_sentences: tuple[str, ...]
    declaration_sentence: str
    terminator: str | None
    source_path: str | None = None

    @property
    def replayable(self) -> bool:
        return len(self.block_sentences) > 1


def strip_attributes(sentence: str) -> str:
    text = sentence.lstrip()
    while text.startswith("#["):
        end = text.find("]")
        if end == -1:
            break
        text = text[end + 1 :].lstrip()
    return text


def strip_leading_comments(sentence: str) -> str:
    text = sentence.lstrip()
    while text.startswith("(*"):
        end = text.find("*)")
        if end == -1:
            break
        text = text[end + 2 :].lstrip()
    return text


def _normalized_sentence(sentence: str) -> str:
    return strip_leading_comments(strip_attributes(sentence)).strip()


def _theorem_block_end(sentences: list[str], start_idx: int) -> tuple[int, str | None]:
    declaration = _normalized_sentence(sentences[start_idx])
    if ":=" in declaration:
        return start_idx, None
    for idx in range(start_idx + 1, len(sentences)):
        normalized = _normalized_sentence(sentences[idx])
        if not normalized:
            continue
        match = PROOF_END_RE.match(normalized)
        if match:
            return idx, match.group(1)
    return start_idx, None


def collect_theorem_blocks(
    source: str,
    *,
    source_path: str | None = None,
) -> list[CoqTheoremBlock]:
    sentences = split_coq_sentences(source)
    module_stack: list[str] = []
    section_stack: list[str] = []
    blocks: list[CoqTheoremBlock] = []

    idx = 0
    while idx < len(sentences):
        sentence = sentences[idx]
        normalized = _normalized_sentence(sentence)
        if not normalized:
            idx += 1
            continue
        if normalized.startswith("(*") and normalized.endswith("*)"):
            idx += 1
            continue

        section_match = SECTION_START_RE.match(normalized)
        if section_match:
            section_stack.append(section_match.group(1))
            idx += 1
            continue

        end_match = END_RE.match(normalized)
        if end_match:
            name = end_match.group(1)
            if section_stack and section_stack[-1] == name:
                section_stack.pop()
                idx += 1
                continue
            if name in module_stack:
                while module_stack and module_stack[-1] != name:
                    module_stack.pop()
                if module_stack and module_stack[-1] == name:
                    module_stack.pop()
            idx += 1
            continue

        if normalized.startswith(("Module Import", "Module Export", "Module Include")):
            idx += 1
            continue

        module_match = MODULE_START_RE.match(normalized)
        if module_match:
            if ":=" not in normalized:
                module_stack.append(module_match.group(1))
            idx += 1
            continue

        theorem_match = THEOREM_RE.match(normalized)
        if theorem_match:
            name = theorem_match.group(2)
            qualname = ".".join([*module_stack, name]) if module_stack else name
            end_idx, terminator = _theorem_block_end(sentences, idx)
            blocks.append(
                CoqTheoremBlock(
                    qualname=qualname,
                    prelude_sentences=tuple(sentences[:idx]),
                    block_sentences=tuple(sentences[idx : end_idx + 1]),
                    declaration_sentence=sentence,
                    terminator=terminator,
                    source_path=source_path,
                )
            )
            idx = end_idx + 1
            continue

        idx += 1

    return blocks


def extract_theorems_from_source(source: str) -> list[str]:
    return [block.qualname for block in collect_theorem_blocks(source)]


def index_theorem_blocks(paths: list[Path]) -> dict[str, CoqTheoremBlock]:
    index: dict[str, CoqTheoremBlock] = {}
    for path in paths:
        source = path.read_text()
        for block in collect_theorem_blocks(source, source_path=str(path)):
            existing = index.get(block.qualname)
            if existing is not None:
                raise ValueError(
                    "duplicate Coq theorem block:"
                    f" {block.qualname} in {existing.source_path} and {block.source_path}"
                )
            index[block.qualname] = block
    return index
