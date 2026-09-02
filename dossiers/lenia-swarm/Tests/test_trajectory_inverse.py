import base64
import json

import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler.trajectory_inverse import (
    DEFAULT_INITIAL_PARAMS,
    blind_runtime_config,
    image_state_patch,
    prepare_experiment,
    prepare_refinement_experiment,
)


def native_config() -> dict:
    return {
        "grid": {"sx": 8, "sy": 8},
        "implementation": {"mode": "qd24_additive_v1"},
        "init": {"state_patch": {"data": "target cells"}},
        "params": {
            "mode": "explicit",
            "r": [1.0],
            "b": [[1.0]],
            "w": [[0.0]],
            "a": [[0.0]],
            "m": [0.15],
            "s": [0.017],
            "h": [1.0],
            "R": 13.0,
        },
        "provenance": {"native_R": 13, "species": "secret target"},
    }


def test_blinded_config_preserves_initial_state_but_removes_target_parameters() -> None:
    source = native_config()
    blinded = blind_runtime_config(source)

    assert blinded["init"] == source["init"]
    assert blinded["params"]["r"] == [1.0]
    assert blinded["params"]["m"] == [DEFAULT_INITIAL_PARAMS["m"]]
    assert blinded["params"]["s"] == [DEFAULT_INITIAL_PARAMS["s"]]
    assert blinded["params"]["R"] == DEFAULT_INITIAL_PARAMS["R"]
    assert "native_R" not in blinded["provenance"]
    assert "species" not in blinded["provenance"]
    assert source["params"]["R"] == 13.0


def test_image_state_patch_encodes_normalized_row_major_float32(tmp_path) -> None:
    pixels = np.array([[0, 255], [64, 128]], dtype=np.uint8)
    image_path = tmp_path / "frame.png"
    Image.fromarray(pixels).save(image_path)

    patch = image_state_patch(image_path, (4, 4))
    decoded = np.frombuffer(base64.b64decode(patch["data"]), dtype="<f4")

    assert patch["center"] == [4, 4]
    assert (patch["width"], patch["height"], patch["channels"]) == (2, 2, 1)
    np.testing.assert_allclose(decoded, pixels.ravel(order="C") / 255.0)


def test_prepare_experiment_separates_still_and_temporal_evidence(tmp_path) -> None:
    source_path = tmp_path / "native.json"
    source_path.write_text(json.dumps(native_config()))
    frames = tmp_path / "frames"
    frames.mkdir()
    for step, value in [(100, 32), (200, 96), (300, 160)]:
        Image.new("L", (8, 8), value).save(frames / f"frame_{step:06d}.png")

    paths = prepare_experiment(
        source_config=source_path,
        frames_dir=frames,
        output_dir=tmp_path / "experiment",
        observed_steps=[100, 200, 300],
        generations=2,
        population=4,
        sigma=1.0,
        learning_rate=0.05,
    )
    still = json.loads(paths["still"].read_text())
    trajectory = json.loads(paths["trajectory"].read_text())

    assert still["fitness"]["template_sequence_steps"] == [300]
    assert still["sigma"] == 1.0
    assert still["learning_rate"] == 0.05
    assert "template_sequence_delta_reward" not in still["fitness"]
    assert trajectory["fitness"]["template_sequence_steps"] == [100, 200, 300]
    assert trajectory["fitness"]["template_sequence_delta_reward"] > 0
    assert trajectory["fitness"]["template_sequence_signed_delta_reward"] > 0
    assert len(trajectory["fitness"]["template_sequence_state_patches"]) == 3


def test_prepare_refinement_centers_a_narrow_stage_on_the_coarse_winner(tmp_path) -> None:
    source_path = tmp_path / "native.json"
    source_path.write_text(json.dumps(native_config()))
    winner_path = tmp_path / "best.json"
    winner_path.write_text(
        json.dumps(
            {
                "fitness": 0.75,
                "params": {"r": [1.0], "m": [0.149], "s": [0.019], "R": 13.1},
            }
        )
    )
    coarse_es_path = tmp_path / "coarse-es.json"
    coarse_es_path.write_text(
        json.dumps({"population": 96, "fitness": {"objective": "template_sequence"}})
    )

    paths = prepare_refinement_experiment(
        source_config=source_path,
        coarse_best=winner_path,
        coarse_es=coarse_es_path,
        output_dir=tmp_path / "refinement",
    )
    base = json.loads(paths["base"].read_text())
    es = json.loads(paths["es"].read_text())
    manifest = json.loads(paths["manifest"].read_text())

    assert base["params"]["m"] == [0.149]
    assert base["params"]["s"] == [0.019]
    assert base["params"]["R"] == 13.1
    assert es["population"] == 96
    assert es["generations"] == 12
    assert es["sigma"] == 0.15
    assert es["output_dir"].endswith("refinement/refine-run")
    assert manifest["coarse_fitness"] == 0.75
