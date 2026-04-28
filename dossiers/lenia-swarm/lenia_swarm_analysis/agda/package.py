from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .codegen import render_agda_package
from .facing_packet import build_agda_facing_packet


def _default_semantic_source_root() -> Path:
    return (Path(__file__).resolve().parent.parent / "agda").resolve()


def build_agda_package(
    empirical_packet_path: Path,
    *,
    output_root: Path,
    root_module: str = "Morphospace",
    semantic_source_root: Path | None = None,
) -> dict[str, object]:
    semantic_root = (
        semantic_source_root.expanduser().resolve()
        if semantic_source_root is not None
        else _default_semantic_source_root()
    )
    module_source_root = semantic_root / root_module
    if not module_source_root.is_dir():
        raise SystemExit(f"missing semantic Agda source root: {module_source_root}")

    packet = build_agda_facing_packet(empirical_packet_path.expanduser().resolve())
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    facing_packet_path = output_root / "agda-facing-packet.json"
    facing_packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    generated_files = render_agda_package(packet, root_module=root_module)
    written_generated: list[str] = []
    for relative_path, source in generated_files.items():
        target_path = output_root / root_module / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source, encoding="utf-8")
        written_generated.append(str(target_path))

    copied_semantic: list[str] = []
    for source_path in module_source_root.rglob("*.agda"):
        relative_path = source_path.relative_to(semantic_root)
        target_path = output_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied_semantic.append(str(target_path))

    return {
        "rootModule": root_module,
        "outputRoot": str(output_root),
        "agdaFacingPacket": str(facing_packet_path),
        "generatedFileCount": len(written_generated),
        "semanticFileCount": len(copied_semantic),
        "generatedFiles": written_generated,
        "semanticFiles": copied_semantic,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble a generated plus semantic Agda package "
            "from an empirical fibration packet."
        )
    )
    parser.add_argument(
        "--empirical-packet",
        required=True,
        help="Path to empirical_fibration_packet_v1 JSON",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="Directory where the Agda package should be written",
    )
    parser.add_argument(
        "--root-module",
        default="Morphospace",
        help="Top-level Agda module name for the package",
    )
    parser.add_argument(
        "--semantic-source-root",
        help="Optional directory containing hand-written Agda modules",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    result = build_agda_package(
        Path(args.empirical_packet),
        output_root=Path(args.output_root),
        root_module=str(args.root_module),
        semantic_source_root=(
            Path(args.semantic_source_root) if args.semantic_source_root else None
        ),
    )
    print(
        "Agda package:"
        f" root_module={result['rootModule']}"
        f" output_root={result['outputRoot']}"
        f" generated_files={result['generatedFileCount']}"
        f" semantic_files={result['semanticFileCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
