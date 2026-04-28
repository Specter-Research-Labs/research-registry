import argparse
import subprocess
from pathlib import Path

PNG_TOOL_CHOICES = ("auto", "sips", "pdftoppm", "none")


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        cmd,
        check=True,
        cwd=cwd,
    )


def _convert_pdf_to_png(
    pdf_file: Path,
    png_file: Path,
    dpi: int,
    png_tool: str,
) -> None:
    if png_tool == "none":
        return

    if png_tool in {"auto", "sips"}:
        try:
            _run(
                [
                    "sips",
                    "-s",
                    "format",
                    "png",
                    "--resampleHeightWidthMax",
                    "2000",
                    str(pdf_file),
                    "--out",
                    str(png_file),
                ]
            )
            print(f"  -> Converted to PNG: {png_file.name} (using sips)")
            return
        except FileNotFoundError:
            if png_tool == "sips":
                raise
        except subprocess.CalledProcessError as exc:
            if png_tool == "sips":
                raise exc

    if png_tool in {"auto", "pdftoppm"}:
        prefix = png_file.with_suffix("")
        _run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-singlefile",
                str(pdf_file),
                str(prefix),
            ]
        )
        print(f"  -> Converted to PNG: {png_file.name} (using pdftoppm)")
        return

    raise ValueError(f"Unknown png tool: {png_tool}")


def build_figures(output_dir: Path, dpi: int, png_tool: str) -> None:
    figures_dir = Path(__file__).resolve().parent
    src_dir = figures_dir / "src"
    out_dir = output_dir if output_dir.is_absolute() else figures_dir / output_dir

    if not src_dir.exists():
        raise FileNotFoundError(f"Missing figures src dir: {src_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    tex_files = sorted(src_dir.glob("*.tex"))
    tex_files = [f for f in tex_files if f.name != "common-styles.tex"]
    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {src_dir}")

    print(f"Found {len(tex_files)} figure files to build.")

    for tex_file in tex_files:
        print(f"Building {tex_file.name}...")
        _run(
            [
                "tectonic",
                "--outdir",
                str(out_dir),
                tex_file.name,
            ],
            cwd=src_dir,
        )
        pdf_file = out_dir / f"{tex_file.stem}.pdf"
        print(f"  -> Generated PDF: {pdf_file.name}")

        if png_tool != "none":
            png_file = out_dir / f"{tex_file.stem}.png"
            _convert_pdf_to_png(pdf_file, png_file, dpi, png_tool)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TikZ figures.")
    parser.add_argument(
        "--out-dir",
        default="out",
        help="Output directory for generated PDFs/PNGs (relative to figures dir).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI for pdftoppm conversion.",
    )
    parser.add_argument(
        "--png-tool",
        choices=PNG_TOOL_CHOICES,
        default="auto",
        help="PNG conversion tool (auto tries sips then pdftoppm).",
    )
    args = parser.parse_args()

    build_figures(Path(args.out_dir), dpi=args.dpi, png_tool=args.png_tool)


if __name__ == "__main__":
    main()
