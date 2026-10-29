"""Blender (`bpy`) procedural 3D character animation keyframes, combat choreography, and jaw lip-sync."""

from __future__ import annotations

import math
from typing import Any


def apply_expression_pose(rig: dict[str, Any], expression: str, frame: int = 1) -> None:
    """Adjust 3D brow angles and mouth posture on the rigged head."""
    brow_l = rig["joints"].get("brow_l")
    brow_r = rig["joints"].get("brow_r")
    jaw = rig["joints"].get("jaw")
    if not (brow_l and brow_r and jaw):
        return

    presets = {
        "neutral": (0.0, 0.0, 0.02),
        "calm": (0.04, -0.04, 0.02),
        "determined": (-0.18, 0.18, 0.03),
        "angry": (-0.32, 0.32, 0.06),
        "joyful": (0.16, -0.16, 0.10),
        "sad": (0.24, -0.24, 0.01),
        "fearful": (0.28, -0.28, 0.14),
        "surprised": (0.35, -0.35, 0.22),
        # Inner brows raised with a barely-parted jaw: watchful concern
        # without tipping into the wide-eyed "fearful" read.
        "concerned": (0.22, -0.22, 0.045),
        "alert": (0.20, -0.20, 0.035),
    }
    bl_rot, br_rot, jaw_base = presets.get(expression, presets["neutral"])
    brow_l.rotation_euler[1] = bl_rot
    brow_r.rotation_euler[1] = br_rot
    brow_l.keyframe_insert(data_path="rotation_euler", frame=frame)
    brow_r.keyframe_insert(data_path="rotation_euler", frame=frame)
    jaw.rotation_euler[0] = jaw_base
    jaw.keyframe_insert(data_path="rotation_euler", frame=frame)


def apply_viseme_lipsync(
    rig: dict[str, Any],
    viseme_envelope: list[float],
    fps: int,
    start_frame: int = 1,
) -> None:
    """Drive 3D character jaw/mouth joint rotation directly from speech viseme envelope."""
    jaw = rig["joints"].get("jaw")
    head = rig["joints"].get("head")
    if not jaw or not viseme_envelope:
        return

    for idx, openness in enumerate(viseme_envelope):
        frame = start_frame + idx
        clamped = max(0.0, min(1.0, float(openness)))
        jaw.rotation_euler[0] = 0.02 + clamped * 0.42
        jaw.keyframe_insert(data_path="rotation_euler", index=0, frame=frame)
        if head and idx % 3 == 0:
            head.rotation_euler[0] = -clamped * 0.06 * math.sin(idx * 0.4)
            head.keyframe_insert(data_path="rotation_euler", index=0, frame=frame)


