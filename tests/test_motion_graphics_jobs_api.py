import time
from pathlib import Path

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
