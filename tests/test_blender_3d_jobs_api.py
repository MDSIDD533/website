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
        "jungle_war",
        "last_survivor",
        "nature_valley",
        "history_fort",
        "abstract_shapes",
    ]
    default = payload["default_request"]
    assert default["width"] == 1280
    assert default["height"] == 720
    assert default["fps"] == 15
    assert default["quality"] == "turbo"
    assert default["camera_move"] == "drone"
    assert default["render_profile"] == {
        "samples": 1,
        "noise_threshold": 0.3,
        "denoiser": "OPENIMAGEDENOISE",
        "denoise_prefilter": "NONE",
        "denoise_quality": "FAST",
        "denoise_input_passes": "RGB",
        "max_bounces": 0,
        "diffuse_bounces": 0,
        "glossy_bounces": 0,
        "light_sampling_threshold": 0.15,
        "encode_crf": 23,
        "encode_preset": "veryfast",
    }


def test_blender_preview_selects_ww2_with_turbo_default(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/blender-3d/preview",
        json={
            "script_text": WW2_SCRIPT,
            "request": {},
            "mode": "render",
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
    assert payload["request"]["width"] == 1280
    assert payload["request"]["height"] == 720
    assert payload["request"]["fps"] == 15
    assert payload["request"]["quality"] == "turbo"
    assert payload["total_frames"] == 274
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


def test_blender_preview_selects_jungle_war(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/blender-3d/preview",
        json={
            "script_text": (
                "Title: Jungle War\n"
                "A patrol moved through the dark jungle while camouflaged soldiers "
                "hid in the canopy before a guerrilla ambush in heavy rain."
            ),
            "duration_sec": 60,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"]["theme"] == "jungle_war"
    assert payload["total_frames"] == 900
    assert payload["request"]["camera_move"] == "drone"


def test_blender_preview_selects_last_survivor_with_piper_joe_hero(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/jobs/blender-3d/preview",
        json={
            "script_text": (
                "Title: The Last Survivor (Jungle War)\n"
                "HERO: Rain was falling when my last radio went silent, and I knew my entire unit was gone.\n"
                "HERO: I am the only soldier still standing, yet every fallen brother marches beside me through this jungle."
            ),
            "duration_sec": 30,
            "include_hero_voice": True,
            "hero_voice_id": "en_male_heroic",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"]["theme"] == "last_survivor"
    assert payload["total_frames"] == 450
    assert payload["request"]["camera_move"] == "hero_tracking"
    assert payload["request"]["include_hero_voice"] is True
    assert payload["request"]["hero_voice_id"] == "en_male_heroic"
    assert len(payload["plan"]["hero_dialogue"]) == 2


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
