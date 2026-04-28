from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PARAM_GETOT: Final[int] = 1
PARAM_ND: Final[int] = 10
PARAM_RTIME: Final[int] = 13
PARAM_NCELS: Final[int] = 18
PARAM_NG: Final[int] = 19
RNG_SEED_WORD_COUNT: Final[int] = 8

NODE_X_INDEX: Final[int] = 0
NODE_Y_INDEX: Final[int] = 1
NODE_Z_INDEX: Final[int] = 2
NODE_EQD_INDEX: Final[int] = 4
NODE_ADD_INDEX: Final[int] = 5
NODE_ORIX_INDEX: Final[int] = 16
NODE_ORIY_INDEX: Final[int] = 17
NODE_ORIZ_INDEX: Final[int] = 18
NODE_COD_INDEX: Final[int] = 20
NODE_GRD_INDEX: Final[int] = 21
NODE_PLD_INDEX: Final[int] = 22
NODE_VOD_INDEX: Final[int] = 23
NODE_PLA_INDEX: Final[int] = 26
NODE_KVOL_INDEX: Final[int] = 27
NODE_TYPE_INDEX: Final[int] = 28
NODE_CELL_INDEX: Final[int] = 29
NODE_OTHER_INDEX: Final[int] = 30
NODE_MARGIN_INDEX: Final[int] = 31
NODE_TALONE_INDEX: Final[int] = 32
NODE_FIX_INDEX: Final[int] = 33


@dataclass(frozen=True)
class LegacySnapshotNode:
    x: float
    y: float
    z: float
    eqd: float
    add: float
    orix: float
    oriy: float
    oriz: float
    cod: float
    grd: float
    pld: float
    vod: float
    pla: float
    kvol: float
    tipus: int
    icel: int
    altre: int
    marge: int
    talone: int
    fix: int
    gex: tuple[float, ...]


@dataclass(frozen=True)
class LegacySnapshot:
    version_line: str
    run_name: str
    getot: int
    rtime: float
    node_count: int
    cell_count: int
    gene_count: int
    nodes: tuple[LegacySnapshotNode, ...]


@dataclass(frozen=True)
class LegacySnapshotSummary:
    path: Path | None
    getot: int
    rtime: float
    node_count: int
    cell_count: int
    gene_count: int
    contact_count: int
    max_distance_from_origin: float
    mean_distance_from_origin: float
    mean_neighbor_count: float
    type1_cell_count: int
    type2_cell_count: int


@dataclass(frozen=True)
class LegacySnapshotSeries:
    frames: tuple[LegacySnapshotSummary, ...]


@dataclass(frozen=True)
class LegacyEpithelialSnapshotSummary:
    path: Path | None
    getot: int
    rtime: float
    node_count: int
    cell_count: int
    epithelial_node_count: int
    apical_node_count: int
    basal_node_count: int
    paired_epithelial_node_count: int
    epithelial_cell_count: int
    gene1_positive_node_count: int
    gene2_positive_node_count: int
    gene1_positive_cell_count: int
    gene2_positive_cell_count: int
    polarized_expression_cell_count: int
    zero_pla_node_count: int
    zero_kvol_node_count: int
    mean_grd: float
    mean_cod: float
    mean_pld: float
    mean_vod: float


def _find_line(lines: list[str], header: str) -> int:
    for index, line in enumerate(lines):
        if line.strip() == header:
            return index
    raise ValueError(f"missing section header: {header}")


_FORTRAN_FLOAT_WITHOUT_E = re.compile(
    r"^(?P<mantissa>[+-]?(?:\d+(?:\.\d*)?|\.\d+))(?P<exponent>[+-]\d+)$"
)


def _parse_legacy_float(value: str) -> float:
    normalized = value.replace("\x00", "").strip().replace("D", "E").replace("d", "e")
    try:
        return float(normalized)
    except ValueError:
        match = _FORTRAN_FLOAT_WITHOUT_E.fullmatch(normalized)
        if match is None:
            raise
        mantissa = match.group("mantissa")
        exponent = match.group("exponent")
        return float(f"{mantissa}E{exponent}")


