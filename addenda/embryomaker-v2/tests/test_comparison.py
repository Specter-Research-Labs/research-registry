import json
from pathlib import Path

from typer.testing import CliRunner

from embryomaker_v2.cli import app
from embryomaker_v2.comparison import (
    compare_cell_sorting_summaries,
    compare_cell_sorting_trajectory,
    compare_invagination_geometry,
    compare_invagination_summaries,
    parse_v2_cell_sorting_summary,
    parse_v2_invagination_summary,
)
from embryomaker_v2.legacy_snapshot import (
    load_legacy_snapshot_series,
    parse_legacy_snapshot,
    summarize_legacy_epithelial_snapshot,
    summarize_legacy_snapshot,
)

runner = CliRunner()


def _node_row(
    *,
    x: float,
    y: float,
    z: float,
    eqd: float,
    add: float,
    orix: float,
    oriy: float,
    oriz: float,
    cod: float = 0.0,
    grd: float = 0.0,
    pld: float = 0.0,
    vod: float = 0.0,
    pla: float = 0.0,
    kvol: float = 0.0,
    tipus: int,
    icel: int,
    altre: int = 0,
) -> str:
    values = [0.0] * 35
    values[0] = x
    values[1] = y
    values[2] = z
    values[4] = eqd
    values[5] = add
    values[16] = orix
    values[17] = oriy
    values[18] = oriz
    values[20] = cod
    values[21] = grd
    values[22] = pld
    values[23] = vod
    values[26] = pla
    values[27] = kvol
    values[28] = float(tipus)
    values[29] = float(icel)
    values[30] = float(altre)
    return " ".join(f"{value:.16E}" for value in values)


def _sample_snapshot_text(*, getot: int = 10) -> str:
    return "\n".join(
        [
            "THIS FILE WAS WRITTEN IN THE FORMAT OF THE TEST VERSION",
            "demo-run",
            "35 number of node parameters",
            "5 number of global variables",
            "",
            "30 functions",
            "",
            "0 unused",
            "",
            "parameters",
            "",
            f" 1 {float(getot):.16E} getot",
            "10 2.0000000000000000E+00 nd",
            "13 1.5000000000000000E+00 rtime",
            "18 2.0000000000000000E+00 ncels",
            "19 2.0000000000000000E+00 ng",
            "",
            "G matrix: gene expression",
            "",
            "node  gene 1                 gene 2    etc...",
            "1 1.0000000000000000E+00 0.0000000000000000E+00",
            "2 0.0000000000000000E+00 1.0000000000000000E+00",
            "",
            "node properties",
            "",
            "x y z ...",
            _node_row(
                x=0.0,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.5,
                orix=0.0,
                oriy=0.0,
                oriz=0.0,
                tipus=3,
                icel=1,
            ),
            _node_row(
                x=0.5,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.5,
                orix=0.5,
                oriy=0.0,
                oriz=0.0,
                tipus=3,
                icel=2,
            ),
            "",
            "node properties at time 0 (nodeo)",
            "",
            "x y z ...",
            _node_row(
                x=0.0,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.5,
                orix=0.0,
                oriy=0.0,
                oriz=0.0,
                tipus=3,
                icel=1,
            ),
            _node_row(
                x=0.5,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.5,
                orix=0.5,
                oriy=0.0,
                oriz=0.0,
                tipus=3,
                icel=2,
            ),
            "",
            "random seed at the first iteration",
            "",
            "      -11111      -11111      -11111      -11111"
            "      -11111      -11111      -11111      -11111",
            "",
            "random seed at this iteration",
            "",
            " 1 2 3 4 5 6 7 8",
            "",
        ]
    )


