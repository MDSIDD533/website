"""Persistent Character Studio CRUD, outfit switching without identity drift, and approval state."""

from __future__ import annotations

import uuid
from typing import Any

from backend.core.database import dumps_json, get_db, loads_json, utc_now_iso
from backend.core.security import validate_identifier

OUTFIT_PRESETS: dict[str, dict[str, Any]] = {
    "historical_armor": {
        "id": "historical_armor",
        "label": "Crimson & Brass Citadel Armor",
        "primary": "#7c1d24",
        "secondary": "#c59b27",
        "trim": "#2c303a",
        "cape": True,
        "shoulder_pauldrons": True,
    },
    "royal_tunic": {
        "id": "royal_tunic",
        "label": "Embroidered Royal Tunic",
        "primary": "#1c4966",
        "secondary": "#d9b45b",
        "trim": "#eae6df",
        "cape": True,
        "shoulder_pauldrons": False,
    },
    "desert_nomad": {
        "id": "desert_nomad",
        "label": "Sandstone Desert Scarf & Coat",
        "primary": "#9c7448",
        "secondary": "#3b5249",
        "trim": "#d8c3a5",
        "cape": True,
        "shoulder_pauldrons": False,
    },
    "scholar_robe": {
        "id": "scholar_robe",
        "label": "Emerald Scholar Robe",
        "primary": "#26533b",
        "secondary": "#c7a265",
        "trim": "#1e2420",
        "cape": False,
        "shoulder_pauldrons": False,
    },
    "expedition_coat": {
        "id": "expedition_coat",
        "label": "Modern / Adventure Field Jacket",
        "primary": "#2f3e4e",
        "secondary": "#8c6239",
        "trim": "#cfd8dc",
        "cape": False,
        "shoulder_pauldrons": False,
    },
    "stealth_garb": {
        "id": "stealth_garb",
        "label": "Obsidian Night Guard Attire",
        "primary": "#23222b",
        "secondary": "#7d2c38",
        "trim": "#6c757d",
        "cape": True,
        "shoulder_pauldrons": True,
    },
}

DEFAULT_CHARACTER_ANIMATIONS = {
    "walking": "walk",
    "running": "run",
    "idle": "idle",
    "speaking": "speak",
    "fighting": ["cinematic_combat", "punch", "kick", "block", "dodge"],
}

DEFAULT_EXPRESSIONS = {
    "neutral": "Balanced brow, relaxed jaw",
    "determined": "Lowered inner brow, focused gaze",
    "angry": "Sharp brow furrow, tense jaw",
    "joyful": "Lifted brow arch, open warm smile",
    "sad": "Upward inner brow tilt, lowered gaze",
    "fearful": "Wide eyes, raised brows",
    "surprised": "High brow arch, open jaw",
}


