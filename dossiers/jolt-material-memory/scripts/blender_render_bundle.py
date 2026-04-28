from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, cast

try:
    import bpy  # type: ignore[import-not-found]
    import mathutils  # type: ignore[import-not-found]
    import numpy as np
except ModuleNotFoundError:
    bpy = cast(Any, None)
    mathutils = cast(Any, None)
    np = cast(Any, None)

Color4 = tuple[float, float, float, float]

MEMBRANE_COLOR: Color4 = (0.72, 0.90, 0.93, 1.0)
FIBER_COLOR: Color4 = (0.20, 0.52, 0.68, 1.0)
CORE_COOL: Color4 = (0.18, 0.48, 0.88, 1.0)
CORE_HOT: Color4 = (0.97, 0.47, 0.20, 1.0)
CONTACT_LOW: Color4 = (0.28, 0.73, 0.78, 1.0)
CONTACT_HIGH: Color4 = (0.98, 0.68, 0.21, 1.0)
GOAL_COLOR: Color4 = (0.95, 0.34, 0.23, 1.0)
SHOCK_COLOR: Color4 = (1.00, 0.82, 0.36, 1.0)


def _require_blender() -> None:
    if bpy is None or mathutils is None or np is None:
        raise RuntimeError("This script must run inside Blender's Python environment")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a jolt-material-memory research bundle")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["still", "animation"], default="still")
    parser.add_argument("--frame", type=int, default=-1)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution-x", type=int, default=1920)
    parser.add_argument("--resolution-y", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--look", choices=["hydrogel", "porcelain"], default="hydrogel")
    return parser.parse_args(argv)


def _lerp_color(left: Color4, right: Color4, amount: float) -> Color4:
    clamped = max(0.0, min(1.0, amount))
    return tuple(
        float((1.0 - clamped) * left_value + clamped * right_value)
        for left_value, right_value in zip(left, right, strict=True)
    )  # type: ignore[return-value]


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo + 1.0e-6:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _vector(values: np.ndarray) -> Any:
    assert mathutils is not None
    return mathutils.Vector((float(values[0]), float(values[1]), float(values[2])))


def _require_track(tracks: Any, key: str) -> np.ndarray:
    if key not in tracks:
        raise ValueError(f"bundle is missing required track {key}")
    return np.asarray(tracks[key], dtype=np.float32)


def _channel_range(
    manifest: dict[str, Any],
    key: str,
    *,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    channels = manifest.get("channels")
    if not isinstance(channels, dict):
        return fallback
    spec = channels.get(key)
    if not isinstance(spec, dict):
        return fallback
    raw_range = spec.get("range")
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        return fallback
    lo = raw_range[0]
    hi = raw_range[1]
    if isinstance(lo, bool) or isinstance(hi, bool):
        return fallback
    if not isinstance(lo, int | float) or not isinstance(hi, int | float):
        return fallback
    return float(lo), float(hi)


def _clear_scene() -> None:
    assert bpy is not None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)
    for block in bpy.data.curves:
        bpy.data.curves.remove(block)
    for block in bpy.data.cameras:
        bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        bpy.data.lights.remove(block)
    for block in bpy.data.objects:
        if block.users == 0:
            bpy.data.objects.remove(block)


def _configure_cycles(samples: int) -> None:
    assert bpy is not None
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.refresh_devices()
    devices = list(prefs.devices)
    if not devices:
        raise RuntimeError("No Cycles devices found for Blender")
    for device in devices:
        device.use = True

    scene.view_settings.exposure = -0.8
    scene.view_settings.gamma = 0.95


def _set_world() -> None:
    assert bpy is not None
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new(type="ShaderNodeOutputWorld")
    background = nodes.new(type="ShaderNodeBackground")
    background.inputs["Color"].default_value = (0.22, 0.24, 0.28, 1.0)
    background.inputs["Strength"].default_value = 0.08
    links.new(background.outputs["Background"], output.inputs["Surface"])


def _new_material(name: str) -> tuple[Any, Any, Any, Any]:
    assert bpy is not None
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (360, 0)
    return material, nodes, links, output


def _make_membrane_material(look: str) -> Any:
    material, nodes, links, output = _new_material("Membrane")
    shader = nodes.new(type="ShaderNodeBsdfPrincipled")
    shader.location = (60, 0)
    shader.inputs["Base Color"].default_value = (0.58, 0.84, 0.91, 1.0)
    shader.inputs["Roughness"].default_value = 0.12 if look == "hydrogel" else 0.28
    shader.inputs["Subsurface Weight"].default_value = 0.18 if look == "hydrogel" else 0.05
    shader.inputs["Subsurface Radius"].default_value = (0.50, 0.22, 0.16)
    shader.inputs["Transmission Weight"].default_value = 0.18 if look == "hydrogel" else 0.0
    shader.inputs["IOR"].default_value = 1.33 if look == "hydrogel" else 1.45
    shader.inputs["Coat Weight"].default_value = 0.22
    shader.inputs["Emission Color"].default_value = (0.08, 0.18, 0.22, 1.0)
    shader.inputs["Emission Strength"].default_value = 0.20
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _make_fiber_material(look: str) -> Any:
    material, nodes, links, output = _new_material("Fiber")
    shader = nodes.new(type="ShaderNodeBsdfPrincipled")
    shader.location = (0, 0)
    shader.inputs["Base Color"].default_value = FIBER_COLOR
    shader.inputs["Roughness"].default_value = 0.20 if look == "hydrogel" else 0.32
    shader.inputs["Metallic"].default_value = 0.0
    shader.inputs["Transmission Weight"].default_value = 0.02 if look == "hydrogel" else 0.0
    shader.inputs["Emission Color"].default_value = (0.28, 0.64, 0.92, 1.0)
    shader.inputs["Emission Strength"].default_value = 0.82
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _make_floor_material() -> Any:
    material, nodes, links, output = _new_material("Floor")
    shader = nodes.new(type="ShaderNodeBsdfPrincipled")
    shader.location = (0, 0)
    shader.inputs["Base Color"].default_value = (0.34, 0.37, 0.41, 1.0)
    shader.inputs["Roughness"].default_value = 0.62
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _make_core_material(name: str) -> dict[str, Any]:
    material, nodes, links, output = _new_material(name)
    shader = nodes.new(type="ShaderNodeBsdfPrincipled")
    shader.location = (0, 0)
    shader.inputs["Base Color"].default_value = CORE_COOL
    shader.inputs["Roughness"].default_value = 0.16
    shader.inputs["Transmission Weight"].default_value = 0.08
    shader.inputs["Coat Weight"].default_value = 0.18
    shader.inputs["Emission Color"].default_value = CORE_COOL
    shader.inputs["Emission Strength"].default_value = 0.8
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return {
        "material": material,
        "base_color": shader.inputs["Base Color"],
        "emission_color": shader.inputs["Emission Color"],
        "emission_strength": shader.inputs["Emission Strength"],
    }


def _make_emission_material(name: str, color: Color4, strength: float) -> dict[str, Any]:
    material, nodes, links, output = _new_material(name)
    emission = nodes.new(type="ShaderNodeEmission")
    emission.location = (0, 0)
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return {
        "material": material,
        "color": emission.inputs["Color"],
        "strength": emission.inputs["Strength"],
    }


def _append_material(obj: Any, material: Any) -> None:
    if not obj.data.materials:
        obj.data.materials.append(material)
    else:
        obj.data.materials[0] = material


def _add_light(
    *,
    name: str,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
    energy: float,
    color: tuple[float, float, float],
    size: float,
) -> None:
    assert bpy is not None
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light_data.color = color
    light_data.shape = "RECTANGLE"
    light_data.size = size
    light_object = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light_object)
    light_object.location = location
    light_object.rotation_euler = rotation


