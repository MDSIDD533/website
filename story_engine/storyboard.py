"""Storyboard planner converting structured script analysis into editable 3D scenes."""

from __future__ import annotations

import uuid
from typing import Any

from animation_engine.choreography import plan_scene_choreography

SHOT_SEQUENCE = [
    ("establishing", "slow_push_in"),
    ("medium", "orbit_subtle"),
    ("over_the_shoulder", "dolly_track"),
    ("wide", "pan_across"),
    ("close_up", "slow_push_in"),
]

COMBAT_SHOT = ("action", "dynamic_combat_track")

LIGHTING_BY_TIME = {
    "sunrise": "golden_sunrise",
    "day": "natural_daylight",
    "sunset": "dramatic_warm",
    "night": "moonlit_torches",
}


def build_storyboard_scenes(
    project_id: str,
    analysis: dict[str, Any],
    *,
    target_duration_sec: float = 12.0,
    narration_enabled: bool = True,
    narrator_voice_id: str | None = None,
    music_mood: str = "epic_historical",
) -> list[dict[str, Any]]:
    blocks = analysis.get("scene_blocks", [])
    if not blocks:
        return []

    lang = analysis.get("effective_language", "en")
    default_narrator = narrator_voice_id or (
        "ur_narrator_deep" if lang in {"ur", "roman_ur"} else "en_narrator_deep"
    )

    char_voice_lookup = {
        c["name"]: c["default_voice_id"]
        for c in analysis.get("characters", [])
    }

    per_scene_base = max(2.5, round(target_duration_sec / max(1, len(blocks)), 1))
    scenes: list[dict[str, Any]] = []

    for idx, blk in enumerate(blocks):
        scene_id = f"scn_{uuid.uuid4().hex[:10]}"
        actions: list[str] = list(blk.get("actions", ["walk"]))
        is_combat = any(
            a in actions for a in ("cinematic_combat", "punch", "kick", "dodge", "block")
        )

        if is_combat:
            cam_shot, cam_move = COMBAT_SHOT
        else:
            cam_shot, cam_move = SHOT_SEQUENCE[idx % len(SHOT_SEQUENCE)]

        chars_present: list[str] = list(blk.get("characters_present", []))
        choreo = plan_scene_choreography(
            characters_present=chars_present,
            actions=actions,
            is_combat=is_combat,
        )

        dialogue_items: list[dict[str, Any]] = []
        est_speech_words = 0
        for d in blk.get("dialogue", []):
            spk = d["speaker"]
            txt = d["text"]
            est_speech_words += len(txt.split())
            dialogue_items.append(
                {
                    "id": f"dlg_{uuid.uuid4().hex[:8]}",
                    "speaker": spk,
                    "voice_id": char_voice_lookup.get(spk, default_narrator),
                    "text": txt,
                    "emotion": d.get("emotion", "determined"),
                    "speed": 1.0,
                    "pitch": 1.0,
                    "pause_after_sec": d.get("pause_after_sec", 0.3),
                    "auto_synthesized": bool(d.get("auto_synthesized", False)),
                }
            )

        narration_text = blk.get("narration", "") if narration_enabled else ""
        if narration_text:
            est_speech_words += len(narration_text.split())

        # Estimate realistic duration from spoken words (~2.5 words/sec) bounded cleanly
        estimated_dur = max(per_scene_base, round(est_speech_words / 2.6 + 1.2, 1))
        duration_sec = min(14.0, max(2.5, estimated_dur))

        weather = blk.get("weather", "clear")
        env = blk.get("environment_preset", "fortress")
        audio_cues = {
            "ambience": env,
            "weather_sfx": weather if weather != "clear" else "wind_subtle",
            "footsteps": any(a in actions for a in ("walk", "run", "chase", "cinematic_combat")),
            "combat_sfx": is_combat,
            "music_mood": "tense_combat" if is_combat else music_mood,
            "music_volume": 0.24,
            "sfx_volume": 0.42,
            "dialogue_ducking": True,
        }

        scenes.append(
            {
                "id": scene_id,
                "project_id": project_id,
                "scene_index": idx,
                "title": blk.get("header") or f"Scene {idx + 1}",
                "summary": (narration_text or (dialogue_items[0]["text"] if dialogue_items else ""))[:180],
                "location_name": blk.get("location_name", env.replace("_", " ").title()),
                "environment_preset": env,
                "time_of_day": blk.get("time_of_day", "sunset"),
                "weather": weather,
                "lighting_style": LIGHTING_BY_TIME.get(blk.get("time_of_day", "sunset"), "dramatic_warm"),
                "camera_shot": cam_shot,
                "camera_movement": cam_move,
                "duration_sec": duration_sec,
                "transition_type": blk.get("transition", "crossfade"),
                "characters_present": chars_present,
                "character_positions": choreo["character_positions"],
                "actions": actions,
                "combat_choreography": choreo["combat_choreography"],
                "props": blk.get("props", []),
                "narration_text": narration_text,
                "narration_voice_id": default_narrator,
                "dialogue": dialogue_items,
                "audio_cues": audio_cues,
                "historical_notes": blk.get("historical_notes", {}),
                "generation_status": "pending",
            }
        )

    return scenes
