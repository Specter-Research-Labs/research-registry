from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import write_json

SOURCE_URL = "https://chakazul.github.io/Lenia/JavaScript/Lenia-LifeForms.js"
QD24_PAPER_ID = "toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity-2024"
QD24_NATIVE_WORLD_SIZE = 192
ZIP_HEADER = "(zip)"
ZIP2_HEADER = "(zip2)"
ZIP_START = 192
B_SIMP = [
    "0",
    "1/12",
    "1/6",
    "1/4",
    "1/3",
    "5/12",
    "1/2",
    "7/12",
    "2/3",
    "3/4",
    "5/6",
    "11/12",
    "1",
    "13/12",
    "7/6",
    "5/4",
    "4/3",
    "17/12",
    "3/2",
    "19/12",
    "5/3",
    "7/4",
    "11/6",
    "23/12",
    "2",
]


@dataclass(frozen=True)
class ChakazulPreset:
    code: str
    name: str
    label: str
    rule: str
    cells: list[list[float]]
    taxonomy: dict[str, str]

    @property
    def family(self) -> str | None:
        family = self.taxonomy.get("family")
        if family is None:
            return None
        match = re.match(r"family:\s+([^ ]+)\s+(.+)", family)
        if match:
            return match.group(2)
        return family.removeprefix("family:").strip()

    def pattern_payload(self) -> dict[str, Any]:
        parsed_rule = parse_rule(self.rule)
        return {
            "source": SOURCE_URL,
            "code": self.code,
            "name": self.name,
            "label": self.label,
            "taxonomy": self.taxonomy,
            "rule": self.rule,
            "parsed_rule": parsed_rule,
            "R": parsed_rule["R"],
            "T": parsed_rule["T"],
            "cells": [self.cells],
            "kernels": qd24_kernels(parsed_rule),
        }


def fetch_source(url: str = SOURCE_URL) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def extract_js_array(source: str, name: str) -> list[Any]:
    match = re.search(rf"\bvar\s+{re.escape(name)}\s*=\s*(\[.*?\]);", source, re.S)
    if match is None:
        raise SystemExit(f"missing {name} array")
    return json.loads(strip_js_comments(match.group(1)))


def strip_js_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.S)


def from_zip_char(char: str) -> int:
    if char == "0":
        return 0
    if char == "1":
        return 100
    return ord(char) - (ZIP_START - 1)


def is_zip_repeat(text: str) -> bool:
    return bool(text) and ord(text[0]) >= ZIP_START


def from_repeat(text: str) -> int:
    if text == "":
        return 1
    if is_zip_repeat(text):
        if len(text) == 1:
            return from_zip_char(text)
        return from_zip_char(text[0]) * 100 + from_zip_char(text[1])
    return int(text)


def unzip_cells(cell_text: str) -> list[list[float]]:
    is_zip1 = cell_text.startswith(ZIP_HEADER)
    is_zip2 = cell_text.startswith(ZIP2_HEADER)
    if not is_zip1 and not is_zip2:
        return [[float(value) for value in row.split(",")] for row in cell_text.split("/")]
    if is_zip1:
        cell_text = cell_text[len(ZIP_HEADER) :]
    if is_zip2:
        cell_text = cell_text[len(ZIP2_HEADER) :]

    rows: list[list[float]] = []
    width = 0
    for row_text in cell_text.split("/"):
        expanded = ""
        for repeat_part in row_text.strip().split("-"):
            row_parts = repeat_part.split(".")
            if len(row_parts) == 1:
                expanded += repeat_part
            else:
                expanded += "0" * from_repeat(row_parts[0]) + row_parts[1]
        row = [round(from_zip_char(char) / 100, 10) for char in expanded]
        rows.append(row)
        width = max(width, len(row))

    for row in rows:
        row.extend([0.0] * (width - len(row)))

    if not is_zip2:
        return rows

    doubled: list[list[float]] = []
    for row in rows:
        expanded_row = [value for value in row for _ in range(2)]
        doubled.append(expanded_row)
        doubled.append(list(expanded_row))
    return doubled


