from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")

from matplotlib import pyplot as plt

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import _resolve_rows_path


def _default_output_dir(analysis_dir: Path) -> Path:
    return analysis_dir.parent.parent / "topology-generator-sheets" / analysis_dir.name


def _load_generator_artifacts(
    analysis_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest = read_json(analysis_dir / "analysis-manifest.json")
    generators = json.loads((analysis_dir / "generators.json").read_text(encoding="utf-8"))
    packet = read_json(analysis_dir / "generator-packet.json")
    if not isinstance(generators, list):
        raise SystemExit(f"{analysis_dir}/generators.json: expected a JSON array")
    return manifest, generators, packet


def _rows_by_specimen_id(source_manifest: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(source_manifest)
    rows_path = _resolve_rows_path(source_manifest, manifest)
    rows = read_jsonl(rows_path)
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        specimen_id = row.get("specimenId")
        if isinstance(specimen_id, str) and specimen_id:
            mapping[specimen_id] = row
    return mapping


def _fingerprint_image(row: dict[str, Any]) -> np.ndarray:
    terminal = row.get("terminal")
    if not isinstance(terminal, dict):
        raise SystemExit("Cycle sheet rendering requires terminal payloads")
    resolution = terminal.get("fingerprintResolution")
    payload = terminal.get("fingerprintU8")
    if not isinstance(resolution, int) or not isinstance(payload, list):
        raise SystemExit("Cycle sheet rendering requires fingerprint payloads")
    image = np.asarray(payload, dtype=np.float64) / 255.0
    return image.reshape((resolution, resolution))


def _cycle_rows(
    generator: dict[str, Any],
    rows_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    cycle_ids = generator.get("representativeSpecimenIds")
    if not isinstance(cycle_ids, list) or not cycle_ids:
        return []
    rows: list[dict[str, Any]] = []
    for specimen_id in cycle_ids:
        if not isinstance(specimen_id, str):
            continue
        row = rows_by_id.get(specimen_id)
        if row is not None:
            rows.append(row)
    return rows


def _series(rows: list[dict[str, Any]], field: str, *, section: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        payload = row.get(section)
        if not isinstance(payload, dict):
            values.append(float("nan"))
            continue
        value = payload.get(field)
        values.append(float(value) if isinstance(value, (int, float)) else float("nan"))
    return values


def _title(row: dict[str, Any]) -> str:
    terminal = row.get("terminal", {})
    angular = terminal.get("angularSymmetry", {}) if isinstance(terminal, dict) else {}
    campaign = row.get("campaignId")
    order = angular.get("dominantOrder")
    amplitude = angular.get("dominantAmplitude")
    if isinstance(amplitude, (int, float)):
        return f"{campaign}\nord={order} amp={amplitude:.3f}"
    return f"{campaign}\nord={order}"


def _render_generator_sheet(
    generator: dict[str, Any],
    rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    if not rows:
        raise SystemExit("Cannot render a generator sheet without cycle rows")

    count = len(rows)
    fig = plt.figure(figsize=(max(10, 2.1 * count), 7.5))
    outer = fig.add_gridspec(2, 1, height_ratios=[2.2, 1.3], hspace=0.28)
    top = outer[0].subgridspec(1, count, wspace=0.1)
    for index, row in enumerate(rows):
        ax = fig.add_subplot(top[0, index])
        ax.imshow(_fingerprint_image(row), cmap="magma", interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(_title(row), fontsize=8)

    x = np.arange(count)
    bottom = outer[1].subgridspec(1, 3, wspace=0.28)
    plots = [
        ("Mass", _series(rows, "finalMass", section="terminal")),
        ("Gyration", _series(rows, "finalGyration", section="terminal")),
        ("Tortuosity", _series(rows, "pathTortuosity", section="trajectory")),
    ]
    for index, (label, values) in enumerate(plots):
        ax = fig.add_subplot(bottom[0, index])
        ax.plot(x, values, marker="o", linewidth=1.4, color="#1f77b4")
        ax.set_title(label)
        ax.set_xlabel("Cycle Step")
        ax.grid(alpha=0.25)

    generator_id = generator.get("generatorId")
    persistence = generator.get("persistence")
    fig.suptitle(f"{generator_id}  persistence={persistence:.6f}", fontsize=13)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_index(
    summaries: list[dict[str, Any]],
    output_path: Path,
) -> None:
    cards = []
    for summary in summaries:
        cards.append(
            f"""
            <section class="card">
              <h2>{summary['generatorId']}</h2>
              <p>persistence={summary['persistence']:.6f} vertices={summary['vertexCount']}</p>
              <p>representative orders={summary['dominantOrders']}</p>
              <img src="{summary['imageName']}" alt="{summary['generatorId']}" />
            </section>
            """
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Topology Generator Sheets</title>
  <style>
    body {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      margin: 24px;
      background: #f7f7f4;
      color: #151515;
    }}
    h1 {{ margin-bottom: 20px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 20px;
    }}
    .card {{ background: white; border: 1px solid #ddd; padding: 16px; }}
    img {{ width: 100%; height: auto; border: 1px solid #ddd; }}
    p {{ margin: 6px 0; }}
  </style>
</head>
<body>
  <h1>Topology Generator Sheets</h1>
  <div class="grid">
    {''.join(cards)}
  </div>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def render_generator_sheets(analysis_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest, generators, packet = _load_generator_artifacts(analysis_dir)
    source_manifest = packet.get("sourceManifest")
    if not isinstance(source_manifest, str) or not source_manifest:
        raise SystemExit(f"{analysis_dir}: generator packet missing sourceManifest")
    rows_by_id = _rows_by_specimen_id(Path(source_manifest))

    summaries: list[dict[str, Any]] = []
    sheets_dir = output_dir / "sheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    for generator in packet.get("generators", []):
        if not isinstance(generator, dict):
            continue
        generator_id = generator.get("generatorId")
        if not isinstance(generator_id, str) or not generator_id:
            continue
        rows = _cycle_rows(generator, rows_by_id)
        if not rows:
            continue
        image_name = f"{generator_id}.png"
        _render_generator_sheet(generator, rows, sheets_dir / image_name)
        orders: dict[str, int] = {}
        for row in rows:
            angular = row.get("terminal", {}).get("angularSymmetry", {})
            order = angular.get("dominantOrder")
            key = str(order)
            orders[key] = orders.get(key, 0) + 1
        summaries.append(
            {
                "generatorId": generator_id,
                "persistence": float(generator.get("persistence", 0.0)),
                "vertexCount": len(rows),
                "dominantOrders": orders,
                "imageName": f"sheets/{image_name}",
            }
        )

    summaries.sort(key=lambda item: (-item["persistence"], item["generatorId"]))
    _render_index(summaries, output_dir / "index.html")
    summary = {
        "version": 1,
        "packetKind": "topology_generator_sheets_v1",
        "sourceAnalysisDir": str(analysis_dir),
        "sourceManifest": source_manifest,
        "sheetCount": len(summaries),
        "sheets": summaries,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render visual sheets for topology generator packets."
    )
    parser.add_argument("--analysis-dir", required=True, help="Generator analysis output directory")
    parser.add_argument("--output", help="Output directory for rendered sheets")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    analysis_dir = Path(args.analysis_dir).expanduser().resolve()
    if not analysis_dir.is_dir():
        raise SystemExit(f"Missing analysis dir: {analysis_dir}")
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(analysis_dir).resolve()
    )
    summary = render_generator_sheets(analysis_dir, output_dir)
    print(
        "Topology generator sheets:"
        f" sheets={summary['sheetCount']}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