def _row_to_character(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "role": row["role"],
        "appearance_description": row["appearance_description"],
        "face_reference_path": row["face_reference_path"],
        "hair_style": row["hair_style"],
        "hair_color": row["hair_color"],
        "skin_tone": row["skin_tone"],
        "outfit_preset": row["outfit_preset"],
        "outfits": loads_json(row["outfits_json"], [row["outfit_preset"]]),
        "active_outfit": row["active_outfit"] or row["outfit_preset"],
        "body_proportions": loads_json(
            row["body_proportions_json"],
            {"height_scale": 1.0, "shoulder_width": 1.0, "build": "athletic"},
        ),
        "color_palette": loads_json(row["color_palette_json"], ["#7c1d24", "#c59b27", "#2c303a"]),
        "personality": row["personality"],
        "default_voice_id": row["default_voice_id"],
        "language": row["language"],
        "rig_type": row["rig_type"],
        "animations": loads_json(row["animations_json"], DEFAULT_CHARACTER_ANIMATIONS),
        "expressions": loads_json(row["expressions_json"], DEFAULT_EXPRESSIONS),
        "props": loads_json(row["props_json"], []),
        "approved": bool(row["approved"]),
        "preview_image_path": row["preview_image_path"],
        "identity_seed": int(row["identity_seed"]),
        "consistency_method": "deterministic_3d_rig_v1 (exact mesh/bone/proportion lock across scenes; generative face texture conditioning not claimed)",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_characters(project_id: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM characters WHERE project_id = ? OR project_id IS NULL ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM characters ORDER BY created_at ASC").fetchall()
    return [_row_to_character(r) for r in rows]


def get_character(character_id: str) -> dict[str, Any]:
    validate_identifier(character_id, "character_id")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not row:
        raise KeyError(f"Character '{character_id}' not found.")
    return _row_to_character(row)


def create_character(data: dict[str, Any]) -> dict[str, Any]:
    char_id = data.get("id") or f"chr_{uuid.uuid4().hex[:10]}"
    validate_identifier(char_id, "character_id")
    now = utc_now_iso()
    outfit = data.get("outfit_preset", "historical_armor")
    if outfit not in OUTFIT_PRESETS:
        outfit = "historical_armor"
    preset_info = OUTFIT_PRESETS[outfit]
    outfits = data.get("outfits") or list({outfit, "royal_tunic", "desert_nomad"})
    palette = data.get("color_palette") or [
        preset_info["primary"],
        preset_info["secondary"],
        preset_info["trim"],
    ]
    proportions = data.get("body_proportions") or {
        "height_scale": 1.0,
        "shoulder_width": 1.04 if data.get("gender") != "female" else 0.94,
        "build": "athletic",
    }
    seed = int(data.get("identity_seed") or (sum(ord(c) for c in data.get("name", "Hero")) % 900 + 100))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO characters (
                id, project_id, name, role, appearance_description, face_reference_path,
                hair_style, hair_color, skin_tone, outfit_preset, outfits_json, active_outfit,
                body_proportions_json, color_palette_json, personality, default_voice_id,
                language, rig_type, animations_json, expressions_json, props_json,
                approved, preview_image_path, identity_seed, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                char_id,
                data.get("project_id"),
                (data.get("name") or "Unnamed Character").strip(),
                data.get("role", "protagonist"),
                data.get("appearance_description", "Expressive stylized-realistic 3D character"),
                data.get("face_reference_path", ""),
                data.get("hair_style", "short_dark"),
                data.get("hair_color", "#231b16"),
                data.get("skin_tone", "#c9936b"),
                outfit,
                dumps_json(outfits),
                data.get("active_outfit", outfit),
                dumps_json(proportions),
                dumps_json(palette),
                data.get("personality", "courageous, expressive"),
                data.get("default_voice_id", "en_male_heroic"),
                data.get("language", "en"),
                data.get("rig_type", "sidd_humanoid_rig_v1"),
                dumps_json(data.get("animations") or DEFAULT_CHARACTER_ANIMATIONS),
                dumps_json(data.get("expressions") or DEFAULT_EXPRESSIONS),
                dumps_json(data.get("props") or []),
                int(bool(data.get("approved", False))),
                data.get("preview_image_path", ""),
                seed,
                now,
                now,
            ),
        )
    return get_character(char_id)


def update_character(character_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    existing = get_character(character_id)
    merged = {**existing, **patch}
    # Preserve core identity seed unless explicitly reset so switching outfits never alters core identity
    merged["identity_seed"] = existing["identity_seed"]
    now = utc_now_iso()

    active_outfit = merged.get("active_outfit") or merged.get("outfit_preset") or "historical_armor"
    outfits_list = list(merged.get("outfits") or [])
    if active_outfit not in outfits_list:
        outfits_list.append(active_outfit)

    with get_db() as conn:
        conn.execute(
            """
            UPDATE characters SET
                name=?, role=?, appearance_description=?, face_reference_path=?,
                hair_style=?, hair_color=?, skin_tone=?, outfit_preset=?,
                outfits_json=?, active_outfit=?, body_proportions_json=?,
                color_palette_json=?, personality=?, default_voice_id=?,
                language=?, animations_json=?, expressions_json=?, props_json=?,
                approved=?, preview_image_path=?, updated_at=?
            WHERE id=?
            """,
            (
                merged["name"],
                merged["role"],
                merged["appearance_description"],
                merged["face_reference_path"],
                merged["hair_style"],
                merged["hair_color"],
                merged["skin_tone"],
                merged["outfit_preset"],
                dumps_json(outfits_list),
                active_outfit,
                dumps_json(merged["body_proportions"]),
                dumps_json(merged["color_palette"]),
                merged["personality"],
                merged["default_voice_id"],
                merged["language"],
                dumps_json(merged["animations"]),
                dumps_json(merged["expressions"]),
                dumps_json(merged["props"]),
                int(bool(merged["approved"])),
                merged["preview_image_path"],
                now,
                character_id,
            ),
        )
    return get_character(character_id)


def delete_character(character_id: str) -> dict[str, Any]:
    validate_identifier(character_id, "character_id")
    with get_db() as conn:
        conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
    return {"deleted": True, "id": character_id}
