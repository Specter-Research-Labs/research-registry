#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return data


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute a plan-driven holonomy sweep.")
    parser.add_argument("--plan", required=True, help="Path to holonomy sweep plan JSON")
    parser.add_argument(
        "--cli-binary",
        default="./.build/release/LeniaCLI",
        help="Path to the LeniaCLI binary",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip jobs whose output already contains summary.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    plan_path = Path(args.plan).expanduser().resolve()
    if not plan_path.is_file():
        raise SystemExit(f"Missing plan: {plan_path}")
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    if not cli_binary.is_file():
        raise SystemExit(f"Missing CLI binary: {cli_binary}")

    plan = _read_json(plan_path)
    if int(plan.get("version", 0)) != 1:
        raise SystemExit("Holonomy sweep plan version must be 1")
    output_root = Path(str(plan["output_root"])).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    loops_dir = output_root / "_loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    sweep_summary: list[dict[str, Any]] = []

    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise SystemExit("Holonomy sweep plan must define at least one job")

    for job in jobs:
        if not isinstance(job, dict):
            raise SystemExit("Holonomy sweep jobs must be objects")
        name = str(job["name"])
        run_id = str(job["run_id"])
        bundle = Path(str(job["bundle"])).expanduser().resolve()
        output_dir = output_root / str(job.get("output_subdir", name))
        loop_spec = job.get("loop")
        if not isinstance(loop_spec, dict):
            raise SystemExit(f"Holonomy sweep job {name} is missing loop")
        loop_path = loops_dir / f"{name}.json"
        loop_path.write_text(
            json.dumps(loop_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        summary_path = output_dir / "summary.json"
        if args.skip_existing and summary_path.is_file():
            sweep_summary.append(
                {
                    "name": name,
                    "runId": run_id,
                    "outputDir": str(output_dir),
                    "status": "skipped",
                }
            )
            continue

        command = [
            str(cli_binary),
            "holonomy",
            "--run-id",
            run_id,
            "--bundle",
            str(bundle),
            "--loop",
            str(loop_path),
            "--output",
            str(output_dir),
        ]
        if bool(plan.get("export_enabled", False)):
            command.append("--export-enabled")
        db = plan.get("db")
        if isinstance(db, str) and db:
            command.extend(["--db", db])

        subprocess.run(command, check=True)
        if not summary_path.is_file():
            raise SystemExit(f"Holonomy job {name} completed without summary: {summary_path}")
        summary = _read_json(summary_path)
        sweep_summary.append(
            {
                "name": name,
                "runId": run_id,
                "outputDir": str(output_dir),
                "loopName": summary.get("loop_name"),
                "phenotypeClosureDistance": summary.get("phenotype_closure_distance"),
                "transportedStateClosureDistance": summary.get(
                    "transported_state_closure_distance"
                ),
            }
        )

    (output_root / "sweep-summary.json").write_text(
        json.dumps(
            {
                "planPath": str(plan_path),
                "cliBinary": str(cli_binary),
                "jobs": sweep_summary,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(
        "Holonomy sweep:"
        f" jobs={len(sweep_summary)}"
        f" output={output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
