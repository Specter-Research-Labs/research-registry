from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MeshCoordinateInfo:
    row: int
    col: int
    device_id: int
    is_local: bool


@dataclass(frozen=True)
class SystemMeshInfo:
    global_shape: tuple[int, int]
    local_shape: tuple[int, int]
    pcie_device_ids: tuple[int, ...]
    logical_device_ids: tuple[int, ...]
    coordinates: tuple[MeshCoordinateInfo, ...]

    @property
    def mesh_size(self) -> int:
        return self.global_shape[0] * self.global_shape[1]


def get_available_pcie_device_ids() -> list[int]:
    dev_root = Path("/dev/tenstorrent")
    if dev_root.exists():
        device_ids = sorted(int(path.name) for path in dev_root.iterdir() if path.name.isdigit())
        if device_ids:
            return device_ids

    import ttnn

    if hasattr(ttnn, "get_pcie_device_ids"):
        return list(ttnn.get_pcie_device_ids())
    if hasattr(ttnn, "GetNumPCIeDevices"):
        return list(range(ttnn.GetNumPCIeDevices()))
    if hasattr(ttnn, "get_device_ids"):
        return list(ttnn.get_device_ids())
    return list(range(ttnn.GetNumAvailableDevices()))


def probe_system_mesh() -> SystemMeshInfo:
    import ttnn

    descriptor = ttnn._ttnn.multi_device.SystemMeshDescriptor()
    global_shape = tuple(descriptor.shape())
    local_shape = tuple(descriptor.local_shape())
    all_local = descriptor.all_local()
    coordinates = []
    for row in range(global_shape[0]):
        for col in range(global_shape[1]):
            coord = ttnn.MeshCoordinate(row, col)
            coordinates.append(
                MeshCoordinateInfo(
                    row=row,
                    col=col,
                    device_id=descriptor.get_device_id(coord),
                    is_local=all_local or descriptor.is_local(coord),
                )
            )
    logical_device_ids = list(ttnn.get_device_ids()) if hasattr(ttnn, "get_device_ids") else []
    return SystemMeshInfo(
        global_shape=global_shape,
        local_shape=local_shape,
        pcie_device_ids=tuple(get_available_pcie_device_ids()),
        logical_device_ids=tuple(logical_device_ids),
        coordinates=tuple(coordinates),
    )


def format_system_mesh(info: SystemMeshInfo) -> str:
    lines = [
        f"PCIe device ids: {list(info.pcie_device_ids)}",
        f"Logical device ids: {list(info.logical_device_ids)}",
        f"System mesh global shape: {info.global_shape}",
        f"System mesh local shape: {info.local_shape}",
        "System mesh coordinates:",
    ]
    for entry in info.coordinates:
        locality = "local" if entry.is_local else "remote"
        lines.append(f"  ({entry.row}, {entry.col}) -> device {entry.device_id} [{locality}]")
    return "\n".join(lines)
