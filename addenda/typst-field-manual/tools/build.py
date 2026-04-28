from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"
ADDENDUM_NAME = "typst-field-manual"


def _die(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _artifact_root(fallback: Path) -> Path:
    raw = os.environ.get(ARTIFACT_ENV)
    if raw is None:
        return fallback
    trimmed = raw.strip()
    if not trimmed:
        _die(f"{ARTIFACT_ENV} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / ADDENDUM_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a Typst document with vendored fonts.")
    parser.add_argument("input", type=Path, help="Input .typ file.")
    args = parser.parse_args()

    typst = shutil.which("typst")
    if typst is None:
        _die(
            "typst not found in PATH.\n"
            "- If you use Nix: `nix shell nixpkgs#typst -c typst --version`\n"
            "- Or install typst via your preferred method."
        )

    addendum_root = Path(__file__).resolve().parents[1]
    fonts_dir = addendum_root / "assets" / "fonts"
    if not fonts_dir.is_dir():
        _die(f"missing fonts dir: {fonts_dir}")

    input_path: Path = args.input
    if not input_path.is_file():
        _die(f"missing input file: {input_path}")

    fallback_root = addendum_root / "artifacts"
    out_root = _artifact_root(fallback_root)
    out_dir = out_root / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_pdf = out_dir / f"{input_path.stem}.pdf"

    cmd = [
        typst,
        "compile",
        "--root",
        str(addendum_root),
        str(input_path),
        str(out_pdf),
        "--font-path",
        str(fonts_dir),
    ]
    subprocess.run(cmd, check=True)

    print(out_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
