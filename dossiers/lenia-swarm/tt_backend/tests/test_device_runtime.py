from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from tt_lenia.device import (
    PartitionTiming,
    apply_tt_runtime_env,
    infer_mesh_shape_from_visible_devices,
    open_ttnn_device,
    parallel_elapsed_s,
    resolve_execution_mode,
    resolve_execution_strategy,
    resolve_runtime_device_selection,
    restore_tt_runtime_env,
)


def test_infer_mesh_shape_from_visible_devices_for_common_quietbox_meshes():
    assert infer_mesh_shape_from_visible_devices("0") == (1, 2)
    assert infer_mesh_shape_from_visible_devices(("0", "1")) == (1, 4)
    assert infer_mesh_shape_from_visible_devices(["0", "1", "2", "3"]) == (1, 8)


def test_resolve_execution_mode_rejects_ambiguous_single_multi_device():
    try:
        resolve_execution_mode(
            execution_mode="single",
            device_list=["0", "1"],
            visible_devices=None,
            mesh_shape=None,
        )
    except ValueError as exc:
        assert "single execution mode" in str(exc)
    else:
        raise AssertionError("Expected single mode to reject multiple devices.")


def test_resolve_runtime_device_selection_prefers_mesh_only_in_mesh_mode():
    visible_devices, mesh_shape = resolve_runtime_device_selection(
        backend="tt",
        execution_mode="mesh",
        device_list=["0", "1", "2", "3"],
        visible_devices=None,
        mesh_shape=None,
    )

    assert visible_devices == "0,1,2,3"
    assert mesh_shape == (1, 8)


def test_resolve_runtime_device_selection_keeps_fleet_unshaped():
    visible_devices, mesh_shape = resolve_runtime_device_selection(
        backend="tt",
        execution_mode="fleet",
        device_list=["0", "1", "2", "3"],
        visible_devices=None,
        mesh_shape=None,
    )

    assert visible_devices == "0,1,2,3"
    assert mesh_shape is None


def test_resolve_runtime_device_selection_keeps_reference_unshaped():
    visible_devices, mesh_shape = resolve_runtime_device_selection(
        backend="reference",
        execution_mode="fleet",
        device_list=["0", "1", "2", "3"],
        visible_devices=None,
        mesh_shape=None,
    )

    assert visible_devices == "0,1,2,3"
    assert mesh_shape is None


def test_parallel_elapsed_uses_slowest_worker_timing_not_parent_wall_time():
    timings = [
        PartitionTiming(visible_device="0", batch_start=0, batch_end=1, elapsed_s=0.031),
        PartitionTiming(visible_device="1", batch_start=1, batch_end=2, elapsed_s=0.044),
    ]

    assert parallel_elapsed_s(timings) == 0.044


def test_resolve_execution_strategy_names_current_mesh_distribution():
    assert (
        resolve_execution_strategy(
            execution_mode="mesh",
        )
        == "mesh-replicated-spmd"
    )
    assert (
        resolve_execution_strategy(
            execution_mode="fleet",
        )
        == "fleet-independent"
    )


def test_open_ttnn_device_sets_1d_fabric_for_spmd_mesh(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeTTNN:
        CONFIG = SimpleNamespace(throw_exception_on_fallback=False)
        FabricConfig = SimpleNamespace(FABRIC_1D="fabric-1d", FABRIC_2D="fabric-2d")

        @staticmethod
        def set_fabric_config(config):
            calls.append(("set_fabric_config", config))

        @staticmethod
        def MeshShape(rows, cols):
            return ("mesh-shape", rows, cols)

        @staticmethod
        def open_mesh_device(mesh_shape):
            calls.append(("open_mesh_device", mesh_shape))
            return ("mesh-device", mesh_shape)

        @staticmethod
        def open_device(device_id=0):
            calls.append(("open_device", device_id))
            return ("device", device_id)

    monkeypatch.setitem(sys.modules, "ttnn", FakeTTNN)

    device = open_ttnn_device(mesh_shape=(1, 4))

    assert device == ("mesh-device", ("mesh-shape", 1, 4))
    assert FakeTTNN.CONFIG.throw_exception_on_fallback is True
    assert calls == [
        ("set_fabric_config", "fabric-1d"),
        ("open_mesh_device", ("mesh-shape", 1, 4)),
    ]


def test_open_ttnn_device_preserves_2d_fabric_for_explicit_2d_mesh(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeTTNN:
        CONFIG = SimpleNamespace(throw_exception_on_fallback=False)
        FabricConfig = SimpleNamespace(FABRIC_1D="fabric-1d", FABRIC_2D="fabric-2d")

        @staticmethod
        def set_fabric_config(config):
            calls.append(("set_fabric_config", config))

        @staticmethod
        def MeshShape(rows, cols):
            return ("mesh-shape", rows, cols)

        @staticmethod
        def open_mesh_device(mesh_shape):
            calls.append(("open_mesh_device", mesh_shape))
            return ("mesh-device", mesh_shape)

    monkeypatch.setitem(sys.modules, "ttnn", FakeTTNN)

    device = open_ttnn_device(mesh_shape=(2, 4))

    assert device == ("mesh-device", ("mesh-shape", 2, 4))
    assert calls == [
        ("set_fabric_config", "fabric-2d"),
        ("open_mesh_device", ("mesh-shape", 2, 4)),
    ]


def test_apply_tt_runtime_env_clears_slow_dispatch_by_default(monkeypatch):
    monkeypatch.setenv("TT_METAL_SLOW_DISPATCH_MODE", "1")
    monkeypatch.delenv("LENIA_TT_ALLOW_SLOW_DISPATCH", raising=False)

    previous = apply_tt_runtime_env()

    assert "TT_METAL_SLOW_DISPATCH_MODE" not in os.environ
    restore_tt_runtime_env(previous)
    assert os.environ["TT_METAL_SLOW_DISPATCH_MODE"] == "1"


def test_apply_tt_runtime_env_can_preserve_slow_dispatch_for_debug(monkeypatch):
    monkeypatch.setenv("TT_METAL_SLOW_DISPATCH_MODE", "1")
    monkeypatch.setenv("LENIA_TT_ALLOW_SLOW_DISPATCH", "1")

    previous = apply_tt_runtime_env()

    assert os.environ["TT_METAL_SLOW_DISPATCH_MODE"] == "1"
    restore_tt_runtime_env(previous)


def test_apply_tt_runtime_env_can_scope_mesh_dft(monkeypatch):
    monkeypatch.setenv("LENIA_TT_MESH_DFT", "previous")

    previous = apply_tt_runtime_env(mesh_dft=True)

    assert os.environ["LENIA_TT_MESH_DFT"] == "1"
    restore_tt_runtime_env(previous)
    assert os.environ["LENIA_TT_MESH_DFT"] == "previous"
