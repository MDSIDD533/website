from fastapi.testclient import TestClient


WW2_SCRIPT = (
    "Title: The Global Conflict\n"
    "World War II was the deadliest conflict in human history. "
    "It began in 1939 when Germany invaded Poland. "
    "Great Britain and France declared war on Germany. "
    "The war quickly spread across Europe and the Pacific."
)


def test_blender_theme_catalog_marks_blender_as_primary(api_client: TestClient) -> None:
    response = api_client.get("/api/jobs/blender-3d/themes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "blender"
    assert payload["job_type"] == "blender_3d"
    assert payload["primary"] is True
    assert [theme["id"] for theme in payload["themes"]] == [
        "ww2_battlefield",
        "finance_city",
        "space_voyage",
        "ocean_voyage",
        "tech_lab",
        "nature_valley",
        "history_fort",
        "abstract_shapes",
    ]
    default = payload["default_request"]
    assert default["width"] == 1920
    assert default["height"] == 1080
    assert default["fps"] == 24
    assert default["render_profile"] == {
        "samples": 3,
        "noise_threshold": 0.12,
        "denoiser": "OPENIMAGEDENOISE",
        "denoise_prefilter": "FAST",
        "denoise_quality": "FAST",
        "max_bounces": 1,
        "diffuse_bounces": 0,
        "glossy_bounces": 0,
        "encode_crf": 18,
    }


def test_blender_preview_selects_ww2_and_native_1080p(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/blender-3d/preview",
        json={
            "script_text": WW2_SCRIPT,
            "request": {},
            "mode": "render",
            "fps": 24,
            "quality": "standard",
            "duration_sec": 18.235,
            "theme": "auto",
            "include_captions": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "blender_3d"
    assert payload["topic"]["theme"] == "ww2_battlefield"
    assert payload["topic"]["confidence"] == 0.98
    assert payload["request"]["width"] == 1920
    assert payload["request"]["height"] == 1080
    assert payload["total_frames"] == 438
    assert payload["plan"]["captions"] == [
        "THE GLOBAL CONFLICT",
        "1939 · INVASION",
        "WAR DECLARED",
        "LAND · SEA · AIR",
    ]
    assert payload["scene_count"] >= 4


def test_blender_preview_can_select_other_topics(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/blender-3d/preview",
        json={
            "script_text": "A rocket carried astronauts to the Moon and a satellite entered orbit.",
            "duration_sec": 6,
        },
    )

    assert response.status_code == 200
    assert response.json()["topic"]["theme"] == "space_voyage"


def test_blender_invalid_request_is_rejected_before_enqueue(api_client: TestClient) -> None:
    before = api_client.get("/api/jobs").json()["jobs"]

    response = api_client.post(
        "/api/jobs/blender-3d",
        json={
            "script_text": WW2_SCRIPT,
            "request": {"width": 1919},
            "duration_sec": 6,
        },
    )

    assert response.status_code == 422
    after = api_client.get("/api/jobs").json()["jobs"]
    assert len(after) == len(before)


def test_blender_runtime_endpoint_without_probe(api_client: TestClient) -> None:
    response = api_client.get("/api/jobs/blender-3d/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert "available" in runtime
    assert "python" in runtime
    assert runtime["probed"] is False
