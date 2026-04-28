from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_bench_module():
    bench_path = Path(__file__).resolve().parents[1] / "devtools" / "bench.py"
    spec = importlib.util.spec_from_file_location("tt_backend_bench", bench_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_tracy_command_strips_profiler_flags():
    bench = _load_bench_module()
    script_path = Path("/tmp/bench.py")
    command = bench.build_tracy_command(
        script_path=script_path,
        argv=[
            "--backend",
            "tt",
            "--grid-sizes",
            "128",
            "--tracy-output-dir",
            "/tmp/prof",
            "--tracy-perf-counters",
            "all",
            "--tracy-sync-host-device",
        ],
        output_dir=Path("/tmp/prof"),
        perf_counters="all",
        sync_host_device=True,
        tracy_tools_folder=Path("/tmp/tracy-bin"),
    )

    assert command[:6] == [
        command[0],
        "-m",
        "tracy",
        "-v",
        "-r",
        "-p",
    ]
    assert "--sync-host-device" in command
    assert "--profiler-capture-perf-counters" in command
    assert "--tracy-output-dir" not in command
    assert "--tracy-perf-counters" not in command
    assert "--tracy-sync-host-device" not in command[command.index(str(script_path)) + 1 :]
    assert command[-5:] == [str(script_path), "--backend", "tt", "--grid-sizes", "128"]


def test_build_serialized_case_command_rewrites_case_and_summary():
    bench = _load_bench_module()
    script_path = Path("/tmp/bench.py")
    summary_path = Path("/tmp/summary.json")

    command = bench.build_serialized_case_command(
        script_path=script_path,
        argv=[
            "--backend",
            "tt",
            "--device-list",
            "0,1,2,3",
            "--grid-sizes",
            "128,256",
            "--batch-sizes",
            "1,4",
            "--persistent-workers",
        ],
        grid_size=512,
        batch_size=4,
        summary_path=summary_path,
    )

    assert command[:2] == [command[0], str(script_path)]
    assert command[-6:] == [
        "--grid-sizes",
        "512",
        "--batch-sizes",
        "4",
        "--summary-json",
        str(summary_path),
    ]


def test_resolve_config_path_accepts_repo_relative_configs():
    bench = _load_bench_module()

    config_path = bench.resolve_config_path(Path("configs/base/paper_base_2c_128.json"))

    assert config_path.is_absolute()
    assert config_path.name == "paper_base_2c_128.json"
    assert config_path.exists()


def test_resolve_bench_execution_mode_defaults_device_list_to_mesh():
    bench = _load_bench_module()

    mode = bench.resolve_bench_execution_mode(
        requested_mode=None,
        device_list=["0", "1", "2", "3"],
        visible_devices=None,
        mesh_shape=None,
    )

    assert mode == "mesh"


def test_resolve_bench_execution_mode_keeps_explicit_fleet():
    bench = _load_bench_module()

    mode = bench.resolve_bench_execution_mode(
        requested_mode="fleet",
        device_list=["0", "1"],
        visible_devices=None,
        mesh_shape=None,
    )

    assert mode == "fleet"
