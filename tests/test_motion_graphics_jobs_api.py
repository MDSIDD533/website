import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def _wait_for_job(client: TestClient, job_id: str, timeout_sec: float = 10.0):
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish; last state={last}")


def test_motion_graphics_template_catalog(api_client: TestClient) -> None:
    response = api_client.get("/api/jobs/motion-graphics/templates")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert [item["id"] for item in templates] == [
        "title",
        "data",
        "shape",
        "quote",
        "outro",
    ]
    quote = next(item for item in templates if item["id"] == "quote")
    assert quote["default_request"]["speaker_name"] == "Bilal"
    assert quote["default_variables"]["response_line"].startswith("If every word")
    assert {entry["id"] for entry in quote["variable_schema"]} >= {
        "quote_line_1",
        "speaker_name",
        "response_line",
    }


def test_motion_graphics_preview_uses_parser_dialogue(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/motion-graphics/preview",
        json={
            "template": "quote",
            "request": {},
            "script_text": (
                "Bilal says: 'Can words move?' "
                "Zara replies: 'Yes, locally.'"
            ),
            "mode": "build_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scene_count"] == 1
    assert payload["scenes"][0]["dialogue"][0] == {
        "speaker": "Bilal",
        "line": "Can words move?",
    }
    assert payload["request"]["speaker_name"] == "Bilal"
    assert payload["request"]["quote_lines"] == ["Can words move?"]
    assert payload["request"]["response_speaker"] == "Zara"
    assert payload["request"]["response_line"] == "Yes, locally."
    assert payload["variables"]["has_response"] is True


def test_motion_graphics_build_only_job_and_artifact(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/motion-graphics",
        json={
            "template": "outro",
            "request": {
                "closing_lines": ["API TEST ENDS"],
                "tagline": "Built through the Jobs API.",
                "brand_label": "TEST STUDIO",
                "glyph": "T",
                "credit_lines": ["LOCAL BUILD"],
                "cta_label": "",
                "duration_sec": 5,
            },
            "script_text": "",
            "mode": "build_only",
        },
    )

    assert response.status_code == 200
    queued = response.json()["job"]
    assert queued["job_type"] == "motion_graphics"
    assert queued["payload"]["template"] == "outro"

    completed = _wait_for_job(api_client, queued["id"])
    assert completed["status"] == "completed", completed
    outputs = completed["output_paths"]
    assert outputs["template"] == "outro"
    assert outputs["mode"] == "build_only"
    assert Path(outputs["index_html"]).is_file()
    assert Path(outputs["variables_json"]).is_file()
    assert Path(outputs["parsed_scenes"]).is_file()

    artifact = api_client.get(
        f"/api/jobs/{queued['id']}/artifacts/variables_json"
    )
    assert artifact.status_code == 200
    assert artifact.json()["closing_line_1"] == "API TEST ENDS"

    outside = api_client.get(f"/api/jobs/{queued['id']}/artifacts/template")
    assert outside.status_code in {403, 404}


def test_motion_graphics_invalid_request_is_rejected_before_enqueue(
    api_client: TestClient,
) -> None:
    before = api_client.get("/api/jobs").json()["jobs"]

    response = api_client.post(
        "/api/jobs/motion-graphics",
        json={
            "template": "quote",
            "request": {"quote_lines": []},
            "script_text": "",
            "mode": "build_only",
        },
    )

    assert response.status_code == 422
    after = api_client.get("/api/jobs").json()["jobs"]
    assert len(after) == len(before)


AUTO_SCRIPT = (
    "Bilal qile mein aata hai. Zara mash'al jalati hai. "
    "Dono baat karte hain."
)


def test_auto_motion_graphics_preview(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/motion-graphics/auto/preview",
        json={
            "script_text": AUTO_SCRIPT,
            "mode": "build_only",
            "fps": 30,
            "quality": "standard",
            "include_dialogue_audio": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["template"] == "auto"
    assert payload["include_dialogue_audio"] is True
    assert payload["scene_count"] == 3
    assert payload["clip_count"] == 3
    assert payload["total_duration_sec"] == 9.0
    assert [clip["template"] for clip in payload["clips"]] == [
        "title",
        "title",
        "title",
    ]
    assert payload["scenes"][0]["actions"] == ["walk"]
    assert payload["scenes"][2]["characters"] == ["Bilal", "Zara"]
    assert payload["plan"]["policy"] == "scene_led_hybrid_v1"


def test_auto_motion_graphics_build_only_job_and_artifacts(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/jobs/motion-graphics/auto",
        json={
            "script_text": AUTO_SCRIPT,
            "mode": "build_only",
            "fps": 30,
            "quality": "standard",
            "include_dialogue_audio": True,
        },
    )

    assert response.status_code == 200
    queued = response.json()["job"]
    assert queued["job_type"] == "motion_graphics"
    assert queued["payload"]["template"] == "auto"
    assert queued["payload"]["planned_clip_count"] == 3
    assert queued["payload"]["include_dialogue_audio"] is True
    assert response.json()["preview"]["include_dialogue_audio"] is True

    completed = _wait_for_job(api_client, queued["id"])
    assert completed["status"] == "completed", completed
    outputs = completed["output_paths"]
    assert outputs["template"] == "auto"
    assert outputs["mode"] == "build_only"
    assert outputs["include_dialogue_audio"] is True
    assert outputs["scene_count"] == 3
    assert outputs["clip_count"] == 3
    assert Path(outputs["auto_plan_json"]).is_file()
    assert Path(outputs["parsed_scenes"]).is_file()
    assert Path(outputs["sequence_result_json"]).is_file()
    assert Path(outputs["clip_01_index_html"]).is_file()
    assert Path(outputs["clip_03_variables_json"]).is_file()

    artifact = api_client.get(
        f"/api/jobs/{queued['id']}/artifacts/auto_plan_json"
    )
    assert artifact.status_code == 200
    plan = artifact.json()
    assert [clip["template"] for clip in plan["clips"]] == [
        "title",
        "title",
        "title",
    ]


def test_auto_motion_graphics_manager_passes_dialogue_audio_flag(
    api_client: TestClient,
    monkeypatch: Any,
) -> None:
    import backend.services.job_manager as job_manager

    captured: dict[str, Any] = {}

    def fake_execute(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        output_root = Path(kwargs["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        audio_dir = output_root / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        final_video = output_root / "combined_with_audio.mp4"
        silent_video = output_root / "combined.mp4"
        dialogue_wav = audio_dir / "dialogue-audio.wav"
        line_wav = audio_dir / "clip-01-line-01.wav"
        for path in (final_video, silent_video, dialogue_wav, line_wav):
            path.write_bytes(b"fake-render-artifact")
        plan = {
            "scene_count": 1,
            "clip_count": 1,
            "scenes": [{"scene_index": 0}],
            "clips": [{"clip_id": "clip-01", "template": "quote"}],
            "total_duration_sec": 6.0,
        }
        return {
            "status": "completed",
            "elapsed_sec": 0.25,
            "plan": plan,
            "clips": [
                {
                    "clip_id": "clip-01",
                    "dialogue_audio_lines": [{"wav_path": str(line_wav)}],
                }
            ],
            "combined_video": str(final_video),
            "combined_video_silent": str(silent_video),
            "verification": {
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "duration_sec": 6.0,
                "decoded_frames": 180,
                "streams": [{"codec_type": "video", "type": "video"}],
            },
            "verification_json": str(output_root / "combined-verification.json"),
            "dialogue_audio_wav": str(dialogue_wav),
            "dialogue_audio_json": str(audio_dir / "dialogue-audio.json"),
            "dialogue_audio": {
                "audio_path": str(dialogue_wav),
                "line_count": 1,
                "engines": ["espeak-ng-local"],
                "lines": [
                    {
                        "speaker": "Zara",
                        "text": "Ready!",
                        "voice_id": "en_female_warm",
                        "wav_path": str(line_wav),
                    }
                ],
            },
            "verification_with_audio": {
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "duration_sec": 6.0,
                "decoded_frames": 180,
                "streams": [
                    {"codec_type": "video", "type": "video"},
                    {"codec_type": "audio", "type": "audio"},
                ],
            },
            "verification_with_audio_json": str(
                output_root / "combined-with-audio-verification.json"
            ),
            "concat": {"method": "stream_copy"},
        }

    monkeypatch.setattr(
        job_manager,
        "execute_auto_motion_graphics_sequence",
        fake_execute,
    )

    response = api_client.post(
        "/api/jobs/motion-graphics/auto",
        json={
            "script_text": "Zara kehti hai: 'Ready!'",
            "mode": "render",
            "fps": 30,
            "quality": "standard",
            "include_dialogue_audio": True,
        },
    )

    assert response.status_code == 200
    queued = response.json()["job"]
    assert queued["payload"]["include_dialogue_audio"] is True

    completed = _wait_for_job(api_client, queued["id"])
    assert completed["status"] == "completed", completed
    assert captured["include_dialogue_audio"] is True
    outputs = completed["output_paths"]
    assert outputs["include_dialogue_audio"] is True
    assert outputs["video"].endswith("combined_with_audio.mp4")
    assert outputs["combined_video_silent"].endswith("combined.mp4")
    assert outputs["has_dialogue_audio"] is True
    assert outputs["dialogue_audio_wav"].endswith("dialogue-audio.wav")
    assert outputs["clip_01_line_01_wav"].endswith("clip-01-line-01.wav")
    assert any(stream["type"] == "audio" for stream in outputs["verification"]["streams"])

def test_auto_motion_graphics_blank_script_is_rejected_before_enqueue(
    api_client: TestClient,
) -> None:
    before = api_client.get("/api/jobs").json()["jobs"]

    response = api_client.post(
        "/api/jobs/motion-graphics/auto",
        json={"script_text": "   ", "mode": "build_only"},
    )

    assert response.status_code == 422
    after = api_client.get("/api/jobs").json()["jobs"]
    assert len(after) == len(before)
