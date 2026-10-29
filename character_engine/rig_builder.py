"""Blender (`bpy`) articulated 3D humanoid character & prop builder."""

from __future__ import annotations

from typing import Any

from character_engine.profiles import OUTFIT_PRESETS


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = (hex_color or "#888888").lstrip("#")
    if len(h) != 6:
        h = "888888"
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    # sRGB -> linear approx for Principled BSDF
    return (r**2.2, g**2.2, b**2.2, alpha)


def make_material(
    bpy: Any,
    name: str,
    rgba: tuple[float, float, float, float],
    *,
    roughness: float = 0.55,
    metallic: float = 0.05,
    emission_strength: float = 0.0,
) -> Any:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission_strength > 0 and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = rgba
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def _new_pivot(bpy: Any, col: Any, name: str, loc: tuple[float, float, float], parent: Any = None) -> Any:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.1
    obj.location = loc
    col.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def _add_part(
    bpy: Any,
    col: Any,
    kind: str,
    name: str,
    *,
    parent: Any,
    loc: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: Any,
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Any:
    if kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=18, ring_count=12, radius=1.0, location=(0, 0, 0))
    elif kind == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.0, depth=2.0, location=(0, 0, 0))
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.0, radius2=0.15, depth=2.0, location=(0, 0, 0))
    else:
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))

    obj = bpy.context.active_object
    obj.name = name
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)

    for poly in obj.data.polygons:
        poly.use_smooth = True

    obj.parent = parent
    obj.location = loc
    obj.rotation_euler = rot
    obj.scale = scale
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return obj


