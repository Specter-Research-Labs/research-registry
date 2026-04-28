from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_campaign


def test_run_campaign_writes_manifest_before_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter_path = tmp_path / "counter.txt"
    fake_binary = tmp_path / "fake_binary.py"
    fake_binary.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "args = sys.argv[1:]",
                "def value(name: str) -> str:",
                "    return args[args.index(name) + 1]",
                "",
                "counter_path = Path(os.environ['FAKE_BINARY_COUNTER'])",
                "count = int(counter_path.read_text() if counter_path.exists() else '0') + 1",
                "counter_path.write_text(str(count), encoding='utf-8')",
                "if count == 2:",
                "    sys.exit(1)",
                "",
                "out_path = Path(value('--out'))",
                "out_path.parent.mkdir(parents=True, exist_ok=True)",
                "step = {",
                "    'record_type': 'step',",
                "    'drive_signal': 1.0,",
                "    'com_x': 0.5,",
                "    'goal_distance': 0.2,",
                "}",
                "summary = {",
                "    'record_type': 'summary',",
                "    'run_id': out_path.stem,",
                "    'seed': int(value('--seed')),",
                "    'scenario': value('--scenario'),",
                "    'policy': value('--policy'),",
                "    'memory_mode': value('--memory'),",
                "    'backend': value('--backend'),",
                "    'tau_proxy': 10.0,",
                "    'tau_time': 2.0,",
                "    'reached_goal': True,",
                "}",
                "payload = json.dumps(step) + '\\n' + json.dumps(summary) + '\\n'",
                "out_path.write_text(payload, encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )
    fake_binary.chmod(0o755)

    config_path = tmp_path / "campaign.json"
    config_path.write_text(
        json.dumps(
            {
                "campaign_name": "runner_test",
                "artifact_subdir": "data",
                "build_first": False,
                "binary_path": str(fake_binary),
                "scenarios": ["damage"],
                "backends": ["cpu"],
                "seed_start": 1,
                "seed_count": 1,
                "steps": 10,
                "dt": 0.1,
            }
        ),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    log_root = tmp_path / "logs"
    monkeypatch.setenv("FAKE_BINARY_COUNTER", str(counter_path))
    monkeypatch.setenv("SPECTER_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("SPECTER_LOG_ROOT", str(log_root))
    monkeypatch.setattr("sys.argv", ["run_campaign.py", "--config", str(config_path)])

    with pytest.raises(RuntimeError, match="run failed"):
        run_campaign.main()

    manifest_path = (
        artifact_root
        / "jolt-material-memory"
        / "data"
        / "runner_test"
        / "campaign_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 2
    assert manifest["config_snapshot"]["campaign_name"] == "runner_test"
    assert len(manifest["runs"]) == 2
    assert manifest["runs"][0]["return_code"] == 0
    assert manifest["runs"][1]["return_code"] == 1