def animate_character_clip(
    rig: dict[str, Any],
    *,
    action_clip: str,
    frame_start: int,
    frame_end: int,
    fps: int,
    base_pos: tuple[float, float, float],
    base_yaw_rad: float,
    role_in_combat: str = "none",
    combat_cfg: dict[str, Any] | None = None,
) -> None:
    """Insert frame-accurate 3D skeletal keyframes on the character rig in Blender."""
    root = rig["root"]
    j = rig["joints"]
    total_frames = max(2, frame_end - frame_start + 1)
    bx, by, bz = base_pos
    combat = combat_cfg or {}
    contact_f = frame_start + int(total_frames * float(combat.get("contact_frame_pct", 0.45)))
    second_f = frame_start + int(total_frames * float(combat.get("secondary_exchange_pct", 0.76)))

    step = 2 if total_frames > 36 else 1
    frames = list(range(frame_start, frame_end + 1, step))
    if frames[-1] != frame_end:
        frames.append(frame_end)

    for f in frames:
        t = (f - frame_start) / float(max(1, fps))
        u = (f - frame_start) / float(max(1, total_frames - 1))

        rx, ry, rz = bx, by, bz
        yaw = base_yaw_rad
        torso_pitch = 0.0
        torso_yaw = 0.0
        head_pitch = 0.0
        head_yaw = 0.0
        arm_l = [0.0, 0.08, 0.0]
        arm_r = [0.0, -0.08, 0.0]
        fore_l = [-0.18, 0.0, 0.0]
        fore_r = [-0.18, 0.0, 0.0]
        # Natural split stance for standing/acting clips (locomotion, sitting,
        # and combat branches overwrite these): one foot slightly forward so
        # the legs never collapse into a single column in side view.
        leg_l = -0.09
        leg_r = 0.11
        shin_l = 0.10
        shin_r = 0.05

        if action_clip in {"walk", "group_move"}:
            freq = 2.1 * math.pi
            stride = math.sin(t * freq)
            fwd = 0.55 * u
            rx = bx + math.sin(yaw) * fwd
            ry = by - math.cos(yaw) * fwd
            rz = bz + abs(math.cos(t * freq)) * 0.035
            leg_l = 0.48 * stride
            leg_r = -0.48 * stride
            shin_l = max(0.0, -stride) * 0.45
            shin_r = max(0.0, stride) * 0.45
            arm_l[0] = -0.36 * stride
            arm_r[0] = 0.36 * stride
            fore_l[0] = -0.25
            fore_r[0] = -0.25
            torso_pitch = 0.05

        elif action_clip in {"run", "chase"}:
            freq = 3.8 * math.pi
            stride = math.sin(t * freq)
            fwd = 1.25 * u
            rx = bx + math.sin(yaw) * fwd
            ry = by - math.cos(yaw) * fwd
            rz = bz + abs(math.sin(t * freq)) * 0.07
            torso_pitch = 0.22
            leg_l = 0.78 * stride
            leg_r = -0.78 * stride
            shin_l = 0.2 + max(0.0, -stride) * 0.65
            shin_r = 0.2 + max(0.0, stride) * 0.65
            arm_l[0] = -0.68 * stride
            arm_r[0] = 0.68 * stride
            fore_l[0] = -0.75
            fore_r[0] = -0.75

        elif action_clip == "turn":
            yaw = base_yaw_rad + math.sin(u * math.pi * 0.5) * 0.85
            head_yaw = math.sin(min(1.0, u * 1.3) * math.pi * 0.5) * 0.22
            leg_l = 0.18 * math.sin(u * math.pi * 2)
            leg_r = -leg_l

        elif action_clip == "sit":
            sit_amt = min(1.0, u * 2.2)
            rz = bz - 0.34 * sit_amt
            leg_l = -1.15 * sit_amt
            leg_r = -1.15 * sit_amt
            shin_l = 1.25 * sit_amt
            shin_r = 1.25 * sit_amt
            torso_pitch = 0.08 * sit_amt

        elif action_clip == "stand":
            sit_amt = max(0.0, 1.0 - u * 2.0)
            rz = bz - 0.34 * sit_amt
            leg_l = -1.15 * sit_amt
            leg_r = -1.15 * sit_amt
            shin_l = 1.25 * sit_amt
            shin_r = 1.25 * sit_amt

        elif action_clip in {"speak", "gesture", "look_at"}:
            torso_pitch = 0.03 * math.sin(t * 1.8)
            head_yaw = 0.14 * math.sin(t * 1.4)
            head_pitch = 0.06 * math.cos(t * 2.1)
            if action_clip in {"speak", "gesture"}:
                gest = 0.5 + 0.5 * math.sin(t * 3.1)
                arm_r[0] = -0.45 - 0.30 * gest
                arm_r[2] = 0.18 * math.sin(t * 2.4)
                fore_r[0] = -0.55 - 0.25 * gest
                arm_l[0] = -0.25 - 0.15 * math.cos(t * 2.6)
                fore_l[0] = -0.42

        elif action_clip == "interact_prop":
            raise_amt = 0.5 + 0.5 * math.sin(u * math.pi)
            arm_r[0] = -0.95 * raise_amt - 0.25
            fore_r[0] = -0.45
            head_pitch = -0.12 * raise_amt

        elif action_clip == "react":
            recoil = math.sin(min(1.0, u * 1.8) * math.pi)
            torso_pitch = -0.18 * recoil
            arm_l[0] = -0.55 * recoil
            arm_r[0] = -0.55 * recoil
            fore_l[0] = -0.65 * recoil
            fore_r[0] = -0.65 * recoil

        elif action_clip in {"cinematic_combat", "punch", "kick", "block", "dodge", "fall", "get_up"}:
            # Combat guard stance baseline
            leg_l = -0.26
            leg_r = 0.24
            shin_l = 0.28
            shin_r = 0.22
            arm_l[0] = -0.58
            fore_l[0] = -0.75
            arm_r[0] = -0.62
            fore_r[0] = -0.68
            torso_pitch = 0.10

            # Gaussian-like impulse around primary and secondary contact beats
            imp1 = math.exp(-((f - contact_f) / max(2.0, fps * 0.14)) ** 2)
            imp2 = math.exp(-((f - second_f) / max(2.0, fps * 0.15)) ** 2)

            if role_in_combat == "defender" or action_clip in {"block", "dodge", "fall", "get_up"}:
                reaction = combat.get("defense_reaction", action_clip)
                if reaction == "dodge" or action_clip == "dodge":
                    rx = bx + math.cos(yaw) * (0.48 * imp1)
                    ry = by + math.sin(yaw) * (0.48 * imp1)
                    torso_pitch = 0.30 * imp1
                elif action_clip == "fall":
                    fall_u = min(1.0, max(0.0, (u - 0.3) * 1.8))
                    rz = bz - 0.55 * fall_u
                    torso_pitch = -1.15 * fall_u
                elif action_clip == "get_up":
                    rec_u = 1.0 - min(1.0, u * 1.5)
                    rz = bz - 0.50 * rec_u
                    torso_pitch = 0.65 * rec_u
                else:
                    # Shield / weapon block + counter-strike on beat 2
                    arm_l[0] = -0.95 - 0.35 * imp1
                    arm_l[2] = -0.35 * imp1
                    fore_l[0] = -0.95
                    rx = bx - math.sin(yaw) * (0.14 * imp1)
                    ry = by + math.cos(yaw) * (0.14 * imp1)
                    # Counter slash on second beat
                    arm_r[0] = -0.62 - 0.78 * imp2
                    fore_r[0] = -0.68 + 0.48 * imp2
                    torso_yaw = 0.38 * imp2
            else:
                # Attacker strike choreography
                if action_clip == "kick":
                    leg_r = -1.25 * imp1 + 0.24 * (1.0 - imp1)
                    shin_r = 0.15 * (1.0 - imp1)
                    torso_pitch = -0.16 * imp1
                else:
                    lunge = 0.26 * imp1
                    rx = bx + math.sin(yaw) * lunge
                    ry = by - math.cos(yaw) * lunge
                    arm_r[0] = -1.38 * imp1 - 0.55 * (1.0 - imp1)
                    arm_r[1] = -0.35 * imp1
                    fore_r[0] = -0.15 * imp1 - 0.68 * (1.0 - imp1)
                    torso_yaw = 0.45 * imp1 - 0.32 * imp2
                    # Defend counter on beat 2
                    arm_l[0] = -0.92 * imp2 - 0.55 * (1.0 - imp2)

        else:
            # Smooth idle breathing
            breath = math.sin(t * 2.0)
            rz = bz + 0.012 * breath
            torso_pitch = 0.02 * breath
            arm_l[0] = 0.04 * breath
            arm_r[0] = -0.04 * breath
            head_yaw = 0.07 * math.sin(t * 0.9)

        root.location = (rx, ry, rz)
        root.rotation_euler = (0.0, 0.0, yaw)
        root.keyframe_insert(data_path="location", frame=f)
        root.keyframe_insert(data_path="rotation_euler", frame=f)

        # Subtle, deterministic asymmetry: a whisper of pelvic/shoulder tilt
        # (mirrored by screen side) keeps standing poses from reading as rigid
        # mannequins, while remaining far below anything that changes blocking.
        stance_side = 1.0 if bx >= 0.0 else -1.0
        weight_shift = 0.018 * stance_side + 0.006 * math.sin(t * 0.7 + bx)
        if j.get("pelvis") is not None:
            j["pelvis"].rotation_euler = (0.0, -weight_shift * 0.7, 0.0)
            j["pelvis"].keyframe_insert(data_path="rotation_euler", frame=f)

        j["torso"].rotation_euler = (torso_pitch, weight_shift, torso_yaw)
        j["torso"].keyframe_insert(data_path="rotation_euler", frame=f)

        j["head"].rotation_euler = (head_pitch, -weight_shift * 0.55, head_yaw)
        j["head"].keyframe_insert(data_path="rotation_euler", frame=f)

        # Secondary motion: cape lag/sway and living (non-frozen) wrists.
        cape = j.get("cape")
        if cape is not None:
            cape.rotation_euler = (
                0.045 + 0.035 * math.sin(t * 1.7 + bx * 1.3) + abs(torso_pitch) * 0.35,
                0.0,
                0.020 * math.sin(t * 1.15 + by),
            )
            cape.keyframe_insert(data_path="rotation_euler", frame=f)
        for hand_key, phase in (("hand_l", 0.0), ("hand_r", 1.7)):
            hand = j.get(hand_key)
            if hand is not None:
                hand.rotation_euler = (
                    -0.14 + 0.035 * math.sin(t * 2.0 + phase),
                    0.0,
                    0.05 * math.sin(t * 1.3 + phase),
                )
                hand.keyframe_insert(data_path="rotation_euler", frame=f)

        j["upper_arm_l"].rotation_euler = tuple(arm_l)
        j["upper_arm_r"].rotation_euler = tuple(arm_r)
        j["forearm_l"].rotation_euler = tuple(fore_l)
        j["forearm_r"].rotation_euler = tuple(fore_r)
        j["upper_arm_l"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["upper_arm_r"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["forearm_l"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["forearm_r"].keyframe_insert(data_path="rotation_euler", frame=f)

        j["thigh_l"].rotation_euler = (leg_l, 0.0, 0.0)
        j["thigh_r"].rotation_euler = (leg_r, 0.0, 0.0)
        j["shin_l"].rotation_euler = (shin_l, 0.0, 0.0)
        j["shin_r"].rotation_euler = (shin_r, 0.0, 0.0)
        j["thigh_l"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["thigh_r"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["shin_l"].keyframe_insert(data_path="rotation_euler", frame=f)
        j["shin_r"].keyframe_insert(data_path="rotation_euler", frame=f)
