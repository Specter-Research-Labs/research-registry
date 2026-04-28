import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RunRecord:
    experiment: str
    run_index: int
    seed: int
    status: str
    return_code: int
    started_at: str
    ended_at: str
    duration_seconds: float
    command: list[str]
    stdout_path: str
    stderr_path: str


@dataclass(frozen=True)
class CampaignItem:
    experiment: str
    repeats: int
    base_seed: int
    python_bin: str
    extra_args: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic experiment campaigns with provenance capture. "
            "Supports direct CLI mode and declarative plan-file mode."
        )
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        help="CLI mode: experiment scripts to execute.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="CLI mode: runs per experiment.",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=10_000,
        help="CLI mode: first seed in deterministic sequence.",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        help=(
            "Option 2: JSON plan file with campaign items. "
            "When provided, --experiments is ignored."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/campaign_runs"),
        help="Directory for logs and manifest output.",
    )
    parser.add_argument(
        "--python-bin",
        default="python",
        help="Default python executable for CLI mode and plan items without python_bin.",
    )
    args = parser.parse_args()

    if args.plan_file is None and not args.experiments:
        raise ValueError("Provide --experiments for CLI mode, or --plan-file for Option 2")
    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")

    return args


def current_iso_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def resolve_repo_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_env(seed: int) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(seed)
    env["SPECTER_EXPERIMENT_SEED"] = str(seed)
    return env


def parse_plan_file(plan_file: Path, default_python_bin: str) -> list[CampaignItem]:
    if not plan_file.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_file}")

    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "items" not in payload:
        raise ValueError("Plan file must be a JSON object with an 'items' list")
    items = payload["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("Plan file 'items' must be a non-empty list")

    parsed: list[CampaignItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Plan item {index} must be an object")
        experiment = item.get("experiment")
        repeats = item.get("repeats", 1)
        base_seed = item.get("base_seed", 10_000)
        python_bin = item.get("python_bin", default_python_bin)
        extra_args = item.get("extra_args", [])

        if not isinstance(experiment, str) or not experiment:
            raise ValueError(f"Plan item {index} needs non-empty string 'experiment'")
        if not isinstance(repeats, int) or repeats < 1:
            raise ValueError(f"Plan item {index} has invalid repeats={repeats}")
        if not isinstance(base_seed, int):
            raise ValueError(f"Plan item {index} has invalid base_seed={base_seed}")
        if not isinstance(python_bin, str) or not python_bin:
            raise ValueError(f"Plan item {index} has invalid python_bin")
        if not isinstance(extra_args, list) or not all(isinstance(a, str) for a in extra_args):
            raise ValueError(f"Plan item {index} has invalid extra_args; expected list[str]")

        parsed.append(
            CampaignItem(
                experiment=experiment,
                repeats=repeats,
                base_seed=base_seed,
                python_bin=python_bin,
                extra_args=extra_args,
            )
        )

    return parsed


def build_campaign_items(args: argparse.Namespace) -> list[CampaignItem]:
    if args.plan_file is not None:
        return parse_plan_file(args.plan_file, args.python_bin)

    return [
        CampaignItem(
            experiment=experiment,
            repeats=args.repeats,
            base_seed=args.base_seed,
            python_bin=args.python_bin,
            extra_args=[],
        )
        for experiment in args.experiments
    ]


def run_once(
    item: CampaignItem,
    run_index: int,
    seed: int,
    output_dir: Path,
) -> RunRecord:
    script_name = Path(item.experiment).stem
    run_tag = f"{script_name}_run{run_index:03d}_seed{seed}"
    stdout_path = output_dir / f"{run_tag}.stdout.log"
    stderr_path = output_dir / f"{run_tag}.stderr.log"

    command = [item.python_bin, item.experiment, *item.extra_args]
    started_at = current_iso_timestamp()
    started_monotonic = time.perf_counter()

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.run(
            command,
            env=build_env(seed),
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            check=False,
        )

    ended_at = current_iso_timestamp()
    duration = time.perf_counter() - started_monotonic
    status = "success" if process.returncode == 0 else "failed"

    return RunRecord(
        experiment=item.experiment,
        run_index=run_index,
        seed=seed,
        status=status,
        return_code=process.returncode,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=round(duration, 3),
        command=command,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    commit = resolve_repo_commit()
    campaign_started_at = current_iso_timestamp()
    records: list[RunRecord] = []
    items = build_campaign_items(args)

    for item in items:
        if not Path(item.experiment).exists():
            raise FileNotFoundError(f"Experiment script not found: {item.experiment}")

        for run_index in range(item.repeats):
            seed = item.base_seed + run_index
            print(
                f"Running {item.experiment} ({run_index + 1}/{item.repeats}) with seed={seed}",
                flush=True,
            )
            record = run_once(item, run_index, seed, output_dir)
            records.append(record)
            print(
                f"  -> {record.status} in {record.duration_seconds:.3f}s "
                f"(exit={record.return_code})",
                flush=True,
            )

            if record.return_code != 0:
                raise RuntimeError(
                    "Campaign aborted because an experiment failed. "
                    f"Inspect logs: {record.stdout_path} and {record.stderr_path}"
                )

    manifest = {
        "campaign_started_at": campaign_started_at,
        "campaign_ended_at": current_iso_timestamp(),
        "repository_commit": commit,
        "plan_file": str(args.plan_file) if args.plan_file is not None else None,
        "records": [asdict(record) for record in records],
    }
    manifest_path = output_dir / "campaign_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Campaign complete. Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
