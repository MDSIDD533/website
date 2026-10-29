"""Cinematic camera framing & keyframed camera movement rigs in Blender."""

from __future__ import annotations

import math
from typing import Any

CAMERA_SHOT_CATALOG: list[dict[str, Any]] = [
    # Establishing was 7.4m away at 2.8m high: characters filled a quarter of
    # the frame height and faces were unreadable. This closer, lower framing
    # still shows the full fortress while giving people real screen presence.
    {"id": "establishing", "label": "Establishing Wide Shot", "lens_mm": 30.0, "dist": 5.9, "height": 1.62, "fstop": 5.6},
    {"id": "wide", "label": "Wide Full-Body Shot", "lens_mm": 34.0, "dist": 4.9, "height": 1.50, "fstop": 4.5},
    {"id": "medium", "label": "Medium Conversation Shot", "lens_mm": 45.0, "dist": 3.3, "height": 1.38, "fstop": 2.8},
    {"id": "close_up", "label": "Close-Up Portrait Shot", "lens_mm": 65.0, "dist": 2.0, "height": 1.50, "fstop": 2.8},
    {"id": "tracking", "label": "Tracking Follow Shot", "lens_mm": 35.0, "dist": 4.0, "height": 1.45, "fstop": 3.5},
    {"id": "over_the_shoulder", "label": "Over-The-Shoulder Dialogue Shot", "lens_mm": 50.0, "dist": 3.0, "height": 1.50, "fstop": 2.8},
    {"id": "action", "label": "Dynamic Action / Combat Shot", "lens_mm": 28.0, "dist": 4.1, "height": 1.20, "fstop": 4.0},
]

CAMERA_MOVEMENTS = [
    "static",
    "slow_push_in",
    "pull_back",
    "pan_across",
    "orbit_subtle",
    "dolly_track",
    "dynamic_combat_track",
]


def setup_cinematic_camera(
    bpy: Any,
    *,
    shot_type: str,
    movement: str,
    frame_start: int,
    frame_end: int,
    focus_point: tuple[float, float, float] = (0.0, 0.0, 1.38),
    angle_offset_deg: float = 0.0,
) -> Any:
    """Create a Track-To constrained cinematic Blender camera with smooth keyframed motion."""
    scene = bpy.context.scene
    col = scene.collection
    preset = next((s for s in CAMERA_SHOT_CATALOG if s["id"] == shot_type), CAMERA_SHOT_CATALOG[1])

    target = bpy.data.objects.new("CameraFocusTarget", None)
    target.location = focus_point
    col.objects.link(target)

    cam_data = bpy.data.cameras.new(name="StudioCamera")
    cam_data.lens = float(preset["lens_mm"])
    cam_data.clip_end = 120.0
    # Shallow, shot-appropriate depth of field focused on the actors; both
    # characters share roughly the same depth plane in two-shots, so the
    # fortress softens behind them instead of competing for attention.
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = target
    cam_data.dof.aperture_fstop = float(preset.get("fstop", 4.0))
    cam_obj = bpy.data.objects.new(name="StudioCamera", object_data=cam_data)
    col.objects.link(cam_obj)
    scene.camera = cam_obj

    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    dist = float(preset["dist"])
    z_h = float(preset["height"])
    # Dialogue blocking makes partners face each other along ±X. A camera at
    # 0° therefore sees both as flat side profiles with overlapping legs.
    # A gentle 14° offset adds depth without emptying the backdrop (actors
    # additionally cheat a few degrees toward camera in choreography).
    base_ang = math.radians(angle_offset_deg if angle_offset_deg else 14.0)
    if shot_type == "over_the_shoulder":
        base_ang += 0.38

    start_x = focus_point[0] + math.sin(base_ang) * dist
    start_y = focus_point[1] - math.cos(base_ang) * dist
    start_z = z_h

    end_x, end_y, end_z = start_x, start_y, start_z
    if movement == "slow_push_in":
        end_x = focus_point[0] + math.sin(base_ang) * (dist * 0.80)
        end_y = focus_point[1] - math.cos(base_ang) * (dist * 0.80)
    elif movement == "pull_back":
        end_x = focus_point[0] + math.sin(base_ang) * (dist * 1.24)
        end_y = focus_point[1] - math.cos(base_ang) * (dist * 1.24)
        end_z = z_h + 0.35
    elif movement == "pan_across":
        start_x -= 0.95
        end_x += 0.95
    elif movement == "orbit_subtle":
        end_ang = base_ang + 0.34
        end_x = focus_point[0] + math.sin(end_ang) * dist
        end_y = focus_point[1] - math.cos(end_ang) * dist
    elif movement == "dolly_track":
        end_y = start_y + 0.65
        end_x = start_x + 0.45
    elif movement == "dynamic_combat_track":
        mid_f = max(frame_start + 1, (frame_start + frame_end) // 2)
        cam_obj.location = (start_x - 0.55, start_y, start_z)
        cam_obj.keyframe_insert(data_path="location", frame=frame_start)
        cam_obj.location = (focus_point[0] + 0.35, focus_point[1] - dist * 0.78, start_z - 0.18)
        cam_obj.keyframe_insert(data_path="location", frame=mid_f)
        cam_obj.location = (start_x + 0.75, start_y + 0.25, start_z + 0.12)
        cam_obj.keyframe_insert(data_path="location", frame=frame_end)
        return cam_obj

    cam_obj.location = (start_x, start_y, start_z)
    cam_obj.keyframe_insert(data_path="location", frame=frame_start)
    cam_obj.location = (end_x, end_y, end_z)
    cam_obj.keyframe_insert(data_path="location", frame=frame_end)
    return cam_obj
