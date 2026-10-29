"""Restricted headless Blender (`bpy`) worker for scene animation, character previews, and environment previews.

Invoked via `python -m render_engine.blender_worker <spec_json_path>` so memory is cleanly isolated
per render task and the job manager can pause (SIGSTOP), resume (SIGCONT), or cancel (SIGTERM) safely,
while streaming genuine per-frame completion events (`SIDD_FRAME:<done>/<total>`).
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Any


def compute_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    base_short = {
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
        "1440p": 1440,
        "4k": 2160,
    }.get(resolution.lower(), 720)

    if aspect_ratio == "9:16":
        w = base_short
        h = int(round(base_short * 16 / 9))
    elif aspect_ratio == "1:1":
        w = base_short
        h = base_short
    else:
        # 16:9 default
        h = base_short
        w = int(round(base_short * 16 / 9))

    # Ensure even pixel dimensions for yuv420p H.264
    return (w + (w % 2), h + (h % 2))


def _configure_cinematic_post(bpy: Any) -> None:
    """Subtle torch bloom + warm-shadow/cool-highlight grade for cinematic renders.

    Kept intentionally gentle: the sunset fortress palette is already warm, so
    this only adds fog-glow around emissives above luminance 1.0 and a small
    lift/gain split-tone. Applied in Blender's compositor before PNG write.
    """
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    render_layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.0
    glare.mix = -0.08
    glare.size = 8

    grade = tree.nodes.new("CompositorNodeColorBalance")
    grade.correction_method = "LIFT_GAMMA_GAIN"
    grade.lift = (0.97, 1.01, 1.05)
    grade.gamma = (1.0, 1.0, 1.0)
    grade.gain = (1.05, 1.01, 0.97)

    composite = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(render_layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], grade.inputs["Image"])
    tree.links.new(grade.outputs["Image"], composite.inputs["Image"])


def _configure_cycles(bpy: Any, quality_profile: str, width: int, height: int) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.use_persistent_data = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.08

    is_cinematic = quality_profile == "cinematic"
    if is_cinematic:
        # Full-resolution showcase preset. Adaptive sampling makes 64 the cap,
        # not the cost of every pixel; OIDN then removes the remaining grain.
        samples = 64
        scale_pct = 100
        bounces = 4
        use_denoise = True
        scene.cycles.adaptive_threshold = 0.01
    elif quality_profile == "high_quality":
        samples = 14
        scale_pct = 100
        bounces = 3
        use_denoise = True
    elif quality_profile == "balanced":
        samples = 6
        scale_pct = 80
        bounces = 2
        use_denoise = False
    else:
        # low_resource (fast CPU raytracing)
        samples = 3
        scale_pct = 50
        bounces = 1
        use_denoise = False

    scene.cycles.samples = samples
    scene.cycles.max_bounces = bounces
    if is_cinematic:
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 3
        scene.cycles.transmission_bounces = 2
        scene.cycles.volume_bounces = 1
        scene.cycles.sample_clamp_indirect = 8.0
        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False
        scene.cycles.use_light_tree = True
    else:
        scene.cycles.diffuse_bounces = 1
        scene.cycles.glossy_bounces = 1
        scene.cycles.transmission_bounces = 1
        scene.cycles.volume_bounces = 0
    scene.cycles.use_denoising = use_denoise
    if use_denoise:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        scene.cycles.denoising_prefilter = "ACCURATE"

    if is_cinematic:
        # AgX (Blender 4.2 default) with a touch of extra exposure; the split
        # tone itself lives in the compositor so previews stay honest stills.
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = 0.12
        _configure_cinematic_post(bpy)

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = scale_pct
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    return {
        "samples": samples,
        "scale_pct": scale_pct,
        "bounces": bounces,
        "use_denoise": use_denoise,
        "adaptive_threshold": scene.cycles.adaptive_threshold,
        "quality_profile": quality_profile,
    }


def render_character_preview(spec: dict[str, Any]) -> dict[str, Any]:
    import bpy  # type: ignore

    from animation_engine.clips import animate_character_clip, apply_expression_pose
    from character_engine.rig_builder import build_character_rig_in_blender
    from scene_engine.cameras import setup_cinematic_camera
    from scene_engine.environments import build_environment_in_blender

    bpy.ops.wm.read_factory_settings(use_empty=True)
    profile = spec["character"]
    out_png = Path(spec["output_png"])
    out_png.parent.mkdir(parents=True, exist_ok=True)

    _configure_cycles(bpy, spec.get("quality_profile", "balanced"), 640, 640)
    build_environment_in_blender(
        bpy,
        environment_preset="palace",
        location_key=f"preview_{profile['id']}",
        time_of_day="sunset",
        weather="clear",
        frame_start=1,
        frame_end=2,
    )
    rig = build_character_rig_in_blender(bpy, profile)
    animate_character_clip(
        rig,
        action_clip="gesture",
        frame_start=1,
        frame_end=2,
        fps=24,
        base_pos=(0.0, 0.0, 0.0),
        base_yaw_rad=0.18,
    )
    apply_expression_pose(rig, "determined", frame=1)
    setup_cinematic_camera(
        bpy,
        shot_type="medium",
        movement="static",
        frame_start=1,
        frame_end=2,
        focus_point=(0.0, 0.0, 1.38),
    )

    bpy.context.scene.frame_set(1)
    bpy.context.scene.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)
    return {"output_png": str(out_png), "exists": out_png.is_file()}


def render_environment_preview(spec: dict[str, Any]) -> dict[str, Any]:
    import bpy  # type: ignore

    from scene_engine.cameras import setup_cinematic_camera
    from scene_engine.environments import build_environment_in_blender

    bpy.ops.wm.read_factory_settings(use_empty=True)
    out_png = Path(spec["output_png"])
    out_png.parent.mkdir(parents=True, exist_ok=True)

    _configure_cycles(bpy, spec.get("quality_profile", "balanced"), 800, 450)
    build_environment_in_blender(
        bpy,
        environment_preset=spec.get("environment_preset", "fortress"),
        location_key=spec.get("location_key", "env_preview"),
        time_of_day=spec.get("time_of_day", "sunset"),
        weather=spec.get("weather", "clear"),
        frame_start=1,
        frame_end=2,
    )
    setup_cinematic_camera(
        bpy,
        shot_type="establishing",
        movement="static",
        frame_start=1,
        frame_end=2,
        focus_point=(0.0, 2.2, 1.8),
    )
    bpy.context.scene.frame_set(1)
    bpy.context.scene.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)
    return {"output_png": str(out_png), "exists": out_png.is_file()}


def render_animated_scene(spec: dict[str, Any]) -> dict[str, Any]:
    import bpy  # type: ignore

    from animation_engine.choreography import resolve_collision_free_positions
    from animation_engine.clips import (
        animate_character_clip,
        apply_expression_pose,
        apply_viseme_lipsync,
    )
    from character_engine.rig_builder import build_character_rig_in_blender
    from scene_engine.cameras import setup_cinematic_camera
    from scene_engine.environments import build_environment_in_blender

    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene_data = spec["scene"]
    characters_by_name: dict[str, dict[str, Any]] = {
        c["name"].lower(): c for c in spec.get("characters", [])
    }
    visemes_by_speaker: dict[str, list[float]] = {
        k.lower(): v for k, v in (spec.get("character_visemes") or {}).items()
    }

    target_fps = int(spec.get("fps", 24))
    quality_profile = spec.get("quality_profile", "low_resource")
    duration_sec = float(spec.get("duration_sec") or scene_data.get("duration_sec", 3.5))
    width, height = compute_dimensions(spec.get("resolution", "720p"), spec.get("aspect_ratio", "16:9"))

    # Internal keyframe render rate: full target_fps in high_quality, 12fps in balanced, 8fps in low_resource
    if quality_profile == "high_quality":
        render_fps = target_fps
    elif quality_profile == "balanced":
        render_fps = min(target_fps, 12)
    else:
        render_fps = min(target_fps, 8)

    total_frames = max(4, int(round(duration_sec * render_fps)))
    frame_start = 1
    frame_end = total_frames

    cycles_cfg = _configure_cycles(bpy, quality_profile, width, height)
    bpy.context.scene.render.fps = render_fps
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end

    print("SIDD_STAGE:building_3d_environment", flush=True)
    build_environment_in_blender(
        bpy,
        environment_preset=scene_data.get("environment_preset", "fortress"),
        location_key=scene_data.get("location_name") or scene_data.get("environment_preset", "fortress"),
        time_of_day=scene_data.get("time_of_day", "sunset"),
        weather=scene_data.get("weather", "clear"),
        frame_start=frame_start,
        frame_end=frame_end,
    )

    print("SIDD_STAGE:rigging_and_animating_characters", flush=True)
    raw_positions = scene_data.get("character_positions") or []
    if not raw_positions and scene_data.get("characters_present"):
        raw_positions = [
            {"character_name": nm, "x": idx * 1.3 - 0.65, "y": 0.0, "z": 0.0, "yaw_deg": 0.0, "action_clip": "idle"}
            for idx, nm in enumerate(scene_data["characters_present"])
        ]
    safe_positions = resolve_collision_free_positions(raw_positions)

    combat_cfg = scene_data.get("combat_choreography") or {}
    scene_props = list(scene_data.get("props") or [])
    focus_xs: list[float] = []
    focus_ys: list[float] = []

    for idx, pos_cfg in enumerate(safe_positions):
        cname = pos_cfg.get("character_name", f"Character_{idx + 1}")
        c_prof = characters_by_name.get(cname.lower()) or {
            "id": f"auto_{idx}",
            "name": cname,
            "skin_tone": "#c9936b",
            "hair_color": "#231b16",
            "outfit_preset": "historical_armor",
            "identity_seed": 101 + idx * 29,
        }
        # Give combatant props automatically when combat or props are specified
        char_props = list(c_prof.get("props") or [])
        for p in scene_props:
            if p not in char_props:
                char_props.append(p)
        if combat_cfg.get("enabled") and "sword" not in char_props:
            char_props.append("sword")
            if idx == 0 and "shield" not in char_props:
                char_props.append("shield")

        rig = build_character_rig_in_blender(bpy, c_prof, props_override=char_props)

        role_in_combat = "none"
        if combat_cfg.get("enabled"):
            role_in_combat = "defender" if idx == 1 else "attacker"

        bx = float(pos_cfg.get("x", 0.0))
        by = float(pos_cfg.get("y", 0.0))
        bz = float(pos_cfg.get("z", 0.0))
        yaw_rad = math.radians(float(pos_cfg.get("yaw_deg", 0.0)))
        focus_xs.append(bx)
        focus_ys.append(by)

        animate_character_clip(
            rig,
            action_clip=pos_cfg.get("action_clip") or (scene_data.get("actions") or ["idle"])[0],
            frame_start=frame_start,
            frame_end=frame_end,
            fps=render_fps,
            base_pos=(bx, by, bz),
            base_yaw_rad=yaw_rad,
            role_in_combat=role_in_combat,
            combat_cfg=combat_cfg,
        )
        apply_expression_pose(rig, pos_cfg.get("expression", "determined"), frame=frame_start)

        # Resample viseme envelope from target_fps to render_fps so 3D jaw sync matches exact timing
        raw_vis = visemes_by_speaker.get(cname.lower())
        if raw_vis:
            mapped_vis = [
                raw_vis[min(len(raw_vis) - 1, int(round(f_i * len(raw_vis) / max(1, total_frames))))]
                for f_i in range(total_frames)
            ]
            apply_viseme_lipsync(rig, mapped_vis, fps=render_fps, start_frame=frame_start)

    focus_x = sum(focus_xs) / len(focus_xs) if focus_xs else 0.0
    focus_y = sum(focus_ys) / len(focus_ys) if focus_ys else 0.0
    setup_cinematic_camera(
        bpy,
        shot_type=scene_data.get("camera_shot", "wide"),
        movement=scene_data.get("camera_movement", "slow_push_in"),
        frame_start=frame_start,
        frame_end=frame_end,
        focus_point=(focus_x, focus_y, 1.38),
        angle_offset_deg=float(combat_cfg.get("camera_angle_offset_deg", 0.0)) if combat_cfg.get("enabled") else 0.0,
    )

    frames_dir = Path(spec["frames_dir"])
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = Path(spec["thumbnail_path"])
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"SIDD_STAGE:raytracing_frames (0/{total_frames})", flush=True)
    rendered_paths: list[str] = []
    mid_frame = max(1, (frame_start + frame_end) // 2)

    for f in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(f)
        frame_file = frames_dir / f"frame_{f:04d}.png"
        bpy.context.scene.render.filepath = str(frame_file)
        bpy.ops.render.render(write_still=True)
        if not frame_file.is_file():
            raise RuntimeError(f"Blender failed to write frame {f} at {frame_file}")
        rendered_paths.append(str(frame_file))
        if f == mid_frame or (f == frame_end and not thumbnail_path.is_file()):
            shutil.copy2(frame_file, thumbnail_path)
        print(f"SIDD_FRAME:{f}/{total_frames}", flush=True)

    elapsed = round(time.time() - t0, 2)
    return {
        "frames_dir": str(frames_dir),
        "frame_count": len(rendered_paths),
        "render_fps": render_fps,
        "target_fps": target_fps,
        "target_width": width,
        "target_height": height,
        "thumbnail_path": str(thumbnail_path),
        "elapsed_sec": elapsed,
        "cycles": cycles_cfg,
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m render_engine.blender_worker <spec.json> <result.json>", file=sys.stderr)
        return 2

    spec_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    mode = spec.get("mode", "scene")

    if mode == "character_preview":
        res = render_character_preview(spec)
    elif mode == "environment_preview":
        res = render_environment_preview(spec)
    else:
        res = render_animated_scene(spec)

    result_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
