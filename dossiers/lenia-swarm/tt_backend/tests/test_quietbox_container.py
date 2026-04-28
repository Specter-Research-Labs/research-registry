from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_quietbox_module():
    module_path = Path(__file__).resolve().parents[1] / "devtools" / "quietbox_container.py"
    spec = importlib.util.spec_from_file_location("tt_backend_quietbox_container", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_filtered_ttl_compile_stdout_hides_generated_kernel_dump(tmp_path, capsys):
    quietbox = _load_quietbox_module()
    script = tmp_path / "emit_ttl_compile_log.py"
    script.write_text(
        "\n".join(
            [
                "print('payload-before')",
                "print('=== reader kernel written to /tmp/generated_reader.cpp ===')",
                "print('generated C++ body that should stay hidden')",
                "print('=' * 60)",
                "print('[TTNN interop] Detected generated kernels')",
                "print('TTNN INTEROP: Compiling kernel')",
                "print('Found 1 kernels:')",
                "print('- reader (/tmp/generated_reader.cpp)')",
                "print('Core range: (0,0)-(7,3)')",
                "print('Compiled kernel ready /tmp/generated_reader.cpp')",
                "print('payload-after')",
            ]
        ),
        encoding="utf-8",
    )

    return_code = quietbox._run_filtered_ttl_compile_stdout([sys.executable, str(script)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "payload-before" in captured.out
    assert "payload-after" in captured.out
    assert "generated C++ body that should stay hidden" not in captured.out
    assert "[TTNN interop]" not in captured.out
    assert "suppressed 1 TT-Lang generated kernel source blocks" in captured.out