def _parse_parameter_block(lines: list[str]) -> dict[int, float]:
    start = _find_line(lines, "parameters") + 2
    params: dict[int, float] = {}
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            break
        parts = stripped.split(maxsplit=2)
        if len(parts) < 2:
            raise ValueError("malformed parameter row")
        params[int(parts[0])] = _parse_legacy_float(parts[1])
        index += 1
    return params


def _parse_gene_expression_block(
    lines: list[str],
    node_count: int,
    gene_count: int,
) -> list[tuple[float, ...]]:
    if gene_count <= 0:
        return [tuple() for _ in range(node_count)]

    start = _find_line(lines, "G matrix: gene expression") + 3
    rows: list[tuple[float, ...]] = []
    for line in lines[start : start + node_count]:
        parts = line.split()
        if len(parts) < gene_count + 1:
            raise ValueError("malformed gene-expression row")
        rows.append(tuple(_parse_legacy_float(value) for value in parts[1 : gene_count + 1]))
    if len(rows) != node_count:
        raise ValueError("gene-expression row count drifted")
    return rows


def _parse_node_block(
    lines: list[str],
    header: str,
    node_count: int,
    gene_rows: list[tuple[float, ...]],
) -> tuple[LegacySnapshotNode, ...]:
    start = _find_line(lines, header) + 3
    nodes: list[LegacySnapshotNode] = []
    for node_index, line in enumerate(lines[start : start + node_count]):
        parts = line.split()
        if len(parts) < 30:
            raise ValueError("malformed node row")
        nodes.append(
            LegacySnapshotNode(
                x=_parse_legacy_float(parts[NODE_X_INDEX]),
                y=_parse_legacy_float(parts[NODE_Y_INDEX]),
                z=_parse_legacy_float(parts[NODE_Z_INDEX]),
                eqd=_parse_legacy_float(parts[NODE_EQD_INDEX]),
                add=_parse_legacy_float(parts[NODE_ADD_INDEX]),
                orix=_parse_legacy_float(parts[NODE_ORIX_INDEX]),
                oriy=_parse_legacy_float(parts[NODE_ORIY_INDEX]),
                oriz=_parse_legacy_float(parts[NODE_ORIZ_INDEX]),
                cod=_parse_legacy_float(parts[NODE_COD_INDEX]),
                grd=_parse_legacy_float(parts[NODE_GRD_INDEX]),
                pld=_parse_legacy_float(parts[NODE_PLD_INDEX]),
                vod=_parse_legacy_float(parts[NODE_VOD_INDEX]),
                pla=_parse_legacy_float(parts[NODE_PLA_INDEX]),
                kvol=_parse_legacy_float(parts[NODE_KVOL_INDEX]),
                tipus=int(_parse_legacy_float(parts[NODE_TYPE_INDEX])),
                icel=int(_parse_legacy_float(parts[NODE_CELL_INDEX])),
                altre=int(_parse_legacy_float(parts[NODE_OTHER_INDEX])),
                marge=int(_parse_legacy_float(parts[NODE_MARGIN_INDEX])),
                talone=int(_parse_legacy_float(parts[NODE_TALONE_INDEX])),
                fix=int(_parse_legacy_float(parts[NODE_FIX_INDEX])),
                gex=gene_rows[node_index],
            )
        )
    if len(nodes) != node_count:
        raise ValueError("node row count drifted")
    return tuple(nodes)


def parse_legacy_snapshot(path: Path) -> LegacySnapshot:
    lines = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").splitlines()
    if len(lines) < 2:
        raise ValueError("snapshot file is too short")

    params = _parse_parameter_block(lines)
    node_count = int(round(params[PARAM_ND]))
    cell_count = int(round(params[PARAM_NCELS]))
    gene_count = int(round(params[PARAM_NG]))
    gene_rows = _parse_gene_expression_block(lines, node_count, gene_count)
    nodes = _parse_node_block(lines, "node properties", node_count, gene_rows)

    return LegacySnapshot(
        version_line=lines[0].strip(),
        run_name=lines[1].strip(),
        getot=int(round(params[PARAM_GETOT])),
        rtime=params[PARAM_RTIME],
        node_count=node_count,
        cell_count=cell_count,
        gene_count=gene_count,
        nodes=nodes,
    )


