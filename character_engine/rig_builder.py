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


def _set_bsdf_input(bsdf: Any, name: str, value: Any) -> None:
    """Set a Principled BSDF input only when this Blender build exposes it."""
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value


def _add_procedural_surface_detail(
    mat: Any,
    bsdf: Any,
    *,
    roughness: float,
    noise_scale: float,
    bump_strength: float,
    roughness_variation: float,
) -> None:
    """Add texture-free micro detail (pores, weave, stone grain) via procedural noise.

    Generated coordinates are used deliberately: every procedural primitive in this
    project has generated bounds, while not every primitive has useful UV density.
    The base colour is untouched, preserving locked character/environment palettes.
    """
    if noise_scale <= 0 or (bump_strength <= 0 and roughness_variation <= 0):
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = float(noise_scale)
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.72

    # Tonal mottling: base hue is preserved, value varies ±~8% so large
    # surfaces (stone, ground, cloth) do not read as flat colour fills.
    tone = nodes.new("ShaderNodeMapRange")
    tone.inputs["From Min"].default_value = 0.15
    tone.inputs["From Max"].default_value = 0.85
    tone.inputs["To Min"].default_value = 0.84
    tone.inputs["To Max"].default_value = 1.0
    links.new(noise.outputs["Fac"], tone.inputs["Value"])
    tone_mix = nodes.new("ShaderNodeMixRGB")
    tone_mix.blend_type = "MULTIPLY"
    tone_mix.inputs["Fac"].default_value = 1.0
    tone_mix.inputs["Color1"].default_value = tuple(bsdf.inputs["Base Color"].default_value)
    links.new(tone.outputs["Result"], tone_mix.inputs["Color2"])
    links.new(tone_mix.outputs["Color"], bsdf.inputs["Base Color"])

    if bump_strength > 0:
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = float(bump_strength)
        bump.inputs["Distance"].default_value = 0.035
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    if roughness_variation > 0:
        variation = max(0.0, min(0.3, float(roughness_variation)))
        remap = nodes.new("ShaderNodeMapRange")
        remap.inputs["From Min"].default_value = 0.18
        remap.inputs["From Max"].default_value = 0.82
        remap.inputs["To Min"].default_value = max(0.03, roughness - variation)
        remap.inputs["To Max"].default_value = min(1.0, roughness + variation)
        links.new(noise.outputs["Fac"], remap.inputs["Value"])
        links.new(remap.outputs["Result"], bsdf.inputs["Roughness"])


def make_material(
    bpy: Any,
    name: str,
    rgba: tuple[float, float, float, float],
    *,
    roughness: float = 0.55,
    metallic: float = 0.05,
    emission_strength: float = 0.0,
    subsurface_weight: float = 0.0,
    subsurface_radius: tuple[float, float, float] = (1.0, 0.35, 0.18),
    subsurface_scale: float = 0.035,
    sheen_weight: float = 0.0,
    coat_weight: float = 0.0,
    specular_ior_level: float = 0.5,
    anisotropic: float = 0.0,
    noise_scale: float = 0.0,
    bump_strength: float = 0.0,
    roughness_variation: float = 0.0,
) -> Any:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic

        _set_bsdf_input(bsdf, "Subsurface Weight", float(subsurface_weight))
        _set_bsdf_input(bsdf, "Subsurface Radius", subsurface_radius)
        _set_bsdf_input(bsdf, "Subsurface Scale", float(subsurface_scale))
        _set_bsdf_input(bsdf, "Sheen Weight", float(sheen_weight))
        _set_bsdf_input(bsdf, "Sheen Roughness", 0.55)
        _set_bsdf_input(bsdf, "Sheen Tint", rgba)
        _set_bsdf_input(bsdf, "Coat Weight", float(coat_weight))
        _set_bsdf_input(bsdf, "Coat Roughness", 0.18)
        _set_bsdf_input(bsdf, "Specular IOR Level", float(specular_ior_level))
        _set_bsdf_input(bsdf, "Anisotropic", float(anisotropic))

        if emission_strength > 0 and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = rgba
            bsdf.inputs["Emission Strength"].default_value = emission_strength

        _add_procedural_surface_detail(
            mat,
            bsdf,
            roughness=roughness,
            noise_scale=noise_scale,
            bump_strength=bump_strength,
            roughness_variation=roughness_variation,
        )
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