def _add_stage() -> None:
    assert bpy is not None
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.name = "Floor"
    floor.scale = (18.0, 10.0, 1.0)
    _append_material(floor, _make_floor_material())

    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(0.0, 8.0, 5.2),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    backdrop = bpy.context.object
    backdrop.name = "Backdrop"
    backdrop.scale = (18.0, 8.0, 1.0)
    _append_material(backdrop, _make_floor_material())


def _build_curve_object(
    name: str,
    body_count: int,
    *,
    bevel_depth: float,
    bevel_resolution: int,
    material: Any,
) -> tuple[Any, Any]:
    assert bpy is not None
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "3D"
    curve.fill_mode = "FULL"
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = bevel_resolution
    curve.use_fill_caps = True
    curve.resolution_u = 1
    curve.use_radius = True
    spline = curve.splines.new("POLY")
    spline.points.add(body_count - 1)
    for point in spline.points:
        point.co = (0.0, 0.0, 0.0, 1.0)
        point.radius = 1.0
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(material)
    return obj, spline


def _build_core_objects(body_count: int) -> list[dict[str, Any]]:
    assert bpy is not None
    visuals: list[dict[str, Any]] = []
    for index in range(body_count):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48,
            ring_count=24,
            radius=0.16,
            location=(0.0, 0.0, 0.0),
        )
        sphere = bpy.context.object
        sphere.name = f"Core.{index:02d}"
        bpy.ops.object.shade_smooth()
        material_data = _make_core_material(f"CoreMaterial.{index:02d}")
        _append_material(sphere, material_data["material"])
        visuals.append(
            {
                "object": sphere,
                "base_color": material_data["base_color"],
                "emission_color": material_data["emission_color"],
                "emission_strength": material_data["emission_strength"],
            }
        )
    return visuals


