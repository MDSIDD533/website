"""Project persistence, script-to-storyboard orchestration, timeline editing, and manifest reopening."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from animation_engine.choreography import resolve_collision_free_positions
from backend.core.database import dumps_json, get_db, loads_json, utc_now_iso
from backend.core.security import sanitize_story_text, validate_identifier
from backend.services.hardware_service import evaluate_workload_warnings
from backend.services.license_service import record_asset_provenance
from character_engine.profiles import create_character, list_characters
from project_storage.manager import (
    delete_project_files,
    get_project_dir,
    write_project_manifest,
)
from story_engine.parser import analyze_script
from story_engine.storyboard import build_storyboard_scenes


def _row_to_scene(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "scene_index": int(row["scene_index"]),
        "title": row["title"],
        "summary": row["summary"],
        "location_name": row["location_name"],
        "environment_preset": row["environment_preset"],
        "time_of_day": row["time_of_day"],
        "weather": row["weather"],
        "lighting_style": row["lighting_style"],
        "camera_shot": row["camera_shot"],
        "camera_movement": row["camera_movement"],
        "duration_sec": float(row["duration_sec"]),
        "transition_type": row["transition_type"],
        "characters_present": loads_json(row["characters_present_json"], []),
        "character_positions": loads_json(row["character_positions_json"], []),
        "actions": loads_json(row["actions_json"], []),
        "combat_choreography": loads_json(row["combat_choreography_json"], {}),
        "props": loads_json(row["props_json"], []),
        "narration_text": row["narration_text"],
        "narration_voice_id": row["narration_voice_id"],
        "dialogue": loads_json(row["dialogue_json"], []),
        "audio_cues": loads_json(row["audio_cues_json"], {}),
        "historical_notes": loads_json(row["historical_notes_json"], {}),
        "generation_status": row["generation_status"],
        "thumbnail_path": row["thumbnail_path"],
        "rendered_video_path": row["rendered_video_path"],
        "audio_mix_path": row["audio_mix_path"],
        "subtitle_path": row["subtitle_path"],
        "error_message": row["error_message"],
        "render_metrics": loads_json(row["render_metrics_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_project(row: Any, include_details: bool = True) -> dict[str, Any]:
    proj = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "language": row["language"],
        "visual_style": row["visual_style"],
        "genre": row["genre"],
        "historical_accuracy_mode": bool(row["historical_accuracy_mode"]),
        "target_duration_sec": float(row["target_duration_sec"]),
        "aspect_ratio": row["aspect_ratio"],
        "resolution": row["resolution"],
        "fps": int(row["fps"]),
        "quality_profile": row["quality_profile"],
        "num_scenes_target": int(row["num_scenes_target"]),
        "script_text": row["script_text"],
        "narration_prefs": loads_json(
            row["narration_prefs_json"],
            {"enabled": True, "voice_id": "en_narrator_deep"},
        ),
        "dialogue_prefs": loads_json(
            row["dialogue_prefs_json"],
            {"enabled": True, "subtitles": True, "burn_in_captions": True},
        ),
        "music_prefs": loads_json(
            row["music_prefs_json"],
            {"enabled": True, "mood": "epic_historical", "volume": 0.24},
        ),
        "analysis": loads_json(row["analysis_json"], {}),
        "export_status": row["export_status"],
        "latest_export_path": row["latest_export_path"],
        "render_report": loads_json(row["render_report_json"], {}),
        "save_status": row["save_status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_details:
        proj["scenes"] = list_project_scenes(proj["id"])
        proj["characters"] = list_characters(proj["id"])
        proj["workload_warnings"] = evaluate_workload_warnings(
            resolution=proj["resolution"],
            fps=proj["fps"],
            duration_sec=sum(s["duration_sec"] for s in proj["scenes"]) or proj["target_duration_sec"],
            quality_profile=proj["quality_profile"],
        )
    return proj


def sync_project_manifest(project_id: str) -> Path:
    proj = get_project(project_id, include_details=True)
    return write_project_manifest(project_id, proj)


def list_projects() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    items = []
    for r in rows:
        p = _row_to_project(r, include_details=False)
        with get_db() as conn:
            sc_count = conn.execute("SELECT COUNT(*) AS c FROM scenes WHERE project_id = ?", (p["id"],)).fetchone()["c"]
            done_count = conn.execute(
                "SELECT COUNT(*) AS c FROM scenes WHERE project_id = ? AND generation_status = 'completed'",
                (p["id"],),
            ).fetchone()["c"]
            thumb_row = conn.execute(
                "SELECT thumbnail_path FROM scenes WHERE project_id = ? AND thumbnail_path != '' ORDER BY scene_index ASC LIMIT 1",
                (p["id"],),
            ).fetchone()
        p["scene_count"] = int(sc_count)
        p["rendered_scene_count"] = int(done_count)
        p["cover_thumbnail_path"] = thumb_row["thumbnail_path"] if thumb_row else ""
        items.append(p)
    return items


def get_project(project_id: str, include_details: bool = True) -> dict[str, Any]:
    validate_identifier(project_id, "project_id")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise KeyError(f"Project '{project_id}' not found.")
    return _row_to_project(row, include_details=include_details)


def list_project_scenes(project_id: str) -> list[dict[str, Any]]:
    validate_identifier(project_id, "project_id")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_index ASC",
            (project_id,),
        ).fetchall()
    return [_row_to_scene(r) for r in rows]


def get_scene(scene_id: str) -> dict[str, Any]:
    validate_identifier(scene_id, "scene_id")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
    if not row:
        raise KeyError(f"Scene '{scene_id}' not found.")
    return _row_to_scene(row)


def create_project(data: dict[str, Any]) -> dict[str, Any]:
    proj_id = data.get("id") or f"prj_{uuid.uuid4().hex[:10]}"
    validate_identifier(proj_id, "project_id")
    now = utc_now_iso()

    title = (data.get("title") or "Untitled Cinematic Story").strip()[:140]
    script_text = sanitize_story_text(data.get("script_text") or "")
    raw_lang = (data.get("language") or "auto").strip()
    if script_text.strip():
        from story_engine.normalizer import detect_script_language

        detected = detect_script_language(script_text)
        if raw_lang in {"auto", "", "mixed"} or (raw_lang == "en" and detected in {"ur", "roman_ur"}):
            language = detected
        else:
            language = raw_lang
    else:
        language = "en" if raw_lang in {"auto", "", "mixed"} else raw_lang

    narr_default_voice = "ur_narrator_deep" if language in {"ur", "roman_ur"} else "en_narrator_deep"

    narration_prefs = dict(data.get("narration_prefs") or {"enabled": True, "voice_id": narr_default_voice})
    if raw_lang in {"auto", "", "mixed"} and narration_prefs.get("voice_id") == "en_narrator_deep" and language in {"ur", "roman_ur"}:
        narration_prefs["voice_id"] = "ur_narrator_deep"
    dialogue_prefs = data.get("dialogue_prefs") or {"enabled": True, "subtitles": True, "burn_in_captions": True}
    music_prefs = data.get("music_prefs") or {"enabled": True, "mood": "epic_historical", "volume": 0.24}

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, title, description, language, visual_style, genre,
                historical_accuracy_mode, target_duration_sec, aspect_ratio,
                resolution, fps, quality_profile, num_scenes_target,
                script_text, narration_prefs_json, dialogue_prefs_json,
                music_prefs_json, analysis_json, export_status,
                latest_export_path, render_report_json, save_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'draft', '', '{}', 'saved', ?, ?)
            """,
            (
                proj_id,
                title,
                (data.get("description") or "").strip(),
                language,
                data.get("visual_style", "cinematic_3d"),
                data.get("genre", "historical"),
                int(bool(data.get("historical_accuracy_mode", False))),
                float(data.get("target_duration_sec", 10.0)),
                data.get("aspect_ratio", "16:9"),
                data.get("resolution", "720p"),
                int(data.get("fps", 24)),
                data.get("quality_profile", "low_resource"),
                int(data.get("num_scenes_target", 3)),
                script_text,
                dumps_json(narration_prefs),
                dumps_json(dialogue_prefs),
                dumps_json(music_prefs),
                now,
                now,
            ),
        )

    get_project_dir(proj_id, create=True)
    record_asset_provenance(
        project_id=proj_id,
        asset_name=f"User Script — {title}",
        asset_type="script",
        source_kind="user_authored",
        license_spdx="User-Authored-Original",
        notes="User-provided story script stored strictly locally.",
    )
    record_asset_provenance(
        project_id=proj_id,
        asset_name="SIDD Procedural 3D Environments, Humanoid Rigs & Audio Score",
        asset_type="3d_and_audio_procedural",
        source_kind="procedural_local",
        license_spdx="MIT",
        notes="Generated mathematically via Blender Python API & SciPy DSP.",
    )

    if script_text.strip() and data.get("auto_generate_storyboard", False):
        generate_project_storyboard(proj_id)
    else:
        sync_project_manifest(proj_id)

    return get_project(proj_id, include_details=True)


