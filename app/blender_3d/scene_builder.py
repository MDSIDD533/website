from __future__ import annotations

import json
import math
import random
from typing import Any, Callable, Iterable

from .planner import Blender3DRequest, THEMES, quality_profile

BUILDER_VERSION = "blender3d-scene-v1"


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

    def setup_world_and_lights(self, *, world_strength: float = 0.72, sun_energy: float = 3.0, sun_rotation=(math.radians(48), math.radians(12), math.radians(-32)), sun_color="#FFF1D6") -> None:
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
        fill_data.energy = 420
        fill_data.use_shadow = False
        fill_data.shape = "RECTANGLE"
        fill_data.size = 42
        fill_data.size_y = 22
        fill = bpy.data.objects.new("CameraFill", fill_data)
        self.collection.objects.link(fill)
        fill.location = (0, -52, 28)
        fill.rotation_euler = (math.radians(62), 0, 0)

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

    def setup_camera(self, positions: list[tuple[float, tuple[float, float, float]]], targets: list[tuple[float, tuple[float, float, float]]], lens_pairs: list[tuple[float, float]] | None = None) -> Any:
        bpy = self.bpy
        target = self.empty("CameraTarget", targets[0][1])
        camera_data = bpy.data.cameras.new("Blender3DCamera")
        camera_data.lens = 36
        camera_data.clip_end = 1000
        camera = bpy.data.objects.new("Blender3DCamera", camera_data)
        self.collection.objects.link(camera)
        camera.location = positions[0][1]
        constraint = camera.constraints.new(type="TRACK_TO")
        constraint.target = target
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"

        if self.request.camera_move == "orbit" and targets:
            center = targets[len(targets) // 2][1]
            orbit_positions = []
            for index, fraction in enumerate((0.0, 0.28, 0.56, 0.82, 1.0)):
                angle = math.radians(-135 + index * 42)
                orbit_positions.append((fraction, (center[0] + 48 * math.cos(angle), center[1] + 48 * math.sin(angle), center[2] + 12 + index % 2 * 4)))
            positions = orbit_positions
            targets = [(fraction, center) for fraction, _ in orbit_positions]
        elif self.request.camera_move == "tracking" and targets:
            center = targets[len(targets) // 2][1]
            targets = [(fraction, center) for fraction, _ in positions]

        self.keys(camera, "location", [(self.at(fraction), position) for fraction, position in positions], "BEZIER")
        self.keys(target, "location", [(self.at(fraction), position) for fraction, position in targets], "BEZIER")
        for fraction, lens in (lens_pairs or [(0.0, 35.0), (0.55, 46.0), (1.0, 40.0)]):
            frame = self.frame(self.at(fraction))
            self.scene.frame_set(frame)
            camera_data.lens = lens
            camera_data.keyframe_insert(data_path="lens", frame=frame)
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

    def make_tree(self, name: str, loc, *, scale: float = 1.0, palm: bool = False) -> Any:
        root = self.empty(name, loc, (0, 0, self.rng.random() * math.tau))
        root.scale = (scale, scale, scale)
        if palm:
            trunk = self.cylinder(f"{name}_Trunk", (0.25, 0, 1.55), (0.24, 0.24, 3.1), self.M["wood"], (0, math.radians(-9), 0), root)
            for index in range(5):
                angle = index * math.tau / 5
                leaf = self.box(f"{name}_Frond{index}", (0.55 + 0.75 * math.cos(angle), 0.75 * math.sin(angle), 3.18), (1.65, 0.22, 0.06), self.M["leaf"], (0, math.radians(-14), angle), root)
                self.oscillate_rotation(leaf, 2, 0.05, 2.2, angle)
            return root
        self.cylinder(f"{name}_Trunk", (0, 0, 0.9), (0.28, 0.28, 1.8), self.M["wood"], parent=root)
        self.sphere(f"{name}_CrownA", (0, 0, 2.35), (1.55, 1.55, 1.3), self.M["leaf"], parent=root)
        self.sphere(f"{name}_CrownB", (0.42, 0.25, 2.0), (1.05, 1.05, 0.95), self.M["leaf_light"], parent=root)
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
        self.setup_camera(
            [(0.0, (-48, -44, 18)), (0.3, (-28, -34, 12)), (0.58, (0, -27, 8)), (0.8, (25, -19, 9)), (1.0, (43, -11, 14))],
            [(0.0, (-12, target[1], target[2])), (0.35, target), (0.7, (target[0] + 10, target[1], target[2])), (1.0, target)],
            [(0.0, 34), (0.55, 44), (1.0, 39)],
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
        _safe_set(scene.view_settings, "look", "Medium Contrast")
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
        _safe_set(cycles, "denoising_input_passes", "RGB_ALBEDO")
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
        _safe_set(cycles, "light_sampling_threshold", 0.08 if self.request.quality == "draft" else 0.05 if self.request.quality == "standard" else 0.01)
        # Benchmarked on the native-1080p battlefield frame: FORWARD + Fast GI
        # was faster than MIS for this sun/area-light, low-bounce stylized set.
        _safe_set(cycles, "direct_light_sampling_type", "FORWARD_PATH_TRACING")
        _safe_set(cycles, "use_light_tree", True)
        _safe_set(cycles, "use_fast_gi", True)
        _safe_set(cycles, "fast_gi_method", "REPLACE")
        _safe_set(cycles, "ao_bounces_render", 1)
        _safe_set(cycles, "use_auto_tile", True)
        _safe_set(cycles, "tile_size", 1024)
        _safe_set(self.bpy.context.view_layer.cycles, "use_denoising", True)
        return {
            "engine": "CYCLES",
            "device": "CPU",
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