def _build_contact_objects(body_count: int) -> list[dict[str, Any]]:
    assert bpy is not None
    visuals: list[dict[str, Any]] = []
    for index in range(body_count):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32,
            radius=0.18,
            depth=0.04,
            location=(0.0, 0.02, 0.0),
        )
        disc = bpy.context.object
        disc.name = f"Footprint.{index:02d}"
        bpy.ops.object.shade_smooth()
        material_data = _make_emission_material(f"FootprintMaterial.{index:02d}", CONTACT_LOW, 0.0)
        _append_material(disc, material_data["material"])
        visuals.append(
            {
                "object": disc,
                "color": material_data["color"],
                "strength": material_data["strength"],
            }
        )
    return visuals


def _build_goal_marker() -> Any:
    assert bpy is not None
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=0.06,
        depth=4.4,
        location=(0.0, 2.2, 0.0),
    )
    marker = bpy.context.object
    marker.name = "GoalMarker"
    bpy.ops.object.shade_smooth()
    _append_material(marker, _make_emission_material("GoalMaterial", GOAL_COLOR, 8.0)["material"])
    return marker


def _build_damage_ring() -> dict[str, Any]:
    assert bpy is not None
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.8,
        minor_radius=0.04,
        major_segments=64,
        minor_segments=24,
        location=(0.0, 0.08, 0.0),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    ring = bpy.context.object
    ring.name = "DamageRing"
    bpy.ops.object.shade_smooth()
    material_data = _make_emission_material("DamageRingMaterial", SHOCK_COLOR, 0.0)
    _append_material(ring, material_data["material"])
    return {
        "object": ring,
        "color": material_data["color"],
        "strength": material_data["strength"],
    }


def _build_camera_rig() -> tuple[Any, Any]:
    assert bpy is not None
    target = bpy.data.objects.new("CameraTarget", None)
    bpy.context.collection.objects.link(target)

    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens = 62
    camera_data.dof.use_dof = True
    camera_data.dof.focus_object = target
    camera_data.dof.aperture_fstop = 3.2
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera, target


def _keyframe_socket(socket: Any, frame: int) -> None:
    socket.keyframe_insert(data_path="default_value", frame=frame)


def _set_linear_interpolation() -> None:
    assert bpy is not None
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    for action in bpy.data.actions:
        fcurves = getattr(action, "fcurves", None)
        if fcurves is None:
            continue
        for curve in fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"


def _animate_curve(
    spline: Any,
    positions: np.ndarray,
    radii: np.ndarray,
    *,
    frame: int,
) -> None:
    body_count = int(positions.shape[0])
    for index in range(body_count):
        point = spline.points[index]
        point.co = (
            float(positions[index, 0]),
            float(positions[index, 1]),
            float(positions[index, 2]),
            1.0,
        )
        point.radius = float(radii[index])
        point.keyframe_insert(data_path="co", frame=frame)
        point.keyframe_insert(data_path="radius", frame=frame)


def _animate_camera(camera: Any, target: Any, center: np.ndarray, *, frame: int) -> None:
    assert mathutils is not None
    target.location = (float(center[0]), float(center[1] + 0.35), float(center[2]))
    target.keyframe_insert(data_path="location", frame=frame)

    offset = mathutils.Vector((8.4, -10.8, 5.4))
    camera_position = mathutils.Vector(target.location) + offset
    camera.location = camera_position
    direction = mathutils.Vector(target.location) - camera_position
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.keyframe_insert(data_path="location", frame=frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=frame)


