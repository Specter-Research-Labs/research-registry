from __future__ import annotations

import re
import sys
from pathlib import Path


ADDENDUM_ROOT = Path(__file__).resolve().parents[1]
TOKENS_FILE = ADDENDUM_ROOT / "tokens.typ"
SURFACE_FILES: tuple[tuple[Path, int], ...] = (
    (ADDENDUM_ROOT / "specter-fm.typ", 20),
    (ADDENDUM_ROOT / "specter-paper.typ", 20),
)

REQUIRED_SNIPPETS = (
    '#import "tokens.typ": tokens',
)

FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b_cfg\b", "legacy _cfg constants must not be used; use tokens.typ"),
    (r"luma\(", "color literals must live in tokens.typ"),
    (r'"IBM Plex [^"]+"', "font family literals must live in tokens.typ"),
    (
        r"\b(0\.6pt|1\.4pt|2\.4pt|16mm|18mm|34mm|60mm|26pt|14pt)\b",
        "core style scale literals must live in tokens.typ",
    ),
)


def _die(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def main() -> int:
    errors: list[str] = []
    checked: list[str] = []

    if not TOKENS_FILE.is_file():
        errors.append(f"missing file: {TOKENS_FILE}")

    for path, minimum_token_refs in SURFACE_FILES:
        if not path.is_file():
            errors.append(f"missing file: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        checked.append(path.name)

        for snippet in REQUIRED_SNIPPETS:
            if snippet not in text:
                errors.append(f"{path.name}: missing required snippet: {snippet}")

        for pattern, reason in FORBIDDEN_PATTERNS:
            match = re.search(pattern, text)
            if match:
                line_no = text.count("\n", 0, match.start()) + 1
                literal = match.group(0)
                errors.append(
                    f"{path.name}: line {line_no}: forbidden literal `{literal}` ({reason})"
                )

        if text.count("tokens.") < minimum_token_refs:
            errors.append(
                f"{path.name}: expected token-based styling references; "
                "found too few `tokens.` usages"
            )

    if errors:
        print("style token check failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print(f"ok: shared tokens drive {', '.join(checked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
