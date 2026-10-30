"""Unit tests for the rule-based script parser (Phase 2, sub-step 3.1)."""

from __future__ import annotations

from app.script_parser import parse_script


def test_single_scene_no_dialogue() -> None:
    scenes = parse_script("Bilal qile mein chalta hai.")
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["scene_id"] == 1
    assert scene["location"] == "fort"
    assert scene["characters"] == ["Bilal"]
    assert scene["actions"] == ["walk"]
    assert scene["dialogue"] == []
    assert scene["duration_sec"] == 3.0


def test_two_scenes_with_dialogue() -> None:
    scenes = parse_script(
        "Zara mash'al jalati hai. Bilal kehta hai: 'Guard your left flank!'"
    )
    assert len(scenes) == 2
    assert scenes[0]["characters"] == ["Zara"]
    assert "light_torch" in scenes[0]["actions"]
    dialogue = scenes[1]["dialogue"]
    assert len(dialogue) == 1
    assert dialogue[0]["speaker"] == "Bilal"
    assert "Guard your left flank" in dialogue[0]["line"]
    # 3.0 base + 1.0 for the dialogue line (single "talk" action adds 0)
    assert scenes[1]["duration_sec"] == 4.0


def test_unknown_location_falls_back_to_fort() -> None:
    scenes = parse_script("Bilal kisi ajnabi jagah chalta hai.")
    assert len(scenes) == 1
    assert scenes[0]["location"] == "fort"


def test_multiple_characters_one_scene() -> None:
    scenes = parse_script("Bilal aur Zara qile mein baat karte hain.")
    assert len(scenes) == 1
    assert set(scenes[0]["characters"]) == {"Bilal", "Zara"}
    assert "talk" in scenes[0]["actions"]


def test_roman_urdu_english_mix() -> None:
    scenes = parse_script(
        "Zara walks into the qila at night. Bilal says: 'Ready?'"
    )
    assert len(scenes) == 2
    assert scenes[0]["location"] == "fort"
    assert scenes[0]["time_of_day"] == "night"
    assert scenes[0]["characters"] == ["Zara"]
    assert "walk" in scenes[0]["actions"]
    # No inheritance: scene 2 names no time, so it gets its own default.
    assert scenes[1]["time_of_day"] == "day"
    dialogue = scenes[1]["dialogue"]
    assert len(dialogue) == 1
    assert dialogue[0]["speaker"] == "Bilal"
    assert "Ready?" in dialogue[0]["line"]


def test_aata_hai_and_dono_context_resolution() -> None:
    scenes = parse_script(
        "Bilal qile mein aata hai. "
        "Zara mash'al jalati hai. "
        "Dono baat karte hain."
    )

    assert len(scenes) == 3
    assert scenes[0]["characters"] == ["Bilal"]
    assert scenes[0]["actions"] == ["walk"]
    assert scenes[1]["characters"] == ["Zara"]
    assert scenes[1]["actions"] == ["light_torch"]
    assert scenes[2]["characters"] == ["Bilal", "Zara"]
    assert scenes[2]["actions"] == ["talk"]
    # Dono uses character context only; location/time still use defaults.
    assert scenes[2]["location"] == "fort"
    assert scenes[2]["time_of_day"] == "day"


def test_dono_preserves_first_mention_order() -> None:
    scenes = parse_script(
        "Zara qile mein aati hai. Bilal aata hai. Dono baat karte hain."
    )

    assert scenes[0]["actions"] == ["walk"]
    assert scenes[1]["actions"] == ["walk"]
    assert scenes[2]["characters"] == ["Zara", "Bilal"]


def test_dono_without_two_known_characters_stays_unresolved() -> None:
    scenes = parse_script("Dono baat karte hain.")

    assert scenes[0]["characters"] == []
    assert scenes[0]["actions"] == ["talk"]
