"""Reusable 3D environments, atmospheric weather, lighting, and animated background elements in Blender."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from character_engine.rig_builder import hex_to_rgba, make_material

ENVIRONMENT_CATALOG: list[dict[str, Any]] = [
    {
        "id": "fortress",
        "label": "Ancient Fortress & Ramparts",
        "category": "historical",
        "description": "Crenellated sandstone battlements, twin watchtowers, gate arch, flickering wall torches, and animated banners.",
        "ground_color": "#8b6f4e",
        "accent_color": "#b08d63",
    },
    {
        "id": "palace",
        "label": "Royal Palace Courtyard",
        "category": "historical",
        "description": "Polished courtyard tiles, colonnade arches, royal dais, and golden braziers.",
        "ground_color": "#b8ad9e",
        "accent_color": "#c9a24b",
    },
    {
        "id": "ancient_city",
        "label": "Ancient Domed City",
        "category": "historical",
        "description": "Historic skyline of domes, towers, market archways, and fluttering street banners.",
        "ground_color": "#9c8265",
        "accent_color": "#c79c63",
    },
    {
        "id": "village",
        "label": "Countryside Village",
        "category": "historical",
        "description": "Clay-and-timber cottages, central stone well, wooden fences, and warm lanterns.",
        "ground_color": "#6e6847",
        "accent_color": "#a88964",
    },
    {
        "id": "desert",
        "label": "Golden Desert Dunes",
        "category": "nature",
        "description": "Sculpted wind-swept sand dunes, weathered canyon pillars, and distant horizon haze.",
        "ground_color": "#c89d62",
        "accent_color": "#9c6f3e",
    },
    {
        "id": "forest",
        "label": "Ancient Woodland Clearing",
        "category": "nature",
        "description": "Tall timber trunks, layered foliage canopies, mossy rocks, and drifting forest motes.",
        "ground_color": "#384d30",
        "accent_color": "#2b5933",
    },
    {
        "id": "mountain",
        "label": "High Mountain Pass",
        "category": "nature",
        "description": "Craggy slate ridges, snow-dusted distant peaks, and narrow cliff trail.",
        "ground_color": "#585d63",
        "accent_color": "#8c96a3",
    },
    {
        "id": "battlefield",
        "label": "Siege Battlefield",
        "category": "action",
        "description": "Scorched earthworks, timber barricades, war standards, and drifting embers.",
        "ground_color": "#4f4338",
        "accent_color": "#7d2923",
    },
    {
        "id": "street",
        "label": "Historic Market Street",
        "category": "urban",
        "description": "Cobblestone lane flanked by multi-story facades, awnings, and hanging lamps.",
        "ground_color": "#5a5652",
        "accent_color": "#a66c46",
    },
    {
        "id": "room",
        "label": "Stone Council Chamber",
        "category": "interior",
        "description": "Vaulted interior hall with arched window shafts, council table, and wall sconces.",
        "ground_color": "#544c45",
        "accent_color": "#8f6f44",
    },
    {
        "id": "temple",
        "label": "Sanctuary Temple",
        "category": "historical",
        "description": "Stepped stone plinth, ceremonial pillars, and central sacred brazier.",
        "ground_color": "#8c8578",
        "accent_color": "#b89552",
    },
    {
        "id": "ship_camp",
        "label": "Harbor Ship & Expedition Camp",
        "category": "adventure",
        "description": "Timber deck & expedition tents beside reflective water and a crackling campfire.",
        "ground_color": "#5e4835",
        "accent_color": "#2b4f6e",
    },
]

WEATHER_OPTIONS = ["clear", "rain", "fog", "smoke", "fire", "dust"]
TIME_OPTIONS = ["sunrise", "day", "sunset", "night"]


def _add_mesh(
    bpy: Any,
    col: Any,
    kind: str,
    name: str,
    loc: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: Any,
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Any:
    if kind == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.0, depth=2.0, location=loc, rotation=rot)
    elif kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=1.0, location=loc, rotation=rot)
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.0, radius2=0.05, depth=2.0, location=loc, rotation=rot)
    elif kind == "plane":
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=loc, rotation=rot)

    obj = bpy.context.active_object
    obj.name = name
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    obj.scale = scale
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return obj


def setup_world_lighting_and_weather(
    bpy: Any,
    *,
    time_of_day: str,
    weather: str,
    frame_start: int,
    frame_end: int,
    rng: random.Random,
) -> None:
    scene = bpy.context.scene
    col = scene.collection

    sky_presets = {
        "sunrise": ((0.55, 0.28, 0.14, 1.0), 1.3, (1.0, 0.68, 0.42), 3.4, (1.15, 0.15, 0.65)),
        "day": ((0.24, 0.44, 0.78, 1.0), 1.5, (1.0, 0.96, 0.88), 4.2, (0.65, 0.10, 0.45)),
        # Dimmer, less saturated world wash at sunset: the old 1.2-strength
        # orange sky flattened every surface into one monochrome tint and
        # left the torches nothing to model. Let sun + torches do the work.
        "sunset": ((0.36, 0.15, 0.10, 1.0), 0.55, (1.0, 0.52, 0.24), 2.7, (1.28, 0.18, -0.55)),
        "night": ((0.02, 0.035, 0.08, 1.0), 0.40, (0.48, 0.62, 0.95), 1.15, (0.85, 0.12, -0.35)),
    }
    sky_rgba, world_strength, sun_rgb, sun_energy, sun_rot = sky_presets.get(time_of_day, sky_presets["sunset"])

    if weather in {"rain", "fog", "smoke"}:
        sky_rgba = (sky_rgba[0] * 0.55 + 0.12, sky_rgba[1] * 0.58 + 0.13, sky_rgba[2] * 0.62 + 0.15, 1.0)
        sun_energy *= 0.65

    world = bpy.data.worlds.new("StudioWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = sky_rgba
        bg.inputs["Strength"].default_value = world_strength

    # Key directional Sun/Moon light
    sun_data = bpy.data.lights.new(name="KeySun", type="SUN")
    sun_data.color = sun_rgb
    sun_data.energy = sun_energy
    # Wider sun disc = softer, more cinematic shadow edges than a pin light.
    sun_data.angle = 0.28
    sun_obj = bpy.data.objects.new(name="KeySun", object_data=sun_data)
    col.objects.link(sun_obj)
    sun_obj.rotation_euler = sun_rot

    # Cool, restrained fill from camera-left: faces stay readable, but the
    # warm key (sun + torches) keeps modelling them — teal/orange separation
    # instead of the old flat, evenly-lit wash.
    fill_data = bpy.data.lights.new(name="CinematicFill", type="AREA")
    fill_data.color = (0.58, 0.72, 1.0)
    fill_data.energy = 42.0 if time_of_day == "night" else 30.0
    fill_data.size = 4.0
    fill_obj = bpy.data.objects.new(name="CinematicFill", object_data=fill_data)
    col.objects.link(fill_obj)
    fill_obj.location = (-2.5, -4.8, 3.0)
    fill_obj.rotation_euler = (1.15, 0.0, -0.45)

    # Warm rim/back light behind the actors so hair, shoulders, and capes
    # separate from the equally warm fortress wall behind them.
    rim_data = bpy.data.lights.new(name="CinematicRim", type="POINT")
    rim_data.color = (1.0, 0.58, 0.30)
    rim_data.energy = 180.0 if time_of_day == "night" else 120.0
    rim_data.shadow_soft_size = 0.35
    rim_obj = bpy.data.objects.new(name="CinematicRim", object_data=rim_data)
    col.objects.link(rim_obj)
    rim_obj.location = (0.0, 3.4, 2.8)

    # Animated atmospheric particles (rain drops, embers, dust motes, or fog planes)
    if weather in {"rain", "dust", "fire", "smoke"}:
        if weather == "rain":
            p_mat = make_material(bpy, "RainMat", (0.65, 0.78, 0.95, 1.0), roughness=0.1, emission_strength=1.2)
            p_scale = (0.008, 0.008, 0.16)
            dz = -2.6
        elif weather == "fire":
            p_mat = make_material(bpy, "EmberMat", (1.0, 0.35, 0.04, 1.0), roughness=0.3, emission_strength=12.0)
            p_scale = (0.025, 0.025, 0.025)
            dz = 1.6
        else:
            p_mat = make_material(bpy, "DustMat", (0.78, 0.66, 0.48, 1.0), roughness=0.85)
            p_scale = (0.032, 0.032, 0.032)
            dz = 0.35

        for idx in range(18):
            px = rng.uniform(-4.5, 4.5)
            py = rng.uniform(-2.8, 4.5)
            pz = rng.uniform(0.4, 3.6)
            mote = _add_mesh(bpy, col, "cube" if weather == "rain" else "sphere", f"WeatherMote_{idx}", (px, py, pz), p_scale, p_mat)
            mote.location = (px, py, pz)
            mote.keyframe_insert(data_path="location", frame=frame_start)
            mote.location = (px + rng.uniform(-0.8, 0.8), py + rng.uniform(-0.4, 0.4), max(0.1, pz + dz))
            mote.keyframe_insert(data_path="location", frame=frame_end)

    if weather in {"fog", "smoke"}:
        fog_mat = make_material(bpy, "FogLayerMat", (0.62, 0.65, 0.70, 1.0), roughness=0.95)
        for idx in range(3):
            fy = 3.5 + idx * 2.5
            fog_bar = _add_mesh(bpy, col, "sphere", f"FogCloud_{idx}", (-1.5 + idx * 1.5, fy, 0.45), (3.2, 1.2, 0.38), fog_mat)
            fog_bar.keyframe_insert(data_path="location", frame=frame_start)
            fog_bar.location = (-0.8 + idx * 1.5, fy, 0.52)
            fog_bar.keyframe_insert(data_path="location", frame=frame_end)


def build_environment_in_blender(
    bpy: Any,
    *,
    environment_preset: str,
    location_key: str,
    time_of_day: str,
    weather: str,
    frame_start: int,
    frame_end: int,
) -> None:
    """Build deterministic, recurring-consistent 3D architecture/terrain & moving props."""
    col = bpy.context.scene.collection
    seed_int = int(hashlib.sha256(f"{environment_preset}:{location_key}".encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_int)

    env_meta = next((e for e in ENVIRONMENT_CATALOG if e["id"] == environment_preset), ENVIRONMENT_CATALOG[0])
    wet_roughness = 0.22 if weather == "rain" else 0.86

    ground_mat = make_material(
        bpy,
        "EnvGround",
        hex_to_rgba(env_meta["ground_color"]),
        roughness=wet_roughness,
        # Broad tonal mottling (micro-grain averages away at this distance).
        noise_scale=35.0,
        bump_strength=0.05,
        roughness_variation=0.14,
    )
    stone_mat = make_material(
        bpy,
        "EnvStone",
        hex_to_rgba(env_meta["accent_color"]),
        roughness=0.82,
        noise_scale=14.0,
        bump_strength=0.07,
        roughness_variation=0.16,
    )
    dark_stone_mat = make_material(
        bpy,
        "EnvStoneDark",
        hex_to_rgba("#5d4a34"),
        roughness=0.88,
        noise_scale=16.0,
        bump_strength=0.06,
        roughness_variation=0.14,
    )
    dark_wood_mat = make_material(
        bpy,
        "EnvWood",
        hex_to_rgba("#4a3321"),
        roughness=0.82,
        noise_scale=10.0,
        bump_strength=0.05,
        roughness_variation=0.10,
    )
    foliage_mat = make_material(
        bpy,
        "EnvFoliage",
        hex_to_rgba("#294d29"),
        roughness=0.80,
        noise_scale=7.0,
        bump_strength=0.06,
        roughness_variation=0.12,
    )
    banner_mat = make_material(
        bpy,
        "EnvBanner",
        hex_to_rgba("#8a1c24"),
        roughness=0.70,
        sheen_weight=0.45,
        noise_scale=14.0,
        bump_strength=0.025,
        roughness_variation=0.08,
    )
    metal_mat = make_material(bpy, "EnvMetal", hex_to_rgba("#6d5636"), roughness=0.30, metallic=1.0)
    flame_mat = make_material(bpy, "EnvFlame", (1.0, 0.42, 0.06, 1.0), roughness=0.2, emission_strength=16.0)

    # Expansive ground plane + scattered foreground pebbles for scale/texture.
    _add_mesh(bpy, col, "plane", "GroundPlane", (0, 0, 0), (45.0, 45.0, 1.0), ground_mat)
    for pebble_idx in range(36):
        pebble_x = rng.uniform(-6.0, 6.0)
        pebble_y = rng.uniform(-2.5, 5.5)
        if abs(pebble_x) < 1.6 and -1.2 < pebble_y < 1.4:
            continue  # keep the actors' footing clear
        pebble_r = rng.uniform(0.035, 0.11)
        _add_mesh(
            bpy,
            col,
            "sphere",
            f"Pebble_{pebble_idx}",
            (pebble_x, pebble_y, pebble_r * 0.28),
            (pebble_r, pebble_r * rng.uniform(0.7, 1.0), pebble_r * 0.42),
            dark_stone_mat if pebble_idx % 3 else stone_mat,
            rot=(0.0, 0.0, rng.uniform(0.0, 3.14)),
        )

    def _add_torch(name: str, x: float, y: float, z: float) -> None:
        _add_mesh(bpy, col, "cylinder", f"{name}_Post", (x, y, z * 0.5), (0.06, 0.06, z * 0.5), dark_wood_mat)
        flame = _add_mesh(bpy, col, "cone", f"{name}_Flame", (x, y, z + 0.14), (0.11, 0.11, 0.18), flame_mat)
        _add_mesh(bpy, col, "cylinder", f"{name}_Bracket", (x, y, z + 0.03), (0.085, 0.085, 0.030), metal_mat)
        pt = bpy.data.lights.new(name=f"{name}_Light", type="POINT")
        pt.color = (1.0, 0.52, 0.16)
        base_energy = 240.0 if time_of_day == "night" else 110.0
        pt.energy = base_energy
        pt.shadow_soft_size = 0.28
        pt_obj = bpy.data.objects.new(name=f"{name}_Light", object_data=pt)
        col.objects.link(pt_obj)
        pt_obj.location = (x, y, z + 0.25)
        # Animated torch flicker in both flame shape and emitted light energy.
        for f in range(frame_start, frame_end + 1, max(1, (frame_end - frame_start) // 6 or 1)):
            s = 1.0 + 0.16 * math.sin(f * 0.9 + x)
            flame.scale = (0.11 * s, 0.11 * s, 0.18 * (2.0 - s))
            flame.keyframe_insert(data_path="scale", frame=f)
            pt.energy = base_energy * (0.88 + 0.20 * (0.5 + 0.5 * math.sin(f * 1.7 + x * 2.1)))
            pt.keyframe_insert(data_path="energy", frame=f)

    def _add_waving_banner(name: str, x: float, y: float, z: float) -> None:
        _add_mesh(bpy, col, "cylinder", f"{name}_Pole", (x, y, z * 0.5), (0.04, 0.04, z * 0.5), dark_wood_mat)
        cloth = _add_mesh(bpy, col, "cube", f"{name}_Cloth", (x + 0.35, y, z - 0.55), (0.35, 0.02, 0.48), banner_mat)
        cloth.rotation_euler = (0.0, 0.0, -0.10)
        cloth.keyframe_insert(data_path="rotation_euler", frame=frame_start)
        cloth.rotation_euler = (0.12, 0.08, 0.16)
        cloth.keyframe_insert(data_path="rotation_euler", frame=max(frame_start + 1, (frame_start + frame_end) // 2))
        cloth.rotation_euler = (-0.06, -0.05, -0.08)
        cloth.keyframe_insert(data_path="rotation_euler", frame=frame_end)

    if environment_preset in {"fortress", "ancient_city", "palace", "temple"}:
        # Rear monumental wall / colonnade + towers
        _add_mesh(bpy, col, "cube", "RearWall", (0.0, 6.2, 2.1), (9.0, 0.55, 2.1), stone_mat)
        for crenel_x in range(-8, 9, 2):
            _add_mesh(bpy, col, "cube", f"Crenel_{crenel_x}", (float(crenel_x), 5.9, 4.45), (0.48, 0.58, 0.32), stone_mat)
        _add_mesh(bpy, col, "cylinder", "WatchTowerL", (-6.2, 5.8, 3.4), (1.35, 1.35, 3.4), stone_mat)
        _add_mesh(bpy, col, "cylinder", "WatchTowerR", (6.2, 5.8, 3.4), (1.35, 1.35, 3.4), stone_mat)
        # NOTE: applied-on panels/courses were tried and read as scaffolding
        # in renders. The wall's surface interest comes from the procedural
        # stone material, buttresses, towers, and windows instead.
        if environment_preset in {"ancient_city", "palace", "temple"}:
            _add_mesh(bpy, col, "sphere", "DomeCenter", (0.0, 7.5, 4.4), (2.2, 2.2, 1.8), stone_mat)
            for px in (-3.2, -1.4, 1.4, 3.2):
                _add_mesh(bpy, col, "cylinder", f"Colonnade_{px}", (px, 3.8, 1.8), (0.24, 0.24, 1.8), stone_mat)
        _add_torch("WallTorchL", -2.4, 3.2, 1.65)
        _add_torch("WallTorchR", 2.4, 3.2, 1.65)
        _add_waving_banner("BannerL", -3.8, 4.4, 3.4)
        _add_waving_banner("BannerR", 3.8, 4.4, 3.4)

    elif environment_preset in {"forest", "village"}:
        for idx in range(10):
            tx = rng.uniform(-7.0, 7.0)
            ty = rng.uniform(2.5, 10.0)
            h = rng.uniform(1.8, 3.0)
            _add_mesh(bpy, col, "cylinder", f"Trunk_{idx}", (tx, ty, h * 0.5), (0.18, 0.18, h * 0.5), dark_wood_mat)
            _add_mesh(bpy, col, "cone", f"Canopy_{idx}", (tx, ty, h + 0.9), (0.95, 0.95, 1.35), foliage_mat)
        if environment_preset == "village":
            _add_mesh(bpy, col, "cube", "CottageL", (-4.2, 5.2, 1.2), (1.6, 1.4, 1.2), stone_mat)
            _add_mesh(bpy, col, "cone", "RoofL", (-4.2, 5.2, 2.9), (2.1, 2.0, 0.8), dark_wood_mat)
            _add_torch("VillageLantern", 2.0, 2.6, 1.5)

    elif environment_preset in {"desert", "mountain"}:
        for idx in range(7):
            mx = -8.0 + idx * 2.7 + rng.uniform(-0.5, 0.5)
            my = rng.uniform(5.5, 12.5)
            mh = rng.uniform(2.2, 5.2) if environment_preset == "mountain" else rng.uniform(0.9, 2.0)
            kind = "cone" if environment_preset == "mountain" else "sphere"
            _add_mesh(bpy, col, kind, f"Ridge_{idx}", (mx, my, mh * 0.45), (2.4, 1.9, mh * 0.65), stone_mat)
        _add_waving_banner("OutpostMarker", 3.1, 3.5, 2.6)

    elif environment_preset == "battlefield":
        for bx in (-3.6, 0.0, 3.6):
            _add_mesh(bpy, col, "cube", f"Barricade_{bx}", (bx, 4.2, 0.55), (1.1, 0.25, 0.45), dark_wood_mat, rot=(0.35, 0.0, 0.1))
        _add_torch("BrazierL", -2.8, 2.8, 1.2)
        _add_torch("BrazierR", 2.8, 2.8, 1.2)
        _add_waving_banner("WarStandard", -0.5, 5.0, 3.2)

    elif environment_preset == "room":
        _add_mesh(bpy, col, "cube", "BackChamberWall", (0.0, 4.8, 2.2), (6.5, 0.3, 2.2), stone_mat)
        _add_mesh(bpy, col, "cube", "LeftChamberWall", (-5.5, 1.0, 2.2), (0.3, 5.0, 2.2), stone_mat)
        _add_mesh(bpy, col, "cube", "CouncilTable", (0.0, 1.9, 0.45), (1.3, 0.6, 0.42), dark_wood_mat)
        _add_torch("SconceL", -2.4, 4.3, 1.8)
        _add_torch("SconceR", 2.4, 4.3, 1.8)

    else:
        # street or ship_camp
        _add_mesh(bpy, col, "cube", "StructureL", (-4.4, 4.6, 1.8), (1.5, 2.6, 1.8), stone_mat)
        _add_mesh(bpy, col, "cone", "CampTentR", (3.8, 4.8, 1.3), (1.7, 1.7, 1.3), banner_mat)
        _add_torch("CampFire", 1.8, 2.5, 0.4)
        _add_waving_banner("CampFlag", -2.2, 4.0, 2.8)

    setup_world_lighting_and_weather(
        bpy,
        time_of_day=time_of_day,
        weather=weather,
        frame_start=frame_start,
        frame_end=frame_end,
        rng=rng,
    )
