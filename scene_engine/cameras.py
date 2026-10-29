"""Cinematic camera framing & keyframed camera movement rigs in Blender."""

from __future__ import annotations

import math
from typing import Any

CAMERA_SHOT_CATALOG: list[dict[str, Any]] = [
    {"id": "establishing", "label": "Establishing Wide Shot", "lens_mm": 24.0, "dist": 7.4, "height": 2.8},
    {"id": "wide", "label": "Wide Full-Body Shot", "lens_mm": 32.0, "dist": 5.4, "height": 1.85},
    {"id": "medium", "label": "Medium Conversation Shot", "lens_mm": 45.0, "dist": 3.4, "height": 1.52},
    {"id": "close_up", "label": "Close-Up Portrait Shot", "lens_mm": 65.0, "dist": 2.05, "height": 1.56},
    {"id": "tracking", "label": "Tracking Follow Shot", "lens_mm": 35.0, "dist": 4.2, "height": 1.65},
    {"id": "over_the_shoulder", "label": "Over-The-Shoulder Dialogue Shot", "lens_mm": 50.0, "dist": 3.1, "height": 1.60},
    {"id": "action", "label": "Dynamic Action / Combat Shot", "lens_mm": 28.0, "dist": 4.3, "height": 1.42},
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
    cam_obj = bpy.data.objects.new(name="StudioCamera", object_data=cam_data)
    col.objects.link(cam_obj)
    scene.camera = cam_obj

    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    dist = float(preset["dist"])
    z_h = float(preset["height"])
    base_ang = math.radians(angle_offset_deg)
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