def extract_legacy_rng_seed_words(path: Path) -> tuple[int, ...]:
    lines = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").splitlines()
    start = _find_line(lines, "random seed at this iteration") + 1
    values: list[int] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if values:
                break
            continue
        values.extend(int(value) for value in stripped.split())
        if len(values) >= RNG_SEED_WORD_COUNT:
            break
    if len(values) != RNG_SEED_WORD_COUNT:
        raise ValueError("legacy snapshot random-seed block drifted")
    return tuple(values)


def summarize_legacy_snapshot(snapshot: LegacySnapshot) -> LegacySnapshotSummary:
    max_distance = 0.0
    distance_sum = 0.0
    neighbor_counts = [0] * snapshot.node_count
    contact_count = 0

    for node in snapshot.nodes:
        distance = (node.x * node.x + node.y * node.y + node.z * node.z) ** 0.5
        distance_sum += distance
        max_distance = max(max_distance, distance)

    for left_index, left in enumerate(snapshot.nodes):
        for right_index in range(left_index + 1, snapshot.node_count):
            right = snapshot.nodes[right_index]
            dx = right.x - left.x
            dy = right.y - left.y
            dz = right.z - left.z
            distance_sq = (dx * dx) + (dy * dy) + (dz * dz)
            cutoff = left.add + right.add
            if distance_sq <= (cutoff * cutoff):
                contact_count += 1
                neighbor_counts[left_index] += 1
                neighbor_counts[right_index] += 1

    try:
        cell_types = extract_legacy_cell_types(snapshot)
    except ValueError:
        type1_cell_count = 0
        type2_cell_count = 0
    else:
        type1_cell_count = sum(1 for value in cell_types if value == 1)
        type2_cell_count = sum(1 for value in cell_types if value == 2)
    mean_neighbor_count = sum(neighbor_counts) / max(float(snapshot.node_count), 1.0)

    return LegacySnapshotSummary(
        path=None,
        getot=snapshot.getot,
        rtime=snapshot.rtime,
        node_count=snapshot.node_count,
        cell_count=snapshot.cell_count,
        gene_count=snapshot.gene_count,
        contact_count=contact_count,
        max_distance_from_origin=max_distance,
        mean_distance_from_origin=distance_sum / max(float(snapshot.node_count), 1.0),
        mean_neighbor_count=mean_neighbor_count,
        type1_cell_count=type1_cell_count,
        type2_cell_count=type2_cell_count,
    )


def extract_legacy_cell_types(snapshot: LegacySnapshot) -> tuple[int, ...]:
    cell_types: dict[int, int] = {}
    for node in snapshot.nodes:
        if len(node.gex) < 2 or node.icel <= 0 or node.icel in cell_types:
            continue
        if node.gex[0] > node.gex[1]:
            cell_types[node.icel] = 1
        elif node.gex[1] > node.gex[0]:
            cell_types[node.icel] = 2

    if len(cell_types) != snapshot.cell_count:
        raise ValueError("legacy snapshot cell-type coverage drifted")
    return tuple(cell_types[cell_index] for cell_index in range(1, snapshot.cell_count + 1))


def extract_legacy_node_positions(
    snapshot: LegacySnapshot,
) -> tuple[tuple[float, float, float], ...]:
    return tuple((node.x, node.y, node.z) for node in snapshot.nodes)


def write_legacy_invagination_bootstrap(snapshot: LegacySnapshot, path: Path) -> None:
    path.write_text(
        "".join(
            (
                f"{node.x:.17g} {node.y:.17g} {node.z:.17g} "
                f"{node.eqd:.17g} {node.add:.17g} {node.cod:.17g} {node.grd:.17g} "
                f"{node.pld:.17g} {node.vod:.17g} {node.pla:.17g} {node.kvol:.17g} "
                f"{node.tipus} {node.icel} {node.altre} {node.marge} {node.talone} {node.fix} "
                f"{(node.gex[0] if len(node.gex) >= 1 else 0.0):.17g} "
                f"{(node.gex[1] if len(node.gex) >= 2 else 0.0):.17g}\n"
            )
            for node in snapshot.nodes
        ),
        encoding="utf-8",
    )


