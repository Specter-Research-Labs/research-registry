from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

from lenia_swarm_analysis.chakazul_presets import (
    build_manifest,
    parse_presets,
    parse_rule,
    qd24_additive_native_parity_config,
    qd24_kernels,
    unzip_cells,
    write_preset_library,
    write_qd24_additive_native_parity_configs,
    write_qd24_config_lanes,
)


def test_unzip_cells_decodes_chakazul_repeat_and_values() -> None:
    cells = unzip_cells("(zip)Á.1À/2.Ā")

    assert cells == [
        [0.0, 0.0, 1.0, 0.01],
        [0.0, 0.0, 0.65, 0.0],
    ]


def test_parse_rule_extracts_classical_lenia_knobs() -> None:
    rule = "R=27;k=quad4(1,2/3,1/3);d=gaus(0.25,0.033)*0.1"

    parsed = parse_rule(rule)

    assert parsed["R"] == 27
    assert parsed["T"] == 10
    assert parsed["kernel_core"] == "quad4"
    assert parsed["kernel_weights"] == [[1.0, 2 / 3, 1 / 3]]
    assert parsed["growth_function"] == "gaus"
    assert parsed["growth_args"] == [0.25, 0.033]
    assert parsed["growth_scale"] == 0.1
    assert qd24_kernels(parsed) == [
        {
            "b": [1.0, 2 / 3, 1 / 3],
            "c0": 0,
            "c1": 0,
            "h": 1.0,
            "m": 0.25,
            "r": 1.0,
            "s": 0.033,
        }
    ]


def test_qd24_kernels_default_empty_shell_to_single_weight() -> None:
    parsed = parse_rule("R=13;k=quad4();d=quad4(0.11,0.011)*0.1")

    assert parsed["kernel_weights"] == [[]]
    assert qd24_kernels(parsed)[0]["b"] == [1.0]


def test_parse_presets_tracks_taxonomy_and_writes_patterns(tmp_path: Path) -> None:
    source = """
const DEFAULT_ANIMAL = "2G";
var animalArr = [
[">1", "class: Mesokernel", "中核綱"],
[">2", "order: Geminiformes", "雙子目"],
[">3", "family: G Geminidae", "雙子科"],
["2G", "Aerogeminium volitans", "飛雙子虫",
 "R=18;k=quad4(1,11/12);d=quad4(0.32,0.051)*0.1;cells=(zip)1/0À"],
[">3", "family: K Kronidae", "冠形科"],
["K4", "Kronium", "冠虫", "R=21;k=bump4;d=gaus(0.25,0.03)*0.1;cells=(zip)À1"]
];
var catalogueArr = [];
"""

    presets = parse_presets(source)
    manifest = build_manifest(presets)

    assert [preset.code for preset in presets] == ["2G", "K4"]
    assert presets[0].family == "Geminidae"
    assert presets[1].taxonomy["family"] == "family: K Kronidae"
    assert manifest["families"] == {"Geminidae": 1, "Kronidae": 1}

    write_preset_library(presets, tmp_path)
    pattern = json.loads((tmp_path / "patterns" / "2G.json").read_text(encoding="utf-8"))
    assert pattern["name"] == "Aerogeminium volitans"
    assert pattern["R"] == 18
    assert pattern["cells"] == [[[1.0, 0.0], [0.0, 0.01]]]
    assert pattern["kernels"][0]["b"] == [1.0, 11 / 12]

    qd_dirs = write_qd24_config_lanes(
        presets,
        tmp_path / "qd",
        families={"Kronidae"},
        limit_per_family=1,
    )
    assert qd_dirs == [tmp_path / "qd" / "Kronidae" / "K4"]
    qd_pattern = json.loads(
        (tmp_path / "qd" / "Kronidae" / "K4" / "patterns" / "K4.json").read_text(
            encoding="utf-8"
        )
    )
    assert qd_pattern["kernels"][0]["b"] == [1.0]
    qd_base = json.loads(
        (tmp_path / "qd" / "Kronidae" / "K4" / "base.json").read_text(encoding="utf-8")
    )
    assert qd_base["pattern_id"] == "K4"
    assert (
        write_qd24_config_lanes(
            presets,
            tmp_path / "qd-filtered",
            families={"Kronidae"},
            codes={"2G"},
        )
        == []
    )