def _sample_epithelial_snapshot_text(
    *,
    getot: int = 0,
    rtime: float = 0.0,
    x_shift: float = 0.0,
) -> str:
    return "\n".join(
        [
            "THIS FILE WAS WRITTEN IN THE FORMAT OF THE TEST VERSION",
            "epi-run",
            "35 number of node parameters",
            "5 number of global variables",
            "",
            "30 functions",
            "",
            "0 unused",
            "",
            "parameters",
            "",
            f" 1 {float(getot):.16E} getot",
            "10 4.0000000000000000E+00 nd",
            f"13 {rtime:.16E} rtime",
            "18 2.0000000000000000E+00 ncels",
            "19 2.0000000000000000E+00 ng",
            "",
            "G matrix: gene expression",
            "",
            "node  gene 1                 gene 2    etc...",
            "1 0.0000000000000000E+00 1.0000000000000000E+00",
            "2 1.0000000000000000E+00 0.0000000000000000E+00",
            "3 0.0000000000000000E+00 1.0000000000000000E+00",
            "4 1.0000000000000000E+00 0.0000000000000000E+00",
            "",
            "node properties",
            "",
            "x y z ...",
            _node_row(
                x=0.0 + x_shift,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0 + x_shift,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=1,
                altre=2,
            ),
            _node_row(
                x=0.0 + x_shift,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0 + x_shift,
                oriy=0.2,
                oriz=0.0,
                grd=0.25,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=1,
                altre=1,
            ),
            _node_row(
                x=1.0 + x_shift,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0 + x_shift,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=2,
                altre=4,
            ),
            _node_row(
                x=1.0 + x_shift,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0 + x_shift,
                oriy=0.2,
                oriz=0.0,
                grd=0.25,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=2,
                altre=3,
            ),
            "",
            "node properties at time 0 (nodeo)",
            "",
            "x y z ...",
            _node_row(
                x=0.0 + x_shift,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0 + x_shift,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=1,
                altre=2,
            ),
            _node_row(
                x=0.0 + x_shift,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0 + x_shift,
                oriy=0.2,
                oriz=0.0,
                grd=0.25,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=1,
                altre=1,
            ),
            _node_row(
                x=1.0 + x_shift,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0 + x_shift,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=2,
                altre=4,
            ),
            _node_row(
                x=1.0 + x_shift,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0 + x_shift,
                oriy=0.2,
                oriz=0.0,
                grd=0.25,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=2,
                altre=3,
            ),
            "",
            "random seed at the first iteration",
            "",
            "      -11111      -11111      -11111      -11111"
            "      -11111      -11111      -11111      -11111",
            "",
            "random seed at this iteration",
            "",
            " 1 2 3 4 5 6 7 8",
            "",
        ]
    )


_CELL_SORTING_SUMMARY_TAIL = [
    "node_count: 2",
    "cell_count: 2",
    "contact_count: 1",
    "max_distance_from_origin: 0.5",
    "mean_distance_from_origin: 0.25",
    "mean_neighbor_count: 1.0",
    "type1_cell_count: 1",
    "type2_cell_count: 1",
    "total_noise_attempts: 84",
    "total_noise_accepted: 42",
    "total_noise_rejected: 42",
    "total_noise_zero_displacement: 0",
]

_INVAGINATION_BOOTSTRAP_TEXT = "".join(
    [
        "0 0 0 0.25 0.40000000000000002 "
        "0.10000000000000001 0.25 0 0 0 0 2 1 2 0 0 0 0 1\n",
        "0 0.20000000000000001 0 0.25 0.40000000000000002 "
        "0 0.25 0 0 1 1 1 1 1 0 0 0 1 0\n",
        "1 0 0 0.25 0.40000000000000002 "
        "0.10000000000000001 0.25 0 0 0 0 2 2 4 0 0 0 0 1\n",
        "1 0.20000000000000001 0 0.25 0.40000000000000002 "
        "0 0.25 0 0 1 1 1 2 3 0 0 0 1 0\n",
    ]
)

_INVAGINATION_POSITIONS_TEXT = "0.1 0 0\n0.1 0.2 0\n1.1 0 0\n1.1 0.2 0\n"


def _cell_sorting_summary_lines(steps: int | str = 10) -> list[str]:
    return [f"steps: {steps}", *_CELL_SORTING_SUMMARY_TAIL]


