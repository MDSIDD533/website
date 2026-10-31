from __future__ import annotations

import json
import math
import random
from typing import Any, Callable, Iterable

from .planner import Blender3DRequest, THEMES, quality_profile

BUILDER_VERSION = "blender3d-scene-v3"


def _rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    text = value.lstrip("#")
    if len(text) != 6:
        return (0.5, 0.5, 0.5, alpha)
    return tuple(int(text[index : index + 2], 16) / 255.0 for index in (0, 2, 4)) + (alpha,)  # type: ignore[return-value]


def _safe_set(obj: Any, name: str, value: Any) -> None:
    try:
        setattr(obj, name, value)
    except Exception:
        pass


class SceneFactory:
    """Small optimized factory around Blender's Python API.

    Mesh datablocks are shared per primitive/material pair.  That keeps the
    procedural scenes useful and legible without paying for thousands of
    unique meshes during a CPU Cycles render.
    """

    def __init__(self, plan: dict[str, Any]):
        try:
            import bpy  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised only without Blender
            raise RuntimeError(f"Blender Python module bpy is unavailable: {exc}") from exc
        self.bpy = bpy
        self.plan = plan
        self.request = Blender3DRequest.from_dict(plan.get("request") or {})
        self.theme = self.request.theme if self.request.theme != "auto" else str((plan.get("topic") or {}).get("theme") or "abstract_shapes")
        self.theme_info = THEMES[self.theme]
        self.palette = (plan.get("topic") or {}).get("palette") or self.theme_info.palette
        # The plan stores palette through ThemeInfo in previews, but the
        # canonical worker spec may omit it; theme palette is authoritative.
        self.palette = self.theme_info.palette
        self.duration = float(self.request.duration_sec)
        self.fps = int(self.request.fps)
        self.total_frames = max(2, round(self.duration * self.fps))
        self.intensity = float(self.request.intensity)
        self.rng = random.Random(int(self.request.seed) + sum(ord(char) for char in self.theme))
        self.materials: dict[str, Any] = {}
        self.base_meshes: dict[str, Any] = {}
        self.material_meshes: dict[tuple[str, str], Any] = {}
        self._reset()
        self._common_materials()

    # ------------------------------------------------------------------ core
    def _reset(self) -> None:
        bpy = self.bpy
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.collection = bpy.data.collections.new("SIDD_Dynamic3D")
        self.scene.collection.children.link(self.collection)

    def frame(self, sec: float) -> int:
        ratio = 0.0 if self.duration <= 0 else max(0.0, min(1.0, float(sec) / self.duration))
        return 1 + round(ratio * (self.total_frames - 1))

    def at(self, fraction: float) -> float:
        return max(0.0, min(1.0, float(fraction))) * self.duration

    def mat(
        self,
        name: str,
        color: Any,
        *,
        roughness: float = 0.82,
        metallic: float = 0.0,
        alpha: float = 1.0,
        emission: Any = None,
        emission_strength: float = 0.0,
    ) -> Any:
        if name in self.materials:
            return self.materials[name]
        bpy = self.bpy
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        rgba = _rgba(color, alpha) if isinstance(color, str) else tuple(color)
        if bsdf:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = metallic
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            if emission is not None:
                emit = _rgba(emission, 1.0) if isinstance(emission, str) else tuple(emission)
                if "Emission Color" in bsdf.inputs:
                    bsdf.inputs["Emission Color"].default_value = emit
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = emission_strength
        material.diffuse_color = rgba
        if alpha < 1:
            _safe_set(material, "blend_method", "BLEND")
            _safe_set(material, "shadow_method", "NONE")
        self.materials[name] = material
        return material

    def vertex_material(self, name: str, *, roughness: float = 0.9) -> Any:
        if name in self.materials:
            return self.materials[name]
        bpy = self.bpy
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        attr = nodes.new(type="ShaderNodeAttribute")
        attr.attribute_name = "Col"
        if bsdf:
            bsdf.inputs["Roughness"].default_value = roughness
            material.node_tree.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
        self.materials[name] = material
        return material

    def _common_materials(self) -> None:
        palette = self.palette
        self.M = {
            "sky": self.mat("Sky", palette["sky"], roughness=1.0),
            "ground": self.mat("Ground", palette["ground"], roughness=0.95),
            "accent": self.mat("Accent", palette["accent"], roughness=0.62),
            "water": self.mat("Water", palette["water"], roughness=0.28, metallic=0.05),
            "white": self.mat("White", "#F2F0E8", roughness=0.72),
            "black": self.mat("Black", "#111318", roughness=0.7),
            "dark": self.mat("DarkMetal", "#2E3338", roughness=0.55, metallic=0.38),
            "metal": self.mat("Metal", "#707880", roughness=0.42, metallic=0.55),
            "olive": self.mat("Olive", "#4D5A3A", roughness=0.83),
            "olive_light": self.mat("OliveLight", "#667254", roughness=0.86),
            "sand": self.mat("Sand", "#B9A37B", roughness=0.96),
            "wood": self.mat("Wood", "#6B4A2F", roughness=0.9),
            "stone": self.mat("Stone", "#8C8378", roughness=0.94),
            "brick": self.mat("Brick", "#7A6258", roughness=0.95),
            "glass": self.mat("GlassDark", "#18222A", roughness=0.22, metallic=0.18),
            "leaf": self.mat("Leaf", "#3F7A3D", roughness=0.92),
            "leaf_light": self.mat("LeafLight", "#62A653", roughness=0.9),
            "skin": self.mat("Skin", "#B98B68", roughness=0.78),
            "red": self.mat("SignalRed", "#B23A2E", roughness=0.68),
            "gold": self.mat("Gold", "#D9A441", roughness=0.35, metallic=0.55),
            "cyan": self.mat("Cyan", "#2D9DB6", roughness=0.45),
            "blue": self.mat("Blue", "#315B9E", roughness=0.52),
            "smoke": self.mat("Smoke", "#555A5E", roughness=1.0, alpha=0.42),
            "smoke_light": self.mat("SmokeLight", "#9BA0A3", roughness=1.0, alpha=0.34),
            "fire": self.mat("Fire", "#FF7A22", roughness=1.0, alpha=0.82, emission="#FF6A00", emission_strength=3.2),
            "flash": self.mat("Flash", "#FFD166", roughness=1.0, alpha=0.9, emission="#FFC233", emission_strength=5.0),
            "glow": self.mat("Glow", palette["accent"], roughness=1.0, emission=palette["accent"], emission_strength=2.6),
            "cloud": self.mat("Cloud", "#E8EBEC", roughness=1.0, alpha=0.78),
        }

    def _base_mesh(self, kind: str) -> Any:
        if kind in self.base_meshes:
            return self.base_meshes[kind]
        bpy = self.bpy
        ops = bpy.ops.mesh
        if kind == "cube":
            ops.primitive_cube_add(size=1, location=(0, 0, -1000))
        elif kind == "sphere":
            ops.primitive_uv_sphere_add(segments=10, ring_count=7, radius=0.5, location=(0, 0, -1000))
        elif kind == "cylinder":
            ops.primitive_cylinder_add(vertices=10, radius=0.5, depth=1, location=(0, 0, -1000))
        elif kind == "cone":
            ops.primitive_cone_add(vertices=10, radius1=0.5, radius2=0.0, depth=1, location=(0, 0, -1000))
        elif kind == "torus":
            ops.primitive_torus_add(major_segments=14, minor_segments=6, major_radius=0.5, minor_radius=0.08, location=(0, 0, -1000))
        else:
            raise ValueError(f"Unknown primitive: {kind}")
        obj = bpy.context.object
        mesh = obj.data
        mesh.name = f"Base_{kind}"
        mesh.use_fake_user = True
        bpy.data.objects.remove(obj, do_unlink=True)
        self.base_meshes[kind] = mesh
        return mesh

    def _mesh_for(self, kind: str, material: Any) -> Any:
        key = (kind, material.name if material else "")
        if key in self.material_meshes:
            return self.material_meshes[key]
        mesh = self._base_mesh(kind).copy()
        mesh.name = f"{kind}_{material.name if material else 'Plain'}"
        mesh.use_fake_user = True
        if material:
            mesh.materials.append(material)
        self.material_meshes[key] = mesh
        return mesh

    def add(self, kind: str, name: str, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), material: Any = None, parent: Any = None) -> Any:
        obj = self.bpy.data.objects.new(name, self._mesh_for(kind, material or self.M["white"]))
        self.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = rot
        obj.scale = scale
        if parent is not None:
            obj.parent = parent
        return obj

    def empty(self, name: str, loc=(0, 0, 0), rot=(0, 0, 0), parent: Any = None) -> Any:
        obj = self.bpy.data.objects.new(name, None)
        self.collection.objects.link(obj)
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.25
        obj.location = loc
        obj.rotation_euler = rot
        if parent is not None:
            obj.parent = parent
        return obj

    def box(self, name, loc, scale, material, rot=(0, 0, 0), parent=None):
        return self.add("cube", name, loc, scale, rot, material, parent)

    def sphere(self, name, loc, scale, material, rot=(0, 0, 0), parent=None):
        return self.add("sphere", name, loc, scale, rot, material, parent)

    def cylinder(self, name, loc, scale, material, rot=(0, 0, 0), parent=None):
        return self.add("cylinder", name, loc, scale, rot, material, parent)

    def cone(self, name, loc, scale, material, rot=(0, 0, 0), parent=None):
        return self.add("cone", name, loc, scale, rot, material, parent)

    def torus(self, name, loc, scale, material, rot=(0, 0, 0), parent=None):
        return self.add("torus", name, loc, scale, rot, material, parent)

    def beam(self, name: str, start, end, thickness: float, material: Any, parent: Any = None) -> Any:
        from mathutils import Vector  # type: ignore

        a, b = Vector(start), Vector(end)
        direction = b - a
        length = max(0.001, direction.length)
        rotation = direction.to_track_quat("Z", "Y").to_euler()
        return self.cylinder(name, tuple((a + b) / 2), (thickness, thickness, length), material, tuple(rotation), parent)

    # ------------------------------------------------------------- animation
    def key(self, obj: Any, attr: str, sec: float, value: Any) -> None:
        frame = self.frame(sec)
        self.scene.frame_set(frame)
        setattr(obj, attr, value)
        obj.keyframe_insert(data_path=attr, frame=frame)

    def keys(self, obj: Any, attr: str, pairs: Iterable[tuple[float, Any]], interpolation: str = "BEZIER") -> None:
        for sec, value in pairs:
            self.key(obj, attr, sec, value)
        self.set_interpolation(obj, interpolation)

    def set_interpolation(self, obj: Any, interpolation: str = "BEZIER") -> None:
        action = getattr(getattr(obj, "animation_data", None), "action", None)
        if not action:
            return
        for fcurve in action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation

    def set_cycles(self, obj: Any) -> None:
        action = getattr(getattr(obj, "animation_data", None), "action", None)
        if not action:
            return
        for fcurve in action.fcurves:
            if not any(mod.type == "CYCLES" for mod in fcurve.modifiers):
                mod = fcurve.modifiers.new(type="CYCLES")
                mod.mode_before = "REPEAT"
                mod.mode_after = "REPEAT"

    def oscillate_rotation(self, obj: Any, axis: int, amplitude: float, period_sec: float, phase: float = 0.0) -> None:
        base = list(obj.rotation_euler)
        pairs = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            rot = list(base)
            rot[axis] = base[axis] + amplitude * math.sin(phase + math.tau * fraction)
            pairs.append((period_sec * fraction, tuple(rot)))
        self.keys(obj, "rotation_euler", pairs, "SINE")
        self.set_cycles(obj)

    def oscillate_location_z(self, obj: Any, amplitude: float, period_sec: float, phase: float = 0.0) -> None:
        base = tuple(obj.location)
        pairs = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            pairs.append((period_sec * fraction, (base[0], base[1], base[2] + amplitude * math.sin(phase + math.tau * fraction))))
        self.keys(obj, "location", pairs, "SINE")
        self.set_cycles(obj)

    def move(self, obj: Any, start_sec: float, end_sec: float, end_location, *, start_location=None, interpolation: str = "BEZIER") -> None:
        start = tuple(start_location or obj.location)
        self.keys(obj, "location", [(start_sec, start), (end_sec, tuple(end_location))], interpolation)

    def spin(self, obj: Any, axis: int, turns: float, start_sec: float = 0.0, end_sec: float | None = None) -> None:
        base = list(obj.rotation_euler)
        end = list(base)
        end[axis] += math.tau * turns
        self.keys(obj, "rotation_euler", [(start_sec, tuple(base)), (self.duration if end_sec is None else end_sec, tuple(end))], "LINEAR")

    # -------------------------------------------------------------- geometry
    def grid_terrain(
        self,
        name: str,
        *,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
        nx: int,
        ny: int,
        height_fn: Callable[[float, float], float],
        color_fn: Callable[[float, float, float], tuple[float, float, float, float]],
        material: Any,
        loc=(0, 0, 0),
    ) -> Any:
        bpy = self.bpy
        verts: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []
        for iy in range(ny + 1):
            y = y_range[0] + (y_range[1] - y_range[0]) * iy / ny
            for ix in range(nx + 1):
                x = x_range[0] + (x_range[1] - x_range[0]) * ix / nx
                z = height_fn(x, y)
                verts.append((x, y, z))
                colors.append(color_fn(x, y, z))
        faces: list[tuple[int, int, int, int]] = []
        row = nx + 1
        for iy in range(ny):
            for ix in range(nx):
                a = iy * row + ix
                faces.append((a, a + 1, a + row + 1, a + row))
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        color_layer = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
        for index, color in enumerate(colors):
            color_layer.data[index].color = color
        if material:
            mesh.materials.append(material)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        obj = bpy.data.objects.new(name, mesh)
        self.collection.objects.link(obj)
        obj.location = loc
        return obj

    def setup_world_and_lights(self, *, world_strength: float = 0.72, sun_energy: float = 3.0, sun_rotation=(math.radians(48), math.radians(12), math.radians(-32)), sun_color="#FFF1D6", fill_energy: float = 420.0) -> None:
        bpy = self.bpy
        world = bpy.data.worlds.new("DynamicWorld") if not self.scene.world else self.scene.world
        self.scene.world = world
        world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs[0].default_value = _rgba(self.palette["sky"], 1.0)
            background.inputs[1].default_value = world_strength
        sun_data = bpy.data.lights.new("KeySun", type="SUN")
        sun_data.energy = sun_energy
        sun_data.color = _rgba(sun_color)[:3]
        sun = bpy.data.objects.new("KeySun", sun_data)
        self.collection.objects.link(sun)
        sun.rotation_euler = sun_rotation
        fill_data = bpy.data.lights.new("CameraFill", type="AREA")
        fill_data.energy = fill_energy
        fill_data.use_shadow = False
        fill_data.shape = "RECTANGLE"
        fill_data.size = 42
        fill_data.size_y = 22
        fill = bpy.data.objects.new("CameraFill", fill_data)
        self.collection.objects.link(fill)
        fill.location = (0, -52, 28)
        fill.rotation_euler = (math.radians(62), 0, 0)

    def setup_mist_compositor(self, *, color: str = "#2A3D33", max_factor: float = 0.52, start: float = 30.0, depth: float = 100.0) -> None:
        """Apply depth fog in Blender's compositor instead of fog geometry.

        A Cycles Mist pass is essentially free beside the one-sample Turbo
        render, creates continuous aerial perspective, and avoids the hard
        silhouettes/transparent-bounce cost of giant alpha ellipsoids.
        """
        scene = self.scene
        if scene.world:
            _safe_set(scene.world.mist_settings, "use_mist", True)
            _safe_set(scene.world.mist_settings, "start", float(start))
            _safe_set(scene.world.mist_settings, "depth", float(depth))
            _safe_set(scene.world.mist_settings, "falloff", "QUADRATIC")
        _safe_set(self.bpy.context.view_layer, "use_pass_mist", True)
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()

        render_layers = tree.nodes.new(type="CompositorNodeRLayers")
        render_layers.location = (-420, 0)
        map_range = tree.nodes.new(type="CompositorNodeMapRange")
        map_range.location = (-180, -190)
        map_range.inputs[1].default_value = 0.0
        map_range.inputs[2].default_value = 1.0
        map_range.inputs[3].default_value = 0.03
        map_range.inputs[4].default_value = float(max_factor)
        _safe_set(map_range, "use_clamp", True)

        fog_color = tree.nodes.new(type="CompositorNodeRGB")
        fog_color.location = (-180, 150)
        fog_color.outputs[0].default_value = _rgba(color, 1.0)

        mix = tree.nodes.new(type="CompositorNodeMixRGB")
        mix.location = (40, 0)
        _safe_set(mix, "blend_type", "MIX")
        _safe_set(mix, "use_clamp", True)

        composite = tree.nodes.new(type="CompositorNodeComposite")
        composite.location = (260, 0)

        tree.links.new(render_layers.outputs["Mist"], map_range.inputs[0])
        tree.links.new(map_range.outputs[0], mix.inputs[0])
        tree.links.new(render_layers.outputs["Image"], mix.inputs[1])
        tree.links.new(fog_color.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], composite.inputs["Image"])
        tree.links.new(render_layers.outputs["Alpha"], composite.inputs["Alpha"])

    def point_light(self, name: str, loc, color: str, energy: float, parent: Any = None) -> Any:
        data = self.bpy.data.lights.new(name, type="POINT")
        data.energy = energy
        data.color = _rgba(color)[:3]
        data.use_shadow = False
        data.shadow_soft_size = 0.35
        obj = self.bpy.data.objects.new(name, data)
        self.collection.objects.link(obj)
        obj.location = loc
        if parent is not None:
            obj.parent = parent
        return obj

    def setup_camera(
        self,
        positions: list[tuple[float, tuple[float, float, float]]],
        targets: list[tuple[float, tuple[float, float, float]]],
        lens_pairs: list[tuple[float, float]] | None = None,
        *,
        focus_pairs: list[tuple[float, float]] | None = None,
        fstop: float | None = None,
    ) -> Any:
        bpy = self.bpy

        def _interpolate(points: list[tuple[float, tuple[float, float, float]]], fraction: float) -> tuple[float, float, float]:
            if not points:
                return (0.0, 0.0, 0.0)
            if fraction <= points[0][0]:
                return tuple(float(value) for value in points[0][1])  # type: ignore[return-value]
            if fraction >= points[-1][0]:
                return tuple(float(value) for value in points[-1][1])  # type: ignore[return-value]
            for (start_fraction, start), (end_fraction, end) in zip(points, points[1:]):
                if start_fraction <= fraction <= end_fraction:
                    ratio = 0.0 if end_fraction == start_fraction else (fraction - start_fraction) / (end_fraction - start_fraction)
                    return tuple(float(start[index] + (end[index] - start[index]) * ratio) for index in range(3))  # type: ignore[return-value]
            return tuple(float(value) for value in points[-1][1])  # type: ignore[return-value]

        if self.request.camera_move == "orbit" and targets:
            center = targets[len(targets) // 2][1]
            orbit_positions = []
            for index, fraction in enumerate((0.0, 0.28, 0.56, 0.82, 1.0)):
                angle = math.radians(-135 + index * 42)
                orbit_positions.append((fraction, (center[0] + 48 * math.cos(angle), center[1] + 48 * math.sin(angle), center[2] + 14 + index % 2 * 4)))
            positions = orbit_positions
            targets = [(fraction, center) for fraction, _ in orbit_positions]
        elif self.request.camera_move == "tracking" and targets:
            center = targets[len(targets) // 2][1]
            targets = [(fraction, center) for fraction, _ in positions]
        elif self.request.camera_move == "drone" and targets:
            # Keep authored compositions, but lift low/handheld-feeling keys
            # into a high aerial path and pull them slightly away from the
            # target. Explicit Jungle War keys are already above this floor.
            aerial_positions: list[tuple[float, tuple[float, float, float]]] = []
            for fraction, position in positions:
                look_at = _interpolate(targets, fraction)
                aerial_positions.append(
                    (
                        fraction,
                        (
                            look_at[0] + (position[0] - look_at[0]) * 1.10,
                            look_at[1] + (position[1] - look_at[1]) * 1.10,
                            max(float(position[2]), float(look_at[2]) + 14.0),
                        ),
                    )
                )
            positions = aerial_positions

        target = self.empty("CameraTarget", targets[0][1])
        camera_data = bpy.data.cameras.new("Blender3DCamera")
        camera_data.lens = 36
        camera_data.clip_start = 0.5
        camera_data.clip_end = 1000
        # Real Cycles depth of field, focused on the authored subject plane.
        # The f-stop is shallow enough to soften the far background without
        # making the miniature-scale action unreadable at one Turbo sample.
        _safe_set(camera_data.dof, "use_dof", True)
        _safe_set(camera_data.dof, "aperture_fstop", float(fstop if fstop is not None else (2.2 if self.theme == "last_survivor" else (2.8 if self.theme == "jungle_war" else 3.5))))
        camera = bpy.data.objects.new("Blender3DCamera", camera_data)
        self.collection.objects.link(camera)
        camera.location = positions[0][1]
        camera["sidd_camera_move"] = self.request.camera_move
        camera["sidd_camera_style"] = (
            "smooth aerial drone path with Cycles depth of field"
            if self.request.camera_move == "drone"
            else (
                "low rear tracking camera behind the silhouetted hero; face never shown"
                if self.request.camera_move == "hero_tracking"
                else self.request.camera_move
            )
        )
        constraint = camera.constraints.new(type="TRACK_TO")
        constraint.target = target
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"

        self.keys(camera, "location", [(self.at(fraction), position) for fraction, position in positions], "BEZIER")
        self.keys(target, "location", [(self.at(fraction), position) for fraction, position in targets], "BEZIER")
        for animated in (camera, target):
            action = getattr(getattr(animated, "animation_data", None), "action", None)
            if action:
                for fcurve in action.fcurves:
                    for point in fcurve.keyframe_points:
                        _safe_set(point, "handle_left_type", "AUTO_CLAMPED")
                        _safe_set(point, "handle_right_type", "AUTO_CLAMPED")

        if focus_pairs is None:
            focus_pairs = []
            for fraction, position in positions:
                look_at = _interpolate(targets, fraction)
                distance = math.dist(position, look_at)
                focus_pairs.append((fraction, max(1.0, distance * 0.94)))
        for fraction, distance in focus_pairs:
            frame = self.frame(self.at(fraction))
            self.scene.frame_set(frame)
            _safe_set(camera_data.dof, "focus_distance", float(distance))
            try:
                camera_data.keyframe_insert(data_path="dof.focus_distance", frame=frame)
            except Exception:
                try:
                    camera_data.dof.keyframe_insert(data_path="focus_distance", frame=frame)
                except Exception:
                    pass

        for fraction, lens in (lens_pairs or [(0.0, 35.0), (0.55, 46.0), (1.0, 40.0)]):
            frame = self.frame(self.at(fraction))
            self.scene.frame_set(frame)
            camera_data.lens = lens
            camera_data.keyframe_insert(data_path="lens", frame=frame)
        self.set_interpolation(camera_data, "BEZIER")
        self.scene.camera = camera
        return camera

    # ------------------------------------------------------------ characters
    def make_person(
        self,
        name: str,
        loc,
        heading: float,
        *,
        uniform: Any = None,
        scale: float = 1.0,
        weapon: str = "rifle",
        phase: float = 0.0,
        move_distance: float = 0.0,
        start_fraction: float = 0.05,
        end_fraction: float = 0.9,
        helmet: bool = True,
        end_z: float | None = None,
    ) -> Any:
        uniform = uniform or self.M["olive"]
        root = self.empty(name, loc, (0, 0, heading))
        root.scale = (scale, scale, scale)
        body = self.empty(f"{name}_Body", (0, 0, 0), parent=root)
        self.box(f"{name}_Torso", (0, 0, 0.84), (0.31, 0.48, 0.56), uniform, parent=body)
        self.box(f"{name}_Belt", (0, 0, 0.58), (0.34, 0.5, 0.1), self.M["black"], parent=body)
        self.sphere(f"{name}_Head", (0, 0, 1.26), (0.25, 0.25, 0.28), self.M["skin"], parent=body)
        if helmet:
            self.sphere(f"{name}_Helmet", (-0.01, 0, 1.39), (0.32, 0.34, 0.16), uniform, parent=body)
        self.box(f"{name}_Pack", (-0.22, 0, 0.86), (0.15, 0.34, 0.42), self.M["olive_light"], parent=body)

        limbs: list[Any] = []
        for side, sign in (("L", 1), ("R", -1)):
            leg = self.empty(f"{name}_Leg{side}", (0, 0.13 * sign, 0.56), parent=body)
            self.box(f"{name}_LegMesh{side}", (0, 0, -0.25), (0.16, 0.17, 0.52), uniform, parent=leg)
            self.box(f"{name}_Boot{side}", (0.06, 0, -0.51), (0.28, 0.16, 0.1), self.M["black"], parent=leg)
            limbs.append(leg)
            arm = self.empty(f"{name}_Arm{side}", (0, 0.29 * sign, 1.03), parent=body)
            self.box(f"{name}_ArmMesh{side}", (0, 0, -0.2), (0.14, 0.15, 0.44), uniform, parent=arm)
            limbs.append(arm)

        if weapon == "rifle":
            gun = self.empty(f"{name}_Rifle", (0.22, -0.2, 0.94), parent=body)
            self.box(f"{name}_RifleBody", (0.12, 0, 0), (0.62, 0.07, 0.1), self.M["wood"], parent=gun)
            self.cylinder(f"{name}_Barrel", (0.52, 0, 0.02), (0.045, 0.045, 0.42), self.M["dark"], (0, math.radians(90), 0), gun)
        elif weapon == "spear":
            spear = self.empty(f"{name}_Spear", (0.16, -0.3, 0.8), parent=body)
            self.cylinder(f"{name}_Shaft", (0, 0, 0.2), (0.045, 0.045, 1.35), self.M["wood"], parent=spear)
            self.cone(f"{name}_SpearTip", (0, 0, 0.98), (0.12, 0.12, 0.24), self.M["metal"], parent=spear)

        stride = 0.72 / max(0.5, self.fps / 24.0)
        self.oscillate_rotation(limbs[0], 1, 0.48, stride, phase)
        self.oscillate_rotation(limbs[2], 1, 0.48, stride, phase + math.pi)
        self.oscillate_rotation(limbs[1], 1, 0.34, stride, phase + math.pi)
        self.oscillate_rotation(limbs[3], 1, 0.34, stride, phase)
        self.oscillate_location_z(body, 0.035, stride / 2, phase)
        if move_distance:
            distance = move_distance * self.intensity
            end = (
                loc[0] + distance * math.cos(heading),
                loc[1] + distance * math.sin(heading),
                loc[2] if end_z is None else end_z,
            )
            self.move(root, self.at(start_fraction), self.at(end_fraction), end, start_location=loc)
        return root

    def make_hero_soldier(
        self,
        name: str,
        loc,
        heading: float,
        *,
        scale: float = 1.28,
        phase: float = 0.0,
    ) -> Any:
        """Build the protagonist as a rear-facing, rim-lit soldier silhouette.

        The shape is intentionally broader and more layered than the generic
        patrol figures: a wet poncho cone hides most rigid torso joins, while
        a helmet, radio pack, bedroll, antenna and diagonally slung rifle make
        the back view read immediately as a commander.  No facial geometry is
        authored because the Last Survivor camera never moves in front of him.
        """

        uniform = self.mat("HeroWetUniform", "#111B12", roughness=0.94)
        uniform_dark = self.mat("HeroUniformShadow", "#070B08", roughness=0.97)
        pack_mat = self.mat("HeroBackpack", "#172217", roughness=0.92)
        leather = self.mat("HeroWetLeather", "#17100C", roughness=0.88)
        beacon_mat = self.mat(
            "HeroRadioBeacon",
            "#D93A2B",
            roughness=0.7,
            emission="#FF2A1E",
            emission_strength=2.4,
        )

        root = self.empty(name, loc, (0, 0, heading))
        root.scale = (scale, scale, scale)
        root["sidd_role"] = "main_character_hero"
        root["sidd_presentation"] = "back_view_rim_lit_silhouette_no_face"
        body = self.empty(f"{name}_Body", (0, 0, 0), parent=root)

        # Legs and boots.  The pivots remain simple, but the poncho and pack
        # occupy most of the rear silhouette so the walk does not read as a
        # jointed puppet in the final medium-wide tracking shot.
        legs: list[Any] = []
        arms: list[Any] = []
        for side, sign in (("L", 1), ("R", -1)):
            leg = self.empty(f"{name}_Leg{side}", (0, 0.17 * sign, 0.68), parent=body)
            self.box(f"{name}_LegMesh{side}", (0, 0, -0.3), (0.17, 0.18, 0.62), uniform_dark, parent=leg)
            self.box(f"{name}_Boot{side}", (0.07, 0, -0.62), (0.31, 0.17, 0.1), self.M["black"], parent=leg)
            legs.append(leg)

            arm = self.empty(f"{name}_Arm{side}", (0, 0.35 * sign, 1.27), parent=body)
            self.box(f"{name}_ArmMesh{side}", (0.03, 0, -0.26), (0.15, 0.16, 0.54), uniform, parent=arm)
            self.sphere(f"{name}_Glove{side}", (0.06, 0, -0.55), (0.14, 0.13, 0.14), leather, parent=arm)
            arms.append(arm)

        self.box(f"{name}_Torso", (0, 0, 1.02), (0.38, 0.56, 0.68), uniform, parent=body)
        self.cone(f"{name}_RainPoncho", (0, 0, 1.02), (0.7, 0.84, 1.08), uniform_dark, parent=body)
        cape = self.box(
            f"{name}_PonchoBack",
            (-0.36, 0, 0.68),
            (0.06, 0.58, 0.62),
            uniform_dark,
            (0, math.radians(-5), 0),
            body,
        )
        for sign in (-1, 1):
            self.sphere(
                f"{name}_Shoulder{sign}",
                (0, 0.34 * sign, 1.3),
                (0.27, 0.23, 0.22),
                uniform,
                parent=body,
            )
        self.box(f"{name}_Belt", (0, 0, 0.69), (0.46, 0.68, 0.11), leather, parent=body)
        self.box(f"{name}_ChestStrap", (-0.25, 0, 1.08), (0.05, 0.68, 0.1), leather, (math.radians(24), 0, 0), body)

        # Backpack, bedroll and radio details are placed on the camera side
        # (-X in the character's local frame) because the camera stays behind.
        self.box(f"{name}_Backpack", (-0.4, 0, 1.02), (0.22, 0.43, 0.54), pack_mat, parent=body)
        self.box(f"{name}_BackpackFlap", (-0.52, 0, 1.24), (0.035, 0.36, 0.1), uniform, parent=body)
        for strap_sign in (-1, 1):
            self.box(
                f"{name}_BackpackStrap{strap_sign}",
                (-0.52, 0.11 * strap_sign, 1.01),
                (0.03, 0.045, 0.48),
                leather,
                parent=body,
            )
        self.cylinder(
            f"{name}_Bedroll",
            (-0.39, 0, 1.36),
            (0.2, 0.2, 0.52),
            uniform,
            (math.radians(90), 0, 0),
            body,
        )
        self.box(f"{name}_Radio", (-0.46, 0.16, 0.78), (0.08, 0.19, 0.22), self.M["dark"], parent=body)
        self.beam(f"{name}_Antenna", (-0.45, 0.2, 0.88), (-0.54, 0.25, 1.86), 0.018, self.M["dark"], body)
        beacon = self.sphere(f"{name}_RadioBeacon", (-0.54, 0.25, 1.88), (0.04, 0.04, 0.04), beacon_mat, parent=body)
        self.keys(
            beacon,
            "scale",
            [
                (0.0, (0.04, 0.04, 0.04)),
                (0.42, (0.08, 0.08, 0.08)),
                (0.84, (0.028, 0.028, 0.028)),
            ],
            "BEZIER",
        )
        self.set_cycles(beacon)

        gun = self.empty(f"{name}_SlungRifle", (-0.47, 0, 1.05), (math.radians(-36), 0, 0), body)
        self.box(f"{name}_RifleStock", (0, -0.3, 0), (0.07, 0.34, 0.1), leather, parent=gun)
        self.box(f"{name}_RifleReceiver", (0, 0.01, 0), (0.075, 0.34, 0.085), self.M["dark"], parent=gun)
        self.cylinder(
            f"{name}_RifleBarrel",
            (0, 0.4, 0.015),
            (0.04, 0.04, 0.48),
            self.M["black"],
            (math.radians(90), 0, 0),
            gun,
        )

        # The head is a dark helmet/hood mass only.  It remains turned away
        # from the camera for the entire authored shot.
        self.sphere(f"{name}_HeadShadow", (0, 0, 1.55), (0.25, 0.26, 0.28), uniform_dark, parent=body)
        self.sphere(f"{name}_Helmet", (-0.02, 0, 1.64), (0.32, 0.35, 0.22), uniform, parent=body)
        self.cylinder(f"{name}_HelmetBrim", (0, 0, 1.57), (0.46, 0.49, 0.055), uniform_dark, parent=body)
        self.box(f"{name}_HelmetNeckFlap", (-0.15, 0, 1.5), (0.05, 0.33, 0.17), pack_mat, parent=body)

        stride = 0.82
        self.oscillate_rotation(legs[0], 1, 0.45, stride, phase)
        self.oscillate_rotation(legs[1], 1, 0.45, stride, phase + math.pi)
        self.oscillate_rotation(arms[0], 1, 0.25, stride, phase + math.pi)
        self.oscillate_rotation(arms[1], 1, 0.25, stride, phase)
        self.oscillate_location_z(body, 0.032, stride / 2, phase)
        self.oscillate_rotation(cape, 1, 0.045, 1.35, phase + 0.4)
        return root

    def make_tank(self, name: str, loc, heading: float, *, scale: float = 1.0, move_distance: float = 16.0, start_fraction: float = 0.05, end_fraction: float = 0.9) -> Any:
        root = self.empty(name, loc, (0, 0, heading))
        root.scale = (scale, scale, scale)
        self.box(f"{name}_Hull", (0, 0, 0.72), (4.8, 2.25, 0.82), self.M["olive"], parent=root)
        self.box(f"{name}_Nose", (2.35, 0, 0.72), (0.8, 1.8, 0.66), self.M["olive_light"], parent=root)
        for sign in (-1, 1):
            self.box(f"{name}_Track{sign}", (0, 1.08 * sign, 0.44), (5.0, 0.48, 0.82), self.M["black"], parent=root)
            for index, x in enumerate((-1.8, -0.9, 0, 0.9, 1.8)):
                wheel = self.cylinder(f"{name}_Wheel{sign}_{index}", (x, 1.28 * sign, 0.42), (0.5, 0.16, 0.5), self.M["dark"], (math.radians(90), 0, 0), root)
                self.spin(wheel, 1, 4.5, self.at(start_fraction), self.at(end_fraction))
        turret = self.empty(f"{name}_Turret", (-0.15, 0, 1.28), parent=root)
        self.box(f"{name}_TurretBody", (0, 0, 0.28), (2.0, 1.45, 0.58), self.M["olive_light"], parent=turret)
        self.cylinder(f"{name}_Gun", (1.85, 0, 0.34), (0.13, 0.13, 2.5), self.M["dark"], (0, math.radians(90), 0), turret)
        self.cylinder(f"{name}_Hatch", (-0.35, 0, 0.65), (0.55, 0.55, 0.2), self.M["dark"], parent=turret)
        self.oscillate_rotation(turret, 2, 0.12, 5.0, self.rng.random() * math.tau)
        if move_distance:
            distance = move_distance * self.intensity
            end = (loc[0] + distance * math.cos(heading), loc[1] + distance * math.sin(heading), loc[2])
            self.move(root, self.at(start_fraction), self.at(end_fraction), end, start_location=loc)
        return root

    def make_truck(self, name: str, loc, heading: float, *, move_distance: float = 18.0) -> Any:
        root = self.empty(name, loc, (0, 0, heading))
        self.box(f"{name}_Cab", (1.75, 0, 1.0), (1.55, 1.75, 1.35), self.M["olive"], parent=root)
        self.box(f"{name}_Windshield", (2.48, 0, 1.28), (0.08, 1.35, 0.58), self.M["glass"], parent=root)
        self.box(f"{name}_Bed", (-0.9, 0, 1.04), (3.6, 2.0, 1.22), self.M["olive_light"], parent=root)
        self.box(f"{name}_Canvas", (-0.95, 0, 1.76), (3.2, 1.8, 0.42), self.M["sand"], parent=root)
        for x in (-1.9, 1.7):
            for sign in (-1, 1):
                wheel = self.cylinder(f"{name}_Wheel{x}{sign}", (x, 1.05 * sign, 0.42), (0.72, 0.22, 0.72), self.M["black"], (math.radians(90), 0, 0), root)
                self.spin(wheel, 1, 5.0, self.at(0.05), self.at(0.92))
        if move_distance:
            distance = move_distance * self.intensity
            end = (loc[0] + distance * math.cos(heading), loc[1] + distance * math.sin(heading), loc[2])
            self.move(root, self.at(0.05), self.at(0.92), end, start_location=loc)
        return root

    def make_aircraft(self, name: str, points: list[tuple[float, tuple[float, float, float]]], *, scale: float = 1.0, material: Any = None) -> Any:
        root = self.empty(name, points[0][1])
        root.scale = (scale, scale, scale)
        body_mat = material or self.M["olive"]
        self.cylinder(f"{name}_Fuselage", (0, 0, 0), (0.72, 0.72, 5.2), body_mat, (0, math.radians(90), 0), root)
        self.cone(f"{name}_Nose", (2.85, 0, 0), (0.68, 0.68, 0.9), self.M["dark"], (0, math.radians(-90), 0), root)
        self.sphere(f"{name}_Canopy", (0.55, 0, 0.34), (1.05, 0.55, 0.38), self.M["glass"], parent=root)
        self.box(f"{name}_Wing", (0.15, 0, -0.03), (1.25, 6.6, 0.12), body_mat, parent=root)
        self.box(f"{name}_TailWing", (-2.35, 0, 0.18), (0.75, 2.4, 0.1), body_mat, parent=root)
        self.box(f"{name}_Fin", (-2.45, 0, 0.48), (0.8, 0.1, 0.85), self.M["red"], parent=root)
        prop = self.box(f"{name}_Propeller", (3.35, 0, 0), (0.08, 2.2, 0.16), self.M["black"], parent=root)
        self.spin(prop, 0, 48.0)
        self.keys(root, "location", [(self.at(fraction), point) for fraction, point in points], "LINEAR")
        # Bank gently while keeping the nose broadly along eastward paths.
        self.keys(root, "rotation_euler", [(self.at(fraction), (0, 0, math.radians(-5 + index * 2.5))) for index, (fraction, _) in enumerate(points)], "BEZIER")
        return root

    def make_ship(self, name: str, loc, heading: float, *, scale: float = 1.0, move_distance: float = 10.0, warship: bool = True) -> Any:
        root = self.empty(name, loc, (0, 0, heading))
        root.scale = (scale, scale, scale)
        bob = self.empty(f"{name}_Bob", (0, 0, 0), parent=root)
        hull_mat = self.M["dark"] if warship else self.M["wood"]
        self.box(f"{name}_Hull", (0, 0, 0.85), (13, 3.4, 1.7), hull_mat, parent=bob)
        self.cone(f"{name}_Bow", (7.1, 0, 0.85), (2.0, 3.1, 1.55), hull_mat, (0, math.radians(-90), 0), bob)
        self.box(f"{name}_Deck", (-0.3, 0, 1.78), (11.5, 2.9, 0.2), self.M["metal"] if warship else self.M["sand"], parent=bob)
        if warship:
            self.box(f"{name}_Bridge", (0.5, 0, 2.9), (2.7, 2.0, 2.1), self.M["metal"], parent=bob)
            self.cylinder(f"{name}_Mast", (-0.3, 0, 4.8), (0.16, 0.16, 3.4), self.M["dark"], parent=bob)
            for x in (-4.2, 4.1):
                turret = self.empty(f"{name}_Turret{x}", (x, 0, 2.05), parent=bob)
                self.box(f"{name}_TurretBody{x}", (0, 0, 0.25), (1.8, 1.35, 0.5), self.M["dark"], parent=turret)
                self.cylinder(f"{name}_Gun{x}", (1.3, 0, 0.35), (0.12, 0.12, 2.0), self.M["black"], (0, math.radians(90), 0), turret)
                self.oscillate_rotation(turret, 2, 0.1, 6.0, x)
        else:
            self.cylinder(f"{name}_Mast", (0.2, 0, 4.2), (0.18, 0.18, 5.2), self.M["wood"], parent=bob)
            sail = self.box(f"{name}_Sail", (-0.55, 0, 4.1), (0.08, 2.7, 3.2), self.M["white"], parent=bob)
            self.oscillate_rotation(sail, 0, 0.07, 2.4, 0.4)
        self.oscillate_location_z(bob, 0.16, 2.8, loc[0] * 0.1)
        self.oscillate_rotation(bob, 0, 0.025, 3.4, loc[1] * 0.1)
        if move_distance:
            distance = move_distance * self.intensity
            end = (loc[0] + distance * math.cos(heading), loc[1] + distance * math.sin(heading), loc[2])
            self.move(root, self.at(0.03), self.at(0.97), end, start_location=loc)
        return root

    def make_tree(
        self,
        name: str,
        loc,
        *,
        scale: float = 1.0,
        palm: bool = False,
        trunk_material: Any = None,
        crown_material: Any = None,
        crown_material_light: Any = None,
    ) -> Any:
        root = self.empty(name, loc, (0, 0, self.rng.random() * math.tau))
        root.scale = (scale, scale, scale)
        trunk_mat = trunk_material or self.M["wood"]
        crown_mat = crown_material or self.M["leaf"]
        crown_light_mat = crown_material_light or self.M["leaf_light"]
        if palm:
            self.cylinder(f"{name}_Trunk", (0.25, 0, 1.55), (0.24, 0.24, 3.1), trunk_mat, (0, math.radians(-9), 0), root)
            for index in range(5):
                angle = index * math.tau / 5
                leaf = self.box(f"{name}_Frond{index}", (0.55 + 0.75 * math.cos(angle), 0.75 * math.sin(angle), 3.18), (1.65, 0.22, 0.06), crown_mat, (0, math.radians(-14), angle), root)
                self.oscillate_rotation(leaf, 2, 0.05, 2.2, angle)
            return root
        self.cylinder(f"{name}_Trunk", (0, 0, 0.9), (0.28, 0.28, 1.8), trunk_mat, parent=root)
        self.sphere(f"{name}_CrownA", (0, 0, 2.35), (1.55, 1.55, 1.3), crown_mat, parent=root)
        self.sphere(f"{name}_CrownB", (0.42, 0.25, 2.0), (1.05, 1.05, 0.95), crown_light_mat, parent=root)
        return root

    def make_cloud(self, name: str, loc, scale: float, drift: float = 7.0) -> Any:
        root = self.empty(name, loc)
        root.scale = (scale, scale, scale)
        for index, offset in enumerate(((-1.0, 0, 0), (0, 0.2, 0.16), (1.0, -0.1, 0))):
            self.sphere(f"{name}_Puff{index}", offset, (1.7 - index * 0.18, 0.9, 0.58), self.M["cloud"], parent=root)
        self.move(root, 0, self.duration, (loc[0] + drift * self.intensity, loc[1], loc[2]), start_location=loc, interpolation="LINEAR")
        return root

    def make_building(self, name: str, loc, size, material: Any, *, ruined: bool = False, windows: bool = True, window_material: Any = None) -> Any:
        root = self.empty(name, loc)
        width, depth, height = size
        self.box(f"{name}_Body", (0, 0, height / 2), (width, depth, height), material, parent=root)
        if ruined:
            self.box(f"{name}_BrokenTop", (-width * 0.18, 0, height + 0.28), (width * 0.58, depth * 0.88, 0.55), material, (0, math.radians(5), math.radians(3)), root)
            for index in range(3):
                self.box(f"{name}_Rubble{index}", (-width / 2 + 0.8 + index * 1.1, -depth / 2 - 0.5, 0.28), (0.9, 0.7, 0.55), self.M["stone"], (0, 0, index * 0.35), root)
        else:
            self.box(f"{name}_Roof", (0, 0, height + 0.12), (width * 1.04, depth * 1.04, 0.24), self.M["dark"], parent=root)
        if windows:
            cols = max(2, int(width / 2.2))
            rows = max(2, int(height / 2.7))
            mat = window_material or self.M["glass"]
            for row in range(rows):
                for col in range(cols):
                    if ruined and (row * 3 + col) % 4 == 0:
                        continue
                    x = -width / 2 + (col + 0.5) * width / cols
                    z = 1.05 + row * max(1.25, (height - 1.4) / max(1, rows - 1))
                    self.box(f"{name}_Win{row}_{col}", (x, -depth / 2 - 0.035, z), (0.52, 0.07, 0.72), mat, parent=root)
        return root

    def make_explosion(self, name: str, loc, *, scale: float = 1.0, period: float = 2.7, delay: float = 0.0) -> Any:
        root = self.empty(name, loc)
        parts = [
            self.sphere(f"{name}_Core", (0, 0, 0.65), (0.1, 0.1, 0.1), self.M["fire"], parent=root),
            self.cone(f"{name}_Flame", (0, 0, 1.0), (0.1, 0.1, 0.1), self.M["flash"], parent=root),
            self.sphere(f"{name}_Smoke", (0.25, 0.1, 1.35), (0.1, 0.1, 0.1), self.M["smoke"], parent=root),
        ]
        targets = [(1.55 * scale, 1.55 * scale, 1.25 * scale), (0.8 * scale, 0.8 * scale, 1.9 * scale), (1.8 * scale, 1.8 * scale, 1.45 * scale)]
        for part, target in zip(parts, targets):
            self.keys(
                part,
                "scale",
                [
                    (delay, (0.08, 0.08, 0.08)),
                    (delay + period * 0.14, target),
                    (delay + period * 0.42, tuple(value * 0.38 for value in target)),
                    (delay + period, (0.08, 0.08, 0.08)),
                ],
                "BEZIER",
            )
            self.set_cycles(part)
        # No per-explosion point light: eight always-on lights materially slow
        # CPU Cycles, while the emissive core already reads clearly in frame.
        return root

    def make_smoke_column(self, name: str, loc, *, count: int = 6, height: float = 8.0) -> None:
        for index in range(count):
            ratio = index / max(1, count - 1)
            size = 1.1 + ratio * 2.4
            puff = self.sphere(
                f"{name}_{index}",
                (loc[0] + math.sin(index * 1.7) * 0.55, loc[1] + math.cos(index * 1.3) * 0.35, loc[2] + ratio * height),
                (size, size * 0.78, size * 0.62),
                self.M["smoke"] if index % 2 == 0 else self.M["smoke_light"],
            )
            self.oscillate_location_z(puff, 0.22, 3.2 + index * 0.17, index * 0.8)

    def make_flag(self, name: str, loc, material: Any, *, height: float = 4.6, size: float = 1.0) -> Any:
        root = self.empty(name, loc)
        self.cylinder(f"{name}_Pole", (0, 0, height / 2), (0.09, 0.09, height), self.M["dark"], parent=root)
        cloth = self.box(f"{name}_Cloth", (0.82 * size, 0, height - 0.48 * size), (1.55 * size, 0.05, 0.86 * size), material, parent=root)
        self.oscillate_rotation(cloth, 2, 0.09, 1.35, loc[0])
        return root

    # --------------------------------------------------------------- WWII set
    def build_ww2(self) -> None:
        self.setup_world_and_lights(world_strength=0.62, sun_energy=3.4, sun_rotation=(math.radians(50), math.radians(10), math.radians(-34)))
        craters = [(-45, -18), (-22, -2), (2, -24), (18, 3), (38, -20), (-4, 9)]

        def terrain_height(x: float, y: float) -> float:
            z = 0.28 * math.sin(x * 0.055) * math.cos(y * 0.08) + 0.16 * math.sin((x + y) * 0.045)
            if y > 7:
                z -= (y - 7) * 0.16
            if y < -34:
                z += (-34 - y) * 0.035
            for cx, cy in craters:
                distance = math.hypot(x - cx, y - cy)
                if distance < 4.8:
                    z -= 0.75 * (1 - distance / 4.8)
            return z

        def terrain_color(x: float, y: float, z: float):
            if y > 11:
                return (0.65, 0.57, 0.4, 1)
            if y > 6:
                return (0.48, 0.47, 0.34, 1)
            if abs(y + 8) < 2.4:
                return (0.31, 0.29, 0.24, 1)
            for cx, cy in craters:
                if math.hypot(x - cx, y - cy) < 4.2:
                    return (0.16, 0.14, 0.11, 1)
            variation = 0.03 * math.sin(x * 0.6) * math.cos(y * 0.5)
            return (0.31 + variation, 0.36 + variation, 0.25, 1)

        ground_mat = self.vertex_material("BattlefieldVertex", roughness=0.97)
        self.grid_terrain("Battlefield", x_range=(-112, 112), y_range=(-62, 22), nx=72, ny=36, height_fn=terrain_height, color_fn=terrain_color, material=ground_mat)

        def water_height(x: float, y: float) -> float:
            return -0.42 + 0.08 * math.sin(x * 0.16 + y * 0.1) + 0.05 * math.cos(y * 0.28)

        def water_color(x: float, y: float, z: float):
            crest = max(0.0, math.sin(x * 0.16 + y * 0.1)) * 0.08
            return (0.1 + crest, 0.31 + crest, 0.45 + crest, 1)

        water_mat = self.vertex_material("SeaVertex", roughness=0.34)
        water = self.grid_terrain("Sea", x_range=(-125, 125), y_range=(9, 98), nx=42, ny=26, height_fn=water_height, color_fn=water_color, material=water_mat)
        self.oscillate_location_z(water, 0.07, 3.4)

        # No giant backdrop box: its side faces can appear as grey walls at
        # the edge of wide battlefield shots.  The world background is the sky.
        for index, (x, y, z, scale) in enumerate(((-72, 84, 31, 6), (-15, 94, 36, 8), (45, 88, 29, 5), (88, 98, 38, 9))):
            self.make_cloud(f"WarCloud{index}", (x, y, z), scale, drift=8 + index)
        for index, (x, s) in enumerate(((-96, 22), (-70, 15), (76, 18), (102, 25))):
            self.cone(f"DistantHill{index}", (x, 30, 3.5), (s, 15, 8), self.M["olive_light"])

        self.box("MainRoad", (-2, -8, 0.17), (164, 5.2, 0.12), self.M["dark"])
        self.box("BeachRoad", (8, 8.5, -0.36), (142, 3.8, 0.1), self.M["sand"])

        building_specs = [
            (-83, 1, 13, 9, 14), (-67, -4, 11, 8, 10), (-56, 7, 10, 7, 8),
            (53, -4, 12, 8, 11), (68, 3, 14, 9, 15), (82, -7, 10, 8, 9),
            (39, -43, 12, 8, 9), (-48, -45, 11, 8, 8),
        ]
        for index, (x, y, width, depth, height) in enumerate(building_specs):
            self.make_building(f"RuinedBuilding{index}", (x, y, 0), (width, depth, height), self.M["brick"] if index % 2 else self.M["stone"], ruined=True)
        self.make_smoke_column("WestSmoke", (-76, 2, 12), count=6, height=10)
        self.make_smoke_column("EastSmoke", (66, 2, 13), count=6, height=11)
        self.make_smoke_column("CenterSmoke", (12, -16, 2), count=5, height=7)

        # Sandbag lines are shared-mesh squashed spheres, deliberately fewer
        # than the research scene so native 1080p stays practical on CPU.
        for line_index, (x0, x1, y) in enumerate(((-32, 27, 11.4), (-40, 35, -12.2))):
            count = int((x1 - x0) / 0.82)
            for index in range(count):
                x = x0 + index * 0.82
                for layer in range(2):
                    self.sphere(
                        f"Sandbag{line_index}_{index}_{layer}",
                        (x + (0.2 if layer else 0), y + (0.18 if layer else 0), 0.27 + layer * 0.34),
                        (0.78, 0.48, 0.34),
                        self.M["sand"],
                        (0, 0, (index % 3 - 1) * 0.06),
                    )

        for index, x in enumerate(range(-38, 39, 3)):
            self.torus(f"BarbedWire{index}", (x, 15.4, 0.52), (0.95, 0.95, 0.95), self.M["dark"], (math.radians(90), 0, index * 0.2))
            if index % 3 == 0:
                self.cylinder(f"WirePost{index}", (x, 15.4, 0.55), (0.1, 0.1, 1.1), self.M["wood"])
        for index, x in enumerate(range(-34, 38, 6)):
            root = self.empty(f"Hedgehog{index}", (x, 18.2, -0.75))
            for axis in range(3):
                rot = [(0, 0, 0), (math.radians(90), 0, 0), (0, math.radians(90), 0)][axis]
                self.box(f"HedgehogBeam{index}_{axis}", (0, 0, 0.48), (0.2, 0.2, 2.0), self.M["dark"], rot, root)

        for index, (x, y, heading) in enumerate(((-33, -15, math.radians(18)), (24, -15, math.radians(-10)), (-6, 6, math.radians(55)))):
            gun = self.empty(f"Artillery{index}", (x, y, 0.35), (0, 0, heading))
            self.box(f"ArtilleryBase{index}", (0, 0, 0.42), (2.6, 1.25, 0.45), self.M["olive"], parent=gun)
            self.cylinder(f"ArtilleryBarrel{index}", (1.55, 0, 0.98), (0.17, 0.17, 3.0), self.M["dark"], (0, math.radians(68), 0), gun)
            for sign in (-1, 1):
                self.cylinder(f"ArtilleryWheel{index}_{sign}", (-0.4, 0.82 * sign, 0.42), (0.82, 0.18, 0.82), self.M["black"], (math.radians(90), 0, 0), gun)
            flash = self.cone(f"ArtilleryFlash{index}", (3.0, 0, 1.55), (0.1, 0.1, 0.1), self.M["flash"], (0, math.radians(-68), 0), gun)
            self.keys(flash, "scale", [(index * 0.7, (0.08, 0.08, 0.08)), (index * 0.7 + 0.12, (0.55, 0.55, 1.1)), (index * 0.7 + 0.38, (0.08, 0.08, 0.08)), (index * 0.7 + 2.3, (0.08, 0.08, 0.08))])
            self.set_cycles(flash)

        self.make_tank("TankWest", (-48, -18, 0.32), math.radians(7), move_distance=28)
        self.make_tank("TankCenter", (-25, -3, 0.3), math.radians(-4), move_distance=34)
        self.make_tank("TankEast", (31, -19, 0.32), math.radians(172), move_distance=22)
        self.make_tank("TankBeach", (-12, 7.5, -0.18), math.radians(-8), move_distance=25)
        self.make_truck("TruckWest", (-58, -8, 0.28), 0, move_distance=42)
        self.make_truck("TruckEast", (48, -10, 0.28), math.pi, move_distance=30)
        self.make_truck("TruckSupply", (-8, -28, 0.28), math.radians(8), move_distance=25)

        for index in range(8):
            self.make_person(
                f"BeachSoldier{index}",
                (-18 + index * 3.0, 14.6 - (index % 2) * 1.2, -0.62),
                math.radians(-78 + (index % 3) * 7),
                phase=index * 0.7,
                move_distance=7.5,
                start_fraction=0.18,
                end_fraction=0.96,
                end_z=0.02,
            )
        for index in range(5):
            self.make_person(
                f"TrenchSoldier{index}",
                (-22 + index * 6.0, -10.5, 0.34),
                math.radians(84),
                phase=index * 1.1,
                move_distance=0.6,
                start_fraction=0.08,
                end_fraction=0.9,
            )
        for index in range(3):
            self.make_person(
                f"Runner{index}",
                (-38 + index * 7, -22 + index * 2, 0.3),
                math.radians(10),
                phase=index * 0.9,
                move_distance=22,
            )

        for index, (x, y, heading, scale) in enumerate(((-48, 54, 0, 1.25), (8, 68, math.radians(180), 1.45), (54, 46, 0, 1.05))):
            self.make_ship(f"Warship{index}", (x, y, -0.28), heading, scale=scale, move_distance=12 if index != 1 else -9)
        for index, x in enumerate((-22, 0, 22)):
            craft = self.empty(f"LandingCraft{index}", (x, 29 - index * 2, -0.35), (0, 0, math.radians(-90)))
            self.box(f"LandingHull{index}", (0, 0, 0.55), (6.8, 2.6, 1.1), self.M["olive"], parent=craft)
            self.box(f"LandingRamp{index}", (3.55, 0, 0.55), (0.22, 2.3, 1.25), self.M["dark"], parent=craft)
            self.move(craft, self.at(0.08), self.at(0.72), (x + 3, 18 - index * 1.5, -0.45), start_location=(x, 29 - index * 2, -0.35))

        self.make_aircraft("FighterA", [(0.0, (-105, 38, 25)), (0.38, (-28, 30, 21)), (0.72, (46, 24, 23)), (1.0, (112, 18, 27))])
        self.make_aircraft("FighterB", [(0.05, (-112, 12, 18)), (0.45, (-20, 5, 15)), (0.8, (64, 0, 17)), (1.0, (118, -4, 20))], scale=0.86, material=self.M["olive_light"])
        self.make_aircraft("Bomber", [(0.0, (-118, 66, 34)), (0.5, (0, 58, 31)), (1.0, (120, 50, 35))], scale=1.35, material=self.M["dark"])

        explosion_points = [(-42, -18), (-19, -5), (4, -24), (22, 2), (-7, 10), (37, -17), (-58, -27), (12, -34)]
        for index, (x, y) in enumerate(explosion_points):
            self.make_explosion(f"Explosion{index}", (x, y, 0.35), scale=0.9 + (index % 3) * 0.22, period=2.4 + (index % 4) * 0.35, delay=index * 0.31)

        for index in range(7):
            tracer = self.sphere(f"Tracer{index}", (-28 + index * 5, -9, 1.25), (1.15, 0.07, 0.07), self.M["flash"], (0, 0, math.radians(90)))
            start = (-28 + index * 5, -9, 1.25)
            end = (-20 + index * 4, 13, 0.9)
            delay = index * 0.13
            self.keys(tracer, "location", [(delay, start), (delay + 0.62, end), (delay + 0.72, start), (delay + 1.45, start)], "LINEAR")
            self.set_cycles(tracer)

        self.make_flag("BeachFlag", (18, 12.5, -0.45), self.M["red"], height=5.2, size=1.15)
        self.make_flag("TrenchFlag", (-26, -11.2, 0.3), self.M["blue"], height=4.4)
        self.make_flag("BuildingFlag", (63, 1, 13.8), self.M["sand"], height=3.8, size=0.9)
        for index in range(18):
            x = self.rng.uniform(-72, 72)
            y = self.rng.uniform(-38, 2)
            if abs(y + 8) < 4:
                continue
            self.box(f"Debris{index}", (x, y, 0.28), (self.rng.uniform(0.7, 1.8), self.rng.uniform(0.5, 1.1), self.rng.uniform(0.3, 0.7)), self.M["stone"] if index % 2 else self.M["wood"], (0, 0, self.rng.random() * math.tau))

        self.setup_camera(
            [(0.0, (62, -72, 28)), (0.18, (35, -55, 18)), (0.37, (-5, -38, 10)), (0.55, (-38, -22, 7)), (0.7, (-18, -8, 5)), (0.84, (8, -8, 4)), (1.0, (28, -12, 7))],
            [(0.0, (-10, 5, 2)), (0.18, (-20, 5, 2)), (0.37, (-35, 0, 3)), (0.55, (-20, 5, 2)), (0.7, (10, 15, 1)), (0.84, (20, 20, 1)), (1.0, (0, 25, 1))],
            [(0.0, 35), (0.42, 46), (0.72, 50), (1.0, 42)],
        )

    # ----------------------------------------------------------- generic sets
    def _generic_stage(self, *, dark: bool = False) -> None:
        if dark:
            self.setup_world_and_lights(world_strength=0.22, sun_energy=1.5, sun_rotation=(math.radians(55), math.radians(8), math.radians(-25)), sun_color="#DCEAFF")
        else:
            self.setup_world_and_lights(world_strength=0.68, sun_energy=3.1)
        self.box("StageBackdrop", (0, 58, 22), (230, 2, 52), self.M["sky"])

    def _generic_camera(self, target=(0, 8, 3)) -> None:
        # A high, smooth aerial arc rather than the earlier low walk-in move.
        self.setup_camera(
            [(0.0, (-58, -52, 32)), (0.3, (-34, -44, 24)), (0.58, (0, -38, 19)), (0.8, (30, -30, 22)), (1.0, (52, -20, 30))],
            [(0.0, (-12, target[1], target[2])), (0.35, target), (0.7, (target[0] + 10, target[1], target[2])), (1.0, target)],
            [(0.0, 32), (0.55, 43), (1.0, 37)],
            fstop=3.5,
        )

    def build_finance(self) -> None:
        self._generic_stage()
        self.box("CityFloor", (0, 5, -0.15), (170, 105, 0.3), self.M["ground"])
        for index, x in enumerate(range(-60, 61, 20)):
            self.box(f"CityGridX{index}", (x, 3, 0.03), (0.18, 82, 0.05), self.M["cyan"])
        for index, y in enumerate(range(-28, 39, 16)):
            self.box(f"CityGridY{index}", (0, y, 0.04), (135, 0.18, 0.05), self.M["cyan"])
        window_glow = self.mat("WarmWindows", "#FFD27A", roughness=1.0, emission="#FFB84D", emission_strength=1.7)
        towers = [(-48, 22, 11, 9, 23), (-32, 27, 9, 8, 17), (-16, 20, 12, 9, 28), (28, 24, 10, 9, 21), (44, 19, 12, 9, 26), (59, 28, 9, 8, 16)]
        for index, (x, y, w, d, h) in enumerate(towers):
            self.make_building(f"Tower{index}", (x, y, 0), (w, d, h), self.M["metal"] if index % 2 else self.M["dark"], window_material=window_glow)
        bank = self.empty("CentralBank", (7, 15, 0))
        self.box("BankBase", (0, 0, 0.5), (22, 9, 1), self.M["stone"], parent=bank)
        self.box("BankBody", (0, 1.1, 4.3), (20, 6.5, 6.8), self.M["white"], parent=bank)
        self.box("BankRoof", (0, 0, 8.25), (23, 10, 0.7), self.M["gold"], parent=bank)
        for index, x in enumerate((-8.5, -5.1, -1.7, 1.7, 5.1, 8.5)):
            self.cylinder(f"BankColumn{index}", (x, -3.2, 4.1), (0.75, 0.75, 7.2), self.M["white"], parent=bank)
        for index in range(5):
            x = -42 + index * 6
            height = 3 + index * 1.7
            bar = self.box(f"GrowthBar{index}", (x, 1, 0.4), (3.2, 3.2, 0.8), self.M["gold"] if index % 2 else self.M["cyan"])
            self.keys(bar, "scale", [(self.at(0.08 + index * 0.05), (3.2, 3.2, 0.8)), (self.at(0.48 + index * 0.07), (3.2, 3.2, height)), (self.at(1.0), (3.2, 3.2, height * 0.92))])
            self.keys(bar, "location", [(self.at(0.08 + index * 0.05), (x, 1, 0.4)), (self.at(0.48 + index * 0.07), (x, 1, height / 2)), (self.at(1.0), (x, 1, height * 0.46))])
        for index in range(5):
            y = -10 - (index % 2) * 6
            coin_root = self.empty(f"CoinRoot{index}", (-52 + index * 4, y, 2.1))
            coin = self.cylinder(f"Coin{index}", (0, 0, 0), (4.0, 0.55, 4.0), self.M["gold"], (math.radians(90), 0, 0), coin_root)
            self.torus(f"CoinRim{index}", (0, -0.3, 0), (3.25, 3.25, 3.25), self.M["sand"], parent=coin_root)
            self.move(coin_root, self.at(0.05 + index * 0.06), self.at(0.92), (42 - index * 3, y, 2.1), start_location=(-52 + index * 4, y, 2.1))
            self.spin(coin, 1, 7.0, self.at(0.05), self.at(0.92))
        for index in range(8):
            orb = self.sphere(f"FinanceOrb{index}", (-48 + index * 13, 32, 13 + (index % 3) * 2), (0.8, 0.8, 0.8), self.M["glow"])
            self.oscillate_location_z(orb, 0.7, 2.4, index * 0.6)
        self.make_person("FinanceGuide", (-18, -20, 0), math.radians(8), uniform=self.M["blue"], weapon="none", helmet=False, move_distance=34)
        self._generic_camera((0, 8, 4))

    def build_space(self) -> None:
        self._generic_stage(dark=True)
        Moon = self.vertex_material("MoonVertex", roughness=0.98)
        self.grid_terrain(
            "MoonSurface",
            x_range=(-95, 95),
            y_range=(-55, 45),
            nx=48,
            ny=30,
            height_fn=lambda x, y: 0.22 * math.sin(x * 0.09) * math.cos(y * 0.11),
            color_fn=lambda x, y, z: (0.5 + 0.04 * math.sin(x * 0.4), 0.52, 0.56, 1),
            material=Moon,
        )
        star_mat = self.mat("Stars", "#FFFFFF", roughness=1.0, emission="#FFFFFF", emission_strength=3.0)
        for index in range(70):
            self.sphere(f"Star{index}", (self.rng.uniform(-95, 95), self.rng.uniform(48, 56), self.rng.uniform(16, 48)), (0.28, 0.28, 0.28), star_mat)
        earth = self.empty("Earth", (48, 48, 31))
        self.sphere("EarthSphere", (0, 0, 0), (19, 19, 19), self.M["blue"], parent=earth)
        for index, offset in enumerate(((-5, -8.7, 4), (4, -9.2, -3), (0, -9.4, 7), (7, -8.4, 3))):
            self.sphere(f"Continent{index}", offset, (4.6, 1.2, 3.0), self.M["leaf"], parent=earth)
        self.spin(earth, 2, 0.08)
        for index, (x, y, r) in enumerate(((-34, 8, 6), (18, -16, 4.5), (38, 13, 7), (-5, 24, 3.5))):
            self.torus(f"Crater{index}", (x, y, 0.16), (r, r, 0.45), self.M["stone"])
            self.cylinder(f"CraterFloor{index}", (x, y, 0.05), (r * 1.55, r * 1.55, 0.08), self.M["dark"])
        pad = self.empty("LaunchPad", (-16, 2, 0))
        self.cylinder("PadDisc", (0, 0, 0.22), (10, 10, 0.44), self.M["metal"], parent=pad)
        for index, x in enumerate((-3.4, 3.4)):
            self.box(f"LaunchTower{index}", (x, -1.6, 5.2), (0.35, 0.35, 10.4), self.M["dark"], parent=pad)
        self.box("LaunchBridge", (0, -1.6, 8.4), (7.0, 0.35, 0.35), self.M["dark"], parent=pad)
        rocket = self.empty("Rocket", (-16, 2, 0.5))
        self.cylinder("RocketBody", (0, 0, 4.25), (2.15, 2.15, 7.5), self.M["white"], parent=rocket)
        self.cone("RocketNose", (0, 0, 8.75), (2.15, 2.15, 1.7), self.M["red"], parent=rocket)
        self.cylinder("RocketWindow", (0, -1.08, 5.7), (0.72, 0.12, 0.72), self.M["glass"], (math.radians(90), 0, 0), rocket)
        for index, rotation in enumerate(((0, 0, 0), (0, 0, math.radians(120)), (0, 0, math.radians(240)))):
            fin_root = self.empty(f"RocketFinRoot{index}", (0, 0, 1.05), rotation, rocket)
            self.box(f"RocketFin{index}", (1.15, 0, 0), (1.15, 0.14, 1.7), self.M["red"], parent=fin_root)
        flame = self.cone("RocketFlame", (0, 0, -0.25), (1.25, 1.25, 1.9), self.M["fire"], (math.pi, 0, 0), rocket)
        self.oscillate_rotation(flame, 2, 0.05, 0.32)
        self.keys(rocket, "location", [(self.at(0.0), (-16, 2, 0.5)), (self.at(0.24), (-16, 2, 0.65)), (self.at(0.58), (-9, 7, 13)), (self.at(0.9), (10, 18, 29)), (self.at(1.0), (20, 24, 35))])
        self.point_light("RocketLight", (0, 0, 0.2), "#FF8A3D", 450, rocket)
        satellite = self.empty("Satellite", (-34, 22, 24))
        self.box("SatelliteBody", (0, 0, 0), (2.2, 1.2, 1.2), self.M["gold"], parent=satellite)
        for sign in (-1, 1):
            self.box(f"SatellitePanel{sign}", (0, 2.5 * sign, 0), (2.8, 3.6, 0.12), self.M["blue"], parent=satellite)
        orbit_points = []
        for index in range(9):
            fraction = index / 8
            angle = fraction * math.tau
            orbit_points.append((self.at(fraction), (4 + 38 * math.cos(angle), 23 + 8 * math.sin(angle), 25 + 5 * math.sin(angle * 2))))
        self.keys(satellite, "location", orbit_points, "BEZIER")
        self.spin(satellite, 2, 1.0)
        rover = self.empty("MoonRover", (-38, -18, 0.65), (0, 0, math.radians(12)))
        self.box("RoverBody", (0, 0, 0.55), (3.4, 2.0, 0.85), self.M["metal"], parent=rover)
        self.cylinder("RoverMast", (-1.0, 0, 1.55), (0.14, 0.14, 1.7), self.M["dark"], parent=rover)
        for x in (-1.25, 0, 1.25):
            for sign in (-1, 1):
                self.cylinder(f"RoverWheel{x}{sign}", (x, 1.1 * sign, 0.18), (0.62, 0.18, 0.62), self.M["black"], (math.radians(90), 0, 0), rover)
        self.move(rover, self.at(0.08), self.at(0.9), (8, -8, 0.65), start_location=(-38, -18, 0.65))
        self.make_person("Astronaut", (-28, -9, 0.15), math.radians(15), uniform=self.M["white"], weapon="none", helmet=True, move_distance=18)
        self.make_flag("MoonFlag", (18, 2, 0.1), self.M["red"], height=4.0)
        self._generic_camera((0, 8, 7))

    def build_ocean(self) -> None:
        self._generic_stage()
        water_mat = self.vertex_material("OceanVertex", roughness=0.3)
        water = self.grid_terrain(
            "Ocean",
            x_range=(-105, 105),
            y_range=(-55, 70),
            nx=52,
            ny=34,
            height_fn=lambda x, y: -0.25 + 0.14 * math.sin(x * 0.12 + y * 0.08),
            color_fn=lambda x, y, z: (0.08 + 0.04 * math.sin(x * 0.1), 0.36, 0.58, 1),
            material=water_mat,
        )
        self.oscillate_location_z(water, 0.08, 3.0)
        island = self.empty("Island", (30, 15, 0))
        self.sphere("IslandSand", (0, 0, -0.4), (25, 16, 3.4), self.M["sand"], parent=island)
        self.sphere("IslandGrass", (-2, 1, 0.75), (17, 10, 2.1), self.M["leaf_light"], parent=island)
        for index, (x, y, s) in enumerate(((18, 9, 1.15), (28, 18, 1.35), (39, 10, 1.0), (34, 22, 0.9))):
            self.make_tree(f"Palm{index}", (x, y, 1.15), scale=s, palm=True)
        lighthouse = self.empty("Lighthouse", (47, 7, 1.1))
        for index, (z, mat) in enumerate(((2.2, self.M["red"]), (5.2, self.M["white"]), (8.2, self.M["red"]))):
            self.cylinder(f"LighthouseBand{index}", (0, 0, z), (3.2 - index * 0.34, 3.2 - index * 0.34, 3.0), mat, parent=lighthouse)
        self.cylinder("LighthouseLampRoom", (0, 0, 10.35), (2.0, 2.0, 1.3), self.M["glass"], parent=lighthouse)
        self.cone("LighthouseRoof", (0, 0, 11.55), (2.5, 2.5, 1.35), self.M["dark"], parent=lighthouse)
        beam_root = self.empty("LighthouseBeamRoot", (0, 0, 10.3), parent=lighthouse)
        beam_mat = self.mat("LightBeam", "#FFE9A3", roughness=1.0, alpha=0.28, emission="#FFD95E", emission_strength=1.8)
        self.cone("LighthouseBeam", (-8.5, 0, 0), (17, 3.2, 3.2), beam_mat, (0, math.radians(90), 0), beam_root)
        self.spin(beam_root, 2, 1.0)
        self.point_light("LighthouseLight", (0, 0, 10.3), "#FFDF7A", 700, lighthouse)
        self.make_ship("SailingShip", (-48, 30, 0.15), 0, scale=1.35, move_distance=62, warship=False)
        self.make_ship("SmallShip", (42, 43, 0.1), math.pi, scale=0.82, move_distance=24, warship=False)
        for index in range(8):
            bird = self.cone(f"SeaBird{index}", (-55 + index * 6, 42 + (index % 3), 15 + index * 0.4), (1.15, 0.32, 0.28), self.M["white"], (0, math.radians(-90), 0))
            start = tuple(bird.location)
            self.move(bird, 0, self.duration, (start[0] + 70, start[1] - 6, start[2] + 2), start_location=start, interpolation="LINEAR")
        for index in range(5):
            self.make_cloud(f"OceanCloud{index}", (-62 + index * 28, 54, 25 + index % 3 * 3), 4.6, drift=6)
        self.make_person("SailorGuide", (12, -8, 0.55), math.radians(12), uniform=self.M["blue"], weapon="none", helmet=False, move_distance=12)
        self._generic_camera((5, 16, 4))

    def build_tech(self) -> None:
        self._generic_stage(dark=True)
        self.box("LabFloor", (0, 5, -0.16), (170, 105, 0.32), self.M["ground"])
        grid_mat = self.mat("CircuitGlow", "#2FE4EE", roughness=1.0, emission="#20BFD2", emission_strength=2.2)
        for index, x in enumerate(range(-64, 65, 16)):
            self.box(f"CircuitX{index}", (x, 4, 0.035), (0.16, 82, 0.05), grid_mat)
        for index, y in enumerate(range(-30, 41, 14)):
            self.box(f"CircuitY{index}", (0, y, 0.04), (138, 0.16, 0.05), grid_mat)
        blink_mats = [self.mat(f"ServerBlink{i}", color, roughness=1.0, emission=color, emission_strength=2.5) for i, color in enumerate(("#43F2FF", "#FFC857", "#7CFC9A"))]
        for tower_index, (x, y, h) in enumerate(((-48, 22, 17), (-35, 27, 13), (-20, 21, 20), (28, 23, 16), (42, 27, 21), (56, 20, 13))):
            tower = self.make_building(f"ServerTower{tower_index}", (x, y, 0), (8, 6, h), self.M["dark"], window_material=blink_mats[tower_index % 3])
            for light_index in range(5):
                light = self.box(f"ServerLight{tower_index}_{light_index}", (-2.5 + light_index * 1.25, -3.12, 2 + light_index * 2.4), (0.42, 0.08, 0.42), blink_mats[(tower_index + light_index) % 3], parent=tower)
                delay = (tower_index * 0.13 + light_index * 0.11) % 1.2
                self.keys(light, "scale", [(delay, (0.42, 0.08, 0.42)), (delay + 0.28, (0.08, 0.08, 0.08)), (delay + 0.58, (0.42, 0.08, 0.42)), (delay + 1.2, (0.42, 0.08, 0.42))])
                self.set_cycles(light)
        core = self.empty("DataCore", (2, 11, 8))
        self.sphere("CoreSphere", (0, 0, 0), (3.4, 3.4, 3.4), grid_mat, parent=core)
        for index, rot in enumerate(((0, 0, 0), (math.radians(90), 0, 0), (0, math.radians(90), 0))):
            ring = self.torus(f"CoreRing{index}", (0, 0, 0), (7.5, 7.5, 7.5), self.M["gold"] if index == 1 else grid_mat, rot, core)
            self.spin(ring, index % 3, 1.2 + index * 0.35)
        self.oscillate_location_z(core, 0.65, 3.2)
        nodes = [(-25, -4, 7), (-8, 18, 10), (16, 2, 8), (30, 18, 12), (2, -15, 6)]
        for index, point in enumerate(nodes):
            node = self.sphere(f"DataNode{index}", point, (1.0, 1.0, 1.0), blink_mats[index % 3])
            self.oscillate_location_z(node, 0.5, 2.0 + index * 0.2, index)
            self.beam(f"DataLink{index}", point, (2, 11, 8), 0.07, grid_mat)
        robot = self.empty("RobotGuide", (-30, -18, 0), (0, 0, math.radians(10)))
        robot_body = self.empty("RobotBody", (0, 0, 0), parent=robot)
        self.box("RobotTorso", (0, 0, 1.25), (1.15, 1.45, 1.25), self.M["metal"], parent=robot_body)
        self.box("RobotHead", (0, 0, 2.22), (0.9, 1.0, 0.72), self.M["white"], parent=robot_body)
        self.box("RobotEyes", (0.48, 0, 2.28), (0.06, 0.62, 0.16), grid_mat, parent=robot_body)
        self.cylinder("RobotAntenna", (0, 0, 2.78), (0.07, 0.07, 0.55), self.M["dark"], parent=robot_body)
        self.sphere("RobotAntennaTip", (0, 0, 3.1), (0.22, 0.22, 0.22), grid_mat, parent=robot_body)
        for sign in (-1, 1):
            leg = self.empty(f"RobotLeg{sign}", (0, 0.38 * sign, 0.72), parent=robot_body)
            self.box(f"RobotLegMesh{sign}", (0, 0, -0.32), (0.34, 0.34, 0.7), self.M["dark"], parent=leg)
            arm = self.empty(f"RobotArm{sign}", (0, 0.88 * sign, 1.62), parent=robot_body)
            self.box(f"RobotArmMesh{sign}", (0, 0, -0.38), (0.28, 0.28, 0.82), self.M["metal"], parent=arm)
            self.oscillate_rotation(leg, 1, 0.42, 0.8, 0 if sign > 0 else math.pi)
            self.oscillate_rotation(arm, 1, 0.36, 0.8, math.pi if sign > 0 else 0)
        self.oscillate_location_z(robot_body, 0.045, 0.4)
        self.move(robot, self.at(0.05), self.at(0.9), (25, -9, 0), start_location=(-30, -18, 0))
        drone = self.empty("LabDrone", (-35, 5, 12))
        self.box("DroneBody", (0, 0, 0), (1.5, 1.5, 0.42), self.M["dark"], parent=drone)
        for x in (-1, 1):
            for y in (-1, 1):
                rotor = self.cylinder(f"DroneRotor{x}{y}", (1.05 * x, 1.05 * y, 0.18), (0.9, 0.12, 0.08), grid_mat, parent=drone)
                self.spin(rotor, 2, 26)
        points = []
        for index in range(9):
            fraction = index / 8
            angle = fraction * math.tau
            points.append((self.at(fraction), (2 + 34 * math.cos(angle), 8 + 17 * math.sin(angle), 12 + 2 * math.sin(angle * 2))))
        self.keys(drone, "location", points)
        self._generic_camera((0, 7, 5))

    def build_last_survivor(self) -> None:
        """A hero-led rear-tracking shot through a rainy jungle battlefield.

        Unlike the aerial Jungle War set, this scene is composed around one
        protagonist at ground level.  The camera remains south/behind him for
        every key, so the audience sees his helmet, poncho, backpack and
        slung rifle as a dark rim-lit silhouette rather than a low-poly face.
        The route itself tells the five-line story: wreck and dead radio,
        memorials to the fallen unit, enemy fire near a burnt camp, then a
        stream crossing toward a pale dawn beyond the ridge.
        """

        self.setup_world_and_lights(
            world_strength=0.10,
            sun_energy=0.85,
            sun_rotation=(math.radians(62), math.radians(18), math.radians(-28)),
            sun_color="#BFD4C3",
            fill_energy=22.0,
        )
        self.setup_mist_compositor(color="#1E2E26", max_factor=0.5, start=9.0, depth=48.0)

        canopy_dark = self.mat("SurvivorCanopyDark", "#0D2515", roughness=0.98)
        canopy_mid = self.mat("SurvivorCanopyMid", "#1C4526", roughness=0.96)
        canopy_wet = self.mat("SurvivorCanopyWet", "#2B5D34", roughness=0.9)
        undergrowth = self.mat("SurvivorUndergrowth", "#142E1C", roughness=0.98)
        fern = self.mat("SurvivorFern", "#214F2B", roughness=0.95)
        bark = self.mat("SurvivorWetBark", "#2B1E15", roughness=0.97)
        bamboo = self.mat("SurvivorBamboo", "#3C5731", roughness=0.9)
        camo = self.mat("SurvivorCamo", "#2B4029", roughness=0.95)
        camo_dark = self.mat("SurvivorCamoDark", "#1B2B20", roughness=0.97)
        burnt_metal = self.mat("SurvivorBurntMetal", "#252A26", roughness=0.78, metallic=0.18)
        tarp = self.mat("SurvivorWetTarp", "#2C4035", roughness=0.94)
        rain_mat = self.mat(
            "SurvivorRainStreaks",
            "#B9CFDD",
            roughness=1.0,
            alpha=0.36,
            emission="#8FAFC4",
            emission_strength=0.24,
        )
        storm_mat = self.mat("SurvivorStormCloud", "#323D38", roughness=1.0, alpha=0.58)
        dawn_mat = self.mat(
            "SurvivorDawnGlow",
            "#B9D1BC",
            roughness=1.0,
            alpha=0.5,
            emission="#9FC3AA",
            emission_strength=1.05,
        )
        flare_mat = self.mat(
            "SurvivorSignalFlare",
            "#FF4A32",
            roughness=1.0,
            emission="#FF2E1C",
            emission_strength=4.2,
        )

        def trail_x(y: float) -> float:
            return -10.0 + 0.18 * y + 4.0 * math.sin(y * 0.055)

        def trail_dx_dy(y: float) -> float:
            return 0.18 + 0.22 * math.cos(y * 0.055)

        def stream_y(x: float) -> float:
            return 20.0 + 2.2 * math.sin(x * 0.06)

        craters = [(-16.0, -18.0), (-4.0, -2.0), (-18.0, 10.0), (4.0, 14.0)]

        def ground_z(x: float, y: float) -> float:
            z = 0.42 * math.sin(x * 0.05) * math.cos(y * 0.06) + 0.24 * math.sin((x - y) * 0.055)
            trail_distance = abs(x - trail_x(y))
            if trail_distance < 4.6:
                z *= 0.22 + 0.14 * trail_distance
            stream_distance = abs(y - stream_y(x))
            if stream_distance < 4.8:
                z -= 0.68 * (1.0 - stream_distance / 4.8)
            if y > 28.0:
                z += (y - 28.0) * 0.035
            for cx, cy in craters:
                distance = math.hypot(x - cx, y - cy)
                if distance < 3.8:
                    z -= 0.5 * (1.0 - distance / 3.8)
            return z

        def ground_color(x: float, y: float, z: float):
            if abs(y - stream_y(x)) < 3.2:
                return (0.03, 0.1, 0.115, 1)
            if abs(x - trail_x(y)) < 2.9:
                return (0.16, 0.1, 0.048, 1)
            for cx, cy in craters:
                if math.hypot(x - cx, y - cy) < 3.5:
                    return (0.06, 0.046, 0.03, 1)
            variation = 0.016 * math.sin(x * 0.44 + y * 0.32)
            return (0.034 + variation, 0.104 + variation, 0.043, 1)

        self.grid_terrain(
            "LastSurvivorTerrain",
            x_range=(-105, 105),
            y_range=(-78, 78),
            nx=58,
            ny=40,
            height_fn=ground_z,
            color_fn=ground_color,
            material=self.vertex_material("LastSurvivorVertex", roughness=0.98),
        )
        self.box(
            "LastSurvivorHorizonGround",
            (0, 0, -1.8),
            (560, 560, 0.2),
            self.mat("LastSurvivorHorizon", "#0B1B11", roughness=1.0),
        )

        stream_mat = self.mat("LastSurvivorStream", "#17332F", roughness=0.22, metallic=0.04)
        for index, x in enumerate(range(-58, 64, 9)):
            y = stream_y(float(x))
            angle = math.atan(0.132 * math.cos(x * 0.06))
            self.box(
                f"SurvivorStreamSegment{index}",
                (x, y, ground_z(float(x), y) + 0.12),
                (9.4, 4.9, 0.08),
                stream_mat,
                (0, 0, angle),
            )
        bridge_x = trail_x(20.0)
        self.beam(
            "SurvivorLogBridge",
            (bridge_x - 0.5, 14.6, ground_z(bridge_x, 14.6) + 0.48),
            (bridge_x + 0.4, 26.2, ground_z(bridge_x, 26.2) + 0.52),
            0.68,
            bark,
        )

        # Pale dawn and black ridge silhouettes close the low camera's view.
        self.sphere("DawnBeyondRidge", (trail_x(58.0), 58, 12.0), (28, 7, 7), dawn_mat)
        for index, (x, y, width, height) in enumerate(
            ((-62, 58, 30, 13), (-28, 61, 34, 15), (8, 60, 36, 13), (44, 62, 32, 16), (74, 58, 27, 12))
        ):
            self.cone(
                f"SurvivorRidge{index}",
                (x, y, ground_z(float(x), float(y)) + height * 0.34),
                (width, width * 0.58, height),
                canopy_dark,
            )
        for index in range(16):
            x = -76 + index * 10.2 + self.rng.uniform(-2.0, 2.0)
            y = 48 + self.rng.uniform(-3.0, 6.0)
            self.sphere(
                f"SurvivorDistantCanopy{index}",
                (x, y, ground_z(x, y) + self.rng.uniform(4.0, 7.0)),
                (self.rng.uniform(9, 15), self.rng.uniform(6, 10), self.rng.uniform(4.5, 7)),
                canopy_dark if index % 3 else canopy_mid,
            )
        for index, (x, y, z, scale) in enumerate(((-46, 48, 24, 6), (2, 56, 28, 8), (48, 50, 25, 6))):
            cloud = self.empty(f"SurvivorStormCloud{index}", (x, y, z))
            cloud.scale = (scale, scale, scale)
            for puff_index, offset in enumerate(((-1.05, 0, 0), (0, 0.12, 0.16), (1.05, -0.08, 0))):
                self.sphere(
                    f"SurvivorStormPuff{index}_{puff_index}",
                    offset,
                    (1.65, 0.82, 0.52),
                    storm_mat,
                    parent=cloud,
                )
            self.move(cloud, 0, self.duration, (x + 5 + index, y, z), start_location=(x, y, z), interpolation="LINEAR")

        # Front rim light: positioned far along the hero's route so it edges
        # his helmet/shoulders without illuminating a face toward camera.
        self.point_light("DawnRimLight", (trail_x(40.0), 40, 6.0), "#B9D4C3", 1100)
        self.point_light("ColdSideRimLight", (trail_x(2.0) + 10, 4, 4.2), "#7FA9C9", 150)

        tree_pairs = [(canopy_dark, canopy_mid), (canopy_mid, canopy_wet), (undergrowth, canopy_mid)]
        tree_positions: list[tuple[float, float, float]] = []
        attempts = 0
        while len(tree_positions) < 44 and attempts < 420:
            attempts += 1
            x = self.rng.uniform(-66, 66)
            y = self.rng.uniform(-54, 52)
            if abs(x - trail_x(y)) < 5.4 or abs(y - stream_y(x)) < 4.0:
                continue
            tree_positions.append((x, y, self.rng.uniform(1.55, 2.9)))
        foreground_trees = [
            (trail_x(-22.0) - 8.0, -22.0, 2.8),
            (trail_x(-13.0) + 8.5, -13.0, 2.65),
            (trail_x(-3.0) - 8.5, -3.0, 2.95),
            (trail_x(7.0) + 8.0, 7.0, 2.7),
            (trail_x(16.0) - 8.5, 16.0, 2.8),
            (trail_x(27.0) + 9.0, 27.0, 2.6),
        ]
        tree_positions.extend(foreground_trees)
        for index, (x, y, scale) in enumerate(tree_positions):
            crown, crown_light = tree_pairs[index % len(tree_pairs)]
            self.make_tree(
                f"SurvivorTree{index}",
                (x, y, ground_z(x, y) - 0.08),
                scale=scale,
                palm=(index % 8 == 4),
                trunk_material=bark,
                crown_material=crown,
                crown_material_light=crown_light,
            )

        for index in range(48):
            x = self.rng.uniform(-62, 62)
            y = self.rng.uniform(-52, 50)
            if abs(x - trail_x(y)) < 3.2:
                x += 4.2 if x >= trail_x(y) else -4.2
            self.sphere(
                f"SurvivorBush{index}",
                (x, y, ground_z(x, y) + 0.3),
                (self.rng.uniform(1.0, 2.6), self.rng.uniform(0.85, 2.0), self.rng.uniform(0.5, 1.05)),
                undergrowth if index % 3 else canopy_mid,
            )
        for index in range(26):
            x = self.rng.uniform(-55, 55)
            y = self.rng.uniform(-48, 46)
            if abs(x - trail_x(y)) < 3.0:
                continue
            self.cone(f"SurvivorFern{index}", (x, y, ground_z(x, y) + 0.32), (1.05, 1.05, 0.75), fern)
        for cluster in range(5):
            cy = -34 + cluster * 15 + self.rng.uniform(-3, 3)
            cx = trail_x(cy) + (9 if cluster % 2 else -9)
            for stalk in range(4):
                x = cx + self.rng.uniform(-0.8, 0.8)
                y = cy + self.rng.uniform(-0.8, 0.8)
                height = self.rng.uniform(4.2, 6.8)
                self.cylinder(
                    f"SurvivorBamboo{cluster}_{stalk}",
                    (x, y, ground_z(x, y) + height / 2),
                    (0.17, 0.17, height),
                    bamboo,
                    (math.radians(self.rng.uniform(-3, 3)), math.radians(self.rng.uniform(-3, 3)), 0),
                )
        vine_mat = self.mat("SurvivorVine", "#182E20", roughness=0.98)
        for index, (x, y, scale) in enumerate(tree_positions[:15]):
            top = (x + self.rng.uniform(-1.0, 1.0), y + self.rng.uniform(-0.8, 0.8), ground_z(x, y) + 2.1 * scale)
            bottom = (top[0] + self.rng.uniform(-0.4, 0.4), top[1], ground_z(x, y) + 0.25)
            self.beam(f"SurvivorVine{index}", top, bottom, 0.05, vine_mat)
        for index in range(8):
            y = -42 + index * 10 + self.rng.uniform(-2, 2)
            x = trail_x(y) + (7 if index % 2 else -7)
            end = (x + self.rng.uniform(-2, 2), y + 4.5)
            self.beam(
                f"SurvivorFallenLog{index}",
                (x, y, ground_z(x, y) + 0.3),
                (end[0], end[1], ground_z(end[0], end[1]) + 0.3),
                0.52,
                bark,
            )
        for index in range(14):
            x = self.rng.uniform(-55, 55)
            y = self.rng.uniform(-50, 48)
            if abs(x - trail_x(y)) < 3.4:
                continue
            self.box(
                f"SurvivorRock{index}",
                (x, y, ground_z(x, y) + 0.2),
                (self.rng.uniform(0.7, 1.7), self.rng.uniform(0.6, 1.3), self.rng.uniform(0.35, 0.75)),
                self.M["stone"],
                (0, 0, self.rng.uniform(0, math.tau)),
            )
        for index, y in enumerate((-31, -24, -17, -10, -3, 4, 11, 17, 27)):
            x = trail_x(float(y)) + self.rng.uniform(-0.7, 0.7)
            self.cylinder(
                f"SurvivorTrailPuddle{index}",
                (x, y, ground_z(x, float(y)) + 0.06),
                (self.rng.uniform(2.0, 3.2), self.rng.uniform(1.0, 1.7), 0.04),
                stream_mat,
            )

        # Opening beat: burnt truck and broken radio beside the route.
        wreck_y = -23.0
        wreck_x = trail_x(wreck_y) - 6.4
        wreck_z = ground_z(wreck_x, wreck_y)
        wreck = self.empty("SurvivorBurntTruck", (wreck_x, wreck_y, wreck_z + 0.2), (math.radians(4), 0, math.radians(74)))
        self.box("SurvivorWreckCab", (1.8, 0, 0.95), (1.6, 1.75, 1.3), burnt_metal, parent=wreck)
        self.box("SurvivorWreckWindshield", (2.55, 0, 1.22), (0.08, 1.3, 0.55), self.M["black"], parent=wreck)
        self.box("SurvivorWreckBed", (-0.95, 0, 1.0), (3.7, 2.0, 1.2), camo_dark, parent=wreck)
        self.box("SurvivorWreckCanvas", (-1.0, 0, 1.72), (3.1, 1.75, 0.38), self.M["black"], (0, math.radians(-4), 0), wreck)
        for wheel_index, (wx, wy) in enumerate(((-1.9, -1.05), (-1.9, 1.05), (1.7, -1.05), (1.7, 1.05))):
            self.cylinder(f"SurvivorWreckWheel{wheel_index}", (wx, wy, 0.36), (0.72, 0.2, 0.72), self.M["black"], (math.radians(90), 0, 0), wreck)
        self.sphere("SurvivorWreckFire", (wreck_x + 0.4, wreck_y + 0.5, wreck_z + 1.35), (0.65, 0.55, 0.55), self.M["fire"])
        self.cone("SurvivorWreckFlame", (wreck_x + 0.4, wreck_y + 0.5, wreck_z + 1.95), (0.42, 0.42, 1.05), self.M["flash"])
        self.make_smoke_column("SurvivorWreckSmoke", (wreck_x, wreck_y, wreck_z + 2.0), count=5, height=6.5)
        self.point_light("SurvivorWreckFireLight", (wreck_x + 0.5, wreck_y + 0.5, wreck_z + 1.8), "#FF7A2E", 220)

        radio_y = -20.0
        radio_x = trail_x(radio_y) + 2.9
        radio_z = ground_z(radio_x, radio_y)
        radio = self.empty("BrokenFieldRadio", (radio_x, radio_y, radio_z + 0.25), (0, math.radians(-8), math.radians(18)))
        self.box("BrokenRadioBody", (0, 0, 0.22), (0.78, 0.58, 0.44), burnt_metal, parent=radio)
        self.box("BrokenRadioDial", (-0.41, 0, 0.28), (0.04, 0.34, 0.2), self.M["flash"], parent=radio)
        self.beam("BrokenRadioAntennaA", (radio_x - 0.2, radio_y + 0.15, radio_z + 0.5), (radio_x - 0.45, radio_y + 0.3, radio_z + 1.55), 0.025, self.M["dark"])
        self.beam("BrokenRadioAntennaB", (radio_x - 0.45, radio_y + 0.3, radio_z + 1.55), (radio_x - 0.05, radio_y + 0.55, radio_z + 1.15), 0.02, self.M["dark"])

        # Second beat: three battlefield memorials for the fallen unit.  They
        # sit on the hero's right, where the rear camera can read them without
        # another character competing with the protagonist.
        for index, memorial_y in enumerate((-13.0, -8.0, -3.0)):
            mx = trail_x(memorial_y) + 4.4 + (index % 2) * 0.55
            mz = ground_z(mx, memorial_y)
            self.beam(
                f"FallenMemorialRifle{index}",
                (mx, memorial_y, mz + 0.05),
                (mx - 0.18, memorial_y, mz + 1.25),
                0.055,
                self.M["dark"],
            )
            self.sphere(f"FallenMemorialHelmet{index}", (mx - 0.2, memorial_y, mz + 1.32), (0.34, 0.36, 0.22), camo)
            self.box(f"FallenMemorialCross{index}", (mx + 0.12, memorial_y, mz + 0.82), (0.07, 0.52, 0.08), bark)
            self.box(f"FallenMemorialTag{index}", (mx - 0.27, memorial_y - 0.12, mz + 0.92), (0.035, 0.15, 0.2), self.M["gold"])
            self.cylinder(f"FallenMemorialMound{index}", (mx, memorial_y, mz + 0.08), (1.15, 0.72, 0.12), self.mat("FreshGraveMud", "#2A1C11", roughness=1.0))

        # Fourth beat: a burnt survival camp and defensive sandbags near the
        # contact zone, warmed by one surviving lantern.
        camp_y = 9.0
        camp_x = trail_x(camp_y) - 8.2
        camp_z = ground_z(camp_x, camp_y)
        camp = self.empty("SurvivorBurntCamp", (camp_x, camp_y, camp_z), (0, 0, math.radians(-14)))
        for index, (px, py) in enumerate(((-2.2, -1.5), (2.2, -1.5), (-2.2, 1.5), (2.2, 1.5))):
            self.cylinder(f"SurvivorCampPole{index}", (px, py, 1.05), (0.1, 0.1, 2.1), bark, parent=camp)
        self.box("SurvivorCampTarp", (0, 0, 2.25), (5.2, 3.8, 0.11), tarp, (math.radians(5), math.radians(-5), 0), camp)
        for index, (px, py, pz) in enumerate(((-1.3, -0.6, 0.32), (-0.35, -0.6, 0.32), (-0.85, -0.6, 0.9), (1.2, 0.7, 0.3))):
            self.box(f"SurvivorCampCrate{index}", (px, py, pz), (0.82, 0.68, 0.56), self.M["wood"] if index < 3 else camo, parent=camp)
        lantern = self.sphere("SurvivorCampLantern", (1.65, -1.05, 0.58), (0.26, 0.26, 0.32), self.M["flash"], parent=camp)
        self.oscillate_rotation(lantern, 2, 0.05, 1.6)
        self.point_light("SurvivorCampLanternLight", (1.65, -1.05, 0.68), "#FFB45E", 110, camp)
        self.make_smoke_column("SurvivorCampSmoke", (camp_x - 1.0, camp_y + 0.5, camp_z + 1.8), count=4, height=5.2)

        sandbag_y = 13.0
        sandbag_x = trail_x(sandbag_y) + 7.4
        sandbag_z = ground_z(sandbag_x, sandbag_y)
        for index in range(10):
            angle = math.radians(-70 + index * 15)
            self.sphere(
                f"SurvivorSandbag{index}",
                (sandbag_x + 2.0 * math.cos(angle), sandbag_y + 2.0 * math.sin(angle), sandbag_z + 0.27 + (index % 2) * 0.28),
                (0.68, 0.43, 0.3),
                self.M["sand"],
                (0, 0, angle),
            )
        wire_mat = self.mat("SurvivorTripWire", "#69706B", roughness=0.5, metallic=0.55)
        wire_y = 4.5
        self.beam(
            "SurvivorTripWire",
            (trail_x(wire_y) - 3.2, wire_y, ground_z(trail_x(wire_y) - 3.2, wire_y) + 0.28),
            (trail_x(wire_y) + 3.2, wire_y, ground_z(trail_x(wire_y) + 3.2, wire_y) + 0.28),
            0.024,
            wire_mat,
        )

        # Rain concentrated along the hero corridor, where the close camera
        # can actually see it passing through the rim light.
        for group in range(3):
            rain_root = self.empty(f"SurvivorRainSheet{group}", (0, 0, 0), (math.radians(9), 0, math.radians(-4)))
            for streak in range(26):
                y = self.rng.uniform(-38, 36)
                x = trail_x(y) + self.rng.uniform(-16, 16)
                self.cylinder(
                    f"SurvivorRainStreak{group}_{streak}",
                    (x, y, self.rng.uniform(0.4, 10.5)),
                    (0.033, 0.033, self.rng.uniform(1.35, 2.15)),
                    rain_mat,
                    parent=rain_root,
                )
            phase = group * 0.21
            self.keys(
                rain_root,
                "location",
                [(phase, (0, 0, 0)), (phase + 0.78, (1.4, 0, -10.0))],
                "LINEAR",
            )
            self.set_cycles(rain_root)

        # Distant contact timed broadly to the middle spoken lines.  All
        # flashes stay ahead/side of the hero; he continues walking through.
        def burst(name: str, loc, start_fraction: float, scale: float = 1.0) -> None:
            parts = [
                self.sphere(f"{name}Core", (loc[0], loc[1], loc[2] + 0.5), (0.08, 0.08, 0.08), self.M["fire"]),
                self.cone(f"{name}Flame", (loc[0], loc[1], loc[2] + 0.9), (0.08, 0.08, 0.08), self.M["flash"]),
                self.sphere(f"{name}Smoke", (loc[0] + 0.2, loc[1], loc[2] + 1.25), (0.08, 0.08, 0.08), self.M["smoke_light"]),
            ]
            targets = [
                (1.35 * scale, 1.35 * scale, 1.05 * scale),
                (0.68 * scale, 0.68 * scale, 1.65 * scale),
                (1.55 * scale, 1.55 * scale, 1.2 * scale),
            ]
            for part, target in zip(parts, targets):
                self.keys(
                    part,
                    "scale",
                    [
                        (0.0, (0.08, 0.08, 0.08)),
                        (self.at(start_fraction), (0.08, 0.08, 0.08)),
                        (self.at(min(1.0, start_fraction + 0.008)), target),
                        (self.at(min(1.0, start_fraction + 0.03)), tuple(value * 0.34 for value in target)),
                        (self.at(min(1.0, start_fraction + 0.055)), (0.08, 0.08, 0.08)),
                        (self.duration, (0.08, 0.08, 0.08)),
                    ],
                )

        burst("SurvivorDistantBlast", (camp_x + 1.0, camp_y + 4.0, camp_z), 0.67, 0.95)
        for index, (side, flash_y) in enumerate(((-1, 12.0), (1, 14.0), (-1, 16.0), (1, 18.0))):
            flash_x = trail_x(flash_y) + side * 8.5
            flash_z = ground_z(flash_x, flash_y) + 1.25
            flash = self.cone(
                f"SurvivorMuzzleFlash{index}",
                (flash_x, flash_y, flash_z),
                (0.07, 0.07, 0.07),
                self.M["flash"],
                (0, math.radians(-90 if side < 0 else 90), 0),
            )
            pairs: list[tuple[float, tuple[float, float, float]]] = [(0.0, (0.07, 0.07, 0.07))]
            for pulse in range(4):
                start = 0.48 + index * 0.018 + pulse * 0.045
                pairs.extend(
                    [
                        (self.at(start), (0.07, 0.07, 0.07)),
                        (self.at(start + 0.004), (0.52, 0.52, 0.95)),
                        (self.at(start + 0.013), (0.07, 0.07, 0.07)),
                    ]
                )
            pairs.append((self.duration, (0.07, 0.07, 0.07)))
            self.keys(flash, "scale", pairs, "BEZIER")

        for index in range(3):
            tracer_y = 11.0 + index * 2.4
            start_x = trail_x(tracer_y) - 8.0
            end_x = trail_x(tracer_y) + 8.0
            tracer_z = ground_z(start_x, tracer_y) + 3.4 + index * 0.35
            tracer = self.sphere(f"SurvivorTracer{index}", (start_x, tracer_y, tracer_z), (0.02, 0.02, 0.02), flare_mat)
            self.keys(
                tracer,
                "scale",
                [
                    (0.0, (0.02, 0.02, 0.02)),
                    (self.at(0.5), (0.02, 0.02, 0.02)),
                    (self.at(0.506), (1.15, 0.05, 0.05)),
                    (self.at(0.69), (1.15, 0.05, 0.05)),
                    (self.at(0.696), (0.02, 0.02, 0.02)),
                    (self.duration, (0.02, 0.02, 0.02)),
                ],
            )
            delay = index * 0.012
            self.keys(
                tracer,
                "location",
                [
                    (self.at(0.506 + delay), (start_x, tracer_y, tracer_z)),
                    (self.at(0.54 + delay), (end_x, tracer_y + 0.3, tracer_z - 0.15)),
                    (self.at(0.544 + delay), (start_x, tracer_y, tracer_z)),
                    (self.at(0.61 + delay), (start_x, tracer_y, tracer_z)),
                    (self.at(0.644 + delay), (end_x, tracer_y + 0.3, tracer_z - 0.15)),
                    (self.at(0.69), (start_x, tracer_y, tracer_z)),
                ],
                "LINEAR",
            )

        flare_start = (trail_x(26.0) + 5.0, 26.0, ground_z(trail_x(26.0) + 5.0, 26.0) + 1.0)
        flare = self.sphere("EnemySignalFlare", flare_start, (0.04, 0.04, 0.04), flare_mat)
        self.keys(
            flare,
            "location",
            [
                (self.at(0.38), flare_start),
                (self.at(0.49), (flare_start[0] - 2.0, flare_start[1] + 3.0, flare_start[2] + 10.5)),
                (self.at(0.6), (flare_start[0] - 3.0, flare_start[1] + 4.0, flare_start[2] + 7.0)),
            ],
            "BEZIER",
        )
        self.keys(
            flare,
            "scale",
            [
                (0.0, (0.04, 0.04, 0.04)),
                (self.at(0.38), (0.04, 0.04, 0.04)),
                (self.at(0.405), (0.42, 0.42, 0.42)),
                (self.at(0.57), (0.34, 0.34, 0.34)),
                (self.at(0.605), (0.04, 0.04, 0.04)),
                (self.duration, (0.04, 0.04, 0.04)),
            ],
        )
        for index in range(5):
            start = (trail_x(8.0) - 4 + index * 1.8, 8 + (index % 2) * 1.6, 6.5 + index * 0.3)
            bird = self.cone(f"SurvivorBird{index}", start, (0.85, 0.25, 0.22), self.M["black"], (0, math.radians(-90), 0))
            end = (start[0] + 28 + index * 2, start[1] + 12, start[2] + 7)
            self.keys(bird, "location", [(self.at(0.47), start), (self.at(0.6), end)], "BEZIER")

        # The one continuous hero path and its locked rear camera.  Every
        # camera key is behind the corresponding hero key along -Y (the route
        # runs generally north), with only a small lateral shoulder offset.
        fractions = (0.0, 0.14, 0.28, 0.42, 0.56, 0.7, 0.84, 0.92, 1.0)
        hero_ys = (-27.0, -20.0, -14.0, -7.0, 0.0, 7.0, 14.0, 19.0, 24.0)
        hero_offsets = (-0.3, 0.2, -0.2, 0.35, -0.25, 0.2, -0.1, 0.0, 0.0)
        hero_locations: list[tuple[float, float, float]] = []
        hero_headings: list[float] = []
        for y, offset in zip(hero_ys, hero_offsets):
            x = trail_x(y) + offset
            bridge_lift = 0.5 if y >= 19.0 else 0.0
            hero_locations.append((x, y, ground_z(x, y) + bridge_lift))
            hero_headings.append(math.atan2(1.0, trail_dx_dy(y)))
        hero_scale = 1.08
        hero = self.make_hero_soldier("LastSurvivorHero", hero_locations[0], hero_headings[0], scale=hero_scale)
        self.keys(
            hero,
            "location",
            [(self.at(fraction), location) for fraction, location in zip(fractions, hero_locations)],
            "BEZIER",
        )
        self.keys(
            hero,
            "rotation_euler",
            [(self.at(fraction), (0, 0, heading)) for fraction, heading in zip(fractions, hero_headings)],
            "BEZIER",
        )
        # A brief duck under the distant fire, achieved by lowering only the
        # vertical scale; his feet remain planted on the route.
        self.keys(
            hero,
            "scale",
            [
                (self.at(0.46), (hero_scale, hero_scale, hero_scale)),
                (self.at(0.52), (hero_scale, hero_scale, hero_scale * 0.86)),
                (self.at(0.59), (hero_scale, hero_scale, hero_scale)),
                (self.duration, (hero_scale, hero_scale, hero_scale)),
            ],
            "BEZIER",
        )

        camera_offsets = (-1.2, -0.9, 0.75, 1.0, -0.9, -0.65, 0.65, 0.25, 0.0)
        camera_distances = (7.8, 7.2, 6.9, 7.2, 7.6, 8.2, 8.8, 9.3, 10.2)
        camera_heights = (2.1, 1.95, 1.9, 2.0, 2.1, 2.3, 2.55, 2.65, 2.75)
        camera_positions: list[tuple[float, tuple[float, float, float]]] = []
        camera_targets: list[tuple[float, tuple[float, float, float]]] = []
        focus_pairs: list[tuple[float, float]] = []
        for fraction, hero_loc, y, offset, distance, height in zip(
            fractions,
            hero_locations,
            hero_ys,
            camera_offsets,
            camera_distances,
            camera_heights,
        ):
            cam_x = hero_loc[0] + offset
            cam_y = hero_loc[1] - distance
            cam_pos = (cam_x, cam_y, ground_z(cam_x, cam_y) + height)
            forward_x = trail_dx_dy(y)
            forward_len = math.hypot(forward_x, 1.0)
            target = (
                hero_loc[0] + (forward_x / forward_len) * 1.7,
                hero_loc[1] + (1.0 / forward_len) * 1.7,
                hero_loc[2] + 1.42,
            )
            camera_positions.append((fraction, cam_pos))
            camera_targets.append((fraction, target))
            focus_pairs.append((fraction, max(2.5, math.dist(cam_pos, hero_loc) * 0.96)))
        self.setup_camera(
            camera_positions,
            camera_targets,
            [(0.0, 46), (0.28, 49), (0.56, 47), (0.84, 45), (1.0, 43)],
            focus_pairs=focus_pairs,
            fstop=2.2,
        )

    def build_jungle_war(self) -> None:
        """Dark aerial rainforest ambush built for the Turbo profile.

        The set is deliberately deep rather than merely wide: a muddy patrol
        trail and stream recede through several canopy/fog layers while the
        single continuous camera path stays high above the trees.  Shared
        low-segment primitives keep the object count far below the coastal
        WWII set, which matters more than adding expensive Cycles volumetrics
        at one sample.
        """
        self.setup_world_and_lights(
            world_strength=0.22,
            sun_energy=1.55,
            sun_rotation=(math.radians(58), math.radians(16), math.radians(-38)),
            sun_color="#BFD3C3",
            fill_energy=75.0,
        )
        self.setup_mist_compositor(color="#2A3D33", max_factor=0.52, start=30.0, depth=100.0)

        canopy_dark = self.mat("JungleCanopyDark", "#102B18", roughness=0.98)
        canopy_mid = self.mat("JungleCanopyMid", "#1E4A28", roughness=0.96)
        canopy_wet = self.mat("JungleCanopyWet", "#2C6135", roughness=0.9)
        undergrowth = self.mat("JungleUndergrowth", "#17351F", roughness=0.98)
        fern = self.mat("JungleFern", "#24552D", roughness=0.95)
        bark = self.mat("WetBark", "#2E2118", roughness=0.97)
        bamboo = self.mat("WetBamboo", "#3F5B33", roughness=0.88)
        camo = self.mat("JungleCamo", "#2E442A", roughness=0.94)
        camo_dark = self.mat("JungleCamoDark", "#1E2E22", roughness=0.96)
        mud_metal = self.mat("MuddyMetal", "#343A33", roughness=0.72, metallic=0.22)
        tarp = self.mat("WetTarp", "#31463A", roughness=0.92)
        rain_mat = self.mat("RainStreaks", "#B7CCDC", roughness=1.0, alpha=0.34, emission="#8FAFC4", emission_strength=0.28)
        storm_mat = self.mat("StormCloud", "#39443F", roughness=1.0, alpha=0.62)

        def trail_x(y: float) -> float:
            return -10.0 + 0.18 * y + 4.0 * math.sin(y * 0.055)

        def stream_y(x: float) -> float:
            return 22.0 + 3.0 * math.sin(x * 0.05)

        craters = [(-13.0, 3.0), (-2.0, 13.0), (-24.0, -14.0), (10.0, -4.0)]

        def ground_z(x: float, y: float) -> float:
            z = 0.48 * math.sin(x * 0.045) * math.cos(y * 0.055) + 0.28 * math.sin((x - y) * 0.052)
            trail_distance = abs(x - trail_x(y))
            if trail_distance < 5.0:
                z *= 0.25 + 0.15 * trail_distance
            stream_distance = abs(y - stream_y(x))
            if stream_distance < 5.0:
                z -= 0.62 * (1.0 - stream_distance / 5.0)
            if y > 30.0:
                z += (y - 30.0) * 0.022
            for cx, cy in craters:
                distance = math.hypot(x - cx, y - cy)
                if distance < 4.0:
                    z -= 0.48 * (1.0 - distance / 4.0)
            return z

        def ground_color(x: float, y: float, z: float):
            if abs(y - stream_y(x)) < 3.4:
                return (0.035, 0.115, 0.13, 1)
            if abs(x - trail_x(y)) < 3.1:
                return (0.17, 0.105, 0.05, 1)
            for cx, cy in craters:
                if math.hypot(x - cx, y - cy) < 3.7:
                    return (0.075, 0.055, 0.035, 1)
            variation = 0.018 * math.sin(x * 0.42 + y * 0.31)
            return (0.04 + variation, 0.115 + variation, 0.048, 1)

        terrain_mat = self.vertex_material("JungleWarVertex", roughness=0.98)
        self.grid_terrain(
            "JungleWarTerrain",
            x_range=(-118, 118),
            y_range=(-98, 92),
            nx=68,
            ny=44,
            height_fn=ground_z,
            color_fn=ground_color,
            material=terrain_mat,
        )
        # A very dark apron far below the sculpted terrain prevents the high
        # opening/pull-back shots from revealing a rectangular world edge.
        self.box("JungleHorizonGround", (0, 0, -1.7), (560, 560, 0.2), self.mat("JungleHorizon", "#0E2015", roughness=1.0))

        # A segmented dark stream gives the final third a visible crossing
        # without an animated fluid/volume simulation.
        stream_mat = self.mat("JungleStream", "#183632", roughness=0.24, metallic=0.04)
        for index, x in enumerate(range(-70, 76, 10)):
            y = stream_y(float(x))
            angle = math.atan(0.15 * math.cos(x * 0.05))
            self.box(
                f"JungleStreamSegment{index}",
                (x, y, ground_z(float(x), y) + 0.13),
                (10.4, 5.2, 0.08),
                stream_mat,
                (0, 0, angle),
            )
        # Fallen-tree bridge across the stream on the patrol route.
        bridge_x = trail_x(22.0)
        self.beam(
            "StreamLogBridge",
            (bridge_x - 1.0, 15.5, ground_z(bridge_x, 15.5) + 0.5),
            (bridge_x + 0.6, 29.0, ground_z(bridge_x, 29.0) + 0.55),
            0.72,
            bark,
        )

        # Far canopy silhouettes and storm clouds close the horizon.  There is
        # no flat backdrop plane, so the high camera sees depth instead of a wall.
        for index in range(24):
            x = -94 + index * 8.1 + self.rng.uniform(-2.0, 2.0)
            y = 62 + self.rng.uniform(-4.0, 9.0)
            z = ground_z(x, y) + self.rng.uniform(4.0, 7.0)
            self.sphere(
                f"DistantCanopy{index}",
                (x, y, z),
                (self.rng.uniform(10, 16), self.rng.uniform(7, 11), self.rng.uniform(5, 8)),
                canopy_dark if index % 3 else canopy_mid,
            )
        for index, (x, y, z, scale) in enumerate(((-58, 48, 25, 7), (-12, 58, 29, 9), (38, 50, 26, 7), (76, 62, 31, 8))):
            cloud = self.empty(f"StormCloud{index}", (x, y, z))
            cloud.scale = (scale, scale, scale)
            for puff_index, offset in enumerate(((-1.1, 0, 0), (0, 0.15, 0.18), (1.1, -0.1, 0))):
                self.sphere(f"StormCloudPuff{index}_{puff_index}", offset, (1.7, 0.85, 0.55), storm_mat, parent=cloud)
            self.move(cloud, 0, self.duration, (x + 7 + index * 1.5, y, z), start_location=(x, y, z), interpolation="LINEAR")

        # Main jungle.  Positions leave the patrol/stream corridor readable
        # from the drone while crowding the frame edges and background.
        tree_pairs = [(canopy_dark, canopy_mid), (canopy_mid, canopy_wet), (undergrowth, canopy_mid)]
        tree_positions: list[tuple[float, float, float]] = []
        attempts = 0
        while len(tree_positions) < 68 and attempts < 600:
            attempts += 1
            x = self.rng.uniform(-84, 84)
            y = self.rng.uniform(-57, 57)
            if abs(x - trail_x(y)) < 6.4 or abs(y - stream_y(x)) < 4.2:
                continue
            scale = self.rng.uniform(1.45, 2.9)
            tree_positions.append((x, y, scale))
        for index, (x, y, scale) in enumerate(tree_positions):
            crown, crown_light = tree_pairs[index % len(tree_pairs)]
            self.make_tree(
                f"JungleTree{index}",
                (x, y, ground_z(x, y) - 0.08),
                scale=scale,
                palm=(index % 7 == 3),
                trunk_material=bark,
                crown_material=crown,
                crown_material_light=crown_light,
            )

        hero_trees = [(-19.0, -5.0, 2.75), (5.0, 2.0, 3.0), (-17.0, 13.0, 2.85), (10.0, 16.0, 2.65)]
        for index, (x, y, scale) in enumerate(hero_trees):
            self.make_tree(
                f"AmbushHeroTree{index}",
                (x, y, ground_z(x, y) - 0.08),
                scale=scale,
                trunk_material=bark,
                crown_material=canopy_dark,
                crown_material_light=canopy_mid,
            )

        # Undergrowth, ferns, bamboo, vines, rocks and fallen logs create
        # concealment at soldier height and dark texture below the canopy.
        for index in range(86):
            x = self.rng.uniform(-82, 82)
            y = self.rng.uniform(-56, 56)
            if abs(x - trail_x(y)) < 3.4:
                x += 4.5 if x >= trail_x(y) else -4.5
            self.sphere(
                f"JungleBush{index}",
                (x, y, ground_z(x, y) + 0.32),
                (self.rng.uniform(1.1, 2.9), self.rng.uniform(0.9, 2.3), self.rng.uniform(0.55, 1.15)),
                undergrowth if index % 3 else canopy_mid,
            )
        for index in range(42):
            x = self.rng.uniform(-72, 72)
            y = self.rng.uniform(-52, 50)
            if abs(x - trail_x(y)) < 3.2:
                continue
            self.cone(f"JungleFern{index}", (x, y, ground_z(x, y) + 0.35), (1.15, 1.15, 0.8), fern)
        for cluster in range(8):
            cx = self.rng.uniform(-62, 62)
            cy = self.rng.uniform(-44, 44)
            if abs(cx - trail_x(cy)) < 7:
                cx += 10
            for stalk in range(5):
                x = cx + self.rng.uniform(-0.9, 0.9)
                y = cy + self.rng.uniform(-0.9, 0.9)
                height = self.rng.uniform(4.5, 7.5)
                self.cylinder(
                    f"Bamboo{cluster}_{stalk}",
                    (x, y, ground_z(x, y) + height / 2),
                    (0.18, 0.18, height),
                    bamboo,
                    (math.radians(self.rng.uniform(-3, 3)), math.radians(self.rng.uniform(-3, 3)), 0),
                )
        vine_mat = self.mat("HangingVine", "#1B3323", roughness=0.98)
        for index, (x, y, scale) in enumerate(tree_positions[:28]):
            top = (x + self.rng.uniform(-1.2, 1.2), y + self.rng.uniform(-1.0, 1.0), ground_z(x, y) + 2.15 * scale)
            bottom = (top[0] + self.rng.uniform(-0.5, 0.5), top[1] + self.rng.uniform(-0.5, 0.5), ground_z(x, y) + 0.25)
            self.beam(f"HangingVine{index}", top, bottom, 0.055, vine_mat)
        for index in range(13):
            x = self.rng.uniform(-65, 65)
            y = self.rng.uniform(-50, 48)
            if abs(x - trail_x(y)) < 4:
                continue
            angle = self.rng.uniform(0, math.tau)
            end = (x + 5.0 * math.cos(angle), y + 5.0 * math.sin(angle))
            self.beam(
                f"FallenLog{index}",
                (x, y, ground_z(x, y) + 0.32),
                (end[0], end[1], ground_z(end[0], end[1]) + 0.32),
                0.58,
                bark,
            )
        for index in range(22):
            x = self.rng.uniform(-74, 74)
            y = self.rng.uniform(-54, 54)
            self.box(
                f"JungleRock{index}",
                (x, y, ground_z(x, y) + 0.22),
                (self.rng.uniform(0.7, 1.8), self.rng.uniform(0.6, 1.4), self.rng.uniform(0.35, 0.8)),
                self.M["stone"],
                (0, 0, self.rng.uniform(0, math.tau)),
            )

        # Reflective mud puddles punctuate the trail in the rain.
        for index, y in enumerate((-38, -28, -18, -9, -1, 7, 14, 27, 34)):
            x = trail_x(float(y)) + self.rng.uniform(-0.9, 0.9)
            self.cylinder(
                f"TrailPuddle{index}",
                (x, y, ground_z(x, float(y)) + 0.07),
                (self.rng.uniform(2.2, 3.6), self.rng.uniform(1.1, 1.9), 0.045),
                stream_mat,
            )

        # A burnt-out supply truck, half sunk beside the route.  It is built
        # statically rather than reusing the moving-truck helper, whose wheels
        # would otherwise spin while the wreck remains in the mud.
        wreck_y = -21.0
        wreck_x = trail_x(wreck_y) - 5.4
        wreck_z = ground_z(wreck_x, wreck_y)
        wreck = self.empty("BurntSupplyTruck", (wreck_x, wreck_y, wreck_z + 0.22), (math.radians(4), 0, math.radians(76)))
        self.box("WreckCab", (1.8, 0, 0.95), (1.6, 1.75, 1.3), mud_metal, parent=wreck)
        self.box("WreckWindshield", (2.55, 0, 1.22), (0.08, 1.3, 0.55), self.M["black"], parent=wreck)
        self.box("WreckBed", (-0.95, 0, 1.0), (3.7, 2.0, 1.2), camo_dark, parent=wreck)
        self.box("WreckCanvas", (-1.0, 0, 1.72), (3.1, 1.75, 0.38), self.M["black"], (0, math.radians(-4), 0), wreck)
        for wheel_index, (wx, wy) in enumerate(((-1.9, -1.05), (-1.9, 1.05), (1.7, -1.05), (1.7, 1.05))):
            self.cylinder(f"WreckWheel{wheel_index}", (wx, wy, 0.36), (0.72, 0.2, 0.72), self.M["black"], (math.radians(90), 0, 0), wreck)
        for index in range(6):
            ratio = index / 5
            smoke = self.sphere(
                f"WreckSmoke{index}",
                (wreck_x + math.sin(index * 1.4) * 0.5, wreck_y + 0.4, wreck_z + 2.3 + ratio * 6.0),
                (0.9 + ratio * 1.8, 0.75 + ratio * 1.4, 0.65 + ratio * 1.1),
                self.M["smoke"] if index % 2 == 0 else self.M["smoke_light"],
            )
            self.oscillate_location_z(smoke, 0.18, 3.4, index * 0.7)
        self.point_light("WreckFireLight", (wreck_x, wreck_y, wreck_z + 1.7), "#FF7A2E", 180)

        # Survival shelter near the stream: camo tarp, crates, bedrolls and a
        # small warm lantern that gives the dark final section one focal glow.
        camp_x, camp_y = 17.0, 32.0
        camp_z = ground_z(camp_x, camp_y)
        camp = self.empty("SurvivalCamp", (camp_x, camp_y, camp_z), (0, 0, math.radians(-18)))
        for index, (px, py) in enumerate(((-2.4, -1.7), (2.4, -1.7), (-2.4, 1.7), (2.4, 1.7))):
            self.cylinder(f"CampPole{index}", (px, py, 1.15), (0.11, 0.11, 2.3), bark, parent=camp)
        self.box("CampTarp", (0, 0, 2.42), (5.7, 4.3, 0.12), tarp, (math.radians(5), math.radians(-3), 0), camp)
        for index, (px, py, pz) in enumerate(((-1.5, -0.7, 0.35), (-0.45, -0.7, 0.35), (-1.0, -0.7, 1.0), (1.4, 0.8, 0.32))):
            self.box(f"CampCrate{index}", (px, py, pz), (0.9, 0.75, 0.62), self.M["wood"] if index < 3 else camo, parent=camp)
        for index, px in enumerate((-1.2, 0.7)):
            self.box(f"CampBedroll{index}", (px, 1.05, 0.17), (1.65, 0.62, 0.2), camo_dark, parent=camp)
        lantern = self.sphere("CampLantern", (1.8, -1.2, 0.62), (0.28, 0.28, 0.34), self.M["flash"], parent=camp)
        self.oscillate_rotation(lantern, 2, 0.05, 1.7)
        self.point_light("CampLanternLight", (1.8, -1.2, 0.72), "#FFB45E", 95, camp)

        # Hidden mortar pit and two tripwire lines reinforce the guerrilla
        # warfare story without turning this back into an open WWII field.
        mortar_x, mortar_y = -25.0, 9.0
        mortar_z = ground_z(mortar_x, mortar_y)
        mortar = self.empty("HiddenMortar", (mortar_x, mortar_y, mortar_z), (0, 0, math.radians(18)))
        self.box("MortarBase", (0, 0, 0.18), (1.15, 1.0, 0.24), mud_metal, parent=mortar)
        self.cylinder("MortarTube", (0.15, 0, 0.92), (0.17, 0.17, 1.55), self.M["dark"], (0, math.radians(-28), 0), mortar)
        for index in range(16):
            angle = math.radians(-75 + index * 10)
            radius = 2.25
            self.sphere(
                f"MortarSandbag{index}",
                (radius * math.cos(angle), radius * math.sin(angle), 0.28 + (index % 2) * 0.3),
                (0.72, 0.46, 0.32),
                self.M["sand"],
                (0, 0, angle),
                mortar,
            )
        wire_mat = self.mat("TripWire", "#69706B", roughness=0.5, metallic=0.55)
        for wire_index, wire_y in enumerate((-2.0, 12.0)):
            left_x = trail_x(wire_y) - 3.4
            right_x = trail_x(wire_y) + 3.4
            self.beam(
                f"TripWire{wire_index}",
                (left_x, wire_y, ground_z(left_x, wire_y) + 0.28),
                (right_x, wire_y, ground_z(right_x, wire_y) + 0.28),
                0.025,
                wire_mat,
            )
            for side, wx in enumerate((left_x, right_x)):
                self.cylinder(f"TripWireStake{wire_index}_{side}", (wx, wire_y, ground_z(wx, wire_y) + 0.25), (0.07, 0.07, 0.55), bark)

        # Tree platforms with soldiers literally hidden in the branches.
        platform_specs = [hero_trees[0], hero_trees[1], hero_trees[2]]
        for index, (x, y, scale) in enumerate(platform_specs):
            base_z = ground_z(x, y)
            platform_z = base_z + 1.48 * scale
            platform_x = x + (1.35 if index != 1 else -1.25)
            platform_y = y - 1.05
            self.box(f"TreePlatform{index}", (platform_x, platform_y, platform_z), (2.3, 1.65, 0.16), bark)
            self.beam(
                f"TreePlatformBrace{index}",
                (x, y, base_z + 0.55 * scale),
                (platform_x, platform_y, platform_z - 0.08),
                0.11,
                bark,
            )
            heading = math.radians(16) if platform_x < trail_x(platform_y) else math.radians(164)
            self.make_person(
                f"CanopySoldier{index}",
                (platform_x, platform_y, platform_z + 0.1),
                heading,
                uniform=camo if index % 2 == 0 else camo_dark,
                scale=0.94,
                phase=index * 1.3,
                move_distance=0,
            )
            # Leaf screens break up each silhouette from the aerial camera.
            for leaf_index, (ox, oy, oz) in enumerate(((0.8, -0.65, 0.65), (-0.85, 0.45, 0.8), (0.15, 0.8, 1.05))):
                self.sphere(
                    f"CanopyCamo{index}_{leaf_index}",
                    (platform_x + ox, platform_y + oy, platform_z + oz),
                    (0.95, 0.82, 0.62),
                    canopy_dark if leaf_index % 2 == 0 else canopy_mid,
                )

        # Ground ambush party, partially screened by bushes on both banks.
        hidden_specs: list[tuple[float, float, float]] = []
        for index, (y, side) in enumerate(((-4, -1), (-1, 1), (2, -1), (5, 1), (8, -1), (11, 1), (14, -1), (17, 1))):
            x = trail_x(float(y)) + side * self.rng.uniform(5.2, 8.0)
            z = ground_z(x, float(y))
            hidden_specs.append((x, float(y), z))
            heading = 0.0 if side < 0 else math.pi
            self.make_person(
                f"HiddenSoldier{index}",
                (x, y, z),
                heading,
                uniform=camo_dark if index % 2 else camo,
                scale=0.96,
                phase=index * 0.8,
                move_distance=0,
            )
            self.sphere(
                f"HiddenSoldierCover{index}",
                (x - side * 0.75, y - 0.35, z + 0.42),
                (1.35, 1.05, 0.72),
                undergrowth,
            )

        # Main patrol follows the winding trail and crosses the ambush zone
        # around 54% of the shot, then continues toward the stream/camp.
        patrol_heading = math.radians(76)
        patrol_fractions = (0.0, 0.22, 0.45, 0.68, 0.86, 1.0)
        for index in range(5):
            start_y = -42.0 - index * 3.1
            lateral = (-0.85, 0.75, -0.25, 1.05, 0.1)[index]
            start = (trail_x(start_y) + lateral, start_y, ground_z(trail_x(start_y) + lateral, start_y))
            soldier = self.make_person(
                f"JunglePatrol{index}",
                start,
                patrol_heading,
                uniform=camo if index % 2 == 0 else camo_dark,
                phase=index * 0.9,
                move_distance=0,
            )
            path: list[tuple[float, tuple[float, float, float]]] = []
            for fraction in patrol_fractions:
                y = start_y + 78.0 * fraction
                x = trail_x(y) + lateral
                path.append((self.at(fraction), (x, y, ground_z(x, y))))
            self.keys(soldier, "location", path, "BEZIER")

        # A smaller opposing group retreats into the background after contact.
        for index in range(3):
            start_y = 31.0 - index * 2.6
            lateral = (1.2, -1.0, 0.4)[index]
            start = (trail_x(start_y) + lateral, start_y, ground_z(trail_x(start_y) + lateral, start_y))
            soldier = self.make_person(
                f"GuerrillaRetreat{index}",
                start,
                math.radians(104),
                uniform=camo_dark,
                phase=2.0 + index,
                move_distance=0,
            )
            path = []
            for fraction in (0.0, 0.48, 0.72, 1.0):
                travel = 0.0 if fraction <= 0.48 else (fraction - 0.48) / 0.52 * 22.0
                y = start_y + travel
                x = trail_x(y) + lateral + travel * 0.22
                path.append((self.at(fraction), (x, y, ground_z(x, y))))
            self.keys(soldier, "location", path, "BEZIER")

        # Rain is four looping sheets of shared-mesh streaks.  It remains
        # legible from above but does not add a particle simulation or volume.
        for group in range(4):
            rain_root = self.empty(f"RainSheet{group}", (0, 0, 0), (math.radians(10), 0, math.radians(-5)))
            for streak in range(34):
                self.cylinder(
                    f"RainStreak{group}_{streak}",
                    (self.rng.uniform(-78, 78), self.rng.uniform(-62, 62), self.rng.uniform(0.5, 16.5)),
                    (0.035, 0.035, self.rng.uniform(1.35, 2.1)),
                    rain_mat,
                    parent=rain_root,
                )
            phase = group * 0.19
            self.keys(
                rain_root,
                "location",
                [(phase, (0, 0, 0)), (phase + 0.82, (2.2, 0, -16.0))],
                "LINEAR",
            )
            self.set_cycles(rain_root)

        # Fog is supplied by the depth-based Mist compositor configured at
        # the start of this builder; no transparent fog geometry is created.

        # Birds burst out of the canopy as contact begins.
        for index in range(7):
            start = (-8 + index * 2.2, 3 + (index % 3) * 2.0, 7.0 + index * 0.35)
            bird = self.cone(f"JungleBird{index}", start, (0.95, 0.27, 0.24), self.M["black"], (0, math.radians(-90), 0))
            end = (start[0] + 34 + index * 3, start[1] + 15, start[2] + 8)
            self.keys(bird, "location", [(self.at(0.52), start), (self.at(0.65), end)], "BEZIER")

        # Timed ambush effects.  Unlike the looping battlefield explosions,
        # these keys stay tiny before/after the contact section.
        def burst(name: str, loc, start_fraction: float, scale: float = 1.0) -> None:
            parts = [
                self.sphere(f"{name}Core", (loc[0], loc[1], loc[2] + 0.55), (0.08, 0.08, 0.08), self.M["fire"]),
                self.cone(f"{name}Flame", (loc[0], loc[1], loc[2] + 0.95), (0.08, 0.08, 0.08), self.M["flash"]),
                self.sphere(f"{name}Smoke", (loc[0] + 0.25, loc[1], loc[2] + 1.3), (0.08, 0.08, 0.08), self.M["smoke_light"]),
            ]
            targets = [(1.45 * scale, 1.45 * scale, 1.12 * scale), (0.72 * scale, 0.72 * scale, 1.75 * scale), (1.7 * scale, 1.7 * scale, 1.32 * scale)]
            for part, target in zip(parts, targets):
                self.keys(
                    part,
                    "scale",
                    [
                        (0.0, (0.08, 0.08, 0.08)),
                        (self.at(start_fraction), (0.08, 0.08, 0.08)),
                        (self.at(min(1.0, start_fraction + 0.006)), target),
                        (self.at(min(1.0, start_fraction + 0.024)), tuple(value * 0.34 for value in target)),
                        (self.at(min(1.0, start_fraction + 0.045)), (0.08, 0.08, 0.08)),
                        (self.duration, (0.08, 0.08, 0.08)),
                    ],
                )

        burst("TrailExplosion", (trail_x(4.0) + 1.0, 4.0, ground_z(trail_x(4.0), 4.0)), 0.565, 1.08)
        burst("StreamExplosion", (trail_x(15.0) - 1.2, 15.0, ground_z(trail_x(15.0), 15.0)), 0.76, 0.88)

        for index, (x, y, z) in enumerate(hidden_specs[:6]):
            side = -1 if x < trail_x(y) else 1
            flash_loc = (x - side * 0.62, y - 0.15, z + 1.08)
            flash = self.cone(
                f"AmbushMuzzleFlash{index}",
                flash_loc,
                (0.07, 0.07, 0.07),
                self.M["flash"],
                (0, math.radians(-90 if side < 0 else 90), 0),
            )
            pairs: list[tuple[float, tuple[float, float, float]]] = [(0.0, (0.07, 0.07, 0.07))]
            for pulse in range(5):
                start = 0.545 + index * 0.011 + pulse * 0.038
                if start > 0.82:
                    break
                pairs.extend(
                    [
                        (self.at(start), (0.07, 0.07, 0.07)),
                        (self.at(start + 0.0035), (0.58, 0.58, 1.05)),
                        (self.at(start + 0.011), (0.07, 0.07, 0.07)),
                    ]
                )
            pairs.append((self.duration, (0.07, 0.07, 0.07)))
            self.keys(flash, "scale", pairs, "BEZIER")

        for index in range(6):
            y = -1.0 + index * 3.0
            start_x = trail_x(y) - (5.0 if index % 2 == 0 else -5.0)
            end_x = trail_x(y) + (2.0 if index % 2 == 0 else -2.0)
            z = ground_z(start_x, y) + 1.05
            tracer = self.sphere(f"AmbushTracer{index}", (start_x, y, z), (0.02, 0.02, 0.02), self.M["flash"])
            self.keys(
                tracer,
                "scale",
                [
                    (0.0, (0.02, 0.02, 0.02)),
                    (self.at(0.54), (0.02, 0.02, 0.02)),
                    (self.at(0.545), (1.25, 0.055, 0.055)),
                    (self.at(0.78), (1.25, 0.055, 0.055)),
                    (self.at(0.785), (0.02, 0.02, 0.02)),
                    (self.duration, (0.02, 0.02, 0.02)),
                ],
            )
            delay = index * 0.009
            self.keys(
                tracer,
                "location",
                [
                    (self.at(0.545 + delay), (start_x, y, z)),
                    (self.at(0.565 + delay), (end_x, y + 0.4, z - 0.08)),
                    (self.at(0.568 + delay), (start_x, y, z)),
                    (self.at(0.62 + delay), (start_x, y, z)),
                    (self.at(0.64 + delay), (end_x, y + 0.4, z - 0.08)),
                    (self.at(0.643 + delay), (start_x, y, z)),
                    (self.at(0.78), (start_x, y, z)),
                ],
                "LINEAR",
            )

        # One uninterrupted aerial move: opening canopy reveal, patrol track,
        # ambush reveal, stream crossing, then a high pull-back over the camp.
        self.setup_camera(
            [
                (0.0, (-64, -72, 34)),
                (0.16, (-46, -58, 27)),
                (0.32, (-24, -46, 21)),
                (0.48, (6, -36, 18)),
                (0.62, (24, -25, 20)),
                (0.76, (20, -10, 25)),
                (0.88, (-10, -18, 34)),
                (1.0, (-38, -36, 42)),
            ],
            [
                (0.0, (-20, -32, 2)),
                (0.16, (-16, -20, 2)),
                (0.32, (-12, -8, 2)),
                (0.48, (-8, 2, 2)),
                (0.62, (-4, 10, 2)),
                (0.76, (-1, 20, 2)),
                (0.88, (0, 28, 2)),
                (1.0, (0, 30, 2)),
            ],
            [(0.0, 30), (0.3, 36), (0.55, 43), (0.78, 39), (1.0, 33)],
            focus_pairs=[(0.0, 70), (0.16, 57), (0.32, 46), (0.48, 45), (0.62, 50), (0.76, 45), (0.88, 60), (1.0, 90)],
            fstop=2.0,
        )

    def build_nature(self) -> None:
        self._generic_stage()
        terrain_mat = self.vertex_material("ValleyVertex", roughness=0.96)

        def height(x: float, y: float) -> float:
            z = 0.55 * math.sin(x * 0.045) * math.cos(y * 0.06) + 0.25 * math.sin((x - y) * 0.07)
            river_y = -4 + 5 * math.sin(x * 0.045)
            if abs(y - river_y) < 4.5:
                z -= 0.42 * (1 - abs(y - river_y) / 4.5)
            return z

        def color(x: float, y: float, z: float):
            river_y = -4 + 5 * math.sin(x * 0.045)
            if abs(y - river_y) < 3.3:
                return (0.14, 0.43, 0.66, 1)
            if abs(y - river_y) < 5.2:
                return (0.68, 0.6, 0.4, 1)
            variation = 0.035 * math.sin(x * 0.5 + y * 0.3)
            return (0.22 + variation, 0.48 + variation, 0.22, 1)

        self.grid_terrain("Valley", x_range=(-100, 100), y_range=(-55, 48), nx=58, ny=34, height_fn=height, color_fn=color, material=terrain_mat)
        for index, (x, y, s) in enumerate(((-78, 38, 25), (-46, 42, 19), (43, 40, 23), (76, 37, 28))):
            self.cone(f"Mountain{index}", (x, y, 6), (s, s * 0.72, 15 + index * 1.5), self.M["stone"])
            self.cone(f"SnowCap{index}", (x, y, 13.5 + index * 1.5), (s * 0.3, s * 0.22, 3.4), self.M["white"])
        tree_positions = []
        for index in range(30):
            x = self.rng.uniform(-72, 72)
            y = self.rng.uniform(-34, 30)
            if abs(y - (-4 + 5 * math.sin(x * 0.045))) < 6:
                continue
            tree_positions.append((x, y))
            self.make_tree(f"ValleyTree{index}", (x, y, 0.35), scale=self.rng.uniform(0.85, 1.5))
        cottage = self.empty("ValleyCottage", (-28, 16, 0.4), (0, 0, math.radians(-10)))
        self.box("CottageBody", (0, 0, 1.65), (6.6, 4.8, 3.3), self.M["wood"], parent=cottage)
        self.cone("CottageRoof", (0, 0, 4.25), (7.6, 5.6, 2.0), self.M["red"], (0, 0, math.radians(45)), cottage)
        self.box("CottageDoor", (0, -2.46, 1.15), (1.1, 0.1, 2.0), self.M["dark"], parent=cottage)
        self.box("CottageWindow", (-1.8, -2.46, 1.8), (1.0, 0.1, 0.9), self.mat("CottageGlow", "#FFD27A", emission="#FFB84D", emission_strength=1.6), parent=cottage)
        for index in range(3):
            deer = self.empty(f"Deer{index}", (8 + index * 9, 10 + index * 3, 0.55), (0, 0, math.radians(-18 + index * 13)))
            self.box(f"DeerBody{index}", (0, 0, 1.02), (1.9, 0.72, 0.78), self.mat("DeerBrown", "#9B6B43", roughness=0.9), parent=deer)
            neck = self.empty(f"DeerNeck{index}", (0.92, 0, 1.18), parent=deer)
            self.box(f"DeerNeckMesh{index}", (0.18, 0, 0.28), (0.34, 0.3, 0.75), self.mat("DeerBrown", "#9B6B43", roughness=0.9), parent=neck)
            self.box(f"DeerHead{index}", (0.38, 0, 0.62), (0.62, 0.34, 0.34), self.mat("DeerBrown", "#9B6B43", roughness=0.9), parent=neck)
            self.oscillate_rotation(neck, 1, 0.22, 3.2, index * 1.3)
            for leg_index, (lx, ly) in enumerate(((-0.65, -0.24), (-0.65, 0.24), (0.65, -0.24), (0.65, 0.24))):
                self.cylinder(f"DeerLeg{index}_{leg_index}", (lx, ly, 0.42), (0.13, 0.13, 0.84), self.mat("DeerBrown", "#9B6B43", roughness=0.9), parent=deer)
            self.move(deer, self.at(0.1), self.at(0.9), (16 + index * 8, 8 + index * 3, 0.55), start_location=(8 + index * 9, 10 + index * 3, 0.55))
        for index in range(7):
            bird = self.cone(f"ValleyBird{index}", (-60 + index * 5, 32, 18 + index * 0.5), (1.0, 0.28, 0.24), self.M["dark"], (0, math.radians(-90), 0))
            start = tuple(bird.location)
            self.move(bird, 0, self.duration, (start[0] + 95, start[1] - 8, start[2] + 3), start_location=start, interpolation="LINEAR")
        for index in range(5):
            self.make_cloud(f"ValleyCloud{index}", (-62 + index * 27, 48, 27 + index % 2 * 3), 4.4, drift=7)
        self.make_person("ValleyWalker", (-34, -18, 0.4), math.radians(14), uniform=self.M["blue"], weapon="none", helmet=False, move_distance=42)
        self._generic_camera((0, 8, 4))

    def build_history_fort(self) -> None:
        self._generic_stage()
        self.grid_terrain(
            "FortGround",
            x_range=(-100, 100),
            y_range=(-55, 48),
            nx=44,
            ny=28,
            height_fn=lambda x, y: 0.18 * math.sin(x * 0.07) * math.cos(y * 0.08),
            color_fn=lambda x, y, z: (0.55, 0.46, 0.32, 1) if abs(x) < 5 and y < 18 else (0.42, 0.42, 0.26, 1),
            material=self.vertex_material("FortVertex", roughness=0.97),
        )
        fort = self.empty("HistoricFort", (0, 20, 0))
        self.box("FortWall", (0, 0, 4.8), (76, 4.2, 9.6), self.M["stone"], parent=fort)
        self.box("FortGate", (0, -2.2, 2.9), (8.5, 0.5, 5.8), self.M["wood"], parent=fort)
        self.box("FortGateArch", (0, -2.25, 6.3), (10.2, 0.45, 1.2), self.M["brick"], parent=fort)
        for index, x in enumerate(range(-36, 37, 4)):
            self.box(f"Crenellation{index}", (x, -0.4, 10.15), (2.0, 2.4, 1.1), self.M["brick"] if index % 2 else self.M["stone"], parent=fort)
        for index, x in enumerate((-38, 0, 38)):
            height = 15 if x == 0 else 13
            self.cylinder(f"FortTower{index}", (x, 0, height / 2), (8.5, 8.5, height), self.M["brick"], parent=fort)
            self.cone(f"FortTowerRoof{index}", (x, 0, height + 1.7), (9.6, 9.6, 3.4), self.M["red"], parent=fort)
            self.box(f"TowerWindow{index}", (x, -4.35, height - 2.2), (1.0, 0.18, 1.6), self.M["glass"], parent=fort)
        for index, x in enumerate((-24, -12, 12, 24)):
            banner = self.box(f"FortBanner{index}", (x, -2.38, 6.9), (2.2, 0.1, 4.2), self.M["red"] if index % 2 else self.M["gold"], parent=fort)
            self.oscillate_rotation(banner, 0, 0.05, 1.8, index)
        for index, x in enumerate((-7, 7)):
            torch = self.empty(f"GateTorch{index}", (x, 15.5, 0))
            self.cylinder(f"TorchPole{index}", (0, 0, 1.4), (0.16, 0.16, 2.8), self.M["wood"], parent=torch)
            flame = self.cone(f"TorchFlame{index}", (0, 0, 3.15), (0.55, 0.55, 1.05), self.M["fire"], parent=torch)
            self.oscillate_rotation(flame, 2, 0.08, 0.42, index)
            self.point_light(f"TorchLight{index}", (0, 0, 3.1), "#FF9A45", 260, torch)
        for index, (x, y) in enumerate(((-27, 2), (-19, -6), (24, 0), (31, -8))):
            tent = self.empty(f"CampTent{index}", (x, y, 0), (0, 0, self.rng.random()))
            self.cone(f"TentCone{index}", (0, 0, 1.7), (4.6, 4.6, 3.4), self.M["sand"], parent=tent)
            self.box(f"TentDoor{index}", (0, -1.75, 0.75), (1.0, 0.1, 1.5), self.M["dark"], parent=tent)
        cart = self.empty("SupplyCart", (-34, -20, 0), (0, 0, math.radians(22)))
        self.box("CartBed", (0, 0, 0.95), (4.8, 2.3, 0.65), self.M["wood"], parent=cart)
        for x in (-1.7, 1.7):
            for sign in (-1, 1):
                wheel = self.cylinder(f"CartWheel{x}{sign}", (x, 1.25 * sign, 0.55), (1.05, 0.16, 1.05), self.M["dark"], (math.radians(90), 0, 0), cart)
                self.spin(wheel, 1, 4.5, self.at(0.08), self.at(0.9))
        self.move(cart, self.at(0.08), self.at(0.9), (-4, -8, 0), start_location=(-34, -20, 0))
        for index in range(6):
            self.make_person(f"FortGuard{index}", (-18 + index * 7, 12.5 - (index % 2) * 2, 0.25), math.radians(-90), uniform=self.M["red"] if index % 2 else self.M["blue"], weapon="spear", phase=index, move_distance=2.2 if index % 2 else 0)
        self.make_person("FortMessenger", (-30, -25, 0.25), math.radians(55), uniform=self.M["gold"], weapon="none", helmet=False, move_distance=31)
        self.make_flag("FortMainFlag", (0, 20, 15.2), self.M["red"], height=4.6, size=1.25)
        for index in range(10):
            self.make_tree(f"FortTree{index}", (self.rng.uniform(-70, 70), self.rng.uniform(-35, 5), 0.25), scale=self.rng.uniform(0.8, 1.3))
        self._generic_camera((0, 14, 5))

    def build_abstract(self) -> None:
        self._generic_stage(dark=True)
        self.cylinder("MainPlatform", (0, 5, -0.35), (72, 72, 0.7), self.M["ground"])
        self.cylinder("InnerPlatform", (0, 5, 0.06), (46, 46, 0.22), self.M["dark"])
        palette_mats = [self.M["red"], self.M["gold"], self.M["cyan"], self.M["blue"], self.mat("VioletShape", "#7B61C9", roughness=0.5), self.mat("MintShape", "#4EC9A7", roughness=0.5)]
        heroes: list[Any] = []
        specs = [
            ("cube", (-24, 8, 3), (6, 6, 6), 0),
            ("sphere", (-8, 15, 4), (7, 7, 7), 1),
            ("cone", (8, 7, 4), (7, 7, 8), 2),
            ("cylinder", (24, 14, 4), (6, 6, 8), 3),
            ("torus", (0, -8, 5), (10, 10, 10), 4),
        ]
        for index, (kind, loc, scale, mat_index) in enumerate(specs):
            obj = self.add(kind, f"HeroShape{index}", loc, scale, (0, 0, index * 0.3), palette_mats[mat_index])
            heroes.append(obj)
            self.spin(obj, 2, 0.7 + index * 0.14)
            self.keys(obj, "location", [(0, loc), (self.at(0.45), (loc[0], loc[1], loc[2] + 2.4 + index * 0.35)), (self.duration, loc)])
        orbit = self.empty("OrbitGroup", (0, 7, 9))
        for index in range(10):
            angle = index * math.tau / 10
            kind = "sphere" if index % 3 else ("cube" if index % 3 == 1 else "cone")
            child = self.add(kind, f"OrbitShape{index}", (23 * math.cos(angle), 23 * math.sin(angle), math.sin(angle * 2) * 2), (1.7, 1.7, 1.7), (0, 0, angle), palette_mats[index % len(palette_mats)], orbit)
            self.spin(child, 1, 1.5)
        self.spin(orbit, 2, 1.0)
        for index in range(7):
            x = -42 + index * 14
            pillar = self.box(f"RisingPillar{index}", (x, 30, 0.6), (3.2, 3.2, 1.2), palette_mats[index % len(palette_mats)])
            height = 5 + ((index * 3) % 5) * 2.1
            self.keys(pillar, "scale", [(self.at(0.08), (3.2, 3.2, 1.2)), (self.at(0.62), (3.2, 3.2, height)), (self.duration, (3.2, 3.2, height * 0.82))])
            self.keys(pillar, "location", [(self.at(0.08), (x, 30, 0.6)), (self.at(0.62), (x, 30, height / 2)), (self.duration, (x, 30, height * 0.41))])
        for index in range(6):
            ring = self.torus(f"BackdropRing{index}", (-45 + index * 18, 45, 13 + index % 2 * 5), (7, 7, 7), palette_mats[index % len(palette_mats)])
            self.spin(ring, 0, 0.8)
        self.make_person("AbstractGuide", (-28, -20, 0.25), math.radians(20), uniform=self.M["white"], weapon="none", helmet=False, move_distance=38)
        self._generic_camera((0, 7, 5))

    # -------------------------------------------------------------- finalize
    def configure_render(self) -> dict[str, Any]:
        scene = self.scene
        profile = quality_profile(self.request.quality)
        scene.frame_start = 1
        scene.frame_end = self.total_frames
        scene.render.fps = self.fps
        scene.render.resolution_x = int(self.request.width)
        scene.render.resolution_y = int(self.request.height)
        scene.render.resolution_percentage = 100
        scene.render.engine = "CYCLES"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.compression = 15
        scene.render.film_transparent = False
        scene.render.threads_mode = "AUTO"
        scene.render.use_persistent_data = True
        _safe_set(scene.render, "use_simplify", True)
        _safe_set(scene.render, "simplify_subdivision_render", 0)
        _safe_set(scene.display_settings, "display_device", "sRGB")
        _safe_set(scene.view_settings, "view_transform", "Filmic")
        _safe_set(scene.view_settings, "look", "High Contrast" if self.theme in {"jungle_war", "last_survivor"} else "Medium Contrast")
        if self.theme in {"jungle_war", "last_survivor"}:
            # Filmic negative exposure plus the dark palette and Mist-pass
            # compositor supplies the requested moody grade.  The survivor
            # camera is much closer to its subject, so its mist begins sooner
            # and turns the route ahead into layered silhouettes.
            _safe_set(scene.view_settings, "exposure", -0.38 if self.theme == "last_survivor" else -0.24)
            _safe_set(scene.view_settings, "gamma", 0.97 if self.theme == "last_survivor" else 0.96)
            if scene.world:
                _safe_set(scene.world.mist_settings, "use_mist", True)
                _safe_set(scene.world.mist_settings, "start", 9.0 if self.theme == "last_survivor" else 32.0)
                _safe_set(scene.world.mist_settings, "depth", 48.0 if self.theme == "last_survivor" else 95.0)
                _safe_set(scene.world.mist_settings, "falloff", "QUADRATIC")
        else:
            _safe_set(scene.view_settings, "exposure", 0.08 if self.theme not in {"space_voyage", "tech_lab", "abstract_shapes"} else 0.22)
        cycles = scene.cycles
        _safe_set(cycles, "device", "CPU")
        _safe_set(cycles, "use_adaptive_sampling", True)
        _safe_set(cycles, "adaptive_threshold", float(profile["noise_threshold"]))
        _safe_set(cycles, "adaptive_min_samples", 1)
        _safe_set(cycles, "samples", int(profile["samples"]))
        _safe_set(cycles, "use_denoising", True)
        _safe_set(cycles, "denoiser", profile["denoiser"])
        _safe_set(cycles, "denoising_prefilter", profile["denoise_prefilter"])
        _safe_set(cycles, "denoising_quality", profile["denoise_quality"])
        _safe_set(cycles, "denoising_input_passes", profile.get("denoise_input_passes", "RGB_ALBEDO"))
        _safe_set(cycles, "denoising_use_gpu", False)
        _safe_set(cycles, "max_bounces", int(profile["max_bounces"]))
        _safe_set(cycles, "diffuse_bounces", int(profile["diffuse_bounces"]))
        _safe_set(cycles, "glossy_bounces", int(profile["glossy_bounces"]))
        _safe_set(cycles, "transmission_bounces", 0)
        _safe_set(cycles, "transparent_max_bounces", 1)
        _safe_set(cycles, "volume_bounces", 0)
        _safe_set(cycles, "caustics_reflective", False)
        _safe_set(cycles, "caustics_refractive", False)
        _safe_set(cycles, "blur_glossy", 1.0)
        _safe_set(cycles, "sample_clamp_indirect", 1.0)
        _safe_set(cycles, "light_sampling_threshold", float(profile.get("light_sampling_threshold", 0.05)))
        # Benchmarked on the procedural battlefield frames: FORWARD + Fast GI
        # was faster than MIS for this sun/area-light, low-bounce stylized set.
        _safe_set(cycles, "direct_light_sampling_type", "FORWARD_PATH_TRACING")
        _safe_set(cycles, "use_light_tree", True)
        _safe_set(cycles, "use_fast_gi", True)
        _safe_set(cycles, "fast_gi_method", "REPLACE")
        _safe_set(cycles, "ao_bounces_render", 1)
        _safe_set(cycles, "use_auto_tile", True)
        _safe_set(cycles, "tile_size", 1024)
        _safe_set(self.bpy.context.view_layer.cycles, "use_denoising", True)
        camera_data = getattr(scene.camera, "data", None)
        camera_dof = getattr(camera_data, "dof", None)
        return {
            "engine": "CYCLES",
            "device": "CPU",
            "camera_move": self.request.camera_move,
            "camera_depth_of_field": {
                "enabled": bool(getattr(camera_dof, "use_dof", False)),
                "fstop": float(getattr(camera_dof, "aperture_fstop", 0.0) or 0.0),
                "focus_distance": float(getattr(camera_dof, "focus_distance", 0.0) or 0.0),
            },
            "width": int(self.request.width),
            "height": int(self.request.height),
            "resolution_percentage": 100,
            "fps": self.fps,
            "frame_count": self.total_frames,
            "quality": self.request.quality,
            **profile,
        }

    def build(self) -> dict[str, Any]:
        builders: dict[str, Callable[[], None]] = {
            "ww2_battlefield": self.build_ww2,
            "finance_city": self.build_finance,
            "space_voyage": self.build_space,
            "ocean_voyage": self.build_ocean,
            "tech_lab": self.build_tech,
            "jungle_war": self.build_jungle_war,
            "last_survivor": self.build_last_survivor,
            "nature_valley": self.build_nature,
            "history_fort": self.build_history_fort,
            "abstract_shapes": self.build_abstract,
        }
        builders[self.theme]()
        render_info = self.configure_render()
        self.scene.frame_set(self.frame(self.at(0.58)))
        metadata = {
            "builder_version": BUILDER_VERSION,
            "theme": self.theme,
            "scene_label": self.request.scene_label,
            "object_count": len(self.scene.objects),
            "material_count": len(self.bpy.data.materials),
            "camera": self.scene.camera.name if self.scene.camera else None,
            "render": render_info,
        }
        self.scene["sidd_blender3d"] = json.dumps({"plan": self.plan, "metadata": metadata}, ensure_ascii=False)[:30000]
        text = self.bpy.data.texts.new("SIDD_BLENDER3D_PLAN.json")
        text.write(json.dumps({"plan": self.plan, "metadata": metadata}, ensure_ascii=False, indent=2))
        return metadata


def build_dynamic_scene(plan: dict[str, Any]) -> dict[str, Any]:
    """Build one dynamic Blender scene from a planner dictionary."""
    return SceneFactory(plan).build()
