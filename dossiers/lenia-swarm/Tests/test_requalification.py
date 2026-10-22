import base64
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.morphospace import requalification as rq


def base_config(native: int, seed_value: float) -> dict:
    patch = np.full((2, 4, 4), seed_value, dtype="<f4").tobytes()
    return {
        "grid": {"sx": native, "sy": native},
        "params": {"R": 12.0, "r": [seed_value]},
        "init": {
            "a_uniform": {"high": 0, "low": 0},
            "patches": [],
            "seed": 0,
            "state_patch": {
                "center": [native // 2, native // 2],
                "channels": 2,
                "encoding": "f32le",
                "height": 4,
                "width": 4,
                "data": base64.b64encode(patch).decode(),
            },
        },
        "reintegration": {"border": "wall", "dd": 5, "sigma": 0.65},
        "run": {"steps": 900},
    }


def export(root: Path, name: str, body: str, base: dict) -> dict:
    d = root / name
    d.mkdir(parents=True)
    (d / "base.json").write_text(json.dumps(base))
    (d / "search.json").write_text(json.dumps({"steps": 900}))
    (d / "meta.json").write_text("{}")
    return {
        "creatureId": body,
        "exportDir": str(d),
        "baseConfigPath": str(d / "base.json"),
        "searchConfigPath": str(d / "search.json"),
    }


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


@pytest.fixture
def sources(tmp_path: Path) -> list[tuple[str, str, Path, Path]]:
    inputs = tmp_path / "inputs"
    rows = [
        export(inputs, "0000-a", "AAAA0001", base_config(128, 0.1)),
        export(inputs, "0001-b", "BBBB0002", base_config(128, 0.2)),
        export(inputs, "0002-c", "CCCC0003", base_config(256, 0.3)),
    ]
    index = write_jsonl(tmp_path / "index.jsonl", rows)
    replay = tmp_path / "replay"
    screened = []
    for row, passes, moving in ((rows[0], True, True), (rows[1], False, False)):
        config = replay / Path(row["exportDir"]).name / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text(Path(row["baseConfigPath"]).read_text())
        screened.append(
            {
                "candidate_id": Path(row["exportDir"]).name,
                "source_creature_id": row["creatureId"],
                "screen_id": "long-screen",
                "individuality_class": "persistent_individual",
                "individuality_pass": str(passes),
                "locality_pass": "True",
                "translation_pass": str(moving),
                "orbit_or_gyration_pass": "False",
                "individuality_axes": str({"temporal_individuality_score": 0.8}),
                "replay": {"config_path": str(config)},
            }
        )
    screen = write_jsonl(tmp_path / "screened.jsonl", screened)

    gap = tmp_path / "gap" / "requal"
    config = gap / "replay" / "grid256-0000" / "campaigns" / "0002-c" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(Path(rows[2]["baseConfigPath"]).read_text())
    gap_index = write_jsonl(gap / "index.jsonl", [rows[2]])
    record = {
        "campaign": "0002-c",
        "source_creature_id": "CCCC0003",
        "qualified": True,
        "individuality_pass": True,
        "locality_pass": True,
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "individuality_class": "persistent_individual",
        "coherence_min_1e-6": 0.99,
        "in_target_cells": False,
    }
    (gap / "requal.json").write_text(json.dumps({"records": [record]}))
    return [("135", "screen", index, screen), ("004", "requal", gap_index, gap / "requal.json")]


def test_collect_members_keeps_selected_bodies_with_motion_class(tmp_path, sources):
    out = tmp_path / "members.json"
    summary = rq.collect_members(sources=sources, qualified=True, output_path=out)
    assert summary["by_cohort_and_native_arena"] == {"004/256": 1, "135/128": 1}
    members = {m["body"]: m for m in json.loads(out.read_text())["members"]}
    assert set(members) == {"AAAA0001", "CCCC0003"}
    assert members["AAAA0001"]["original"]["motion_class"] == "translating"
    assert members["AAAA0001"]["state_patch_shape"] == [2, 4, 4]


def test_collect_members_can_take_the_rejected_bodies(tmp_path, sources):
    out = tmp_path / "members.json"
    rq.collect_members(sources=sources[:1], qualified=False, output_path=out)
    (member,) = json.loads(out.read_text())["members"]
    assert member["body"] == "BBBB0002"
    assert member["original"]["gates"] == {"individuality": False, "locality": True}


def test_collect_members_rejects_a_replay_that_differs_from_its_input(tmp_path, sources):
    config = Path(
        json.loads((tmp_path / "screened.jsonl").read_text().splitlines()[0])["replay"][
            "config_path"
        ]
    )
    changed = json.loads(config.read_text())
    changed["params"]["R"] = 13.0
    config.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="params_sha256"):
        rq.collect_members(sources=sources, qualified=True, output_path=tmp_path / "members.json")