def _invagination_summary_lines(*, getot: int = 0, rtime: float = 0.0) -> list[str]:
    return [
        f"getot: {getot}",
        f"rtime: {rtime}",
        "node_count: 4",
        "cell_count: 2",
        "epithelial_node_count: 4",
        "apical_node_count: 2",
        "basal_node_count: 2",
        "paired_epithelial_node_count: 4",
        "epithelial_cell_count: 2",
        "gene1_positive_node_count: 2",
        "gene2_positive_node_count: 2",
        "gene1_positive_cell_count: 2",
        "gene2_positive_cell_count: 2",
        "polarized_expression_cell_count: 2",
        "zero_pla_node_count: 2",
        "zero_kvol_node_count: 2",
        "mean_grd: 0.25",
        "mean_cod: 0.05",
        "mean_pld: 0.0",
        "mean_vod: 0.0",
    ]


def _write_executable(path: Path, body: list[str]) -> Path:
    path.write_text("\n".join(["#!/usr/bin/env python3", *body]) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _print_lines(lines: list[str]) -> list[str]:
    return [f"print({line!r})" for line in lines]


def _write_cell_sorting_executable(
    path: Path,
    *,
    dynamic_steps: bool = False,
    assert_bootstrap_inputs: bool = False,
) -> Path:
    body: list[str] = []
    if assert_bootstrap_inputs:
        body.extend(
            [
                "from pathlib import Path",
                "import sys",
                "args = sys.argv[1:]",
                "steps = args[0]",
                "assert '--cell-types-file' in args",
                "assert '--node-positions-file' in args",
                "assert '--noise-seed-words-file' in args",
                "cell_types_path = Path(args[args.index('--cell-types-file') + 1])",
                "node_positions_path = Path(args[args.index('--node-positions-file') + 1])",
                "noise_seed_words_path = Path(args[args.index('--noise-seed-words-file') + 1])",
                "assert cell_types_path.read_text(encoding='utf-8') == '1\\n2\\n'",
                "assert node_positions_path.read_text(encoding='utf-8') == '0 0 0\\n0.5 0 0\\n'",
                "assert noise_seed_words_path.read_text(encoding='utf-8') == "
                "'1\\n2\\n3\\n4\\n5\\n6\\n7\\n8\\n'",
                "print(f'steps: {steps}')",
            ]
        )
    elif dynamic_steps:
        body.extend(["import sys", "steps = sys.argv[1]", "print(f'steps: {steps}')"])
    else:
        body.append("print('steps: 10')")
    return _write_executable(path, [*body, *_print_lines(_CELL_SORTING_SUMMARY_TAIL)])


def _write_invagination_executable(
    path: Path,
    *,
    getot: int = 0,
    rtime: float = 0.0,
    assert_bootstrap: bool = False,
    target_flag: str | None = None,
    target_value: str | None = None,
    write_positions: bool = False,
) -> Path:
    body: list[str] = []
    if assert_bootstrap or target_flag is not None or write_positions:
        body.extend(["from pathlib import Path", "import sys", "args = sys.argv[1:]"])
    if assert_bootstrap:
        bootstrap_assertion = (
            "assert bootstrap_path.read_text(encoding='utf-8') == "
            f"{_INVAGINATION_BOOTSTRAP_TEXT!r}"
        )
        body.extend(
            [
                "assert args[0] == '--bootstrap-file'",
                "bootstrap_path = Path(args[1])",
                bootstrap_assertion,
            ]
        )
    if target_flag is not None:
        body.extend(
            [
                f"assert args[2] == {target_flag!r}",
                f"assert args[3] == {target_value!r}",
                "assert args[4] == '--positions-out'",
                "positions_out = Path(args[5])",
            ]
        )
    elif write_positions:
        body.append("positions_out = Path(args[args.index('--positions-out') + 1])")
    if write_positions:
        body.append(
            f"positions_out.write_text({_INVAGINATION_POSITIONS_TEXT!r}, encoding='utf-8')"
        )
    return _write_executable(
        path,
        [*body, *_print_lines(_invagination_summary_lines(getot=getot, rtime=rtime))],
    )


def test_parse_and_compare_cell_sorting_summaries(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "legacy.dat"
    snapshot_path.write_text(_sample_snapshot_text() + "\n", encoding="utf-8")

    legacy_summary = summarize_legacy_snapshot(parse_legacy_snapshot(snapshot_path))
    v2_summary = parse_v2_cell_sorting_summary("\n".join(_cell_sorting_summary_lines()))

    comparison = compare_cell_sorting_summaries(legacy_summary, v2_summary)

    assert comparison.matches
    assert comparison.mismatches == ()


def test_parse_and_compare_invagination_summaries(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "epithelium.dat"
    snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")

    legacy_summary = summarize_legacy_epithelial_snapshot(parse_legacy_snapshot(snapshot_path))
    v2_summary = parse_v2_invagination_summary("\n".join(_invagination_summary_lines()))

    comparison = compare_invagination_summaries(legacy_summary, v2_summary)

    assert comparison.matches
    assert comparison.mismatches == ()
    assert v2_summary.getot == 0
    assert v2_summary.rtime == 0.0


def test_compare_invagination_geometry_reports_position_error() -> None:
    comparison = compare_invagination_geometry(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (1.1, 0.0, 0.0)),
        absolute_tolerance=0.05,
    )

    assert not comparison.matches
    assert comparison.max_position_error == 0.10000000000000009
    assert comparison.mean_position_error == 0.050000000000000044
    assert comparison.rms_position_error == 0.07071067811865482
    assert comparison.mismatches == (
        "max_position_error: tolerance=0.05 observed=0.10000000000000009",
    )


def test_compare_cell_sorting_trajectory_reports_all_frames(tmp_path: Path) -> None:
    (tmp_path / "_0.dat").write_text(_sample_snapshot_text(getot=0) + "\n", encoding="utf-8")
    (tmp_path / "10.dat").write_text(_sample_snapshot_text(getot=10) + "\n", encoding="utf-8")
    executable_path = _write_cell_sorting_executable(
        tmp_path / "em2_legacy_cell_sorting_summary",
        assert_bootstrap_inputs=True,
    )
    cell_types_path = tmp_path / "cell-types.txt"
    cell_types_path.write_text("1\n2\n", encoding="utf-8")
    node_positions_path = tmp_path / "node-positions.txt"
    node_positions_path.write_text("0 0 0\n0.5 0 0\n", encoding="utf-8")
    noise_seed_words_path = tmp_path / "noise-seed-words.txt"
    noise_seed_words_path.write_text("1\n2\n3\n4\n5\n6\n7\n8\n", encoding="utf-8")

    comparison = compare_cell_sorting_trajectory(
        load_legacy_snapshot_series(tmp_path),
        executable_path,
        initial_seed=1234,
        noise_seed=77,
        cell_types_file=cell_types_path,
        node_positions_file=node_positions_path,
        noise_seed_words_file=noise_seed_words_path,
    )

    assert comparison.matches
    assert len(comparison.frames) == 2
    assert comparison.frames[0].legacy.getot == 0
    assert comparison.frames[1].legacy.getot == 10


def test_compare_invagination_bootstrap_cli_reports_match(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "epithelium.dat"
    snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")
    executable_path = _write_invagination_executable(
        tmp_path / "em2_legacy_invagination_summary",
        assert_bootstrap=True,
    )

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-invagination-bootstrap",
            str(snapshot_path),
            "--executable",
            str(executable_path),
        ],
    )

    assert result.exit_code == 0
    assert "legacy_getot: 0" in result.stdout
    assert "legacy_rtime: 0.0" in result.stdout
    assert "v2_getot: 0" in result.stdout
    assert "v2_rtime: 0.0" in result.stdout
    assert "matches: True" in result.stdout
    assert "decision: pass" in result.stdout
    assert "reason: all comparison metrics matched within the declared tolerance" in result.stdout


def test_compare_invagination_cli_reports_match(tmp_path: Path) -> None:
    bootstrap_snapshot_path = tmp_path / "bootstrap.dat"
    bootstrap_snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")
    snapshot_path = tmp_path / "target.dat"
    snapshot_path.write_text(
        _sample_epithelial_snapshot_text(getot=7, rtime=1.25, x_shift=0.1) + "\n",
        encoding="utf-8",
    )
    executable_path = _write_invagination_executable(
        tmp_path / "em2_legacy_invagination_summary",
        getot=7,
        rtime=1.25,
        assert_bootstrap=True,
        target_flag="--target-rtime",
        target_value="1.25",
        write_positions=True,
    )

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-invagination",
            str(snapshot_path),
            "--bootstrap-snapshot",
            str(bootstrap_snapshot_path),
            "--executable",
            str(executable_path),
        ],
    )

    assert result.exit_code == 0
    assert "legacy_getot: 7" in result.stdout
    assert "legacy_rtime: 1.25" in result.stdout
    assert "v2_getot: 7" in result.stdout
    assert "v2_rtime: 1.25" in result.stdout
    assert "summary_matches: True" in result.stdout
    assert "geometry_matches: True" in result.stdout
    assert "max_position_error: 0.0" in result.stdout
    assert "matches: True" in result.stdout
    assert "decision: pass" in result.stdout