def build_character_rig_in_blender(
    bpy: Any,
    profile: dict[str, Any],
    *,
    props_override: list[str] | None = None,
) -> dict[str, Any]:
    """Build an articulated 3D character rig with consistent facial proportions, switchable outfits, and props."""
    col = bpy.context.scene.collection
    cname = profile.get("name", "Hero")
    seed = int(profile.get("identity_seed", 101))
    proportions = profile.get("body_proportions") or {}
    h_scale = float(proportions.get("height_scale", 1.0))
    w_scale = float(proportions.get("shoulder_width", 1.0))

    active_outfit_key = profile.get("active_outfit") or profile.get("outfit_preset") or "historical_armor"
    outfit = OUTFIT_PRESETS.get(active_outfit_key, OUTFIT_PRESETS["historical_armor"])
    palette = profile.get("color_palette") or [outfit["primary"], outfit["secondary"], outfit["trim"]]

    primary_hex = outfit["primary"] if active_outfit_key != profile.get("outfit_preset") else (palette[0] if palette else outfit["primary"])
    secondary_hex = palette[1] if len(palette) > 1 else outfit["secondary"]
    trim_hex = palette[2] if len(palette) > 2 else outfit["trim"]

    skin_mat = make_material(bpy, f"{cname}_Skin", hex_to_rgba(profile.get("skin_tone", "#c9936b")), roughness=0.62)
    hair_mat = make_material(bpy, f"{cname}_Hair", hex_to_rgba(profile.get("hair_color", "#231b16")), roughness=0.72)
    cloth_mat = make_material(bpy, f"{cname}_Primary", hex_to_rgba(primary_hex), roughness=0.68)
    accent_mat = make_material(
        bpy,
        f"{cname}_Accent",
        hex_to_rgba(secondary_hex),
        roughness=0.32 if outfit.get("shoulder_pauldrons") else 0.55,
        metallic=0.72 if outfit.get("shoulder_pauldrons") else 0.15,
    )
    trim_mat = make_material(bpy, f"{cname}_Trim", hex_to_rgba(trim_hex), roughness=0.75)
    eye_white_mat = make_material(bpy, f"{cname}_EyeWhite", (0.92, 0.92, 0.94, 1.0), roughness=0.18)
    pupil_mat = make_material(bpy, f"{cname}_Pupil", (0.03, 0.03, 0.04, 1.0), roughness=0.1)
    steel_mat = make_material(bpy, f"{cname}_Steel", (0.62, 0.65, 0.70, 1.0), roughness=0.22, metallic=0.92)
    lip_mat = make_material(bpy, f"{cname}_Mouth", (0.28, 0.08, 0.08, 1.0), roughness=0.5)

    root = _new_pivot(bpy, col, f"{cname}_Root", (0.0, 0.0, 0.0))
    root.scale = (h_scale, h_scale, h_scale)

    pelvis = _new_pivot(bpy, col, f"{cname}_Pelvis", (0.0, 0.0, 0.92), parent=root)
    _add_part(bpy, col, "cylinder", f"{cname}_PelvisMesh", parent=pelvis, loc=(0, 0, 0.0), scale=(0.17 * w_scale, 0.12, 0.10), mat=trim_mat)

    torso = _new_pivot(bpy, col, f"{cname}_Torso", (0.0, 0.0, 0.10), parent=pelvis)
    _add_part(bpy, col, "cylinder", f"{cname}_Chest", parent=torso, loc=(0, 0, 0.24), scale=(0.21 * w_scale, 0.13, 0.24), mat=cloth_mat)
    # Belt & sash
    _add_part(bpy, col, "cylinder", f"{cname}_Belt", parent=torso, loc=(0, 0, 0.03), scale=(0.185 * w_scale, 0.135, 0.04), mat=accent_mat)

    if outfit.get("shoulder_pauldrons"):
        _add_part(bpy, col, "sphere", f"{cname}_PauldronL", parent=torso, loc=(-0.25 * w_scale, 0, 0.44), scale=(0.09, 0.09, 0.06), mat=accent_mat)
        _add_part(bpy, col, "sphere", f"{cname}_PauldronR", parent=torso, loc=(0.25 * w_scale, 0, 0.44), scale=(0.09, 0.09, 0.06), mat=accent_mat)

    if outfit.get("cape"):
        _add_part(bpy, col, "cube", f"{cname}_Cape", parent=torso, loc=(0, 0.14, 0.05), scale=(0.22 * w_scale, 0.015, 0.42), mat=trim_mat, rot=(0.08, 0, 0))

    # Head + deterministic seed facial proportions + jaw lip-sync joint
    head_width = 0.125 + ((seed % 7) - 3) * 0.003
    head = _new_pivot(bpy, col, f"{cname}_Head", (0.0, 0.0, 0.54), parent=torso)
    _add_part(bpy, col, "cylinder", f"{cname}_Neck", parent=head, loc=(0, 0, -0.04), scale=(0.055, 0.055, 0.05), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_Cranium", parent=head, loc=(0, 0, 0.11), scale=(head_width, 0.135, 0.15), mat=skin_mat)
    _add_part(bpy, col, "cone", f"{cname}_Nose", parent=head, loc=(0, -0.138, 0.10), scale=(0.022, 0.028, 0.028), mat=skin_mat, rot=(1.35, 0, 0))

    # Hair style
    hair_style = profile.get("hair_style", "short_dark")
    _add_part(bpy, col, "sphere", f"{cname}_HairCap", parent=head, loc=(0, 0.018, 0.145), scale=(head_width * 1.07, 0.142, 0.13), mat=hair_mat)
    if "long" in hair_style or profile.get("role") == "deuteragonist":
        _add_part(bpy, col, "cylinder", f"{cname}_HairBack", parent=head, loc=(0, 0.09, 0.02), scale=(0.095, 0.05, 0.14), mat=hair_mat)

    # Eyes & brows
    _add_part(bpy, col, "sphere", f"{cname}_EyeL", parent=head, loc=(-0.046, -0.118, 0.128), scale=(0.022, 0.015, 0.018), mat=eye_white_mat)
    _add_part(bpy, col, "sphere", f"{cname}_EyeR", parent=head, loc=(0.046, -0.118, 0.128), scale=(0.022, 0.015, 0.018), mat=eye_white_mat)
    _add_part(bpy, col, "sphere", f"{cname}_PupilL", parent=head, loc=(-0.046, -0.131, 0.128), scale=(0.010, 0.008, 0.010), mat=pupil_mat)
    _add_part(bpy, col, "sphere", f"{cname}_PupilR", parent=head, loc=(0.046, -0.131, 0.128), scale=(0.010, 0.008, 0.010), mat=pupil_mat)

    brow_l = _new_pivot(bpy, col, f"{cname}_BrowL", (-0.048, -0.126, 0.158), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_BrowMeshL", parent=brow_l, loc=(0, 0, 0), scale=(0.026, 0.008, 0.006), mat=hair_mat)
    brow_r = _new_pivot(bpy, col, f"{cname}_BrowR", (0.048, -0.126, 0.158), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_BrowMeshR", parent=brow_r, loc=(0, 0, 0), scale=(0.026, 0.008, 0.006), mat=hair_mat)

    # Articulated Jaw/Mouth for local TTS viseme lip-sync
    jaw = _new_pivot(bpy, col, f"{cname}_Jaw", (0.0, -0.075, 0.055), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_MouthCavity", parent=head, loc=(0.0, -0.122, 0.052), scale=(0.036, 0.012, 0.014), mat=lip_mat)
    _add_part(bpy, col, "sphere", f"{cname}_Chin", parent=jaw, loc=(0.0, -0.042, -0.018), scale=(0.068, 0.055, 0.035), mat=skin_mat)

    # Arms
    upper_arm_l = _new_pivot(bpy, col, f"{cname}_UpperArmL", (-0.25 * w_scale, 0.0, 0.43), parent=torso)
    _add_part(bpy, col, "cylinder", f"{cname}_UpperArmMeshL", parent=upper_arm_l, loc=(0, 0, -0.13), scale=(0.055, 0.055, 0.13), mat=cloth_mat)
    forearm_l = _new_pivot(bpy, col, f"{cname}_ForearmL", (0.0, 0.0, -0.26), parent=upper_arm_l)
    _add_part(bpy, col, "cylinder", f"{cname}_ForearmMeshL", parent=forearm_l, loc=(0, 0, -0.12), scale=(0.046, 0.046, 0.12), mat=skin_mat)
    hand_l = _new_pivot(bpy, col, f"{cname}_HandL", (0.0, 0.0, -0.25), parent=forearm_l)
    _add_part(bpy, col, "sphere", f"{cname}_HandMeshL", parent=hand_l, loc=(0, 0, -0.02), scale=(0.042, 0.032, 0.048), mat=skin_mat)

    upper_arm_r = _new_pivot(bpy, col, f"{cname}_UpperArmR", (0.25 * w_scale, 0.0, 0.43), parent=torso)
    _add_part(bpy, col, "cylinder", f"{cname}_UpperArmMeshR", parent=upper_arm_r, loc=(0, 0, -0.13), scale=(0.055, 0.055, 0.13), mat=cloth_mat)
    forearm_r = _new_pivot(bpy, col, f"{cname}_ForearmR", (0.0, 0.0, -0.26), parent=upper_arm_r)
    _add_part(bpy, col, "cylinder", f"{cname}_ForearmMeshR", parent=forearm_r, loc=(0, 0, -0.12), scale=(0.046, 0.046, 0.12), mat=skin_mat)
    hand_r = _new_pivot(bpy, col, f"{cname}_HandR", (0.0, 0.0, -0.25), parent=forearm_r)
    _add_part(bpy, col, "sphere", f"{cname}_HandMeshR", parent=hand_r, loc=(0, 0, -0.02), scale=(0.042, 0.032, 0.048), mat=skin_mat)

    # Legs
    thigh_l = _new_pivot(bpy, col, f"{cname}_ThighL", (-0.10 * w_scale, 0.0, -0.04), parent=pelvis)
    _add_part(bpy, col, "cylinder", f"{cname}_ThighMeshL", parent=thigh_l, loc=(0, 0, -0.21), scale=(0.075, 0.075, 0.21), mat=trim_mat)
    shin_l = _new_pivot(bpy, col, f"{cname}_ShinL", (0.0, 0.0, -0.42), parent=thigh_l)
    _add_part(bpy, col, "cylinder", f"{cname}_ShinMeshL", parent=shin_l, loc=(0, 0, -0.20), scale=(0.058, 0.058, 0.20), mat=accent_mat)
    _add_part(bpy, col, "cube", f"{cname}_BootL", parent=shin_l, loc=(0, -0.045, -0.43), scale=(0.062, 0.11, 0.042), mat=trim_mat)

    thigh_r = _new_pivot(bpy, col, f"{cname}_ThighR", (0.10 * w_scale, 0.0, -0.04), parent=pelvis)
    _add_part(bpy, col, "cylinder", f"{cname}_ThighMeshR", parent=thigh_r, loc=(0, 0, -0.21), scale=(0.075, 0.075, 0.21), mat=trim_mat)
    shin_r = _new_pivot(bpy, col, f"{cname}_ShinR", (0.0, 0.0, -0.42), parent=thigh_r)
    _add_part(bpy, col, "cylinder", f"{cname}_ShinMeshR", parent=shin_r, loc=(0, 0, -0.20), scale=(0.058, 0.058, 0.20), mat=accent_mat)
    _add_part(bpy, col, "cube", f"{cname}_BootR", parent=shin_r, loc=(0, -0.045, -0.43), scale=(0.062, 0.11, 0.042), mat=trim_mat)

    # Optional handheld props
    props = props_override if props_override is not None else (profile.get("props") or [])
    if "sword" in props:
        _add_part(bpy, col, "cylinder", f"{cname}_SwordHilt", parent=hand_r, loc=(0, -0.06, -0.02), scale=(0.016, 0.016, 0.08), mat=accent_mat, rot=(1.57, 0, 0))
        _add_part(bpy, col, "cube", f"{cname}_SwordGuard", parent=hand_r, loc=(0, -0.14, -0.02), scale=(0.07, 0.012, 0.015), mat=accent_mat)
        _add_part(bpy, col, "cube", f"{cname}_SwordBlade", parent=hand_r, loc=(0, -0.52, -0.02), scale=(0.018, 0.36, 0.005), mat=steel_mat)
    elif "spear" in props or "staff" in props:
        _add_part(bpy, col, "cylinder", f"{cname}_Staff", parent=hand_r, loc=(0, -0.10, 0.15), scale=(0.018, 0.018, 0.85), mat=accent_mat)

    if "shield" in props:
        _add_part(bpy, col, "cylinder", f"{cname}_Shield", parent=forearm_l, loc=(-0.07, -0.05, -0.12), scale=(0.24, 0.24, 0.018), mat=accent_mat, rot=(0, 1.45, 0))
    elif "torch" in props:
        flame_mat = make_material(bpy, f"{cname}_TorchFlame", (1.0, 0.38, 0.04, 1.0), roughness=0.3, emission_strength=14.0)
        _add_part(bpy, col, "cylinder", f"{cname}_TorchStick", parent=hand_l, loc=(0, -0.08, 0.12), scale=(0.018, 0.018, 0.18), mat=trim_mat)
        _add_part(bpy, col, "cone", f"{cname}_TorchFire", parent=hand_l, loc=(0, -0.08, 0.34), scale=(0.048, 0.048, 0.08), mat=flame_mat)

    return {
        "root": root,
        "joints": {
            "pelvis": pelvis,
            "torso": torso,
            "head": head,
            "brow_l": brow_l,
            "brow_r": brow_r,
            "jaw": jaw,
            "upper_arm_l": upper_arm_l,
            "forearm_l": forearm_l,
            "hand_l": hand_l,
            "upper_arm_r": upper_arm_r,
            "forearm_r": forearm_r,
            "hand_r": hand_r,
            "thigh_l": thigh_l,
            "shin_l": shin_l,
            "thigh_r": thigh_r,
            "shin_r": shin_r,
        },
    }
