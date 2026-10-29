"""Tests for REST API routes, media path protection, and WebSocket job updates."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_api_routes_and_websocket(api_client: TestClient) -> None:
    health = api_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["app"] == "SIDD AI VIDEO STUDIO"

    hw = api_client.get("/api/system/hardware")
    assert hw.status_code == 200
    assert "cpu" in hw.json()
    assert hw.json()["dependencies"]["blender_bpy"]["installed"] is True

    # Create project & generate storyboard via API
    samples = api_client.get("/api/projects/samples").json()["samples"]
    roman_script = samples["roman_ur_adventure"]["script"]

    created = api_client.post(
        "/api/projects",
        json={
            "title": "Roman Urdu API Story",
            "language": "roman_ur",
            "script_text": roman_script,
            "auto_generate_storyboard": True,
        },
    )
    assert created.status_code == 200
    proj = created.json()
    assert len(proj["scenes"]) == 3
    assert len(proj["characters"]) >= 2

    # Voice synthesis preview API
    vp = api_client.post(
        "/api/voices/preview",
        json={
            "text": "Hum taiyar hain Sardar!",
            "voice_id": "ur_male_heroic",
            "language": "roman_ur",
        },
    )
    assert vp.status_code == 200
    audio_url = vp.json()["audio_url"]
    audio_resp = api_client.get(audio_url)
    assert audio_resp.status_code == 200
    assert audio_resp.content[:4] == b"RIFF"

    # Media endpoint must block both normalized and URL-encoded traversal attempts
    blocked = api_client.get(f"/api/media/project/{proj['id']}/../../etc/passwd")
    assert blocked.status_code in {400, 403, 404}
    blocked_encoded = api_client.get(f"/api/media/project/{proj['id']}/%2e%2e/%2e%2e/etc/passwd")
    assert blocked_encoded.status_code in {400, 403, 404}

    # License report endpoint
    lic = api_client.get(f"/api/projects/{proj['id']}/license-report")
    assert lic.status_code == 200
    assert len(lic.json()["core_software_stack"]) >= 4

    # WebSocket live connection
    with api_client.websocket_connect("/ws/jobs") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "initial_jobs"