def test_compare_invagination_cli_accepts_step_target(tmp_path: Path) -> None:
    bootstrap_snapshot_path = tmp_path / "bootstrap.dat"
    bootstrap_snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")
    snapshot_path = tmp_path / "target.dat"
    snapshot_path.write_text(
        _sample_epithelial_snapshot_text(getot=7, rtime=1.25, x_shift=0.1) + "\n",
        encoding="utf-8",
    )
    executable_path = _write_invagination_executable(
        tmp_path / "em2_legacy_invagination_summary",
        getot=7,
        rtime=1.25,
        assert_bootstrap=True,
        target_flag="--steps",
        target_value="7",
        write_positions=True,
    )

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-invagination",
            str(snapshot_path),
            "--bootstrap-snapshot",
            str(bootstrap_snapshot_path),
            "--executable",
            str(executable_path),
            "--steps",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert "legacy_getot: 7" in result.stdout
    assert "v2_getot: 7" in result.stdout
    assert "matches: True" in result.stdout
    assert "decision: pass" in result.stdout


def test_compare_cell_sorting_cli_writes_json_bundle(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "legacy.dat"
    snapshot_path.write_text(_sample_snapshot_text() + "\n", encoding="utf-8")
    executable_path = _write_cell_sorting_executable(
        tmp_path / "em2_legacy_cell_sorting_summary"
    )
    json_out = tmp_path / "single-frame.json"

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-cell-sorting",
            str(snapshot_path),
            "--executable",
            str(executable_path),
            "--json-out",
            str(json_out),
        ],
    )

    assert result.exit_code == 0
    assert json_out.is_file()
    bundle = json.loads(json_out.read_text(encoding="utf-8"))
    assert bundle["scope"] == "single-frame"
    assert bundle["decision"] == "pass"
    assert bundle["reason"] == "all comparison metrics matched within the declared tolerance"
    assert bundle["matches"] is True
    assert bundle["mismatches"] == []
    assert bundle["seeds"]["initial_seed"] == -11111
    assert bundle["seeds"]["noise_seed"] is None
    assert bundle["legacy"]["getot"] == 10
    assert bundle["v2"]["steps"] == 10