def load_legacy_snapshot_series(directory: Path) -> LegacySnapshotSeries:
    frames: list[LegacySnapshotSummary] = []
    for path in sorted(directory.glob("*.dat")):
        if path.name == "name.dat":
            continue
        snapshot = parse_legacy_snapshot(path)
        summary = summarize_legacy_snapshot(snapshot)
        frames.append(
            LegacySnapshotSummary(
                path=path,
                getot=summary.getot,
                rtime=summary.rtime,
                node_count=summary.node_count,
                cell_count=summary.cell_count,
                gene_count=summary.gene_count,
                contact_count=summary.contact_count,
                max_distance_from_origin=summary.max_distance_from_origin,
                mean_distance_from_origin=summary.mean_distance_from_origin,
                mean_neighbor_count=summary.mean_neighbor_count,
                type1_cell_count=summary.type1_cell_count,
                type2_cell_count=summary.type2_cell_count,
            )
        )

    if not frames:
        raise ValueError(f"no legacy .dat snapshots found in {directory}")

    frames.sort(key=lambda frame: frame.getot)
    return LegacySnapshotSeries(frames=tuple(frames))


def summarize_legacy_epithelial_snapshot(
    snapshot: LegacySnapshot,
) -> LegacyEpithelialSnapshotSummary:
    epithelial_nodes = tuple(node for node in snapshot.nodes if node.tipus in (1, 2))
    apical_nodes = tuple(node for node in epithelial_nodes if node.tipus == 2)
    basal_nodes = tuple(node for node in epithelial_nodes if node.tipus == 1)
    paired_epithelial_node_count = sum(1 for node in epithelial_nodes if node.altre > 0)
    epithelial_cells = {node.icel for node in epithelial_nodes if node.icel > 0}
    gene1_positive_nodes = sum(
        1 for node in epithelial_nodes if len(node.gex) >= 1 and node.gex[0] > 0.0
    )
    gene2_positive_nodes = sum(
        1 for node in epithelial_nodes if len(node.gex) >= 2 and node.gex[1] > 0.0
    )
    cell_expression: dict[int, tuple[bool, bool]] = {}
    for node in epithelial_nodes:
        if node.icel <= 0:
            continue
        current = cell_expression.get(node.icel, (False, False))
        has_gene1 = current[0] or (len(node.gex) >= 1 and node.gex[0] > 0.0)
        has_gene2 = current[1] or (len(node.gex) >= 2 and node.gex[1] > 0.0)
        cell_expression[node.icel] = (has_gene1, has_gene2)

    def _mean(values: tuple[float, ...]) -> float:
        if not values:
            return 0.0
        return sum(values) / float(len(values))

    grd_values = tuple(node.grd for node in epithelial_nodes)
    cod_values = tuple(node.cod for node in epithelial_nodes)
    pld_values = tuple(node.pld for node in epithelial_nodes)
    vod_values = tuple(node.vod for node in epithelial_nodes)

    return LegacyEpithelialSnapshotSummary(
        path=None,
        getot=snapshot.getot,
        rtime=snapshot.rtime,
        node_count=snapshot.node_count,
        cell_count=snapshot.cell_count,
        epithelial_node_count=len(epithelial_nodes),
        apical_node_count=len(apical_nodes),
        basal_node_count=len(basal_nodes),
        paired_epithelial_node_count=paired_epithelial_node_count,
        epithelial_cell_count=len(epithelial_cells),
        gene1_positive_node_count=gene1_positive_nodes,
        gene2_positive_node_count=gene2_positive_nodes,
        gene1_positive_cell_count=sum(1 for gene1, _ in cell_expression.values() if gene1),
        gene2_positive_cell_count=sum(1 for _, gene2 in cell_expression.values() if gene2),
        polarized_expression_cell_count=sum(
            1 for gene1, gene2 in cell_expression.values() if gene1 and gene2
        ),
        zero_pla_node_count=sum(1 for node in epithelial_nodes if node.pla == 0.0),
        zero_kvol_node_count=sum(1 for node in epithelial_nodes if node.kvol == 0.0),
        mean_grd=_mean(grd_values),
        mean_cod=_mean(cod_values),
        mean_pld=_mean(pld_values),
        mean_vod=_mean(vod_values),
    )
