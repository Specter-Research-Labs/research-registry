from __future__ import annotations


def _is_sentence_terminator(source: str, idx: int) -> bool:
    if idx >= len(source):
        return True
    ch = source[idx]
    if ch.isspace():
        return True
    return ch == "(" and idx + 1 < len(source) and source[idx + 1] == "*"


def split_coq_sentences(source: str) -> list[str]:
    sentences: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i = 0
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if not in_string and ch == "(" and nxt == "*":
            depth += 1
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue
        if not in_string and ch == "*" and nxt == ")" and depth > 0:
            depth -= 1
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue
        if ch == '"' and (i == 0 or source[i - 1] != "\\"):
            in_string = not in_string
            buf.append(ch)
            i += 1
            continue
        buf.append(ch)
        if ch == "." and depth == 0 and not in_string and _is_sentence_terminator(source, i + 1):
            sentence = "".join(buf).strip()
            if sentence:
                sentences.append(sentence)
            buf = []
        i += 1
    tail = "".join(buf).strip()
    if tail:
        sentences.append(tail)
    return sentences