def test_compare_invagination_bootstrap_cli_writes_json_bundle(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "epithelium.dat"
    snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")
    executable_path = _write_invagination_executable(
        tmp_path / "em2_legacy_invagination_summary"
    )
    json_out = tmp_path / "invagination-bootstrap.json"

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-invagination-bootstrap",
            str(snapshot_path),
            "--executable",
            str(executable_path),
            "--json-out",
            str(json_out),
        ],
    )

    assert result.exit_code == 0
    assert json_out.is_file()
    bundle = json.loads(json_out.read_text(encoding="utf-8"))
    assert bundle["scope"] == "bootstrap"
    assert bundle["lane"] == "invagination"
    assert bundle["decision"] == "pass"
    assert bundle["matches"] is True
    assert bundle["mismatches"] == []
    assert bundle["legacy"]["getot"] == 0
    assert bundle["legacy"]["rtime"] == 0.0
    assert bundle["legacy"]["epithelial_node_count"] == 4
    assert bundle["v2"]["getot"] == 0
    assert bundle["v2"]["rtime"] == 0.0
    assert bundle["v2"]["epithelial_node_count"] == 4


def test_compare_invagination_cli_writes_json_bundle(tmp_path: Path) -> None:
    bootstrap_snapshot_path = tmp_path / "bootstrap.dat"
    bootstrap_snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")
    snapshot_path = tmp_path / "target.dat"
    snapshot_path.write_text(
        _sample_epithelial_snapshot_text(getot=5802, rtime=10.0, x_shift=0.1) + "\n",
        encoding="utf-8",
    )
    executable_path = _write_invagination_executable(
        tmp_path / "em2_legacy_invagination_summary",
        getot=5802,
        rtime=10.0,
        write_positions=True,
    )
    json_out = tmp_path / "invagination.json"

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-invagination",
            str(snapshot_path),
            "--bootstrap-snapshot",
            str(bootstrap_snapshot_path),
            "--executable",
            str(executable_path),
            "--json-out",
            str(json_out),
        ],
    )

    assert result.exit_code == 0
    assert json_out.is_file()
    bundle = json.loads(json_out.read_text(encoding="utf-8"))
    assert bundle["lane"] == "invagination"
    assert bundle["scope"] == "single-frame"
    assert bundle["decision"] == "pass"
    assert bundle["matches"] is True
    assert bundle["summary_matches"] is True
    assert bundle["geometry_matches"] is True
    assert bundle["mismatches"] == []
    assert bundle["summary_mismatches"] == []
    assert bundle["geometry_mismatches"] == []
    assert bundle["legacy"]["getot"] == 5802
    assert bundle["legacy"]["rtime"] == 10.0
    assert bundle["v2"]["getot"] == 5802
    assert bundle["v2"]["rtime"] == 10.0
    assert bundle["geometry"]["max_position_error"] == 0.0
    assert bundle["geometry"]["mean_position_error"] == 0.0
    assert bundle["geometry"]["rms_position_error"] == 0.0