def unsimplified_fraction(text: str | None) -> int:
    if not text:
        return 0
    if text.endswith("/12"):
        return int(text.split("/")[0])
    try:
        return B_SIMP.index(text)
    except ValueError:
        return 0


def parse_rule(rule: str) -> dict[str, Any]:
    fields = dict(part.split("=", 1) for part in rule.split(";") if "=" in part)
    delta_match = re.match(r"([A-Za-z0-9/]+)\(([^)]*)\)\*([0-9.]+)\+?", fields["d"])
    if delta_match is None:
        raise SystemExit(f"unsupported delta rule: {fields['d']}")
    kernel_match = re.match(r"([A-Za-z0-9/]+)(.*)", fields["k"])
    if kernel_match is None:
        raise SystemExit(f"unsupported kernel rule: {fields['k']}")
    kernel_parts = re.findall(r"\(([^)]*)\)", kernel_match.group(2))
    kernel_weights = [
        [unsimplified_fraction(value.strip()) / 12 for value in part.split(",") if value.strip()]
        for part in kernel_parts
    ]
    scale = float(delta_match.group(3))
    return {
        "R": int(fields["R"]),
        "T": round(1 / scale),
        "kernel": fields["k"],
        "kernel_core": kernel_match.group(1),
        "kernel_weights": kernel_weights,
        "growth": fields["d"],
        "growth_function": delta_match.group(1),
        "growth_args": [
            float(value.strip()) for value in delta_match.group(2).split(",") if value.strip()
        ],
        "growth_scale": scale,
    }


def qd24_kernels(parsed_rule: dict[str, Any]) -> list[dict[str, Any]]:
    growth_args = parsed_rule["growth_args"]
    if len(growth_args) != 2:
        raise SystemExit(f"unsupported growth args: {growth_args}")
    kernel_weights = parsed_rule["kernel_weights"]
    b = kernel_weights[0] if kernel_weights and kernel_weights[0] else [1.0]
    return [
        {
            "b": b,
            "c0": 0,
            "c1": 0,
            "h": 1.0,
            "m": growth_args[0],
            "r": 1.0,
            "s": growth_args[1],
        }
    ]


def parse_presets(source: str) -> list[ChakazulPreset]:
    presets: list[ChakazulPreset] = []
    taxonomy: dict[str, str] = {}
    for row in extract_js_array(source, "animalArr"):
        if not isinstance(row, list) or len(row) < 2:
            continue
        code = str(row[0])
        name = str(row[1])
        if code.startswith(">"):
            rank = name.split(":", 1)[0].strip().lower()
            taxonomy = {
                key: value
                for key, value in taxonomy.items()
                if _rank_depth(key) < _rank_depth(rank)
            }
            taxonomy[rank] = name
            continue
        if len(row) < 4 or ";cells=" not in str(row[3]):
            continue
        rule, cell_text = str(row[3]).split(";cells=", 1)
        presets.append(
            ChakazulPreset(
                code=code,
                name=name,
                label=str(row[2]),
                rule=rule,
                cells=unzip_cells(cell_text),
                taxonomy=dict(taxonomy),
            )
        )
    return presets


def _rank_depth(rank: str) -> int:
    return {"class": 1, "order": 2, "family": 3, "subfamily": 4}.get(rank, 99)


def build_manifest(presets: list[ChakazulPreset]) -> dict[str, Any]:
    families: dict[str, int] = {}
    for preset in presets:
        if preset.family is not None:
            families[preset.family] = families.get(preset.family, 0) + 1
    filenames = preset_filenames(presets)
    return {
        "source": SOURCE_URL,
        "preset_count": len(presets),
        "families": dict(sorted(families.items())),
        "presets": [
            {
                "code": preset.code,
                "name": preset.name,
                "family": preset.family,
                "pattern": f"patterns/{filename}",
                "rule": preset.rule,
                "width": len(preset.cells[0]) if preset.cells else 0,
                "height": len(preset.cells),
            }
            for preset, filename in zip(presets, filenames, strict=True)
        ],
    }


