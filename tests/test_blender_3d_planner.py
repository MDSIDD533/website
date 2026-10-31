import pytest

from app.blender_3d.planner import Blender3DRequest, plan_blender_3d, quality_profile


GLOBAL_CONFLICT_OPENING = """
Title: The Global Conflict
World War II was the deadliest conflict in human history.
It began in 1939 when Germany invaded Poland.
Great Britain and France declared war on Germany.
The war quickly spread across Europe and the Pacific.
Millions of soldiers fought on land, at sea, and in the air.
"""


def test_global_conflict_selects_ww2_battlefield_with_precedence() -> None:
    plan = plan_blender_3d(GLOBAL_CONFLICT_OPENING, {"duration_sec": 18.235})

    assert plan.topic.theme == "ww2_battlefield"
    assert plan.topic.environment == "battlefield"
    assert plan.topic.confidence >= 0.9
    assert "ww2_precedence_over_generic_topics" in plan.topic.reason_codes
    assert {"world war ii", "1939", "Germany", "Poland", "invaded"}.issubset(
        set(plan.topic.matched_cues)
    )
    assert plan.captions == [
        "THE GLOBAL CONFLICT",
        "1939 · INVASION",
        "WAR DECLARED",
        "LAND · SEA · AIR",
    ]
    assert plan.request.width == 1280
    assert plan.request.height == 720
    assert plan.request.fps == 15
    assert plan.request.quality == "turbo"
    assert plan.request.camera_move == "drone"
    assert plan.to_dict()["total_frames"] == 274
    assert plan.scene_beats[-1]["end_sec"] == pytest.approx(18.235)


@pytest.mark.parametrize(
    ("script", "theme"),
    [
        ("Banks moved dollars through the global financial market.", "finance_city"),
        ("A rocket carried astronauts to the Moon while satellites entered orbit.", "space_voyage"),
        ("A ship sailed toward an island lighthouse across ocean waves.", "ocean_voyage"),
        ("A robot and computer servers processed data in a digital laboratory.", "tech_lab"),
        (
            "Soldiers waited in the jungle canopy before a guerrilla ambush in the rain.",
            "jungle_war",
        ),
        ("Trees in the forest stood beside a river below green mountains.", "nature_valley"),
        ("The ancient king entered the royal fort beside the palace.", "history_fort"),
        ("A plain object moves through an empty room.", "abstract_shapes"),
    ],
)
def test_other_topics_select_matching_procedural_scene(script: str, theme: str) -> None:
    plan = plan_blender_3d(script, {})

    assert plan.topic.theme == theme
    assert plan.request.theme == theme
    assert plan.captions
    assert plan.scene_beats[0]["start_sec"] == 0.0


def test_jungle_war_has_moody_captions_and_wins_over_generic_battlefield() -> None:
    plan = plan_blender_3d(
        "Title: Jungle War\n"
        "Hidden soldiers waited in the jungle canopy while a patrol crossed the forest. "
        "A guerrilla ambush erupted in the rain, and the survivors searched for shelter.",
        {"duration_sec": 60},
    )

    assert plan.topic.theme == "jungle_war"
    assert plan.topic.environment == "jungle_war"
    assert "jungle_war_precedence_over_generic_battlefield" in plan.topic.reason_codes
    assert {"jungle war", "guerrilla", "ambush", "jungle", "forest"}.issubset(
        set(plan.topic.matched_cues)
    )
    assert plan.captions == [
        "JUNGLE WAR",
        "HIDDEN IN THE CANOPY",
        "THE AMBUSH",
        "SURVIVE THE JUNGLE",
    ]
    assert plan.to_dict()["total_frames"] == 900


def test_current_parser_shape_and_fort_default_do_not_crash() -> None:
    plan = plan_blender_3d("Bilal qile mein aata hai. Zara mash'al jalati hai.", {})

    # The current parser defaults unknown locations to ``fort``; the explicit
    # Roman-Urdu ``qile`` cue is also a real fort cue, so this theme is valid.
    assert plan.topic.theme == "history_fort"
    assert plan.scenes[0]["characters"] == ["Bilal"]
    assert plan.scenes[0]["actions"] == ["walk"]


def test_explicit_theme_override_keeps_auto_cues_for_audit() -> None:
    plan = plan_blender_3d(
        "World War II began in 1939 when Germany invaded Poland.",
        {"theme": "space_voyage"},
    )

    assert plan.topic.theme == "space_voyage"
    assert plan.request.theme == "space_voyage"
    assert "explicit_theme_override" in plan.topic.reason_codes
    assert "world war ii" in plan.topic.matched_cues


def test_turbo_is_the_saved_default_cpu_profile() -> None:
    assert quality_profile("turbo") == {
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
    assert quality_profile("draft")["samples"] == 2
    assert quality_profile("standard")["samples"] == 3
    assert quality_profile("high")["samples"] == 6
    for quality in ("turbo", "draft", "standard", "high"):
        profile = quality_profile(quality)
        assert profile["denoiser"] == "OPENIMAGEDENOISE"

    request = Blender3DRequest()
    assert (request.width, request.height, request.fps) == (1280, 720, 15)
    assert request.quality == "turbo"
    assert request.camera_move == "drone"
    assert request.to_dict()["render_profile"]["samples"] == 1
    assert Blender3DRequest.from_dict({"fps": 20}).fps == 20


@pytest.mark.parametrize(
    "payload",
    [
        {"theme": "unknown"},
        {"fps": 60},
        {"width": 1919},
        {"duration_sec": 121},
        {"caption_lines": ["x" * 81]},
    ],
)
def test_invalid_blender_requests_are_rejected(payload: dict) -> None:
    with pytest.raises(ValueError):
        Blender3DRequest.from_dict(payload)