def test_qd24_additive_native_parity_config_does_not_screen_scale_cells() -> None:
    source = """
var animalArr = [
[">1", "class: Mesokernel", "中核綱"],
[">2", "order: Orbiformes", "軌道目"],
[">3", "family: O Orbidae", "軌道科"],
["O2", "Orbium unicaudatus ignis", "單尾軌道虫",
 "R=13;k=bump4(1);d=gaus(0.119,0.0148)*0.1;cells=(zip)01/1À"]
];
var catalogueArr = [];
"""

    preset = parse_presets(source)[0]
    config = qd24_additive_native_parity_config(preset)

    assert config["grid"] == {"sx": 192, "sy": 192}
    assert config["implementation"]["kernel_profile"] == "qd24_bump4_v1"
    assert config["implementation"]["growth_profile"] == "gaussian"
    assert config["flow"]["dt"] == 0.1
    assert config["flow"]["n"] == 2
    assert config["flow"]["theta_A"] == 2
    assert config["reintegration"]["border"] == "torus"
    assert config["params"]["R"] == 13
    assert config["params"]["r"] == [1.0]
    assert config["params"]["h"] == [1.0]
    assert config["params"]["w"] == [[0.0]]
    assert config["params"]["a"] == [[0.0]]
    assert config["connectivity"] == [[1]]
    assert config["init"]["state_patch"]["width"] == 2
    assert config["init"]["state_patch"]["height"] == 2
    assert config["init"]["state_patch"]["center"] == [96, 96]
    assert config["provenance"]["native_world_scale"] == 1
    assert config["provenance"]["native_kernel_core"] == "bump4"
    assert config["provenance"]["native_kernel_profile"] == "qd24_bump4_v1"
    assert config["provenance"]["native_growth_function"] == "gaus"
    assert config["provenance"]["native_growth_profile"] == "gaussian"
    assert "state_patch_scale" not in config["provenance"]

    written = write_qd24_additive_native_parity_configs(
        [preset],
        Path("/tmp") / "unused",
        families={"Geminidae"},
    )
    assert written == []


def test_qd24_state_patch_uses_runtime_row_column_extents_for_rectangular_cells() -> None:
    source = """
var animalArr = [
[">1", "class: Mesokernel", "中核綱"],
[">2", "order: Orbiformes", "軌道目"],
[">3", "family: O Orbidae", "軌道科"],
["O2", "Orbium rectangularis", "矩形軌道虫",
 "R=13;k=bump4(1);d=gaus(0.119,0.0148)*0.1;cells=0,1,2/3,4,5"]
];
var catalogueArr = [];
"""

    preset = parse_presets(source)[0]
    config = qd24_additive_native_parity_config(preset)
    state_patch = config["init"]["state_patch"]

    assert state_patch["width"] == 2
    assert state_patch["height"] == 3
    assert config["provenance"]["native_patch_width"] == 3
    assert config["provenance"]["native_patch_height"] == 2
    raw = base64.b64decode(state_patch["data"])
    assert list(struct.unpack("<" + "f" * (len(raw) // 4), raw)) == [
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    ]


def test_qd24_additive_native_parity_config_enlarges_world_for_large_native_patch() -> None:
    wide_row = ",".join(["1"] * 214)
    source = f"""
var animalArr = [
[">1", "class: Mesokernel", "中核綱"],
[">2", "order: Orbiformes", "軌道目"],
[">3", "family: O Orbidae", "軌道科"],
["O9", "Orbium latus", "寬軌道虫",
 "R=13;k=bump4(1);d=gaus(0.119,0.0148)*0.1;cells={wide_row}/{wide_row}"]
];
var catalogueArr = [];
"""

    preset = parse_presets(source)[0]
    config = qd24_additive_native_parity_config(preset)
    state_patch = config["init"]["state_patch"]

    assert config["grid"] == {"sx": 214, "sy": 214}
    assert state_patch["width"] == 2
    assert state_patch["height"] == 214
    assert state_patch["center"] == [107, 107]
    assert config["provenance"]["native_world_size"] == 214
    assert config["provenance"]["native_patch_width"] == 214
    assert config["provenance"]["native_patch_height"] == 2


def test_qd24_additive_native_parity_config_preserves_step_kernel_and_growth() -> None:
    source = """
var animalArr = [
[">1", "class: Exokernel", "外核綱"],
[">2", "order: Scutiformes", "盾形目"],
[">3", "family: S Scutidae", "盾形科"],
["~S2", "Discutium pachus", "乙盾虫(厚)",
 "R=13;k=stpz1/4;d=stpz(0.545,0.186)*0.1;cells=(zip)1/0À"]
];
var catalogueArr = [];
"""

    preset = parse_presets(source)[0]
    config = qd24_additive_native_parity_config(preset)

    assert config["implementation"]["kernel_profile"] == "qd24_step_v1"
    assert config["implementation"]["growth_profile"] == "stpz"
    assert config["params"]["m"] == [0.545]
    assert config["params"]["s"] == [0.186]
    assert config["provenance"]["native_kernel_core"] == "stpz1/4"
    assert config["provenance"]["native_growth_function"] == "stpz"


def test_qd24_additive_native_parity_config_preserves_life_kernel() -> None:
    source = """
var animalArr = [
[">1", "class: Exokernel", "外核綱"],
[">2", "order: Foliformes", "葉形目"],
[">3", "family: F Folidae", "葉形科"],
["~", "Glider", "滑翔機",
 "R=2;k=life;d=stpz(0.35,0.07)*1;cells=0,1,0/0,0,1/1,1,1"]
];
var catalogueArr = [];
"""

    preset = parse_presets(source)[0]
    config = qd24_additive_native_parity_config(preset)

    assert config["implementation"]["kernel_profile"] == "qd24_life_v1"
    assert config["implementation"]["growth_profile"] == "stpz"
    assert config["flow"]["dt"] == 1.0
    assert config["params"]["R"] == 2
    assert config["params"]["r"] == [1.0]
    assert config["params"]["b"] == [[1.0]]
    assert config["params"]["m"] == [0.35]
    assert config["params"]["s"] == [0.07]
    assert config["provenance"]["native_kernel_core"] == "life"
    assert config["provenance"]["native_kernel_profile"] == "qd24_life_v1"
    assert config["provenance"]["native_growth_function"] == "stpz"