def test_torus_inputs_scale_grid_and_recentre_patch(tmp_path, sources):
    members = tmp_path / "members.json"
    rq.collect_members(sources=sources, qualified=True, output_path=members)
    summary = rq.write_torus_inputs(
        members_path=members, scales=[1, 2], steps=40000, output_root=tmp_path / "in"
    )
    assert summary["cells"] == {
        "n128-torus128": 1,
        "n128-torus256": 1,
        "n256-torus256": 1,
        "n256-torus512": 1,
    }
    row = json.loads((tmp_path / "in/n128-torus256/index.jsonl").read_text())
    base = json.loads(Path(row["baseConfigPath"]).read_text())
    assert base["grid"] == {"sx": 256, "sy": 256}
    assert base["init"]["state_patch"]["center"] == [128, 128]
    assert base["reintegration"]["border"] == "torus"
    assert json.loads(Path(row["searchConfigPath"]).read_text())["steps"] == 40000


def test_arena_inputs_take_every_indexed_body_whatever_its_init_seed(tmp_path):
    seeded = base_config(128, 0.4)
    seeded["init"]["seed"] = 104000017
    rows = [
        export(tmp_path / "exports", "0000-a", "AAAA0001", seeded),
        export(tmp_path / "exports", "0001-b", "BBBB0002", base_config(256, 0.5)),
    ]
    index = write_jsonl(tmp_path / "index.jsonl", rows)
    summary = rq.write_arena_inputs(
        index_path=index, scales=[1, 2], steps=650, output_root=tmp_path / "in"
    )
    assert summary["cells"] == {
        "n128-torus128": 1,
        "n128-torus256": 1,
        "n256-torus256": 1,
        "n256-torus512": 1,
    }
    row = json.loads((tmp_path / "in/n128-torus256/index.jsonl").read_text())
    assert row["creatureId"] == "AAAA0001"
    base = json.loads(Path(row["baseConfigPath"]).read_text())
    assert base["init"]["state_patch"]["center"] == [128, 128]
    assert base["init"]["seed"] == 104000017
    receipt = json.loads((tmp_path / "in/receipt.json").read_text())
    assert receipt["index_sha256"] == hashlib.sha256(index.read_bytes()).hexdigest()


def test_arena_inputs_refuse_uniform_noise_beside_the_state_patch(tmp_path):
    noisy = base_config(128, 0.4)
    noisy["init"]["a_uniform"] = {"low": 0, "high": 0.2}
    index = write_jsonl(
        tmp_path / "index.jsonl", [export(tmp_path / "exports", "0000-a", "AAAA0001", noisy)]
    )
    with pytest.raises(ValueError, match="only initial condition"):
        rq.write_arena_inputs(index_path=index, scales=[1], steps=650, output_root=tmp_path / "in")


def assessment(path: Path, arena: int, passes: dict[str, bool]) -> Path:
    bodies = [
        {
            "body": body,
            "campaign": f"0000-{body[-4:].lower()}",
            "arena": arena,
            "border": "torus",
            "criteria": {"adult_phase": True, "long_lived": ok},
            "intrinsic_creature": ok,
            "adult": {
                "onset_step": 4000,
                "lifetime_runs": {"captured": 9.0 if ok else 2.0},
                "reference": {"captured": 0.99, "body_radius": 8.0},
            },
        }
        for body, ok in passes.items()
    ]
    path.write_text(json.dumps({"bodies": bodies}))
    return path


def test_compare_verdicts_reports_prior_transitions(tmp_path, sources):
    members = tmp_path / "members.json"
    rq.collect_members(sources=sources, qualified=True, output_path=members)
    small = assessment(tmp_path / "a128.json", 128, {"AAAA0001": True, "CCCC0003": False})
    large = assessment(tmp_path / "a256.json", 256, {"AAAA0001": True, "CCCC0003": True})
    ensemble = tmp_path / "ensemble.json"
    ensemble.write_text(
        json.dumps(
            {"bodies": {"AAAA0001": {"verdict": "creature"}, "CCCC0003": {"verdict": "unstable"}}}
        )
    )
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"bodies": {"CCCC0003": {"verdict": "not_creature"}}}))
    out = tmp_path / "compare.json"
    summary = rq.compare_verdicts(
        members_path=members,
        assessments=[small, large],
        ensembles=[ensemble],
        prior_ensembles=[prior],
        output_path=out,
    )
    assert summary["verdicts"] == {"004": {"unstable": 1}, "135": {"creature": 1}}
    assert summary["prior_transitions"] == {"not_creature->unstable": 1}
    assert summary["verdicts_by_failed_gates"] == {
        "004/none": {"unstable": 1},
        "135/none": {"creature": 1},
    }
    row = next(r for r in json.loads(out.read_text())["members"] if r["body"] == "CCCC0003")
    assert row["arenas"]["128"]["failed"] == ["long_lived"]