def write_preset_library(presets: list[ChakazulPreset], output_dir: Path) -> None:
    patterns_dir = output_dir / "patterns"
    for preset, filename in zip(presets, preset_filenames(presets), strict=True):
        write_json(patterns_dir / filename, preset.pattern_payload())
    write_json(output_dir / "manifest.json", build_manifest(presets))


def write_qd24_config_lanes(
    presets: list[ChakazulPreset],
    output_dir: Path,
    families: set[str] | None = None,
    codes: set[str] | None = None,
    max_pattern_size: int | None = None,
    limit_per_family: int | None = None,
) -> list[Path]:
    written: list[Path] = []
    counts: dict[str, int] = {}
    for preset, filename in zip(presets, preset_filenames(presets), strict=True):
        family = preset.family or "unclassified"
        if families is not None and family not in families:
            continue
        if codes is not None and preset.code not in codes:
            continue
        width = len(preset.cells[0]) if preset.cells else 0
        height = len(preset.cells)
        if max_pattern_size is not None and max(width, height) > max_pattern_size:
            continue
        if limit_per_family is not None and counts.get(family, 0) >= limit_per_family:
            continue
        counts[family] = counts.get(family, 0) + 1

        pattern_id = Path(filename).stem
        config_dir = output_dir / safe_filename(family) / pattern_id
        write_json(config_dir / "patterns" / f"{pattern_id}.json", preset.pattern_payload())
        write_json(config_dir / "base.json", qd24_base_config(pattern_id, width, height))
        write_json(config_dir / "me.json", qd24_map_elites_smoke_config())
        write_json(config_dir / "aurora.json", qd24_aurora_smoke_config())
        written.append(config_dir)
    return written


def write_qd24_additive_native_parity_configs(
    presets: list[ChakazulPreset],
    output_dir: Path,
    families: set[str] | None = None,
    codes: set[str] | None = None,
    max_pattern_size: int | None = None,
    limit_per_family: int | None = None,
) -> list[Path]:
    written: list[Path] = []
    counts: dict[str, int] = {}
    for preset, filename in zip(presets, preset_filenames(presets), strict=True):
        family = preset.family or "unclassified"
        if families is not None and family not in families:
            continue
        if codes is not None and preset.code not in codes:
            continue
        width = len(preset.cells[0]) if preset.cells else 0
        height = len(preset.cells)
        if max_pattern_size is not None and max(width, height) > max_pattern_size:
            continue
        if limit_per_family is not None and counts.get(family, 0) >= limit_per_family:
            continue
        counts[family] = counts.get(family, 0) + 1

        pattern_id = Path(filename).stem
        config_path = (
            output_dir
            / f"{safe_filename(family)}-{pattern_id}-qd24-additive-native-parity-mlx.json"
        )
        write_json(config_path, qd24_additive_native_parity_config(preset))
        written.append(config_path)
    return written


def qd24_base_config(pattern_id: str, width: int, height: int) -> dict[str, Any]:
    n_cells_size = max(32, width, height)
    world_size = max(QD24_NATIVE_WORLD_SIZE, n_cells_size * 2)
    return {
        "paper": QD24_PAPER_ID,
        "pattern_id": pattern_id,
        "world_size": world_size,
        "world_scale": 1,
        "n_step": 600,
        "n_params_size": 3,
        "n_cells_size": n_cells_size,
    }


