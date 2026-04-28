"""Mesh row-halo orchestration for spatially sharded Lenia tensors."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MeshRowHalo:
    """A mesh tensor with cleanup handles produced while assembling it."""

    tensor: object
    cleanup: tuple[object, ...]

    def close(self) -> None:
        import ttnn

        for tensor in (self.tensor, *self.cleanup):
            if tensor is None:
                continue
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass


def slice_along_dim(tensor, *, dim: int, start: int, end: int):
    import ttnn

    slice_start = [0] * len(tensor.shape)
    slice_end = [int(value) for value in tensor.shape]
    slice_start[dim] = int(start)
    slice_end[dim] = int(end)
    return ttnn.slice(tensor, tuple(slice_start), tuple(slice_end))


def gather_mesh_row_boundaries(
    sharded,
    *,
    local_rows: int,
    boundary_rows: int,
    shard_dim: int,
) -> tuple[object, object, tuple[object, ...]]:
    """Gather top and bottom row-boundary tiles from every mesh rank."""
    import ttnn

    top = slice_along_dim(sharded, dim=shard_dim, start=0, end=boundary_rows)
    bottom = slice_along_dim(
        sharded,
        dim=shard_dim,
        start=local_rows - boundary_rows,
        end=local_rows,
    )
    top_gathered = ttnn.all_gather(top, dim=shard_dim)
    bottom_gathered = ttnn.all_gather(bottom, dim=shard_dim)
    return top_gathered, bottom_gathered, (top, bottom)


def rotate_gathered_boundary(
    gathered,
    *,
    mesh_size: int,
    boundary_rows: int,
    shard_dim: int,
    pad_before: bool,
) -> tuple[object, tuple[object, ...]]:
    """Rotate gathered boundary blocks so mesh_partition selects a neighbor."""
    import ttnn

    if mesh_size <= 1:
        return gathered, ()

    if pad_before:
        head = slice_along_dim(
            gathered,
            dim=shard_dim,
            start=0,
            end=(mesh_size - 1) * boundary_rows,
        )
        tail = slice_along_dim(
            gathered,
            dim=shard_dim,
            start=(mesh_size - 1) * boundary_rows,
            end=mesh_size * boundary_rows,
        )
        return ttnn.concat([tail, head], dim=shard_dim), (head, tail)

    head = slice_along_dim(gathered, dim=shard_dim, start=0, end=boundary_rows)
    tail = slice_along_dim(
        gathered,
        dim=shard_dim,
        start=boundary_rows,
        end=mesh_size * boundary_rows,
    )
    return ttnn.concat([tail, head], dim=shard_dim), (head, tail)


def assemble_one_sided_mesh_row_halo(
    sharded,
    top_gathered,
    bottom_gathered,
    *,
    mesh_size: int,
    boundary_rows: int,
    shard_dim: int,
    pad_before: bool,
) -> MeshRowHalo:
    """Return a mesh tensor whose local shards include one neighbor row halo."""
    import ttnn

    gathered = bottom_gathered if pad_before else top_gathered
    rotated, rotation_cleanup = rotate_gathered_boundary(
        gathered,
        mesh_size=mesh_size,
        boundary_rows=boundary_rows,
        shard_dim=shard_dim,
        pad_before=pad_before,
    )
    halo = ttnn.mesh_partition(rotated, dim=shard_dim)
    padded = (
        ttnn.concat([halo, sharded], dim=shard_dim)
        if pad_before
        else ttnn.concat([sharded, halo], dim=shard_dim)
    )
    cleanup = [halo]
    if rotated is not gathered:
        cleanup.append(rotated)
    cleanup.extend(rotation_cleanup)
    return MeshRowHalo(tensor=padded, cleanup=tuple(cleanup))


def assemble_one_sided_torus_col_halo(
    tensor,
    *,
    boundary_cols: int,
    pad_before: bool,
) -> MeshRowHalo:
    """Return a tensor with a one-sided local torus column halo."""
    import ttnn

    col_dim = len(tensor.shape) - 1
    cols = int(tensor.shape[col_dim])
    halo = (
        slice_along_dim(tensor, dim=col_dim, start=cols - boundary_cols, end=cols)
        if pad_before
        else slice_along_dim(tensor, dim=col_dim, start=0, end=boundary_cols)
    )
    padded = ttnn.concat([halo, tensor], dim=col_dim) if pad_before else ttnn.concat([tensor, halo], dim=col_dim)
    return MeshRowHalo(tensor=padded, cleanup=(halo,))