def _damage_frame(manifest: dict[str, Any]) -> int | None:
    windows = manifest.get("event_windows")
    timeline = manifest.get("timeline")
    if not isinstance(windows, dict) or not isinstance(timeline, dict):
        return None
    raw_step = windows.get("damage_step")
    stride = timeline.get("stride")
    if isinstance(raw_step, bool) or isinstance(stride, bool):
        return None
    if not isinstance(raw_step, int | float) or not isinstance(stride, int | float):
        return None
    stride_value = max(1, int(stride))
    return 1 + int(raw_step) // stride_value


def _animate_scene(
    manifest: dict[str, Any],
    tracks: Any,
    membrane_spline: Any,
    fiber_spline: Any,
    core_objects: list[dict[str, Any]],
    contact_objects: list[dict[str, Any]],
    goal_marker: Any,
    damage_ring: dict[str, Any],
    camera: Any,
    camera_target: Any,
) -> int:
    body_translation = _require_track(tracks, "body_translation")
    body_plasticity = _require_track(tracks, "body_plasticity")
    body_stiffness = _require_track(tracks, "body_stiffness")
    body_contact = _require_track(tracks, "body_contact")
    body_friction = _require_track(tracks, "body_friction")
    goal_x = _require_track(tracks, "goal_x")
    com_translation = _require_track(tracks, "com_translation")

    frame_count = int(body_translation.shape[0])
    if frame_count <= 0:
        raise ValueError("bundle contains no animation frames")

    plastic_lo, plastic_hi = _channel_range(manifest, "body_plasticity", fallback=(0.0, 1.0))
    stiffness_lo, stiffness_hi = _channel_range(manifest, "body_stiffness", fallback=(0.0, 1.0))
    friction_lo, friction_hi = _channel_range(manifest, "body_friction", fallback=(0.0, 1.0))
    damage_frame = _damage_frame(manifest)

    for frame_index in range(frame_count):
        frame = frame_index + 1
        positions = body_translation[frame_index]

        plastic_norm = np.asarray(
            [
                _normalize(float(value), plastic_lo, plastic_hi)
                for value in body_plasticity[frame_index]
            ],
            dtype=np.float32,
        )
        stiffness_norm = np.asarray(
            [
                _normalize(float(value), stiffness_lo, stiffness_hi)
                for value in body_stiffness[frame_index]
            ],
            dtype=np.float32,
        )
        friction_norm = np.asarray(
            [
                _normalize(float(value), friction_lo, friction_hi)
                for value in body_friction[frame_index]
            ],
            dtype=np.float32,
        )

        membrane_radii = 1.10 + 0.55 * plastic_norm
        fiber_radii = 0.38 + 0.28 * stiffness_norm
        _animate_curve(membrane_spline, positions, membrane_radii, frame=frame)
        _animate_curve(fiber_spline, positions, fiber_radii, frame=frame)

        for index, visual in enumerate(core_objects):
            core_object = visual["object"]
            core_plastic = float(plastic_norm[index])
            core_object.location = _vector(positions[index])
            scale = 0.58 + 0.72 * core_plastic
            core_object.scale = (scale, scale, scale)
            core_object.keyframe_insert(data_path="location", frame=frame)
            core_object.keyframe_insert(data_path="scale", frame=frame)

            color = _lerp_color(CORE_COOL, CORE_HOT, core_plastic)
            visual["base_color"].default_value = color
            visual["emission_color"].default_value = color
            visual["emission_strength"].default_value = 0.22 + 2.20 * core_plastic
            _keyframe_socket(visual["base_color"], frame)
            _keyframe_socket(visual["emission_color"], frame)
            _keyframe_socket(visual["emission_strength"], frame)

        for index, visual in enumerate(contact_objects):
            disc = visual["object"]
            disc.location = (
                float(positions[index, 0]),
                0.03,
                float(positions[index, 2]),
            )
            contact_value = float(body_contact[frame_index, index])
            friction_value = float(friction_norm[index])
            disc_scale = 0.22 + 0.82 * contact_value
            disc.scale = (disc_scale, disc_scale, 1.0)
            disc.keyframe_insert(data_path="location", frame=frame)
            disc.keyframe_insert(data_path="scale", frame=frame)

            contact_color = _lerp_color(CONTACT_LOW, CONTACT_HIGH, friction_value)
            visual["color"].default_value = contact_color
            visual["strength"].default_value = 0.04 + 3.00 * contact_value
            _keyframe_socket(visual["color"], frame)
            _keyframe_socket(visual["strength"], frame)

        goal_marker.location = (float(goal_x[frame_index]), 2.2, 0.0)
        goal_marker.keyframe_insert(data_path="location", frame=frame)

        ring_object = damage_ring["object"]
        if damage_frame is not None and frame >= damage_frame and frame <= damage_frame + 18:
            phase = float(frame - damage_frame)
            scale = 0.85 + 0.28 * phase
            ring_object.location = (
                float(com_translation[min(frame_index, frame_count - 1), 0]),
                0.08,
                float(com_translation[min(frame_index, frame_count - 1), 2]),
            )
            ring_object.scale = (scale, scale, 1.0)
            damage_ring["strength"].default_value = max(0.0, 4.8 - 0.24 * phase)
        else:
            ring_object.location = (0.0, 0.08, 0.0)
            ring_object.scale = (0.01, 0.01, 0.01)
            damage_ring["strength"].default_value = 0.0
        ring_object.keyframe_insert(data_path="location", frame=frame)
        ring_object.keyframe_insert(data_path="scale", frame=frame)
        _keyframe_socket(damage_ring["strength"], frame)

        _animate_camera(camera, camera_target, com_translation[frame_index], frame=frame)

    return frame_count


