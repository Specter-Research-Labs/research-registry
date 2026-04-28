from __future__ import annotations

from duckdb import DuckDBPyConnection

from .export_legacy import compute_and_store_topology


def run_topology(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    source_packet_kind: str,
    min_group_size: int,
    max_homology_dim: int,
) -> str:
    return compute_and_store_topology(
        connection,
        study_id=study_id,
        source_packet_kind=source_packet_kind,
        min_group_size=min_group_size,
        max_homology_dim=max_homology_dim,
    )