def update_project(project_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    existing = get_project(project_id, include_details=False)
    merged = {**existing, **patch}
    if "script_text" in patch:
        merged["script_text"] = sanitize_story_text(patch["script_text"])
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """
            UPDATE projects SET
                title=?, description=?, language=?, visual_style=?, genre=?,
                historical_accuracy_mode=?, target_duration_sec=?, aspect_ratio=?,
                resolution=?, fps=?, quality_profile=?, num_scenes_target=?,
                script_text=?, narration_prefs_json=?, dialogue_prefs_json=?,
                music_prefs_json=?, export_status=?, latest_export_path=?,
                render_report_json=?, save_status='saved', updated_at=?
            WHERE id=?
            """,
            (
                merged["title"],
                merged["description"],
                merged["language"],
                merged["visual_style"],
                merged["genre"],
                int(bool(merged["historical_accuracy_mode"])),
                float(merged["target_duration_sec"]),
                merged["aspect_ratio"],
                merged["resolution"],
                int(merged["fps"]),
                merged["quality_profile"],
                int(merged["num_scenes_target"]),
                merged["script_text"],
                dumps_json(merged["narration_prefs"]),
                dumps_json(merged["dialogue_prefs"]),
                dumps_json(merged["music_prefs"]),
                merged["export_status"],
                merged["latest_export_path"],
                dumps_json(merged["render_report"]),
                now,
                project_id,
            ),
        )
    sync_project_manifest(project_id)
    return get_project(project_id, include_details=True)