def _load_bundle(bundle_dir: Path) -> tuple[dict[str, Any], Any]:
    assert np is not None
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    tracks = np.load(bundle_dir / "tracks.npz")
    return manifest, tracks


def _configure_output(out_path: Path, fps: int, resolution_x: int, resolution_y: int) -> None:
    assert bpy is not None
    scene = bpy.context.scene
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out_path)


def _render_still(frame: int) -> None:
    assert bpy is not None
    bpy.context.scene.frame_set(frame)
    bpy.ops.render.render(write_still=True)


def _render_animation(frame_prefix: Path) -> None:
    assert bpy is not None
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(frame_prefix)
    bpy.ops.render.render(animation=True)


def main() -> int:
    _require_blender()
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = _parse_args(argv)

    bundle_dir = Path(args.bundle_dir).resolve()
    out_path = Path(args.out).resolve()
    manifest, tracks = _load_bundle(bundle_dir)
    body_count = int(manifest["scene"]["body_count"])

    _clear_scene()
    _configure_cycles(args.samples)
    _set_world()
    _add_stage()
    _add_light(
        name="KeyLight",
        location=(4.0, -7.2, 6.8),
        rotation=(math.radians(58.0), 0.0, math.radians(20.0)),
        energy=2400.0,
        color=(1.0, 0.93, 0.89),
        size=8.4,
    )
    _add_light(
        name="RimLight",
        location=(-7.5, 3.0, 6.2),
        rotation=(math.radians(108.0), 0.0, math.radians(-118.0)),
        energy=1400.0,
        color=(0.76, 0.90, 1.0),
        size=6.0,
    )
    _add_light(
        name="FillLight",
        location=(0.0, -1.5, 9.5),
        rotation=(math.radians(180.0), 0.0, 0.0),
        energy=420.0,
        color=(1.0, 1.0, 1.0),
        size=10.0,
    )

    membrane_material = _make_membrane_material(args.look)
    fiber_material = _make_fiber_material(args.look)
    _membrane_object, membrane_spline = _build_curve_object(
        "MembraneSpine",
        body_count,
        bevel_depth=0.20,
        bevel_resolution=14,
        material=membrane_material,
    )
    _fiber_object, fiber_spline = _build_curve_object(
        "FiberSpine",
        body_count,
        bevel_depth=0.09,
        bevel_resolution=10,
        material=fiber_material,
    )
    core_objects = _build_core_objects(body_count)
    contact_objects = _build_contact_objects(body_count)
    goal_marker = _build_goal_marker()
    damage_ring = _build_damage_ring()
    camera, camera_target = _build_camera_rig()

    frame_count = _animate_scene(
        manifest,
        tracks,
        membrane_spline,
        fiber_spline,
        core_objects,
        contact_objects,
        goal_marker,
        damage_ring,
        camera,
        camera_target,
    )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frame_count
    _configure_output(out_path, args.fps, args.resolution_x, args.resolution_y)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _set_linear_interpolation()

    if args.mode == "still":
        frame = frame_count if args.frame < 0 else max(1, min(args.frame, frame_count))
        _render_still(frame)
    else:
        _render_animation(out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
