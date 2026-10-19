from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from lenia_swarm_analysis.observer import conditional, measure, transfer
from lenia_swarm_analysis.observer.measure import EVAL_STREAM, Config, split, stream
from lenia_swarm_analysis.observer.states import Quantizer, load_states, patches, sample_transitions

SIDE = 24
CHANNELS = 2
FRAMES = 13

CONFIG = {
    "seed": 3,
    "mass_edges": [0.05, 0.3, 0.6],
    "frame_order": "real",
    "stride": 1,
    "lag": 1,
    "eval_every": 4,
    "n_train": 64,
    "n_eval": 32,
    "batch": 16,
    "lr": 1e-2,
    "tail": 0.25,
    "group": 2,
    "observers": [
        {"name": "lin_r1", "radius": 1, "hidden": 0, "view": "sum"},
        {"name": "mlp_r2", "radius": 2, "hidden": 8, "view": "channels"},
    ],
}


def blob_frames(velocity: tuple[int, int]) -> np.ndarray:
    """A two-channel blob translating across the torus, crossing its edge."""
    yy, xx = np.mgrid[:SIDE, :SIDE]
    frames = []
    for t in range(FRAMES):
        cy, cx = (2 + velocity[0] * t) % SIDE, (2 + velocity[1] * t) % SIDE
        dy = np.minimum(np.abs(yy - cy), SIDE - np.abs(yy - cy))
        dx = np.minimum(np.abs(xx - cx), SIDE - np.abs(xx - cx))
        blob = np.exp(-(dy**2 + dx**2) / 6.0)
        frames.append(np.stack([0.7 * blob, 0.4 * blob], -1))
    return np.asarray(frames, np.float32)


def write_campaign(root: Path, name: str, values: np.ndarray) -> Path:
    campaign = root / "campaigns" / name
    campaign.mkdir(parents=True)
    values.astype("<f4").tofile(campaign / "development-state.f32")
    rows = [{"step": 10 * t, "stateSha256": hashlib.sha256(frame.tobytes()).hexdigest()}
            for t, frame in enumerate(values)]
    (campaign / "development-trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (campaign / "replay-manifest.json").write_text(json.dumps({
        "developmentStatePath": "development-state.f32",
        "developmentStateShape": list(values.shape),
        "developmentStateSteps": [r["step"] for r in rows],
    }))
    return campaign


@pytest.fixture
def replay(tmp_path: Path) -> Path:
    root = tmp_path / "replay"
    for name, velocity in (("a", (1, 0)), ("b", (0, 1)), ("c", (1, 1))):
        write_campaign(root, name, blob_frames(velocity))
    return root


def test_load_states_rejects_a_frame_that_does_not_match_its_hash(replay: Path) -> None:
    campaign = replay / "campaigns" / "a"
    assert load_states(campaign).values.shape == (FRAMES, SIDE, SIDE, CHANNELS)
    values = np.fromfile(campaign / "development-state.f32", dtype="<f4")
    values[-1] += 1.0
    values.tofile(campaign / "development-state.f32")
    with pytest.raises(ValueError, match="does not match its hash"):
        load_states(campaign)


def test_load_states_pairs_frames_with_the_declared_raw_steps(tmp_path: Path) -> None:
    values = blob_frames((1, 0))
    campaign = write_campaign(tmp_path, "subset", values[[0, 3]])
    rows = [{"step": 10 * t, "stateSha256": hashlib.sha256(frame.tobytes()).hexdigest()} for t, frame in enumerate(values)]
    (campaign / "development-trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = json.loads((campaign / "replay-manifest.json").read_text()) | {"developmentStateSteps": [0, 30]}
    (campaign / "replay-manifest.json").write_text(json.dumps(manifest))
    states = load_states(campaign)
    assert states.steps.tolist() == [0, 30]
    np.testing.assert_array_equal(states.values[1], values[3])
    (campaign / "replay-manifest.json").write_text(json.dumps(manifest | {"developmentStateSteps": [0, 20]}))
    with pytest.raises(ValueError, match="does not match its hash"):
        load_states(campaign)


def test_patches_wrap_the_torus_and_targets_come_from_the_next_frame() -> None:
    values = np.zeros((2, 8, 8, 1), np.float32)
    values[0, 0, 0, 0] = 0.6
    values[1, 0, 7, 0] = 0.9
    quantizer = Quantizer((0.25, 0.5, 0.75))
    stream = sample_transitions(values, np.array([0]), lag=1, n=256, quantizer=quantizer,
                                rng=np.random.default_rng(0))
    gathered = patches(stream.frames[None], stream.cells[None], 1)[0]
    tenths = {tuple((p[..., 0] * 10).round().int().ravel().tolist()): int(t)
              for p, t in zip(gathered, stream.target, strict=True)}
    assert tenths[(0, 0, 0, 0, 0, 6, 0, 0, 0)] == 3
    assert tenths[(0, 0, 0, 0, 6, 0, 0, 0, 0)] == 0


def test_shuffled_frame_order_permutes_train_and_held_out_streams_identically(replay: Path) -> None:
    states = load_states(replay / "campaigns" / "a")
    config = Config.from_dict({**CONFIG, "frame_order": "shuffled"})
    values, _, held_out = split(states, config)
    again, _, _ = split(states, config)
    assert np.array_equal(values, again)
    assert not np.array_equal(values, states.values)
    assert held_out.sum() == (FRAMES - 1) // config.eval_every
    assert stream(states, config, EVAL_STREAM).target.shape == (config.n_eval,)


def test_sources_follow_stride_and_leave_room_for_the_lag(replay: Path) -> None:
    states = load_states(replay / "campaigns" / "a")
    config = Config.from_dict({**CONFIG, "stride": 3, "lag": 2})
    _, sources, held_out = split(states, config)
    assert sources.tolist() == [0, 3, 6, 9]
    assert sources[held_out].tolist() == [9]


def test_measure_transfer_conditional(replay: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG))
    out = tmp_path / "measure"
    assert measure.main(["--replay", str(replay), "--config", str(config_path), "--out", str(out),
                         "--device", "cpu"]) == 0

    rows = [json.loads(line) for line in (out / "creatures.jsonl").read_text().splitlines()]
    assert [r["campaign"] for r in rows] == ["a", "b", "c"]
    assert all(np.isfinite(r[o][k]) for r in rows for o in ("lin_r1", "mlp_r2") for k in ("S", "H"))
    assert np.load(out / "eval_x.npy").shape == (3, CONFIG["n_eval"], 5, 5, CHANNELS)

    assert transfer.main(["--measure", str(out), "--observer", "mlp_r2", "--device", "cpu"]) == 0
    matrices = np.load(out / "transfer_mlp_r2.npz")
    assert matrices["L"].shape == matrices["L_dyn"].shape == (3, 3)
    assert (matrices["L_dyn"] <= matrices["L"] + 1e-4).all()

    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text('{"source": "a", "target": "b"}\n{"source": "c", "target": "c"}\n')
    assert conditional.main(["--measure", str(out), "--observer", "mlp_r2", "--pairs", str(pairs),
                             "--device", "cpu"]) == 0
    result = [json.loads(line) for line in
              (out / "conditional_mlp_r2_pairs.jsonl").read_text().splitlines()]
    assert [(r["source"], r["target"]) for r in result] == [("a", "b"), ("c", "c")]
    assert all(r["saving"] == pytest.approx(r["scratch"] - r["codelength"]) for r in result)

    with pytest.raises(FileExistsError):
        transfer.main(["--measure", str(out), "--observer", "mlp_r2", "--device", "cpu"])