def generate_project_storyboard(project_id: str, script_override: str | None = None) -> dict[str, Any]:
    proj = get_project(project_id, include_details=True)
    script_text = sanitize_story_text(script_override if script_override is not None else proj["script_text"])
    if not script_text.strip():
        raise ValueError("Paste or write a script before generating a storyboard.")

    analysis = analyze_script(
        script_text,
        language=proj["language"],
        target_scenes=proj["num_scenes_target"],
        genre=proj["genre"],
        historical_accuracy_mode=proj["historical_accuracy_mode"],
    )

    # Ensure persistent character profiles exist without overwriting user-customized characters
    existing_chars = {c["name"].lower(): c for c in list_characters(project_id)}
    for c_spec in analysis["characters"]:
        key = c_spec["name"].lower()
        if key not in existing_chars:
            created = create_character({**c_spec, "project_id": project_id})
            existing_chars[key] = created
        else:
            # Keep user's custom voice/outfit on analysis dict so storyboard inherits persistent character settings
            c_spec["default_voice_id"] = existing_chars[key]["default_voice_id"]

    scenes_data = build_storyboard_scenes(
        project_id,
        analysis,
        target_duration_sec=proj["target_duration_sec"],
        narration_enabled=bool(proj["narration_prefs"].get("enabled", True)),
        narrator_voice_id=proj["narration_prefs"].get("voice_id"),
        music_mood=proj["music_prefs"].get("mood", "epic_historical"),
    )

    now = utc_now_iso()
    with get_db() as conn:
        conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
        for sc in scenes_data:
            conn.execute(
                """
                INSERT INTO scenes (
                    id, project_id, scene_index, title, summary, location_name,
                    environment_preset, time_of_day, weather, lighting_style,
                    camera_shot, camera_movement, duration_sec, transition_type,
                    characters_present_json, character_positions_json, actions_json,
                    combat_choreography_json, props_json, narration_text,
                    narration_voice_id, dialogue_json, audio_cues_json,
                    historical_notes_json, generation_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    sc["id"],
                    project_id,
                    sc["scene_index"],
                    sc["title"],
                    sc["summary"],
                    sc["location_name"],
                    sc["environment_preset"],
                    sc["time_of_day"],
                    sc["weather"],
                    sc["lighting_style"],
                    sc["camera_shot"],
                    sc["camera_movement"],
                    sc["duration_sec"],
                    sc["transition_type"],
                    dumps_json(sc["characters_present"]),
                    dumps_json(sc["character_positions"]),
                    dumps_json(sc["actions"]),
                    dumps_json(sc["combat_choreography"]),
                    dumps_json(sc["props"]),
                    sc["narration_text"],
                    sc["narration_voice_id"],
                    dumps_json(sc["dialogue"]),
                    dumps_json(sc["audio_cues"]),
                    dumps_json(sc["historical_notes"]),
                    now,
                    now,
                ),
            )
        conn.execute(
            """
            UPDATE projects SET
                script_text=?, language=?, analysis_json=?, export_status='storyboard_ready',
                save_status='saved', updated_at=?
            WHERE id=?
            """,
            (
                script_text,
                analysis["effective_language"],
                dumps_json(analysis),
                now,
                project_id,
            ),
        )

    sync_project_manifest(project_id)
    return get_project(project_id, include_details=True)


def update_scene(scene_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    existing = get_scene(scene_id)
    merged = {**existing, **patch}
    if "character_positions" in patch and isinstance(patch["character_positions"], list):
        merged["character_positions"] = resolve_collision_free_positions(patch["character_positions"])
    merged["duration_sec"] = max(1.0, min(60.0, float(merged["duration_sec"])))

    # Mark modified scene dirty if creative fields changed and caller didn't explicitly set generation_status
    creative_fields = {
        "environment_preset", "time_of_day", "weather", "camera_shot", "camera_movement",
        "duration_sec", "actions", "character_positions", "combat_choreography",
        "narration_text", "narration_voice_id", "dialogue", "audio_cues",
    }
    if "generation_status" not in patch and any(k in patch for k in creative_fields):
        if existing["generation_status"] == "completed":
            merged["generation_status"] = "modified"

    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE scenes SET
                scene_index=?, title=?, summary=?, location_name=?,
                environment_preset=?, time_of_day=?, weather=?, lighting_style=?,
                camera_shot=?, camera_movement=?, duration_sec=?, transition_type=?,
                characters_present_json=?, character_positions_json=?, actions_json=?,
                combat_choreography_json=?, props_json=?, narration_text=?,
                narration_voice_id=?, dialogue_json=?, audio_cues_json=?,
                generation_status=?, thumbnail_path=?, rendered_video_path=?,
                audio_mix_path=?, subtitle_path=?, error_message=?,
                render_metrics_json=?, updated_at=?
            WHERE id=?
            """,
            (
                int(merged["scene_index"]),
                merged["title"],
                merged["summary"],
                merged["location_name"],
                merged["environment_preset"],
                merged["time_of_day"],
                merged["weather"],
                merged["lighting_style"],
                merged["camera_shot"],
                merged["camera_movement"],
                float(merged["duration_sec"]),
                merged["transition_type"],
                dumps_json(merged["characters_present"]),
                dumps_json(merged["character_positions"]),
                dumps_json(merged["actions"]),
                dumps_json(merged["combat_choreography"]),
                dumps_json(merged["props"]),
                merged["narration_text"],
                merged["narration_voice_id"],
                dumps_json(merged["dialogue"]),
                dumps_json(merged["audio_cues"]),
                merged["generation_status"],
                merged["thumbnail_path"],
                merged["rendered_video_path"],
                merged["audio_mix_path"],
                merged["subtitle_path"],
                merged["error_message"],
                dumps_json(merged["render_metrics"]),
                now,
                scene_id,
            ),
        )
        conn.execute("UPDATE projects SET save_status='saved', updated_at=? WHERE id=?", (now, existing["project_id"]))

    sync_project_manifest(existing["project_id"])
    return get_scene(scene_id)


