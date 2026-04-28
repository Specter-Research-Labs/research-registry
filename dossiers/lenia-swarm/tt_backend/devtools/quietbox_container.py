from __future__ import annotations

import argparse
import glob
import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path


DEFAULT_IMAGE = "ghcr.io/tenstorrent/tt-lang/tt-lang-dist-ubuntu-22-04:latest"
DEFAULT_DEPS_SUBDIR = "tmp/tt-metal-pydeps"
DEFAULT_RESET_WAIT_S = 5.0
DEFAULT_SMOKE_TIMEOUT_S = 60.0
DEVICE_GLOB = "/dev/tenstorrent/*"
HUGEPAGE_PATTERNS = ("/dev/hugepages-1G/*tenstorrent", "/dev/hugepages/*tenstorrent")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _dossier_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tt_backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    command: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    timeout_s: float | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(shlex.quote(part) for part in command))
    return subprocess.run(command, check=check, capture_output=capture_output, text=text, timeout=timeout_s)


def _run_filtered_ttl_compile_stdout(command: list[str]) -> int:
    """Run a payload while hiding TT-Lang generated C++ kernel dumps.

    TT-Lang's TTNN interop path currently prints every generated kernel body to
    stdout. That is useful when debugging codegen, but it makes normal Lenia
    runs unreadable. Keep ordinary stdout/stderr visible and suppress only the
    clearly delimited generated-kernel source blocks.
    """

    print("+", " ".join(shlex.quote(part) for part in command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    suppress_kernel_body = False
    suppressed_blocks = 0
    suppressed_summary_lines = 0
    previous_line_was_suppressed = False
    for line in process.stdout:
        stripped = line.strip()
        if stripped.startswith("=== ") and " kernel written to " in stripped and stripped.endswith(" ==="):
            suppress_kernel_body = True
            suppressed_blocks += 1
            previous_line_was_suppressed = True
            continue
        if suppress_kernel_body:
            if stripped == "=" * 60:
                suppress_kernel_body = False
            previous_line_was_suppressed = True
            continue
        if (
            stripped == "=" * 60
            or stripped.startswith("[TTNN interop] Detected ")
            or stripped == "TTNN INTEROP: Compiling kernel"
            or stripped.startswith("Found ") and stripped.endswith(" kernels:")
            or stripped.startswith("- ") and "(" in stripped and stripped.endswith(")")
            or stripped.startswith("Core range: ")
            or stripped.startswith("Compiled kernel ready ")
        ):
            suppressed_summary_lines += 1
            previous_line_was_suppressed = True
            continue
        if not stripped and previous_line_was_suppressed:
            continue
        print(line, end="")
        previous_line_was_suppressed = False
    return_code = process.wait()
    if suppressed_blocks or suppressed_summary_lines:
        print(
            "[quietbox-container] suppressed "
            f"{suppressed_blocks} TT-Lang generated kernel source blocks "
            f"and {suppressed_summary_lines} compile-log lines"
        )
    return return_code


def _require_path(path: Path, *, message: str) -> Path:
    if not path.exists():
        raise SystemExit(message)
    return path


def _require_device_nodes() -> None:
    device_nodes = sorted(Path("/dev/tenstorrent").glob("*"))
    if not device_nodes:
        raise SystemExit("No /dev/tenstorrent device nodes found. Run this on a TT host.")
    if not Path("/dev/hugepages-1G").exists():
        raise SystemExit("Missing /dev/hugepages-1G. TT container runs require the 1G hugepage mount.")


def _find_container_runtime(explicit: str | None) -> str:
    if explicit is not None:
        if shutil.which(explicit) is None:
            raise SystemExit(f"Container runtime {explicit!r} is not installed.")
        return explicit
    for candidate in ("podman", "docker"):
        if shutil.which(candidate) is not None:
            return candidate
    raise SystemExit("Neither podman nor docker is installed.")


def _find_tt_smi(explicit: str | None) -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(
        [
            shutil.which("tt-smi"),
            str(Path.home() / "dev/tt-metal/python_env/bin/tt-smi"),
            "/usr/bin/tt-smi",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("Could not find tt-smi. Set --tt-smi explicitly.")


def _split_card_list(spec: str | None) -> list[int]:
    if spec is None:
        return []
    cards = []
    for token in spec.split(","):
        value = token.strip()
        if value:
            cards.append(int(value))
    return cards


def _selected_tt_cards(*, tt_card_num: int, tt_card_list: list[int], device_mode: str) -> list[int]:
    if device_mode in {"fleet", "mesh"} and tt_card_list:
        return tt_card_list
    return [tt_card_num]


def _container_device_args(*, tt_card_num: int, tt_card_list: list[int], device_mode: str) -> list[str]:
    if device_mode in {"fleet", "mesh"}:
        if not tt_card_list:
            return ["--device", "/dev/tenstorrent"]
        args: list[str] = []
        for container_index, host_index in enumerate(tt_card_list):
            host_device = Path(f"/dev/tenstorrent/{host_index}")
            _require_path(
                host_device,
                message=f"Missing TT device {host_device}. Check --tt-card-list.",
            )
            args.extend(["--device", f"{host_device}:/dev/tenstorrent/{container_index}"])
        return args
    host_device = Path(f"/dev/tenstorrent/{tt_card_num}")
    _require_path(
        host_device,
        message=f"Missing TT device {host_device}. Set --tt-card-num or use --map-all-devices.",
    )
    return ["--device", f"{host_device}:/dev/tenstorrent/0"]


def _image_provides_ttlang(image: str) -> bool:
    return "/tt-lang/" in image or image.startswith("ghcr.io/tenstorrent/tt-lang/")


def _extract_flag_value(command: list[str], flag: str) -> str | None:
    for index, token in enumerate(command):
        if token == flag and index + 1 < len(command):
            return command[index + 1]
        if token.startswith(flag + "="):
            return token.split("=", 1)[1]
    return None


def _infer_smoke_mesh_shape(
    command: list[str],
    default_rows: int,
    default_cols: int,
    *,
    tt_card_list: list[int],
) -> tuple[int, int]:
    if tt_card_list:
        return 1, 2 * len(tt_card_list)
    device_spec = _extract_flag_value(command, "--device-list")
    if device_spec is None:
        return default_rows, default_cols
    visible = tuple(token.strip() for token in device_spec.split(",") if token.strip())
    if visible:
        return 1, 2 * len(visible)
    return default_rows, default_cols


def _fuser_pids(pattern: str) -> set[int]:
    paths = sorted(glob.glob(pattern))
    if not paths:
        return set()
    result = _run(["fuser", *paths], check=False, capture_output=True)
    pids: set[int] = set()
    merged_output = " ".join(part for part in (result.stdout, result.stderr) if part)
    for token in merged_output.replace(":", " ").split():
        if token.isdigit():
            pids.add(int(token))
    return pids


def _device_holder_pids(*, tt_card_num: int, tt_card_list: list[int], device_mode: str) -> set[int]:
    selected_cards = _selected_tt_cards(tt_card_num=tt_card_num, tt_card_list=tt_card_list, device_mode=device_mode)
    if device_mode in {"fleet", "mesh"} and tt_card_list:
        pids: set[int] = set()
        for card in selected_cards:
            pids.update(_fuser_pids(f"/dev/tenstorrent/{card}"))
        return pids
    if device_mode in {"fleet", "mesh"}:
        return _fuser_pids(DEVICE_GLOB)
    return _fuser_pids(f"/dev/tenstorrent/{tt_card_num}")


def _kill_pids(pids: set[int], *, grace_s: float = 2.0) -> None:
    current_pid = os.getpid()
    target_pids = sorted(pid for pid in pids if pid != current_pid and pid > 1)
    if not target_pids:
        return
    print(f"Killing existing TT holders: {target_pids}")
    for pid in target_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + grace_s
    while time.time() < deadline:
        remaining = {pid for pid in target_pids if Path(f"/proc/{pid}").exists()}
        if not remaining:
            return
        time.sleep(0.1)
    remaining = {pid for pid in target_pids if Path(f"/proc/{pid}").exists()}
    if remaining:
        print(f"Escalating to SIGKILL for TT holders: {sorted(remaining)}")
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _clear_hugepage_files() -> None:
    for pattern in HUGEPAGE_PATTERNS:
        for path_str in glob.glob(pattern):
            path = Path(path_str)
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _reset_tt_devices(tt_smi: str, *, wait_s: float) -> None:
    _run([tt_smi, "-r"], check=True)
    time.sleep(wait_s)


def _ensure_torch_dep(runtime: str, image: str, deps_dir: Path) -> None:
    if (deps_dir / "torch").exists():
        return
    deps_dir.mkdir(parents=True, exist_ok=True)
    bootstrap = [
        runtime,
        "run",
        "--rm",
        "-v",
        f"{deps_dir}:/deps",
        image,
        "sh",
        "-lc",
        "python3 -m ensurepip --default-pip >/dev/null 2>&1 && python3 -m pip install --target /deps torch",
    ]
    _run(bootstrap, check=True)


def _container_prefix(
    *,
    runtime: str,
    image: str,
    deps_dir: Path,
    tt_card_num: int,
    tt_card_list: list[int],
    device_mode: str,
    dossier_root: Path,
    tt_metal_root: Path | None,
    tt_lang_root: Path | None,
    include_deps_pythonpath: bool,
) -> list[str]:
    prefix = [runtime, "run", "--rm", "--network", "none"]
    prefix.extend(_container_device_args(tt_card_num=tt_card_num, tt_card_list=tt_card_list, device_mode=device_mode))
    pythonpath_parts = ["/deps"] if include_deps_pythonpath else []
    if tt_lang_root is not None:
        pythonpath_parts.append("/tt-lang/python")
    if _image_provides_ttlang(image):
        prefix.extend(["-e", "TT_METAL_HOME=/opt/ttlang-toolchain/tt-metal"])
    if Path("/dev/hugepages").exists():
        prefix.extend(["-v", "/dev/hugepages:/dev/hugepages"])
    prefix.extend(
        [
            "-v",
            "/dev/hugepages-1G:/dev/hugepages-1G",
            "-v",
            f"{dossier_root}:/repo",
            "-v",
            f"{deps_dir}:/deps",
            "-e",
            "TT_METAL_INSPECTOR=0",
            "-e",
            "TT_METAL_INSPECTOR_RPC=0",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-w",
            "/repo/tt_backend",
        ]
    )
    if pythonpath_parts:
        prefix.extend(["-e", f"PYTHONPATH={':'.join(pythonpath_parts)}"])
    if tt_metal_root is not None:
        prefix.extend(
            [
                "-v",
                f"{tt_metal_root}:/tt-metal-src:ro",
            ]
        )
    if tt_lang_root is not None:
        prefix.extend(
            [
                "-v",
                f"{tt_lang_root}:/tt-lang:ro",
            ]
        )
    prefix.append(image)
    return prefix


def _single_smoke(prefix: list[str], device_id: int, *, timeout_s: float) -> None:
    command = prefix + [
        "python3",
        "-c",
        (
            "import ttnn; "
            f"device = ttnn.open_device(device_id={device_id}); "
            "print('single-device-open-ok'); "
            "ttnn.close_device(device)"
        ),
    ]
    _run(command, check=True, timeout_s=timeout_s)


def _mesh_smoke(prefix: list[str], rows: int, cols: int, *, timeout_s: float) -> None:
    command = prefix + [
        "python3",
        "-c",
        (
            "import ttnn; "
            f"ttnn.set_fabric_config(ttnn.FabricConfig.{'FABRIC_1D' if rows == 1 else 'FABRIC_2D'}); "
            f"mesh = ttnn.open_mesh_device(mesh_shape=ttnn.MeshShape({rows}, {cols})); "
            "print('mesh-open-ok'); "
            "ttnn.close_mesh_device(mesh)"
        ),
    ]
    _run(command, check=True, timeout_s=timeout_s)


def _prepare_host(
    *,
    tt_card_num: int,
    tt_card_list: list[int],
    device_mode: str,
    kill_holders: bool,
    reset_devices: bool,
    tt_smi: str,
    reset_wait_s: float,
) -> None:
    _require_device_nodes()
    holder_pids = _device_holder_pids(tt_card_num=tt_card_num, tt_card_list=tt_card_list, device_mode=device_mode)
    if holder_pids and not kill_holders:
        raise SystemExit(f"TT devices are busy: {sorted(holder_pids)}")
    if holder_pids:
        _kill_pids(holder_pids)
    if reset_devices:
        _reset_tt_devices(tt_smi, wait_s=reset_wait_s)
    _clear_hugepage_files()
    remaining_pids = _device_holder_pids(tt_card_num=tt_card_num, tt_card_list=tt_card_list, device_mode=device_mode)
    if remaining_pids:
        raise SystemExit(f"TT device holders remain after cleanup: {sorted(remaining_pids)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic quietbox TT-Metal container runner for tt_backend.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute inside the TT-Metal container after --. Omit for smoke-only.",
    )
    parser.add_argument("--runtime", default=None, help="Container runtime to use (podman or docker).")
    parser.add_argument("--image", default=os.environ.get("TT_METAL_CONTAINER_IMAGE", DEFAULT_IMAGE))
    parser.add_argument("--deps-dir", type=Path, default=None)
    parser.add_argument(
        "--tt-metal-root",
        type=Path,
        default=None,
        help="Optional TT-Metal checkout to mount read-only as /tt-metal inside the container.",
    )
    parser.add_argument(
        "--tt-lang-root",
        type=Path,
        default=None,
        help="Optional TT-Lang checkout to mount read-only as /tt-lang inside the container.",
    )
    parser.add_argument("--tt-smi", default=os.environ.get("TT_SMI"))
    parser.add_argument(
        "--tt-card-num",
        type=int,
        default=int(os.environ.get("TT_CARD_NUM", "0")),
        help="Host TT card to map into the container as /dev/tenstorrent/0.",
    )
    parser.add_argument(
        "--tt-card-list",
        default=None,
        help="Comma-separated host TT cards to expose for fleet/mesh modes, remapped contiguously in the container.",
    )
    parser.add_argument(
        "--map-all-devices",
        action="store_true",
        help="Deprecated alias for --device-mode mesh.",
    )
    parser.add_argument(
        "--device-mode",
        choices=["single", "fleet", "mesh"],
        default="single",
        help=(
            "single maps one host card to container /dev/tenstorrent/0; "
            "fleet and mesh expose the TT device tree intentionally."
        ),
    )
    parser.add_argument("--reset", action="store_true", help="Force tt-smi -r before smoke or execution.")
    parser.add_argument("--no-kill-holders", action="store_true", help="Fail instead of killing existing TT holders.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip mode-specific TT device smoke tests.")
    parser.add_argument("--smoke-device-id", type=int, default=0)
    parser.add_argument("--mesh-shape", default=None, help="Mesh shape for smoke tests, as rows,cols.")
    parser.add_argument("--reset-wait-s", type=float, default=DEFAULT_RESET_WAIT_S)
    parser.add_argument(
        "--smoke-timeout-s",
        type=float,
        default=DEFAULT_SMOKE_TIMEOUT_S,
        help="Timeout for each smoke command inside the container.",
    )
    parser.add_argument(
        "--bootstrap-deps",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Install torch into the mounted deps dir if it is missing.",
    )
    parser.add_argument(
        "--deps-pythonpath",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Add /deps to PYTHONPATH inside the container.",
    )
    parser.add_argument(
        "--reset-on-smoke-failure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If the smoke test fails, reset devices once and retry the smoke sequence.",
    )
    parser.add_argument(
        "--show-ttlang-compile",
        action="store_true",
        help="Show raw TT-Lang generated C++ kernel dumps from the payload command.",
    )
    return parser.parse_args()


def _run_smokes(
    prefix: list[str],
    *,
    device_mode: str,
    device_id: int,
    rows: int,
    cols: int,
    timeout_s: float,
) -> None:
    if device_mode == "mesh":
        _mesh_smoke(prefix, rows, cols, timeout_s=timeout_s)
        return
    _single_smoke(prefix, device_id, timeout_s=timeout_s)


def main() -> int:
    args = _parse_args()
    runtime = _find_container_runtime(args.runtime)
    tt_smi = _find_tt_smi(args.tt_smi)
    dossier_root = _require_path(_dossier_root(), message="Could not locate dossier root from script path.")
    _require_path(_tt_backend_root(), message="Could not locate tt_backend root from script path.")
    deps_dir = args.deps_dir or Path(os.environ.get("TT_CONTAINER_PYDEPS_DIR", _repo_root() / DEFAULT_DEPS_SUBDIR))
    deps_dir = deps_dir.resolve()
    deps_dir.mkdir(parents=True, exist_ok=True)
    tt_metal_root = args.tt_metal_root
    if tt_metal_root is None:
        tt_metal_env = os.environ.get("TT_METAL_ROOT") or os.environ.get("TT_METAL_HOME")
        if tt_metal_env:
            tt_metal_root = Path(tt_metal_env)
    if tt_metal_root is not None:
        tt_metal_root = _require_path(tt_metal_root.resolve(), message="Configured --tt-metal-root does not exist.")
    tt_lang_root = args.tt_lang_root
    if tt_lang_root is None and not _image_provides_ttlang(args.image):
        tt_lang_env = os.environ.get("TT_LANG_ROOT")
        if tt_lang_env:
            tt_lang_root = Path(tt_lang_env)
        else:
            default_tt_lang_root = Path.home() / "dev" / "tt-lang"
            if default_tt_lang_root.exists():
                tt_lang_root = default_tt_lang_root
    if tt_lang_root is not None:
        tt_lang_root = _require_path(tt_lang_root.resolve(), message="Configured --tt-lang-root does not exist.")
        _require_path(tt_lang_root / "python" / "ttl", message="Configured --tt-lang-root does not contain python/ttl.")

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    tt_card_list = _split_card_list(args.tt_card_list)
    if args.mesh_shape is None:
        rows, cols = _infer_smoke_mesh_shape(command, 1, 8, tt_card_list=tt_card_list)
    else:
        rows_str, cols_str = args.mesh_shape.split(",", maxsplit=1)
        rows, cols = int(rows_str), int(cols_str)
    device_mode = "mesh" if args.map_all_devices else args.device_mode

    _prepare_host(
        tt_card_num=args.tt_card_num,
        tt_card_list=tt_card_list,
        device_mode=device_mode,
        kill_holders=not args.no_kill_holders,
        reset_devices=args.reset,
        tt_smi=tt_smi,
        reset_wait_s=args.reset_wait_s,
    )

    include_deps_pythonpath = args.deps_pythonpath
    if include_deps_pythonpath is None:
        include_deps_pythonpath = not _image_provides_ttlang(args.image)

    if args.bootstrap_deps and include_deps_pythonpath:
        _ensure_torch_dep(runtime, args.image, deps_dir)
    elif include_deps_pythonpath and not (deps_dir / "torch").exists():
        raise SystemExit(f"Missing torch in deps dir {deps_dir}. Re-run with --bootstrap-deps.")

    prefix = _container_prefix(
        runtime=runtime,
        image=args.image,
        deps_dir=deps_dir,
        tt_card_num=args.tt_card_num,
        tt_card_list=tt_card_list,
        device_mode=device_mode,
        dossier_root=dossier_root,
        tt_metal_root=tt_metal_root,
        tt_lang_root=tt_lang_root,
        include_deps_pythonpath=include_deps_pythonpath,
    )

    if not args.skip_smoke:
        try:
            _run_smokes(
                prefix,
                device_mode=device_mode,
                device_id=args.smoke_device_id,
                rows=rows,
                cols=cols,
                timeout_s=args.smoke_timeout_s,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if not args.reset_on_smoke_failure or args.reset:
                raise
            print("Smoke test failed; resetting TT devices once and retrying.")
            _prepare_host(
                tt_card_num=args.tt_card_num,
                tt_card_list=tt_card_list,
                device_mode=device_mode,
                kill_holders=not args.no_kill_holders,
                reset_devices=True,
                tt_smi=tt_smi,
                reset_wait_s=args.reset_wait_s,
            )
            _run_smokes(
                prefix,
                device_mode=device_mode,
                device_id=args.smoke_device_id,
                rows=rows,
                cols=cols,
                timeout_s=args.smoke_timeout_s,
            )

    if command:
        if args.show_ttlang_compile:
            completed = _run(prefix + command, check=False)
            return completed.returncode
        return _run_filtered_ttl_compile_stdout(prefix + command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
