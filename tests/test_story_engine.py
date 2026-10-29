"""Tests for multilingual script parsing, Roman Urdu normalization, and storyboard planning."""

from __future__ import annotations

from story_engine.normalizer import (
    SAMPLE_SCRIPTS,
    detect_script_language,
    normalize_roman_urdu_for_tts,
)
from story_engine.parser import analyze_script
from story_engine.storyboard import build_storyboard_scenes


def test_language_detection_en_ur_roman_urdu() -> None:
    assert detect_script_language(SAMPLE_SCRIPTS["en_historical_fortress"]["script"]) == "en"
    assert detect_script_language(SAMPLE_SCRIPTS["roman_ur_adventure"]["script"]) == "roman_ur"
    assert detect_script_language(SAMPLE_SCRIPTS["ur_cinematic_story"]["script"]) == "ur"


def test_roman_urdu_normalization() -> None:
    urdu_mapped, phonetic = normalize_roman_urdu_for_tts(
        "Sardar Tariq ne qilay ki deewar se registan dekha."
    )
    assert "سردار" in urdu_mapped
    assert "قلعے" in urdu_mapped
    assert "دیوار" in urdu_mapped
    assert len(phonetic) > 10


def test_script_parsing_and_historical_notes(isolated_workspace) -> None:
    analysis = analyze_script(
        SAMPLE_SCRIPTS["en_historical_fortress"]["script"],
        language="en",
        target_scenes=3,
        genre="historical",
        historical_accuracy_mode=True,
    )
    assert analysis["effective_language"] == "en"
    char_names = {c["name"] for c in analysis["characters"]}
    assert {"Tariq", "Zara", "Kael"}.issubset(char_names)
    assert analysis["dialogue_count"] >= 5
    assert "sword" in analysis["props"]
    assert len(analysis["scene_blocks"]) == 3

    # Verify historical vs dramatized distinction
    notes = analysis["scene_blocks"][0]["historical_notes"]
    assert notes["mode_enabled"] is True
    assert len(notes["verified_period_elements"]) >= 1
    assert len(notes["dramatized_fictional_elements"]) >= 1

    scenes = build_storyboard_scenes("prj_test01", analysis, target_duration_sec=12.0)
    assert len(scenes) == 3
    # Scene 2 involves sword combat between Tariq and Kael
    assert scenes[1]["combat_choreography"]["enabled"] is True
    assert scenes[1]["camera_shot"] == "action"


def test_narrative_roman_urdu_story_and_bilingual_subtitles(isolated_workspace) -> None:
    prose = (
        "Ek purane qile ke darwaze par ek bahadur sipahi pehra de raha tha. "
        "Achanak dushman ka ek sipahi qile ke andar aane ki koshish karta hai. "
        "Dono ke darmiyan mukalma hota hai. "
        "Phir ek chhoti talwar ki larai hoti hai. "
        "Aakhir mein qile ka sipahi darwaza band kar deta hai aur qila mehfooz rehta hai."
    )
    analysis = analyze_script(prose, language="auto", target_scenes=3, genre="historical")
    assert analysis["detected_language"] == "roman_ur"
    assert analysis["effective_language"] == "roman_ur"
    assert len(analysis["characters"]) >= 2
    assert "cinematic_combat" in analysis["actions"]
    assert "walk" in analysis["actions"]
    assert "sword" in analysis["props"]

    scenes = build_storyboard_scenes("prj_roman_prose", analysis, target_duration_sec=10.0)
    assert len(scenes) == 3
    assert any(s["combat_choreography"]["enabled"] for s in scenes)
    assert any(len(s["characters_present"]) >= 2 for s in scenes)

    from voice_engine.subtitles import build_urdu_script_segments

    ur_segs = build_urdu_script_segments(
        [{"speaker": "Narrator", "text": "Ek purane qile ke darwaze par ek bahadur sipahi pehra de raha tha.", "start_sec": 0.0, "end_sec": 3.0}]
    )
    assert "قلعے" in ur_segs[0]["text"]
    assert "سپاہی" in ur_segs[0]["text"]