def _add_curve_strand(
    bpy: Any,
    col: Any,
    name: str,
    *,
    parent: Any,
    points: list[tuple[float, float, float]],
    mat: Any,
    bevel_depth: float = 0.0032,
) -> Any:
    """Create one groomed Bezier strand (hair/beard) in the parent's local space."""
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 4
    curve.bevel_depth = float(bevel_depth)
    curve.bevel_resolution = 2
    curve.materials.append(mat)

    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(max(0, len(points) - 1))
    for point, coordinates in zip(spline.bezier_points, points):
        point.co = coordinates
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"

    obj = bpy.data.objects.new(name, curve)
    col.objects.link(obj)
    obj.parent = parent
    obj.location = (0.0, 0.0, 0.0)
    return obj


def _build_hand_with_fingers(
    bpy: Any,
    col: Any,
    cname: str,
    side: str,
    *,
    hand: Any,
    skin_mat: Any,
    grip: bool,
) -> None:
    """Replace the old single-ellipsoid mitten with a palm and five jointed fingers.

    The rig's hand pivot points down local -Z; the character faces local -Y.
    A relaxed hand keeps a slight natural curl toward the palm (+Y in hand
    space). A gripping hand uses the same anatomical curl, only much tighter.
    """
    suffix = side.upper()
    side_sign = -1.0 if side.lower().startswith("l") else 1.0
    _add_part(
        bpy,
        col,
        "sphere",
        f"{cname}_Palm{suffix}",
        parent=hand,
        loc=(0.0, 0.0, -0.036),
        scale=(0.040, 0.022, 0.046),
        mat=skin_mat,
    )

    first_curl = 0.62 if grip else 0.20
    second_curl = 0.72 if grip else 0.28
    # Four fingers across the palm; lengths follow a natural index-to-pinky falloff.
    for finger_idx, (x_offset, length) in enumerate(
        ((-0.027, 0.050), (-0.009, 0.056), (0.009, 0.052), (0.027, 0.041))
    ):
        finger = _new_pivot(
            bpy,
            col,
            f"{cname}_Finger{suffix}_{finger_idx}",
            (x_offset, -0.006, -0.076),
            parent=hand,
        )
        finger.rotation_euler = (first_curl, 0.0, 0.0)
        _add_part(
            bpy,
            col,
            "cylinder",
            f"{cname}_Finger{suffix}_{finger_idx}_Proximal",
            parent=finger,
            loc=(0.0, 0.0, -length * 0.28),
            scale=(0.0075, 0.0075, length * 0.28),
            mat=skin_mat,
        )
        tip = _new_pivot(
            bpy,
            col,
            f"{cname}_Finger{suffix}_{finger_idx}_Joint",
            (0.0, 0.0, -length * 0.56),
            parent=finger,
        )
        tip.rotation_euler = (second_curl, 0.0, 0.0)
        _add_part(
            bpy,
            col,
            "cylinder",
            f"{cname}_Finger{suffix}_{finger_idx}_Distal",
            parent=tip,
            loc=(0.0, 0.0, -length * 0.21),
            scale=(0.0068, 0.0068, length * 0.21),
            mat=skin_mat,
        )

    # Opposing thumb on the inboard side of the palm.
    thumb = _new_pivot(
        bpy,
        col,
        f"{cname}_Thumb{suffix}",
        (-side_sign * 0.036, -0.012, -0.052),
        parent=hand,
    )
    thumb.rotation_euler = (0.42 if grip else 0.20, side_sign * 0.18, side_sign * 0.38)
    _add_part(
        bpy,
        col,
        "cylinder",
        f"{cname}_ThumbMesh{suffix}",
        parent=thumb,
        loc=(0.0, 0.0, -0.024),
        scale=(0.0085, 0.0085, 0.024),
        mat=skin_mat,
    )


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

    skin_mat = make_material(
        bpy,
        f"{cname}_Skin",
        hex_to_rgba(profile.get("skin_tone", "#c9936b")),
        roughness=0.56,
        subsurface_weight=0.34,
        subsurface_radius=(1.0, 0.36, 0.20),
        subsurface_scale=0.035,
        specular_ior_level=0.34,
        noise_scale=28.0,
        bump_strength=0.018,
        roughness_variation=0.06,
    )
    hair_mat = make_material(
        bpy,
        f"{cname}_Hair",
        hex_to_rgba(profile.get("hair_color", "#231b16")),
        roughness=0.48,
        anisotropic=0.55,
        specular_ior_level=0.42,
        noise_scale=55.0,
        bump_strength=0.010,
        roughness_variation=0.10,
    )
    cloth_mat = make_material(
        bpy,
        f"{cname}_Primary",
        hex_to_rgba(primary_hex),
        roughness=0.72,
        sheen_weight=0.42,
        noise_scale=16.0,
        bump_strength=0.028,
        roughness_variation=0.08,
    )
    accent_mat = make_material(
        bpy,
        f"{cname}_Accent",
        hex_to_rgba(secondary_hex),
        roughness=0.30 if outfit.get("shoulder_pauldrons") else 0.58,
        metallic=1.0 if outfit.get("shoulder_pauldrons") else 0.08,
        sheen_weight=0.0 if outfit.get("shoulder_pauldrons") else 0.30,
        noise_scale=12.0,
        bump_strength=0.012,
        roughness_variation=0.07,
    )
    trim_mat = make_material(
        bpy,
        f"{cname}_Trim",
        hex_to_rgba(trim_hex),
        roughness=0.78,
        sheen_weight=0.28,
        noise_scale=18.0,
        bump_strength=0.024,
        roughness_variation=0.08,
    )
    eye_white_mat = make_material(
        bpy,
        f"{cname}_EyeWhite",
        (0.92, 0.92, 0.94, 1.0),
        roughness=0.08,
        coat_weight=0.70,
        specular_ior_level=0.62,
    )
    iris_mat = make_material(
        bpy,
        f"{cname}_Iris",
        hex_to_rgba(str(profile.get("eye_color") or "#3a2415")),
        roughness=0.12,
        coat_weight=0.65,
        specular_ior_level=0.60,
    )
    pupil_mat = make_material(bpy, f"{cname}_Pupil", (0.012, 0.012, 0.014, 1.0), roughness=0.08)
    catchlight_mat = make_material(
        bpy,
        f"{cname}_Catchlight",
        (1.0, 0.98, 0.94, 1.0),
        roughness=0.05,
        emission_strength=3.0,
    )
    steel_mat = make_material(
        bpy,
        f"{cname}_Steel",
        (0.62, 0.65, 0.70, 1.0),
        roughness=0.30,
        metallic=1.0,
        noise_scale=22.0,
        bump_strength=0.006,
        roughness_variation=0.08,
    )
    lip_mat = make_material(
        bpy,
        f"{cname}_Mouth",
        hex_to_rgba("#96524b"),
        roughness=0.38,
        subsurface_weight=0.22,
        coat_weight=0.25,
    )

    root = _new_pivot(bpy, col, f"{cname}_Root", (0.0, 0.0, 0.0))
    root.scale = (h_scale, h_scale, h_scale)

    pelvis = _new_pivot(bpy, col, f"{cname}_Pelvis", (0.0, 0.0, 0.92), parent=root)
    _add_part(bpy, col, "cylinder", f"{cname}_PelvisMesh", parent=pelvis, loc=(0, 0, 0.0), scale=(0.155 * w_scale, 0.11, 0.10), mat=trim_mat)
    # Flared tunic skirt emerging from under the belt; it breaks up the old
    # straight cylinder silhouette without changing the leg rig underneath.
    _add_part(bpy, col, "cylinder", f"{cname}_TunicSkirt", parent=pelvis, loc=(0, 0, -0.105), scale=(0.172 * w_scale, 0.122, 0.105), mat=cloth_mat)
    for fold_idx, fold_x in enumerate((-0.125, -0.062, 0.0, 0.062, 0.125)):
        _add_part(
            bpy,
            col,
            "cube",
            f"{cname}_TunicFold_{fold_idx}",
            parent=pelvis,
            loc=(fold_x * w_scale, -0.116, -0.115),
            scale=(0.010, 0.008, 0.085),
            mat=trim_mat,
            rot=(0.03 * fold_idx, 0.0, 0.05 * (fold_idx - 2)),
        )

    torso = _new_pivot(bpy, col, f"{cname}_Torso", (0.0, 0.0, 0.10), parent=pelvis)
    # Tapered trunk: narrower waist + fuller upper chest instead of one barrel.
    _add_part(bpy, col, "cylinder", f"{cname}_Waist", parent=torso, loc=(0, 0, 0.13), scale=(0.152 * w_scale, 0.104, 0.14), mat=cloth_mat)
    _add_part(bpy, col, "sphere", f"{cname}_Chest", parent=torso, loc=(0, 0, 0.36), scale=(0.185 * w_scale, 0.118, 0.145), mat=cloth_mat)
    _add_part(bpy, col, "cylinder", f"{cname}_Collar", parent=torso, loc=(0, 0, 0.505), scale=(0.108 * w_scale, 0.084, 0.020), mat=trim_mat)
    # Belt, buckle, and a diagonal period sash/strap across the chest front.
    _add_part(bpy, col, "cylinder", f"{cname}_Belt", parent=torso, loc=(0, 0, 0.03), scale=(0.168 * w_scale, 0.122, 0.04), mat=trim_mat)
    _add_part(bpy, col, "cube", f"{cname}_BeltBuckle", parent=torso, loc=(0, -0.126, 0.03), scale=(0.035, 0.010, 0.026), mat=accent_mat)
    _add_part(
        bpy,
        col,
        "cube",
        f"{cname}_ChestStrap",
        parent=torso,
        loc=(0.005 * w_scale, -0.119, 0.27),
        scale=(0.033, 0.011, 0.215),
        mat=trim_mat,
        rot=(0.0, 0.52, 0.0),
    )

    if outfit.get("shoulder_pauldrons"):
        for side_sign, side_name in ((-1.0, "L"), (1.0, "R")):
            _add_part(
                bpy,
                col,
                "sphere",
                f"{cname}_Pauldron{side_name}",
                parent=torso,
                loc=(side_sign * 0.205 * w_scale, 0, 0.44),
                scale=(0.082, 0.082, 0.056),
                mat=accent_mat,
            )
            _add_part(
                bpy,
                col,
                "cylinder",
                f"{cname}_PauldronRim{side_name}",
                parent=torso,
                loc=(side_sign * 0.218 * w_scale, 0, 0.385),
                scale=(0.074, 0.074, 0.018),
                mat=trim_mat,
            )

    cape_pivot = None
    if outfit.get("cape"):
        cape_pivot = _new_pivot(bpy, col, f"{cname}_CapePivot", (0.0, 0.125, 0.46), parent=torso)
        for panel_idx, panel_x in enumerate((-0.128, -0.064, 0.0, 0.064, 0.128)):
            panel_length = 0.30 - abs(panel_idx - 2) * 0.016
            _add_part(
                bpy,
                col,
                "cube",
                f"{cname}_CapePanel_{panel_idx}",
                parent=cape_pivot,
                loc=(panel_x * w_scale, 0.010 * abs(panel_idx - 2), -panel_length),
                scale=(0.032 * w_scale, 0.006, panel_length),
                mat=cloth_mat,
                rot=(0.14 + 0.012 * abs(panel_idx - 2), 0.0, 0.035 * (panel_idx - 2)),
            )

    # Head + deterministic seed facial proportions + jaw lip-sync joint.
    # The previous head was 0.30m tall on a ~1.82m body (~6 heads, doll-like).
    # This narrower 0.25m cranium on a longer neck gives roughly 7.4 heads.
    head_width = 0.104 + ((seed % 7) - 3) * 0.0025
    head = _new_pivot(bpy, col, f"{cname}_Head", (0.0, 0.0, 0.60), parent=torso)
    _add_part(bpy, col, "cylinder", f"{cname}_Neck", parent=head, loc=(0, 0, -0.055), scale=(0.048, 0.050, 0.065), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_Cranium", parent=head, loc=(0, 0.004, 0.105), scale=(head_width, 0.119, 0.125), mat=skin_mat)
    # Brow ridge, tapered lower face/jaw mass, and ears remove the plain egg-head read.
    _add_part(bpy, col, "sphere", f"{cname}_BrowRidge", parent=head, loc=(0, -0.092, 0.122), scale=(0.082, 0.052, 0.034), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_FaceTaper", parent=head, loc=(0, -0.012, 0.038), scale=(0.083, 0.095, 0.068), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_EarL", parent=head, loc=(-head_width - 0.004, 0.006, 0.092), scale=(0.015, 0.025, 0.035), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_EarR", parent=head, loc=(head_width + 0.004, 0.006, 0.092), scale=(0.015, 0.025, 0.035), mat=skin_mat)
    # Defined nose: bridge flowing into a rounded tip and nostril base.
    _add_part(bpy, col, "sphere", f"{cname}_NoseBridge", parent=head, loc=(0, -0.106, 0.082), scale=(0.011, 0.021, 0.036), mat=skin_mat, rot=(0.22, 0, 0))
    _add_part(bpy, col, "sphere", f"{cname}_NoseTip", parent=head, loc=(0, -0.118, 0.052), scale=(0.014, 0.013, 0.014), mat=skin_mat)
    _add_part(bpy, col, "sphere", f"{cname}_NoseBase", parent=head, loc=(0, -0.111, 0.036), scale=(0.022, 0.013, 0.010), mat=skin_mat)

    # Hair: a smaller swept-back scalp volume plus individual groomed strands.
    # The cap now sits behind the forehead instead of wrapping the whole skull.
    hair_style = profile.get("hair_style", "short_dark")
    _add_part(bpy, col, "sphere", f"{cname}_HairCap", parent=head, loc=(0, 0.026, 0.132), scale=(head_width * 1.05, 0.119, 0.110), mat=hair_mat)
    is_long_hair = "long" in hair_style or profile.get("role") == "deuteragonist"
    if is_long_hair:
        _add_part(bpy, col, "cylinder", f"{cname}_HairBack", parent=head, loc=(0, 0.104, -0.045), scale=(0.068, 0.034, 0.120), mat=hair_mat)

    strand_count = 24 if is_long_hair else 18
    for strand_idx in range(strand_count):
        u = -1.0 + (2.0 * strand_idx / max(1, strand_count - 1))
        wave = ((seed * (strand_idx + 3)) % 9 - 4) * 0.0018
        start_x = u * head_width * 0.82
        start_y = -0.035 + abs(u) * 0.045
        start_z = 0.205 - abs(u) * 0.035
        mid_x = u * head_width * 0.98
        if is_long_hair:
            points = [
                (start_x, start_y, start_z),
                (mid_x, 0.070 + wave, 0.105),
                (mid_x * 0.92, 0.105, -0.055 + wave),
                (mid_x * 0.84, 0.112, -0.285 - abs(wave) * 3.0),
            ]
        else:
            points = [
                (start_x, start_y, start_z),
                (mid_x, 0.045 + wave, 0.145),
                (mid_x * 1.01, 0.085, 0.055 + wave),
            ]
        _add_curve_strand(
            bpy,
            col,
            f"{cname}_HairStrand_{strand_idx:02d}",
            parent=head,
            points=points,
            mat=hair_mat,
            bevel_depth=0.0028 if is_long_hair else 0.0034,
        )

    # Short jaw stubble for broad-shouldered short-hair profiles (e.g. Bilal).
    # Explicit profile data wins when a host application provides it.
    has_stubble = profile.get("facial_hair") == "short_beard" or (
        profile.get("gender") == "male"
        or (hair_style == "short_dark" and not is_long_hair and w_scale >= 1.0)
    )
    if has_stubble:
        for beard_idx in range(14):
            u = -1.0 + (2.0 * beard_idx / 13.0)
            bx = u * 0.058
            by = -0.085 - (1.0 - abs(u)) * 0.022
            bz = 0.025 - abs(u) * 0.018
            _add_curve_strand(
                bpy,
                col,
                f"{cname}_BeardStrand_{beard_idx:02d}",
                parent=head,
                points=[(bx, by, bz + 0.020), (bx * 1.04, by - 0.006, bz - 0.025), (bx * 0.98, by - 0.002, bz - 0.055)],
                mat=hair_mat,
                bevel_depth=0.0022,
            )

    # Eyes: whites set into the face, coloured iris, pupil, and a tiny emissive
    # catchlight. These are deliberately smaller than the old cartoon spheres.
    for eye_sign, eye_name in ((-1.0, "L"), (1.0, "R")):
        eye_x = eye_sign * 0.040
        _add_part(bpy, col, "sphere", f"{cname}_Eye{eye_name}", parent=head, loc=(eye_x, -0.104, 0.114), scale=(0.019, 0.012, 0.013), mat=eye_white_mat)
        _add_part(bpy, col, "sphere", f"{cname}_Iris{eye_name}", parent=head, loc=(eye_x, -0.115, 0.114), scale=(0.0095, 0.006, 0.009), mat=iris_mat)
        _add_part(bpy, col, "sphere", f"{cname}_Pupil{eye_name}", parent=head, loc=(eye_x, -0.120, 0.114), scale=(0.0048, 0.0035, 0.0045), mat=pupil_mat)
        _add_part(
            bpy,
            col,
            "sphere",
            f"{cname}_Catchlight{eye_name}",
            parent=head,
            loc=(eye_x - 0.0035, -0.123, 0.118),
            scale=(0.0018, 0.0012, 0.0018),
            mat=catchlight_mat,
        )
        _add_part(bpy, col, "sphere", f"{cname}_UpperLid{eye_name}", parent=head, loc=(eye_x, -0.103, 0.126), scale=(0.020, 0.010, 0.006), mat=skin_mat)

    brow_l = _new_pivot(bpy, col, f"{cname}_BrowL", (-0.041, -0.110, 0.138), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_BrowMeshL", parent=brow_l, loc=(0, 0, 0), scale=(0.024, 0.006, 0.0045), mat=hair_mat)
    brow_r = _new_pivot(bpy, col, f"{cname}_BrowR", (0.041, -0.110, 0.138), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_BrowMeshR", parent=brow_r, loc=(0, 0, 0), scale=(0.024, 0.006, 0.0045), mat=hair_mat)

    # Articulated jaw/mouth for local TTS viseme lip-sync, now with separate lips.
    jaw = _new_pivot(bpy, col, f"{cname}_Jaw", (0.0, -0.045, 0.032), parent=head)
    _add_part(bpy, col, "cube", f"{cname}_MouthCavity", parent=head, loc=(0.0, -0.104, 0.018), scale=(0.030, 0.009, 0.009), mat=lip_mat)
    _add_part(bpy, col, "sphere", f"{cname}_UpperLip", parent=head, loc=(0.0, -0.109, 0.024), scale=(0.027, 0.006, 0.0055), mat=lip_mat)
    _add_part(bpy, col, "sphere", f"{cname}_LowerLip", parent=jaw, loc=(0.0, -0.064, -0.020), scale=(0.023, 0.0055, 0.005), mat=lip_mat)
    _add_part(bpy, col, "sphere", f"{cname}_Chin", parent=jaw, loc=(0.0, -0.052, -0.040), scale=(0.050, 0.042, 0.026), mat=skin_mat)

    # Arms: shoulder pivots at a realistic ~0.41m separation, with longer
    # upper/forearm segments and fully fingered hands (grip-aware curl).
    grip_props = props_override if props_override is not None else (profile.get("props") or [])
    grip_left = "torch" in grip_props
    grip_right = bool({"sword", "spear", "staff"} & set(grip_props))

    upper_arm_l = _new_pivot(bpy, col, f"{cname}_UpperArmL", (-0.205 * w_scale, 0.0, 0.43), parent=torso)
    _add_part(bpy, col, "sphere", f"{cname}_DeltoidL", parent=upper_arm_l, loc=(0, 0, -0.035), scale=(0.058, 0.058, 0.065), mat=cloth_mat)
    _add_part(bpy, col, "cylinder", f"{cname}_UpperArmMeshL", parent=upper_arm_l, loc=(0, 0, -0.15), scale=(0.050, 0.050, 0.15), mat=cloth_mat)
    forearm_l = _new_pivot(bpy, col, f"{cname}_ForearmL", (0.0, 0.0, -0.30), parent=upper_arm_l)
    _add_part(bpy, col, "cylinder", f"{cname}_ForearmMeshL", parent=forearm_l, loc=(0, 0, -0.14), scale=(0.042, 0.042, 0.14), mat=skin_mat)
    _add_part(bpy, col, "cylinder", f"{cname}_CuffL", parent=forearm_l, loc=(0, 0, -0.245), scale=(0.048, 0.048, 0.026), mat=trim_mat)
    hand_l = _new_pivot(bpy, col, f"{cname}_HandL", (0.0, 0.0, -0.29), parent=forearm_l)
    _build_hand_with_fingers(bpy, col, cname, "L", hand=hand_l, skin_mat=skin_mat, grip=grip_left)

    upper_arm_r = _new_pivot(bpy, col, f"{cname}_UpperArmR", (0.205 * w_scale, 0.0, 0.43), parent=torso)
    _add_part(bpy, col, "sphere", f"{cname}_DeltoidR", parent=upper_arm_r, loc=(0, 0, -0.035), scale=(0.058, 0.058, 0.065), mat=cloth_mat)
    _add_part(bpy, col, "cylinder", f"{cname}_UpperArmMeshR", parent=upper_arm_r, loc=(0, 0, -0.15), scale=(0.050, 0.050, 0.15), mat=cloth_mat)
    forearm_r = _new_pivot(bpy, col, f"{cname}_ForearmR", (0.0, 0.0, -0.30), parent=upper_arm_r)
    _add_part(bpy, col, "cylinder", f"{cname}_ForearmMeshR", parent=forearm_r, loc=(0, 0, -0.14), scale=(0.042, 0.042, 0.14), mat=skin_mat)
    _add_part(bpy, col, "cylinder", f"{cname}_CuffR", parent=forearm_r, loc=(0, 0, -0.245), scale=(0.048, 0.048, 0.026), mat=trim_mat)
    hand_r = _new_pivot(bpy, col, f"{cname}_HandR", (0.0, 0.0, -0.29), parent=forearm_r)
    _build_hand_with_fingers(bpy, col, cname, "R", hand=hand_r, skin_mat=skin_mat, grip=grip_right)

    # Legs
    thigh_l = _new_pivot(bpy, col, f"{cname}_ThighL", (-0.10 * w_scale, 0.0, -0.04), parent=pelvis)
    _add_part(bpy, col, "cylinder", f"{cname}_ThighMeshL", parent=thigh_l, loc=(0, 0, -0.21), scale=(0.075, 0.075, 0.21), mat=trim_mat)
    shin_l = _new_pivot(bpy, col, f"{cname}_ShinL", (0.0, 0.0, -0.42), parent=thigh_l)
    _add_part(bpy, col, "cylinder", f"{cname}_ShinMeshL", parent=shin_l, loc=(0, 0, -0.20), scale=(0.058, 0.058, 0.20), mat=trim_mat)
    _add_part(bpy, col, "sphere", f"{cname}_GreaveL", parent=shin_l, loc=(0, -0.042, -0.20), scale=(0.045, 0.022, 0.150), mat=accent_mat)
    _add_part(bpy, col, "cube", f"{cname}_BootL", parent=shin_l, loc=(0, -0.045, -0.43), scale=(0.062, 0.11, 0.042), mat=trim_mat)

    thigh_r = _new_pivot(bpy, col, f"{cname}_ThighR", (0.10 * w_scale, 0.0, -0.04), parent=pelvis)
    _add_part(bpy, col, "cylinder", f"{cname}_ThighMeshR", parent=thigh_r, loc=(0, 0, -0.21), scale=(0.075, 0.075, 0.21), mat=trim_mat)
    shin_r = _new_pivot(bpy, col, f"{cname}_ShinR", (0.0, 0.0, -0.42), parent=thigh_r)
    _add_part(bpy, col, "cylinder", f"{cname}_ShinMeshR", parent=shin_r, loc=(0, 0, -0.20), scale=(0.058, 0.058, 0.20), mat=trim_mat)
    _add_part(bpy, col, "sphere", f"{cname}_GreaveR", parent=shin_r, loc=(0, -0.042, -0.20), scale=(0.045, 0.022, 0.150), mat=accent_mat)
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
            "cape": cape_pivot,
        },
    }