def reorder_project_scenes(project_id: str, ordered_scene_ids: list[str]) -> list[dict[str, Any]]:
    current = list_project_scenes(project_id)
    current_ids = {s["id"] for s in current}
    if set(ordered_scene_ids) != current_ids or len(ordered_scene_ids) != len(current):
        raise ValueError("ordered_scene_ids must contain the exact set of scene IDs belonging to the project.")

    now = utc_now_iso()
    with get_db() as conn:
        for idx, sid in enumerate(ordered_scene_ids):
            conn.execute(
                "UPDATE scenes SET scene_index=?, updated_at=? WHERE id=? AND project_id=?",
                (idx, now, sid, project_id),
            )
        conn.execute("UPDATE projects SET save_status='saved', updated_at=? WHERE id=?", (now, project_id))

    sync_project_manifest(project_id)
    return list_project_scenes(project_id)


def reopen_project_from_manifest(manifest_file: Path) -> dict[str, Any]:
    """Import/reopen a saved project manifest JSON into SQLite."""
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    proj_id = validate_identifier(data["id"], "project_id")
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (proj_id,)).fetchone()
    if exists:
        return get_project(proj_id, include_details=True)

    created = create_project({**data, "auto_generate_storyboard": False})
    now = utc_now_iso()
    with get_db() as conn:
        for sc in data.get("scenes", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO scenes (
                    id, project_id, scene_index, title, summary, location_name,
                    environment_preset, time_of_day, weather, lighting_style,
                    camera_shot, camera_movement, duration_sec, transition_type,
                    characters_present_json, character_positions_json, actions_json,
                    combat_choreography_json, props_json, narration_text,
                    narration_voice_id, dialogue_json, audio_cues_json,
                    historical_notes_json, generation_status, thumbnail_path,
                    rendered_video_path, audio_mix_path, subtitle_path,
                    error_message, render_metrics_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sc["id"],
                    proj_id,
                    sc["scene_index"],
                    sc["title"],
                    sc.get("summary", ""),
                    sc.get("location_name", ""),
                    sc.get("environment_preset", "fortress"),
                    sc.get("time_of_day", "sunset"),
                    sc.get("weather", "clear"),
                    sc.get("lighting_style", "dramatic_warm"),
                    sc.get("camera_shot", "wide"),
                    sc.get("camera_movement", "slow_push_in"),
                    float(sc.get("duration_sec", 3.5)),
                    sc.get("transition_type", "crossfade"),
                    dumps_json(sc.get("characters_present", [])),
                    dumps_json(sc.get("character_positions", [])),
                    dumps_json(sc.get("actions", [])),
                    dumps_json(sc.get("combat_choreography", {})),
                    dumps_json(sc.get("props", [])),
                    sc.get("narration_text", ""),
                    sc.get("narration_voice_id", "en_narrator_deep"),
                    dumps_json(sc.get("dialogue", [])),
                    dumps_json(sc.get("audio_cues", {})),
                    dumps_json(sc.get("historical_notes", {})),
                    sc.get("generation_status", "pending"),
                    sc.get("thumbnail_path", ""),
                    sc.get("rendered_video_path", ""),
                    sc.get("audio_mix_path", ""),
                    sc.get("subtitle_path", ""),
                    sc.get("error_message", ""),
                    dumps_json(sc.get("render_metrics", {})),
                    sc.get("created_at", now),
                    now,
                ),
            )
    return get_project(created["id"], include_details=True)


def delete_project_completely(project_id: str, confirm_token: str) -> dict[str, Any]:
    file_res = delete_project_files(project_id, confirm_token=confirm_token)
    with get_db() as conn:
        conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM asset_provenance WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return file_res