def replay_campaign(root: Path, campaign: str, body: str, arena: int) -> Path:
    d = root / "campaigns" / campaign
    d.mkdir(parents=True)
    (d / "replay-manifest.json").write_text(json.dumps({"sourceCreatureId": body}))
    frames = []
    for step in (400, 800):
        field = np.full(arena * arena, step, dtype="<f2").tobytes()
        frames.append(
            {
                "step": step,
                "width": arena,
                "fieldResolution": arena,
                "fieldF16Base64": base64.b64encode(field).decode(),
            }
        )
    trace = d / "development-trace.jsonl"
    write_jsonl(trace, frames)
    return trace


def test_retire_keeps_terminal_frame_hashes_and_named_bodies(tmp_path):
    root = tmp_path / "n8-torus8"
    stripped = replay_campaign(root, "0000-0001", "AAAA0001", 8)
    kept = replay_campaign(root, "0000-0002", "BBBB0002", 8)
    kept_bytes = kept.read_bytes()
    a = assessment(tmp_path / "a.json", 8, {"AAAA0001": True, "BBBB0002": True})
    summary = rq.retire_trace_fields(
        replay_roots=[root],
        assessments=[a],
        keep_bodies=["BBBB0002"],
        manifest_path=tmp_path / "manifest.json",
        apply=True,
    )
    assert (summary["stripped"], summary["kept"]) == (1, 1)
    assert kept.read_bytes() == kept_bytes
    frames = [json.loads(line) for line in stripped.read_text().splitlines()]
    assert "fieldF16Base64" not in frames[0] and "fieldF16Base64" in frames[1]
    expected = hashlib.sha256(np.full(64, 400, dtype="<f2").tobytes()).hexdigest()
    assert frames[0]["fieldF16Sha256"] == expected


def test_retire_refuses_unassessed_traces(tmp_path):
    root = tmp_path / "n8-torus8"
    replay_campaign(root, "0000-0001", "AAAA0001", 8)
    a = assessment(tmp_path / "a.json", 8, {"BBBB0002": True})
    with pytest.raises(ValueError, match="not covered"):
        rq.retire_trace_fields(
            replay_roots=[root],
            assessments=[a],
            keep_bodies=[],
            manifest_path=tmp_path / "manifest.json",
            apply=False,
        )


def test_trace_frames_match_raw_and_stripped_by_arena_and_body(tmp_path):
    new = [tmp_path / "new" / "n8-torus8", tmp_path / "new" / "n8-torus16"]
    old = [tmp_path / "old" / "003-torus8", tmp_path / "old" / "003-torus16"]
    replay_campaign(new[0], "0004-elite-1-aaaa0001", "AAAA0001", 8)
    replay_campaign(new[1], "0004-elite-1-aaaa0001", "AAAA0001", 16)
    replay_campaign(new[1], "0005-elite-2-bbbb0002", "BBBB0002", 16)
    replay_campaign(old[0], "0000-0001", "AAAA0001", 8)
    changed = replay_campaign(old[1], "0009-elite-1-aaaa0001", "AAAA0001", 16)
    replay_campaign(tmp_path / "old" / "003-wall8", "0009-elite-1-aaaa0001", "AAAA0001", 8)
    a = assessment(tmp_path / "a.json", 8, {"AAAA0001": True})
    rq.retire_trace_fields(
        replay_roots=[old[0]],
        assessments=[a],
        keep_bodies=[],
        manifest_path=tmp_path / "manifest.json",
        apply=True,
    )
    frames = [json.loads(line) for line in changed.read_text().splitlines()]
    frames[1]["centerX"] = 1.0
    write_jsonl(changed, frames)
    summary = rq.compare_trace_frames(
        replay_roots=new, prior_replay_roots=old + [tmp_path / "old" / "003-wall8"]
    )
    assert summary == {
        "shared": 2,
        "identical": 1,
        "differ": [{"arena": "torus16", "body": "aaaa0001", "frames": [2, 2], "first": 1}],
        "only_new": 1,
        "only_prior": 1,
    }
