"""Tests for scene timeline ordering, collision-aware choreography, job queue recovery, and failure honesty."""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

from animation_engine.choreography import (
    MIN_CHARACTER_SEPARATION_M,
    resolve_collision_free_positions,
)
from backend.core.database import get_db, utc_now_iso
from backend.services.job_manager import JobManager
from backend.services.project_service import (
    create_project,
    generate_project_storyboard,
    reopen_project_from_manifest,
    reorder_project_scenes,
)
from render_engine.validator import validate_exported_mp4
from story_engine.normalizer import SAMPLE_SCRIPTS


def test_collision_aware_choreography_separation() -> None:
    overlapping = [
        {"character_name": "Tariq", "x": 0.0, "y": 0.0, "z": 0.0},
        {"character_name": "Kael", "x": 0.05, "y": 0.02, "z": 0.0},
        {"character_name": "Zara", "x": 0.03, "y": -0.01, "z": 0.0},
    ]
    resolved = resolve_collision_free_positions(overlapping)
    for i in range(len(resolved)):
        for j in range(i + 1, len(resolved)):
            dist = math.hypot(resolved[j]["x"] - resolved[i]["x"], resolved[j]["y"] - resolved[i]["y"])
            assert dist >= MIN_CHARACTER_SEPARATION_M - 0.02


def test_timeline_reordering_and_project_save_reopen(isolated_workspace: Path) -> None:
    proj = create_project(
        {
            "title": "Timeline Test Story",
            "script_text": SAMPLE_SCRIPTS["en_historical_fortress"]["script"],
            "auto_generate_storyboard": True,
        }
    )
    orig_ids = [s["id"] for s in proj["scenes"]]
    assert len(orig_ids) == 3

    reversed_ids = list(reversed(orig_ids))
    reordered = reorder_project_scenes(proj["id"], reversed_ids)
    assert [s["id"] for s in reordered] == reversed_ids
    assert [s["scene_index"] for s in reordered] == [0, 1, 2]

    with pytest.raises(ValueError):
        reorder_project_scenes(proj["id"], orig_ids[:1])

    manifest_path = isolated_workspace / "projects" / proj["id"] / "project_manifest.json"
    assert manifest_path.is_file()
    reopened = reopen_project_from_manifest(manifest_path)
    assert reopened["id"] == proj["id"]
    assert [s["id"] for s in reopened["scenes"]] == reversed_ids


def test_validator_never_fakes_corrupt_or_missing_mp4(isolated_workspace: Path) -> None:
    missing = validate_exported_mp4(isolated_workspace / "does_not_exist.mp4")
    assert missing["valid"] is False
    assert missing["errors"]

    fake_file = isolated_workspace / "corrupt.mp4"
    fake_file.write_bytes(b"NOT_A_REAL_MP4" * 200)
    corrupt = validate_exported_mp4(fake_file)
    assert corrupt["valid"] is False
    assert corrupt["errors"]


def test_job_queue_failure_honesty_and_orphan_recovery(isolated_workspace: Path) -> None:
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, project_id, job_type, status, current_stage,
                progress_measurable, payload_json, output_paths_json,
                logs_json, error_details, retry_count, created_at, updated_at
            ) VALUES ('job_orphan01', NULL, 'render_scene', 'running', 'rendering', 0, '{}', '{}', '[]', '', 0, ?, ?)
            """,
            (now, now),
        )

    jm = JobManager()
    recovered_count = jm.recover_orphaned_jobs()
    assert recovered_count == 1
    assert jm.get_job("job_orphan01")["status"] == "interrupted"

    # Enqueue an intentionally invalid scene job and confirm it transitions honestly to 'failed', never 'completed'
    bad_job = jm.enqueue_job("render_scene", project_id="prj_nonexistent", payload={"project_id": "prj_nonexistent", "scene_id": "scn_missing"})
    deadline = time.time() + 8.0
    final_state = jm.get_job(bad_job["id"])
    while final_state["status"] in {"queued", "running"} and time.time() < deadline:
        time.sleep(0.1)
        final_state = jm.get_job(bad_job["id"])

    assert final_state["status"] == "failed"
    assert final_state["error_details"] != ""
