"""End-to-end pipeline test: Script -> Storyboard -> Blender 3D Animated Scenes -> Local TTS + Foley -> Verified MP4."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from render_engine.validator import validate_exported_mp4


@pytest.mark.e2e
def test_end_to_end_script_to_verified_3d_mp4(api_client: TestClient) -> None:
    script = (
        "SCENE 1: EXT. ANCIENT FORTRESS - SUNSET\n"
        "TARIQ: (determined) Look to the desert horizon, Zara!\n"
        "ZARA: (calm) The watchtowers stand ready, Commander.\n\n"
        "SCENE 2: EXT. BATTLEFIELD - NIGHT\n"
        "Tariq clashes swords with Zara in a swift training duel.\n"
        "TARIQ: (determined) Guard your left flank!"
    )

    resp = api_client.post(
        "/api/projects",
        json={
            "title": "E2E Crimson Bastion",
            "language": "en",
            "genre": "historical",
            "target_duration_sec": 5.0,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "fps": 24,
            "quality_profile": "low_resource",
            "num_scenes_target": 2,
            "script_text": script,
            "auto_generate_storyboard": True,
        },
    )
    assert resp.status_code == 200
    project = resp.json()
    project_id = project["id"]
    assert len(project["scenes"]) == 2

    # Trigger full project 3D render job
    render_resp = api_client.post("/api/jobs/render-project", json={"project_id": project_id})
    assert render_resp.status_code == 200
    job_id = render_resp.json()["job"]["id"]

    deadline = time.time() + 180.0
    job = api_client.get(f"/api/jobs/{job_id}").json()
    while job["status"] in {"queued", "running"} and time.time() < deadline:
        time.sleep(0.5)
        job = api_client.get(f"/api/jobs/{job_id}").json()

    assert job["status"] == "completed", f"Render job failed: {job.get('error_details')} | logs={job.get('logs')}"

    updated_proj = api_client.get(f"/api/projects/{project_id}").json()
    assert updated_proj["export_status"] == "completed"
    final_mp4 = Path(updated_proj["latest_export_path"])
    assert final_mp4.is_file()

    # Decode and verify streams independently
    verification = validate_exported_mp4(final_mp4, expect_audio=True, expected_width=1280, expected_height=720)
    assert verification["valid"] is True, f"MP4 decode validation errors: {verification['errors']}"
    assert verification["video_codec"] == "h264"
    assert verification["audio_codec"] == "aac"
    assert verification["duration_sec"] >= 3.0
    assert verification["decoded_video_frames_checked"] >= 10

    # Confirm video appears in Video Library and streams bytes
    lib = api_client.get("/api/library").json()["videos"]
    assert len(lib) == 1
    stream_resp = api_client.get(lib[0]["video_url"])
    assert stream_resp.status_code == 200
    assert len(stream_resp.content) > 15_000
