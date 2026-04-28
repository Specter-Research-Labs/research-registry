from pathlib import Path

from embryomaker_v2.legacy_snapshot import (
    extract_legacy_node_positions,
    extract_legacy_rng_seed_words,
    parse_legacy_snapshot,
    summarize_legacy_epithelial_snapshot,
    summarize_legacy_snapshot,
    write_legacy_invagination_bootstrap,
)


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


def _snapshot_text(
    *,
    run_name: str,
    getot: float,
    nd: int,
    rtime: float,
    ncels: int,
    ng: int,
    gene_rows: list[str],
    node_rows: list[str],
) -> str:
    return "\n".join(
        [
            "THIS FILE WAS WRITTEN IN THE FORMAT OF THE TEST VERSION",
            run_name,
            "35 number of node parameters",
            "5 number of global variables",
            "",
            "30 functions",
            "",
            "0 unused",
            "",
            "parameters",
            "",
            f" 1 {getot:.16E} getot",
            f"10 {float(nd):.16E} nd",
            f"13 {rtime:.16E} rtime",
            f"18 {float(ncels):.16E} ncels",
            f"19 {float(ng):.16E} ng",
            "",
            "G matrix: gene expression",
            "",
            "node  gene 1                 gene 2    etc...",
            *gene_rows,
            "",
            "node properties",
            "",
            "x y z ...",
            *node_rows,
            "",
            "node properties at time 0 (nodeo)",
            "",
            "x y z ...",
            *node_rows,
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


def _sample_snapshot_text() -> str:
    return _snapshot_text(
        run_name="demo-run",
        getot=10.0,
        nd=2,
        rtime=1.5,
        ncels=2,
        ng=2,
        gene_rows=[
            "1 1.0000000000000000E+00 0.0000000000000000E+00",
            "2 0.0000000000000000E+00 1.0000000000000000E+00",
        ],
        node_rows=[
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
        ],
    )


def _sample_epithelial_snapshot_text() -> str:
    return _snapshot_text(
        run_name="epi-run",
        getot=0.0,
        nd=4,
        rtime=0.0,
        ncels=2,
        ng=2,
        gene_rows=[
            "1 0.0000000000000000E+00 1.0000000000000000E+00",
            "2 1.0000000000000000E+00 0.0000000000000000E+00",
            "3 0.0000000000000000E+00 1.0000000000000000E+00",
            "4 1.0000000000000000E+00 0.0000000000000000E+00",
        ],
        node_rows=[
            _node_row(
                x=0.0,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pld=0.0,
                vod=0.0,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=1,
                altre=2,
            ),
            _node_row(
                x=0.0,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=0.0,
                oriy=0.2,
                oriz=0.0,
                cod=0.0,
                grd=0.25,
                pld=0.0,
                vod=0.0,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=1,
                altre=1,
            ),
            _node_row(
                x=1.0,
                y=0.0,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0,
                oriy=0.0,
                oriz=0.0,
                cod=0.1,
                grd=0.25,
                pld=0.0,
                vod=0.0,
                pla=0.0,
                kvol=0.0,
                tipus=2,
                icel=2,
                altre=4,
            ),
            _node_row(
                x=1.0,
                y=0.2,
                z=0.0,
                eqd=0.25,
                add=0.4,
                orix=1.0,
                oriy=0.2,
                oriz=0.0,
                cod=0.0,
                grd=0.25,
                pld=0.0,
                vod=0.0,
                pla=1.0,
                kvol=1.0,
                tipus=1,
                icel=2,
                altre=3,
            ),
        ],
    )


def test_parse_legacy_snapshot_extracts_cell_sorting_subset(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "legacy.dat"
    snapshot_path.write_text(_sample_snapshot_text() + "\n", encoding="utf-8")

    snapshot = parse_legacy_snapshot(snapshot_path)
    summary = summarize_legacy_snapshot(snapshot)

    assert snapshot.run_name == "demo-run"
    assert snapshot.getot == 10
    assert snapshot.node_count == 2
    assert snapshot.cell_count == 2
    assert snapshot.gene_count == 2
    assert snapshot.nodes[0].add == 0.5
    assert snapshot.nodes[0].icel == 1
    assert snapshot.nodes[1].gex == (0.0, 1.0)
    assert summary.contact_count == 1
    assert summary.max_distance_from_origin == 0.5
    assert summary.mean_neighbor_count == 1.0
    assert summary.type1_cell_count == 1
    assert summary.type2_cell_count == 1
    assert extract_legacy_node_positions(snapshot) == ((0.0, 0.0, 0.0), (0.5, 0.0, 0.0))
    assert extract_legacy_rng_seed_words(snapshot_path) == (1, 2, 3, 4, 5, 6, 7, 8)


def test_summarize_legacy_epithelial_snapshot_reports_invagination_bootstrap_state(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "epithelium.dat"
    snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")

    snapshot = parse_legacy_snapshot(snapshot_path)
    summary = summarize_legacy_epithelial_snapshot(snapshot)

    assert snapshot.nodes[0].cod == 0.1
    assert snapshot.nodes[0].grd == 0.25
    assert snapshot.nodes[0].pla == 0.0
    assert snapshot.nodes[0].kvol == 0.0
    assert snapshot.nodes[0].altre == 2
    assert summary.epithelial_node_count == 4
    assert summary.apical_node_count == 2
    assert summary.basal_node_count == 2
    assert summary.rtime == 0.0
    assert summary.paired_epithelial_node_count == 4
    assert summary.epithelial_cell_count == 2
    assert summary.gene1_positive_node_count == 2
    assert summary.gene2_positive_node_count == 2
    assert summary.gene1_positive_cell_count == 2
    assert summary.gene2_positive_cell_count == 2
    assert summary.polarized_expression_cell_count == 2
    assert summary.zero_pla_node_count == 2
    assert summary.zero_kvol_node_count == 2
    assert summary.mean_grd == 0.25
    assert summary.mean_cod == 0.05
    assert summary.mean_pld == 0.0
    assert summary.mean_vod == 0.0


def test_write_legacy_invagination_bootstrap_serializes_kernel_input(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "epithelium.dat"
    snapshot_path.write_text(_sample_epithelial_snapshot_text() + "\n", encoding="utf-8")

    bootstrap_path = tmp_path / "bootstrap.txt"
    write_legacy_invagination_bootstrap(parse_legacy_snapshot(snapshot_path), bootstrap_path)

    assert bootstrap_path.read_text(encoding="utf-8") == "\n".join(
        [
            "0 0 0 0.25 0.40000000000000002 0.10000000000000001 0.25 0 0 0 0 2 1 2 0 0 0 0 1",
            "0 0.20000000000000001 0 0.25 0.40000000000000002 0 0.25 0 0 1 1 1 1 1 0 0 0 1 0",
            "1 0 0 0.25 0.40000000000000002 0.10000000000000001 0.25 0 0 0 0 2 2 4 0 0 0 0 1",
            "1 0.20000000000000001 0 0.25 0.40000000000000002 0 0.25 0 0 1 1 1 2 3 0 0 0 1 0",
            "",
        ]
    )


def test_parse_legacy_snapshot_handles_legacy_fortran_float_quirks(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "legacy.dat"
    snapshot_text = (
        _sample_snapshot_text()
        .replace("demo-run", "demo-run\x00")
        .replace("13 1.5000000000000000E+00 rtime", "13 1.5000000000000000+00 rtime")
    )
    snapshot_path.write_text(snapshot_text + "\n", encoding="utf-8")

    snapshot = parse_legacy_snapshot(snapshot_path)

    assert snapshot.run_name == "demo-run"
    assert snapshot.rtime == 1.5


def test_summarize_legacy_snapshot_tolerates_partial_cell_type_coverage(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "partial-types.dat"
    snapshot_text = _sample_snapshot_text().replace(
        "2 0.0000000000000000E+00 1.0000000000000000E+00",
        "2 0.0000000000000000E+00 0.0000000000000000E+00",
    )
    snapshot_path.write_text(snapshot_text + "\n", encoding="utf-8")

    summary = summarize_legacy_snapshot(parse_legacy_snapshot(snapshot_path))

    assert summary.contact_count == 1
    assert summary.type1_cell_count == 0
    assert summary.type2_cell_count == 0
