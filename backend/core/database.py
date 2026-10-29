"""SQLite metadata storage for projects, characters, scenes, timeline, jobs, licenses, and models."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.core.config import get_settings

_DB_LOCK = threading.RLock()
_INITIALIZED_PATHS: set[Path] = set()

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    visual_style TEXT NOT NULL DEFAULT 'cinematic_3d',
    genre TEXT NOT NULL DEFAULT 'historical',
    historical_accuracy_mode INTEGER NOT NULL DEFAULT 0,
    target_duration_sec REAL NOT NULL DEFAULT 12.0,
    aspect_ratio TEXT NOT NULL DEFAULT '16:9',
    resolution TEXT NOT NULL DEFAULT '720p',
    fps INTEGER NOT NULL DEFAULT 24,
    quality_profile TEXT NOT NULL DEFAULT 'low_resource',
    num_scenes_target INTEGER NOT NULL DEFAULT 3,
    script_text TEXT NOT NULL DEFAULT '',
    narration_prefs_json TEXT NOT NULL DEFAULT '{}',
    dialogue_prefs_json TEXT NOT NULL DEFAULT '{}',
    music_prefs_json TEXT NOT NULL DEFAULT '{}',
    analysis_json TEXT NOT NULL DEFAULT '{}',
    export_status TEXT NOT NULL DEFAULT 'draft',
    latest_export_path TEXT NOT NULL DEFAULT '',
    render_report_json TEXT NOT NULL DEFAULT '{}',
    save_status TEXT NOT NULL DEFAULT 'saved',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'protagonist',
    appearance_description TEXT NOT NULL DEFAULT '',
    face_reference_path TEXT NOT NULL DEFAULT '',
    hair_style TEXT NOT NULL DEFAULT 'short_dark',
    hair_color TEXT NOT NULL DEFAULT '#241c18',
    skin_tone TEXT NOT NULL DEFAULT '#c9936b',
    outfit_preset TEXT NOT NULL DEFAULT 'historical_armor',
    outfits_json TEXT NOT NULL DEFAULT '[]',
    active_outfit TEXT NOT NULL DEFAULT 'historical_armor',
    body_proportions_json TEXT NOT NULL DEFAULT '{}',
    color_palette_json TEXT NOT NULL DEFAULT '[]',
    personality TEXT NOT NULL DEFAULT '',
    default_voice_id TEXT NOT NULL DEFAULT 'en_male_heroic',
    language TEXT NOT NULL DEFAULT 'en',
    rig_type TEXT NOT NULL DEFAULT 'sidd_humanoid_rig_v1',
    animations_json TEXT NOT NULL DEFAULT '{}',
    expressions_json TEXT NOT NULL DEFAULT '{}',
    props_json TEXT NOT NULL DEFAULT '[]',
    approved INTEGER NOT NULL DEFAULT 0,
    preview_image_path TEXT NOT NULL DEFAULT '',
    identity_seed INTEGER NOT NULL DEFAULT 101,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    location_name TEXT NOT NULL DEFAULT '',
    environment_preset TEXT NOT NULL DEFAULT 'fortress',
    time_of_day TEXT NOT NULL DEFAULT 'sunset',
    weather TEXT NOT NULL DEFAULT 'clear',
    lighting_style TEXT NOT NULL DEFAULT 'dramatic_warm',
    camera_shot TEXT NOT NULL DEFAULT 'wide',
    camera_movement TEXT NOT NULL DEFAULT 'slow_push_in',
    duration_sec REAL NOT NULL DEFAULT 4.0,
    transition_type TEXT NOT NULL DEFAULT 'crossfade',
    characters_present_json TEXT NOT NULL DEFAULT '[]',
    character_positions_json TEXT NOT NULL DEFAULT '[]',
    actions_json TEXT NOT NULL DEFAULT '[]',
    combat_choreography_json TEXT NOT NULL DEFAULT '{}',
    props_json TEXT NOT NULL DEFAULT '[]',
    narration_text TEXT NOT NULL DEFAULT '',
    narration_voice_id TEXT NOT NULL DEFAULT 'en_narrator_deep',
    dialogue_json TEXT NOT NULL DEFAULT '[]',
    audio_cues_json TEXT NOT NULL DEFAULT '{}',
    historical_notes_json TEXT NOT NULL DEFAULT '{}',
    generation_status TEXT NOT NULL DEFAULT 'pending',
    thumbnail_path TEXT NOT NULL DEFAULT '',
    rendered_video_path TEXT NOT NULL DEFAULT '',
    audio_mix_path TEXT NOT NULL DEFAULT '',
    subtitle_path TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    render_metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    current_stage TEXT NOT NULL DEFAULT 'queued',
    progress_pct REAL,
    progress_measurable INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    output_paths_json TEXT NOT NULL DEFAULT '{}',
    logs_json TEXT NOT NULL DEFAULT '[]',
    error_details TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    worker_pid INTEGER,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_provenance (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    asset_name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0',
    license_spdx TEXT NOT NULL,
    attribution_required INTEGER NOT NULL DEFAULT 0,
    commercial_allowed INTEGER NOT NULL DEFAULT 1,
    redistribution_allowed INTEGER NOT NULL DEFAULT 1,
    uncertain_rights INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry_state (
    model_id TEXT PRIMARY KEY,
    installed INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 0,
    install_path TEXT NOT NULL DEFAULT '',
    verified_sha256 TEXT NOT NULL DEFAULT '',
    last_verified_at TEXT NOT NULL DEFAULT '',
    user_consented INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id, scene_index);
CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_provenance_project ON asset_provenance(project_id);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_database(db_path: Path | None = None) -> Path:
    target = (db_path or get_settings().db_file).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK:
        conn = sqlite3.connect(str(target), timeout=30.0, check_same_thread=False)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            _INITIALIZED_PATHS.add(target)
        finally:
            conn.close()
    return target


@contextmanager
def get_db(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = (db_path or get_settings().db_file).resolve()
    if target not in _INITIALIZED_PATHS or not target.exists():
        init_database(target)
    conn = sqlite3.connect(str(target), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
