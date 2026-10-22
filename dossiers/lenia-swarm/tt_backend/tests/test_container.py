from __future__ import annotations

from devtools import container


def test_docker_command_maps_every_card_and_pins_the_n300_mesh() -> None:
    command = container.docker_command(["python3", "-m", "tt_lenia.sfpu.replay"])
    assert command[:7] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--device",
        "/dev/tenstorrent",
    ]
    assert "MESH_DEVICE=N300" in command
    assert container.IMAGE.split("@")[1].startswith("sha256:")
    image = command.index(container.IMAGE)
    assert command[image - 2 : image] == ["-w", "/repo/tt_backend"]
    assert command[image + 1 :] == ["python3", "-m", "tt_lenia.sfpu.replay"]