def test_compare_cell_sorting_trajectory_cli_writes_json_bundle(tmp_path: Path) -> None:
    (tmp_path / "_0.dat").write_text(_sample_snapshot_text(getot=0) + "\n", encoding="utf-8")
    (tmp_path / "10.dat").write_text(_sample_snapshot_text(getot=10) + "\n", encoding="utf-8")
    executable_path = _write_cell_sorting_executable(
        tmp_path / "em2_legacy_cell_sorting_summary",
        dynamic_steps=True,
    )
    json_out = tmp_path / "trajectory.json"

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-cell-sorting-trajectory",
            str(tmp_path),
            "--executable",
            str(executable_path),
            "--json-out",
            str(json_out),
        ],
    )

    assert result.exit_code == 0
    assert json_out.is_file()
    bundle = json.loads(json_out.read_text(encoding="utf-8"))
    assert bundle["scope"] == "trajectory"
    assert bundle["decision"] == "pass"
    assert bundle["frame_count"] == 2
    assert bundle["matches"] is True
    assert bundle["seeds"]["initial_seed"] == -11111
    assert bundle["seeds"]["noise_seed"] is None
    assert bundle["bootstrap_cell_types_source"] == str(tmp_path / "_0.dat")
    assert bundle["bootstrap_node_positions_source"] == str(tmp_path / "_0.dat")
    assert bundle["bootstrap_noise_seed_source"] == str(tmp_path / "_0.dat")
    assert bundle["resolved_snapshot_dir"] == str(tmp_path)
    assert bundle["frames"][0]["label"] == "_0.dat"
    assert bundle["frames"][1]["label"] == "10.dat"


def test_compare_cell_sorting_trajectory_cli_resolves_staged_output_layout(
    tmp_path: Path,
) -> None:
    staged_output = tmp_path / "artifacts" / "output" / "run-123"
    staged_output.mkdir(parents=True)
    (staged_output / "_0.dat").write_text(_sample_snapshot_text(getot=0) + "\n", encoding="utf-8")
    (staged_output / "10.dat").write_text(
        _sample_snapshot_text(getot=10) + "\n",
        encoding="utf-8",
    )
    executable_path = _write_cell_sorting_executable(
        tmp_path / "em2_legacy_cell_sorting_summary",
        dynamic_steps=True,
    )

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare-cell-sorting-trajectory",
            str(tmp_path / "artifacts"),
            "--executable",
            str(executable_path),
        ],
    )

    assert result.exit_code == 0
    assert f"resolved_snapshot_dir: {staged_output}" in result.stdout
    assert "matches: True" in result.stdout