def qd24_additive_native_parity_config(preset: ChakazulPreset) -> dict[str, Any]:
    """Build an MLX additive config from native Chakazul/QD24 cells without screen scaling."""
    payload = preset.pattern_payload()
    kernels = payload["kernels"]
    kernel_core = payload["parsed_rule"]["kernel_core"]
    growth_function = payload["parsed_rule"]["growth_function"]
    kernel_profile = {
        "bump4": "qd24_bump4_v1",
        "quad4": "qd24_quad4_v1",
        "stpz1/4": "qd24_step_v1",
        "life": "qd24_life_v1",
    }.get(kernel_core)
    if kernel_profile is None:
        raise SystemExit(f"unsupported QD24 native kernel core: {kernel_core}")
    growth_profile = {
        "gaus": "gaussian",
        "quad4": "quad4",
        "stpz": "stpz",
    }.get(growth_function)
    if growth_profile is None:
        raise SystemExit(f"unsupported QD24 native growth function: {growth_function}")
    width = len(preset.cells[0]) if preset.cells else 0
    height = len(preset.cells)
    native_world_size = max(QD24_NATIVE_WORLD_SIZE, width, height)
    return {
        "backend": "mlx",
        "profile": "experimental",
        "grid": {
            "sx": native_world_size,
            "sy": native_world_size,
        },
        "channels": 1,
        "implementation": {
            "mode": "qd24_additive_v1",
            "kernel_profile": kernel_profile,
            "growth_profile": growth_profile,
        },
        "flow": {
            "dt": 1 / payload["T"],
            "n": 2,
            "theta_A": 2,
        },
        "reintegration": {
            "border": "torus",
            "dd": 5,
            "sigma": 0.65,
        },
        "params": {
            "mode": "explicit",
            "seed": 0,
            "ranges": None,
            "r": [kernel["r"] for kernel in kernels],
            "b": [kernel["b"] for kernel in kernels],
            "w": [[0.0 for _ in kernel["b"]] for kernel in kernels],
            "a": [[0.0 for _ in kernel["b"]] for kernel in kernels],
            "m": [kernel["m"] for kernel in kernels],
            "s": [kernel["s"] for kernel in kernels],
            "h": [kernel["h"] for kernel in kernels],
            "R": payload["R"],
        },
        "connectivity": [[1 for _ in range(1)] for _ in kernels],
        "init": {
            "seed": 0,
            "a_uniform": {
                "low": 0,
                "high": 0,
            },
            "p_uniform": None,
            "patches": [],
            "state_patch": qd24_state_patch(
                preset.cells,
                center=[native_world_size // 2, native_world_size // 2],
            ),
        },
        "run": {
            "steps": 1600,
        },
        "parameter_embedding": {
            "enabled": False,
            "mix": "avg",
            "mix_seed": None,
        },
        "interventions": [],
        "provenance": {
            "source": SOURCE_URL,
            "family": preset.family,
            "pattern_id": preset.code,
            "species": preset.name,
            "section2_family_lane": True,
            "runtime_probe": "qd24_additive_v1_native_parity",
            "native_world_size": native_world_size,
            "native_world_scale": 1,
            "native_R": payload["R"],
            "native_T": payload["T"],
            "native_kernel_core": kernel_core,
            "native_kernel_profile": kernel_profile,
            "native_growth_function": growth_function,
            "native_growth_profile": growth_profile,
            "native_patch_width": width,
            "native_patch_height": height,
            "parity_note": "Uses native Chakazul cells directly; no control-screen state_patch_scale and no R scaling; world enlarges only when the native patch exceeds 192.",
        },
    }


def qd24_state_patch(cells: list[list[float]], center: list[int]) -> dict[str, Any]:
    row_count = len(cells)
    column_count = len(cells[0]) if cells else 0
    packed = b"".join(struct.pack("<f", value) for row in cells for value in row)
    return {
        "width": row_count,
        "height": column_count,
        "channels": 1,
        "center": center,
        "encoding": "f32le",
        "data": base64.b64encode(packed).decode("ascii"),
    }


def qd24_map_elites_smoke_config() -> dict[str, Any]:
    return {
        "algorithm": "me",
        "phenotype_size": 64,
        "center_phenotype": True,
        "record_phenotype": True,
        "n_generations": 2,
        "log_interval": 1,
        "batch_size": 32,
        "repertoire_size": 256,
        "n_init_cvt_samples": 4096,
        "iso_sigma": 0.004,
        "line_sigma": 0.04,
        "fitness": "pos_organism_score_avg",
        "descriptor": [
            "pos_linear_velocity_avg",
            "pos_largest_component_anisotropy_avg",
            "pos_significant_component_count_avg",
            "pos_moment_density_avg",
        ],
        "descriptor_min": [0.0, 0.0, 1.0, 0.0],
        "descriptor_max": [0.5, 1.0, 12.0, 0.35],
        "n_keep": 32,
    }


def qd24_aurora_smoke_config() -> dict[str, Any]:
    return {
        "algorithm": "aurora",
        "phenotype_size": 64,
        "center_phenotype": True,
        "record_phenotype": True,
        "n_generations": 2,
        "log_interval": 1,
        "batch_size": 32,
        "repertoire_size": 256,
        "iso_sigma": 0.004,
        "line_sigma": 0.04,
        "fitness": "pos_linear_velocity_avg",
        "secondary_fitness": None,
        "secondary_fitness_weight": 1.0,
        "n_keep": 32,
        "features": 8,
        "hidden_size": 32,
        "train_ratio": 8,
        "lr_init_value": 0.001,
        "ae_batch_size": 16,
        "n_keep_ae": 64,
        "use_data_augmentation": True,
    }


def preset_filenames(presets: list[ChakazulPreset]) -> list[str]:
    filename_counts: dict[str, int] = {}
    filenames: list[str] = []
    for preset in presets:
        base_name = safe_filename(preset.code)
        filename_counts[base_name] = filename_counts.get(base_name, 0) + 1
        suffix = "" if filename_counts[base_name] == 1 else f"-{filename_counts[base_name]:02d}"
        filenames.append(f"{base_name}{suffix}.json")
    return filenames


def safe_filename(code: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", code.strip("~?"))
    return normalized.strip("-") or "unnamed"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Chakazul Lenia preset taxonomy and cells")
    parser.add_argument("--input", type=Path, help="Local Lenia-LifeForms.js source")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--qd-config-dir", type=Path)
    parser.add_argument("--qd-family", action="append", dest="qd_families")
    parser.add_argument("--qd-code", action="append", dest="qd_codes")
    parser.add_argument("--qd-max-pattern-size", type=int, default=96)
    parser.add_argument("--qd-limit-per-family", type=int)
    parser.add_argument("--qd-additive-native-parity-dir", type=Path)
    args = parser.parse_args()

    source = args.input.read_text(encoding="utf-8") if args.input else fetch_source()
    presets = parse_presets(source)
    write_preset_library(presets, args.output_dir)
    if args.qd_config_dir is not None:
        qd_dirs = write_qd24_config_lanes(
            presets,
            args.qd_config_dir,
            families=set(args.qd_families) if args.qd_families else None,
            codes=set(args.qd_codes) if args.qd_codes else None,
            max_pattern_size=args.qd_max_pattern_size,
            limit_per_family=args.qd_limit_per_family,
        )
        print(f"wrote {len(qd_dirs)} qd-2024 smoke config dirs to {args.qd_config_dir}")
    if args.qd_additive_native_parity_dir is not None:
        additive_configs = write_qd24_additive_native_parity_configs(
            presets,
            args.qd_additive_native_parity_dir,
            families=set(args.qd_families) if args.qd_families else None,
            codes=set(args.qd_codes) if args.qd_codes else None,
            max_pattern_size=args.qd_max_pattern_size,
            limit_per_family=args.qd_limit_per_family,
        )
        print(
            "wrote "
            f"{len(additive_configs)} qd24 additive native-parity configs to "
            f"{args.qd_additive_native_parity_dir}"
        )
    print(f"wrote {len(presets)} presets to {args.output_dir}")


if __name__ == "__main__":
    main()
