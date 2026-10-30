"""Deterministic auto-mapper planner tests."""

from __future__ import annotations

import pytest

from app.motion_graphics.auto_mapper import plan_auto_sequence


E2E_SCRIPT = """Bilal qile mein aata hai. Zara mash'al jalati hai. Dono baat karte hain:

Bilal kehta hai: 'Guard your left flank!' Zara kehti hai: 'Ready!'"""


def test_e2e_script_maps_to_three_titles_and_one_quote() -> None:
    plan = plan_auto_sequence(E2E_SCRIPT)

    assert plan.policy == "scene_led_hybrid_v1"
    assert len(plan.scenes) == 4
    assert [clip.template for clip in plan.clips] == [
        "title",
        "title",
        "title",
        "quote",
    ]
    assert [clip.duration_sec for clip in plan.clips] == [3.0, 3.0, 3.0, 6.0]
    assert plan.total_duration_sec == 15.0

    assert plan.scenes[0]["actions"] == ["walk"]
    assert plan.scenes[2]["characters"] == ["Bilal", "Zara"]

    first = plan.clips[0]
    assert first.request["kicker"] == "SCENE 01 · FORT · DAY"
    assert first.request["title_lines"] == ["Bilal qile mein", "aata hai"]
    assert first.request["sublines"] == ["Bilal · Walk"]

    third = plan.clips[2]
    assert third.request["sublines"] == ["Bilal + Zara · Talk"]

    quote = plan.clips[3]
    assert quote.reason_codes == ("dialogue_present",)
    assert quote.request["quote_lines"] == ["Guard your left flank!"]
    assert quote.request["speaker_name"] == "Bilal"
    assert quote.request["response_speaker"] == "Zara"
    assert quote.request["response_line"] == "Ready!"


def test_user_script_uses_parser_order_and_scene_durations() -> None:
    plan = plan_auto_sequence(
        "Bilal qile mein aata hai. Zara mash'al jalati hai. "
        "Dono baat karte hain."
    )

    assert [scene["scene_id"] for scene in plan.scenes] == [1, 2, 3]
    assert [clip.scene_id for clip in plan.clips] == [1, 2, 3]
    assert [clip.template for clip in plan.clips] == ["title", "title", "title"]
    assert [clip.scene_duration_sec for clip in plan.clips] == [3.0, 3.0, 3.0]
    assert [clip.duration_sec for clip in plan.clips] == [3.0, 3.0, 3.0]
    assert plan.total_duration_sec == 9.0
    assert plan.clips[0].request["title_lines"] == [
        "Bilal qile mein",
        "aata hai",
    ]
    assert plan.clips[0].request["sublines"] == ["Bilal · Walk"]
    assert plan.clips[1].request["sublines"] == ["Zara · Light torch"]
    assert plan.clips[2].request["sublines"] == ["Bilal + Zara · Talk"]


def test_dialogue_scene_selects_quote() -> None:
    plan = plan_auto_sequence("Bilal says: 'Can words move?'")

    assert [clip.template for clip in plan.clips] == ["quote"]
    assert plan.clips[0].request["speaker_name"] == "Bilal"
    assert plan.clips[0].request["quote_lines"] == ["Can words move?"]
    assert plan.clips[0].scene_duration_sec == 4.0
    # Quote template's valid lower bound is 6 seconds.
    assert plan.clips[0].duration_sec == 6.0


def test_explicit_numeric_pairs_select_data() -> None:
    plan = plan_auto_sequence("Capture: 62%, Encode: 24%, Setup: 14%.")

    assert [clip.template for clip in plan.clips] == ["data"]
    request = plan.clips[0].request
    assert request["unit"] == "%"
    assert request["data_points"] == [
        {"label": "CAPTURE", "value": 62.0},
        {"label": "ENCODE", "value": 24.0},
        {"label": "SETUP", "value": 14.0},
    ]
    assert request["source_line"].startswith("Source: script scene 1")


def test_two_plain_numbers_with_labels_before_select_data() -> None:
    plan = plan_auto_sequence("Capture 62, Encode 24.")

    assert [clip.template for clip in plan.clips] == ["data"]
    clip = plan.clips[0]
    assert clip.reason_codes == ("two_or_more_numbers",)
    assert clip.scene_duration_sec == 3.0
    # Data template's valid lower bound is 6 seconds.
    assert clip.duration_sec == 6.0
    assert clip.request["unit"] == ""
    assert clip.request["data_points"] == [
        {"label": "CAPTURE", "value": 62.0},
        {"label": "ENCODE", "value": 24.0},
    ]


def test_two_plain_numbers_with_people_and_count_noun_select_data() -> None:
    plan = plan_auto_sequence(
        "Bilal 10 qadam chalta hai, Zara 20 qadam chalti hai."
    )

    assert [clip.template for clip in plan.clips] == ["data"]
    request = plan.clips[0].request
    assert request["unit"] == "qadam"
    assert request["data_points"] == [
        {"label": "BILAL", "value": 10.0},
        {"label": "ZARA", "value": 20.0},
    ]


def test_two_plain_numbers_with_nouns_after_select_data() -> None:
    plan = plan_auto_sequence("There are 10 soldiers and 20 archers.")

    assert [clip.template for clip in plan.clips] == ["data"]
    assert plan.clips[0].request["data_points"] == [
        {"label": "SOLDIERS", "value": 10.0},
        {"label": "ARCHERS", "value": 20.0},
    ]


def test_single_numeric_pair_falls_back_to_title() -> None:
    plan = plan_auto_sequence("Capture: 62% at the fort.")

    assert [clip.template for clip in plan.clips] == ["title"]
    assert plan.clips[0].reason_codes == ("narrative_scene",)


def test_last_scene_closing_cue_selects_outro() -> None:
    plan = plan_auto_sequence(
        "Bilal qile mein aata hai. Aakhir mein kahani khatam hoti hai."
    )

    assert [clip.template for clip in plan.clips] == ["title", "outro"]
    outro = plan.clips[1]
    assert outro.reason_codes == ("last_scene", "closing_cue")
    assert outro.scene_duration_sec == 3.0
    # Outro template's valid lower bound is 5 seconds.
    assert outro.duration_sec == 5.0
    assert outro.request["kicker"] == "THE END · SCENE 02"
    assert outro.request["cta_label"] == ""


def test_long_narrative_sentence_is_deterministic_and_bounded() -> None:
    long_sentence = (
        "Bilal qile mein aata hai aur Zara mashal jalati hai jab dono purani "
        "deewar ke paas kharay hokar door battlefield ki taraf dekhte hain "
        "aur phir khamoshi se aglay manzar ki tayyari karte hain."
    )

    plan_one = plan_auto_sequence(long_sentence)
    plan_two = plan_auto_sequence(long_sentence)

    assert plan_one.to_dict() == plan_two.to_dict()
    request = plan_one.clips[0].request
    assert len(request["title_lines"]) <= 3
    assert all(len(line) <= 18 for line in request["title_lines"])
    assert len(request["sublines"]) <= 2
    assert all(len(line) <= 48 for line in request["sublines"])


def test_empty_script_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        plan_auto_sequence("   ")
