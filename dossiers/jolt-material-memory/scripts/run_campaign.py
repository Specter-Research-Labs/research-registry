from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _run_capture(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        return ""
    except subprocess.CalledProcessError:
        return ""
    return proc.stdout.strip()


def _jj_metadata() -> dict[str, str]:
    raw = _run_capture(
        ["jj", "log", "-r", "@", "-T", "change_id.short() ++ \" \" ++ commit_id.short()"],
        ROOT,
    )
    if not raw:
        return {"change_id": "", "commit_id": ""}
    parts = raw.split()
    if len(parts) < 2:
        return {"change_id": "", "commit_id": ""}
    return {"change_id": parts[0], "commit_id": parts[1]}


def _normalize_path(path_like: str | Path) -> Path:
    p = Path(path_like)
    if p.is_absolute():
        return p
    return ROOT / p


def _load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _build_if_requested(config: dict[str, Any], build_dir: Path) -> None:
    if not bool(config.get("build_first", True)):
        return
    build_script = ROOT / "scripts" / "build.sh"
    subprocess.run([str(build_script), str(build_dir)], cwd=ROOT, check=True)


def _run_single(command: list[str], cwd: Path, stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        stdout_path.open("w", encoding="utf-8") as out,
        stderr_path.open("w", encoding="utf-8") as err,
    ):
        proc = subprocess.run(command, cwd=cwd, text=True, stdout=out, stderr=err)
    return int(proc.returncode)


def _memory_variants(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("memory_variants")
    if raw is None:
        return [{"name": "baseline"}]
    variants = list(raw)
    if not variants:
        raise ValueError("memory_variants must not be empty")
    normalized: list[dict[str, Any]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError("each memory variant must be an object")
        if "name" not in variant:
            raise ValueError("each memory variant must define a name")
        normalized.append(dict(variant))
    return normalized


def main() -> int:
    from paths import resolve_artifact_dir, resolve_log_dir

    parser = argparse.ArgumentParser(description="Run the jolt-material-memory campaign matrix")
    parser.add_argument(
        "--config",
        default=str(ROOT / "configs" / "paper_track_v1.json"),
        help="Path to campaign JSON config",
    )
    args = parser.parse_args()

    config_path = _normalize_path(args.config)
    config = _load_config(config_path)

    build_dir = _normalize_path(config.get("build_dir", ROOT / "build"))
    binary = _normalize_path(config.get("binary_path", build_dir / "jolt_memory_lab"))

    artifact_subdir = str(config.get("artifact_subdir", "data"))
    campaign_name = str(config.get("campaign_name", "paper_track_v1"))

    artifact_root = resolve_artifact_dir(artifact_subdir, ROOT / "data")
    log_root = resolve_log_dir("campaign_logs", ROOT / "logs")

    campaign_root = artifact_root / campaign_name
    runs_root = campaign_root / "runs"
    logs_root = log_root / campaign_name
    manifest_path = campaign_root / "campaign_manifest.json"

    _build_if_requested(config, build_dir)

    if not binary.exists():
        raise FileNotFoundError(f"binary not found: {binary}")

    scenarios = list(config["scenarios"])
    backends = list(config["backends"])
    layouts = list(config.get("layouts", ["line"]))
    memory_variants = _memory_variants(config)
    seed_start = int(config["seed_start"])
    seed_count = int(config["seed_count"])
    steps = int(config["steps"])
    dt_value = float(config.get("dt", 1.0 / 60.0))

    jj_meta = _jj_metadata()

    manifest: dict[str, Any] = {
        "manifest_version": 2,
        "created_at_utc": _now_iso(),
        "config_path": str(config_path),
        "config_snapshot": config,
        "campaign_root": str(campaign_root),
        "artifact_root": str(artifact_root),
        "log_root": str(log_root),
        "jj_change_id": jj_meta["change_id"],
        "jj_commit_id": jj_meta["commit_id"],
        "jolt_revision": "v5.5.0",
        "build_dir": str(build_dir),
        "binary_path": str(binary),
        "steps": steps,
        "dt": dt_value,
        "runs": [],
    }
    _write_manifest(manifest_path, manifest)

    def register_run(
        scenario: str,
        backend: str,
        layout: str,
        memory_variant: dict[str, Any],
        policy: str,
        memory_mode: str,
        seed: int,
    ) -> None:
        variant_name = str(memory_variant["name"])
        run_id = f"{scenario}_{backend}_{layout}_{variant_name}_{policy}_{memory_mode}_seed{seed}"
        ndjson_path = runs_root / f"{run_id}.ndjson"
        stdout_path = logs_root / f"{run_id}.stdout.log"
        stderr_path = logs_root / f"{run_id}.stderr.log"

        command = [
            str(binary),
            "--scenario",
            scenario,
            "--policy",
            policy,
            "--backend",
            backend,
            "--layout",
            layout,
            "--memory-variant",
            variant_name,
            "--memory",
            memory_mode,
            "--seed",
            str(seed),
            "--steps",
            str(steps),
            "--dt",
            str(dt_value),
            "--out",
            str(ndjson_path),
        ]
        for key, flag in (
            ("plastic_gain", "--plastic-gain"),
            ("plastic_decay", "--plastic-decay"),
            ("max_plastic", "--max-plastic"),
        ):
            if key in memory_variant:
                command.extend([flag, str(float(memory_variant[key]))])

        started = _now_iso()
        return_code = _run_single(command, ROOT, stdout_path, stderr_path)
        ended = _now_iso()

        run_record = {
            "run_id": run_id,
            "scenario": scenario,
            "backend": backend,
            "layout": layout,
            "memory_variant": variant_name,
            "policy": policy,
            "memory_mode": memory_mode,
            "seed": seed,
            "command": command,
            "ndjson_path": str(ndjson_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "started_at_utc": started,
            "ended_at_utc": ended,
            "return_code": return_code,
        }
        for key in ("plastic_gain", "plastic_decay", "max_plastic"):
            if key in memory_variant:
                run_record[key] = float(memory_variant[key])
        manifest["runs"].append(run_record)
        _write_manifest(manifest_path, manifest)
        print(f"[{return_code}] {run_id}")

        if return_code != 0:
            raise RuntimeError(f"run failed: {run_id}")

    for seed in range(seed_start, seed_start + seed_count):
        for scenario in scenarios:
            for backend in backends:
                for layout in layouts:
                    for memory_variant in memory_variants:
                        register_run(
                            scenario, backend, layout, memory_variant, "blind", "off", seed
                        )
                        register_run(
                            scenario, backend, layout, memory_variant, "directed", "off", seed
                        )
                        register_run(
                            scenario, backend, layout, memory_variant, "directed", "on", seed
                        )
                        register_run(
                            scenario,
                            backend,
                            layout,
                            memory_variant,
                            "directed",
                            "inertial_control",
                            seed,
                        )

    _write_manifest(manifest_path, manifest)
    print(f"Manifest written: {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
