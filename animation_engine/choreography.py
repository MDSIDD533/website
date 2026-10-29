"""Collision-aware spatial blocking, action clip catalog, and editable combat choreography."""

from __future__ import annotations

import math
from typing import Any

MIN_CHARACTER_SEPARATION_M = 1.15
COMBAT_STRIKE_DISTANCE_M = 1.45

SUPPORTED_ANIMATION_CLIPS: list[dict[str, Any]] = [
    {"id": "idle", "label": "Idle Breathing", "category": "locomotion", "supports_props": True},
    {"id": "walk", "label": "Walk Forward", "category": "locomotion", "supports_props": True},
    {"id": "run", "label": "Run / Sprint", "category": "locomotion", "supports_props": True},
    {"id": "turn", "label": "Turn Toward Target", "category": "locomotion", "supports_props": True},
    {"id": "look_at", "label": "Look At Partner", "category": "acting", "supports_props": True},
    {"id": "sit", "label": "Sit / Kneel", "category": "posture", "supports_props": False},
    {"id": "stand", "label": "Stand Up", "category": "posture", "supports_props": True},
    {"id": "gesture", "label": "Hand Gestures", "category": "acting", "supports_props": True},
    {"id": "speak", "label": "Speaking + Viseme Lip-Sync", "category": "acting", "supports_props": True},
    {"id": "react", "label": "Emotional Reaction", "category": "acting", "supports_props": True},
    {"id": "chase", "label": "Chase Pursuit", "category": "action", "supports_props": True},
    {"id": "dodge", "label": "Evasive Sidestep Dodge", "category": "combat", "supports_props": True},
    {"id": "punch", "label": "Direct Strike / Punch", "category": "combat", "supports_props": False},
    {"id": "kick", "label": "Snap Kick", "category": "combat", "supports_props": True},
    {"id": "block", "label": "Shield / Forearm Block", "category": "combat", "supports_props": True},
    {"id": "fall", "label": "Knockdown Fall", "category": "combat", "supports_props": False},
    {"id": "get_up", "label": "Recover & Get Back Up", "category": "combat", "supports_props": True},
    {"id": "interact_prop", "label": "Wield / Inspect Prop", "category": "acting", "supports_props": True},
    {"id": "group_move", "label": "Group Formation Advance", "category": "locomotion", "supports_props": True},
    {"id": "cinematic_combat", "label": "Choreographed Combat Exchange", "category": "combat", "supports_props": True},
]

SUPPORTED_EXPRESSIONS = [
    "neutral",
    "determined",
    "angry",
    "joyful",
    "sad",
    "fearful",
    "surprised",
    "calm",
]


def resolve_collision_free_positions(positions: list[dict[str, Any]], min_dist: float = MIN_CHARACTER_SEPARATION_M) -> list[dict[str, Any]]:
    """Iteratively separate character root positions in the XY plane so capsules never intersect."""
    resolved = [dict(p) for p in positions]
    n = len(resolved)
    for _ in range(12):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = float(resolved[j].get("x", 0.0)) - float(resolved[i].get("x", 0.0))
                dy = float(resolved[j].get("y", 0.0)) - float(resolved[i].get("y", 0.0))
                dist = math.hypot(dx, dy)
                if dist < min_dist:
                    if dist < 1e-4:
                        dx, dy, dist = 1.0, 0.0, 1.0
                    overlap = (min_dist - dist) * 0.52
                    nx, ny = dx / dist, dy / dist
                    resolved[i]["x"] = round(float(resolved[i].get("x", 0.0)) - nx * overlap, 3)
                    resolved[i]["y"] = round(float(resolved[i].get("y", 0.0)) - ny * overlap, 3)
                    resolved[j]["x"] = round(float(resolved[j].get("x", 0.0)) + nx * overlap, 3)
                    resolved[j]["y"] = round(float(resolved[j].get("y", 0.0)) + ny * overlap, 3)
                    moved = True
        if not moved:
            break

    # Update facing yaw so characters naturally orient toward each other or camera
    if n >= 2:
        for i in range(n):
            partner = resolved[1 if i == 0 else 0]
            dx = float(partner["x"]) - float(resolved[i]["x"])
            dy = float(partner["y"]) - float(resolved[i]["y"])
            # In Blender +Y is depth away from default -Y camera; yaw 0 faces -Y (camera)
            yaw_rad = math.atan2(dx, -dy)
            resolved[i]["yaw_deg"] = round(math.degrees(yaw_rad), 1)
    elif n == 1:
        resolved[0].setdefault("yaw_deg", 12.0)

    return resolved


def plan_scene_choreography(
    *,
    characters_present: list[str],
    actions: list[str],
    is_combat: bool = False,
) -> dict[str, Any]:
    count = len(characters_present)
    positions: list[dict[str, Any]] = []

    if count == 1:
        primary_clip = "walk" if "walk" in actions else (actions[0] if actions else "idle")
        positions.append(
            {
                "character_name": characters_present[0],
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "yaw_deg": 10.0,
                "action_clip": primary_clip,
                "expression": "determined",
            }
        )
    elif count >= 2:
        half_span = COMBAT_STRIKE_DISTANCE_M * 0.5 if is_combat else 0.95
        for idx, cname in enumerate(characters_present):
            if idx == 0:
                x, y = -half_span, 0.0
                clip = "cinematic_combat" if is_combat else ("speak" if "speak" in actions else "idle")
            elif idx == 1:
                x, y = half_span, 0.12
                if is_combat:
                    clip = "block" if "block" in actions else ("dodge" if "dodge" in actions else "cinematic_combat")
                else:
                    clip = "look_at"
            else:
                angle = (idx - 1) * 0.85
                x = round(math.cos(angle) * 2.1, 2)
                y = round(1.2 + math.sin(angle) * 0.9, 2)
                clip = "group_move" if "group_move" in actions else "idle"

            positions.append(
                {
                    "character_name": cname,
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "z": 0.0,
                    "yaw_deg": 0.0,
                    "action_clip": clip,
                    "expression": "angry" if (is_combat and idx == 1) else "determined",
                }
            )

    safe_positions = resolve_collision_free_positions(positions)

    combat_cfg: dict[str, Any] = {
        "enabled": bool(is_combat and count >= 2),
        "attacker": characters_present[0] if count >= 1 else "",
        "defender": characters_present[1] if count >= 2 else "",
        "attack_direction": "right_slash" if "cinematic_combat" in actions else ("jab_cross" if "punch" in actions else "front_kick"),
        "defense_reaction": "block" if "block" in actions else ("dodge" if "dodge" in actions else "parry_counter"),
        "strike_distance_m": COMBAT_STRIKE_DISTANCE_M,
        "contact_frame_pct": 0.45,
        "secondary_exchange_pct": 0.76,
        "camera_angle_offset_deg": 18.0,
        "collision_guard_active": True,
        "transition_blend_frames": 5,
    }

    return {
        "character_positions": safe_positions,
        "combat_choreography": combat_cfg,
    }
