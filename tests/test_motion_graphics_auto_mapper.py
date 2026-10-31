"""Deterministic auto-mapper planner tests."""

from __future__ import annotations

import pytest

from app.motion_graphics.auto_mapper import plan_auto_sequence, retimed_auto_sequence


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
    # The two short spoken lines now reserve only their estimated speech
    # time + shared lead/gap/tail, instead of the old fixed 6s Quote floor.
    assert [clip.duration_sec for clip in plan.clips] == [3.0, 3.0, 3.0, 3.009]
    assert plan.total_duration_sec == 12.009
    assert plan.clips[3].estimated_speech_sec == 2.259

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
    assert plan.clips[0].scene_duration_sec == 1.811
    assert plan.clips[0].estimated_speech_sec == 1.311
    # Quote's new tight lower bound is 2 seconds; short dialogue is not
    # stretched to the former 6-second floor.
    assert plan.clips[0].duration_sec == 2.0


FULL_DIALOGUE_SCRIPT = """Bilal says: 'Zara, hold the torch beside the eastern wall and watch the road below.'
Zara says: 'I am ready, but the north gate shakes when the cold wind crosses the valley.'
Bilal says: 'Then stay near the gate, and I will cross the yard before the drums begin.'
Zara says: 'When riders reach the bridge, raise the silver banner and call my name aloud.'
Bilal says: 'We will guard this fort together until the first light touches the highest tower.'"""


def test_five_long_dialogue_scenes_fill_a_tight_conversation() -> None:
    plan = plan_auto_sequence(FULL_DIALOGUE_SCRIPT)

    assert [clip.template for clip in plan.clips] == ["quote"] * 5
    assert [clip.request["speaker_name"] for clip in plan.clips] == [
        "Bilal",
        "Zara",
        "Bilal",
        "Zara",
        "Bilal",
    ]
    assert [clip.duration_sec for clip in plan.clips] == [
        5.567,
        6.295,
        6.295,
        5.931,
        5.811,
    ]
    assert plan.total_duration_sec == 29.899
    assert plan.estimated_speech_sec == 27.399
    # Every clip starts with its own spoken line; there is no silent
    # narrative card before the conversation.
    assert all(clip.estimated_speech_sec > 5.0 for clip in plan.clips)


def test_measured_dialogue_retiming_shrinks_clips_without_repeating() -> None:
    plan = plan_auto_sequence(FULL_DIALOGUE_SCRIPT)
    retimed = retimed_auto_sequence(
        plan,
        {
            "clip-01": (4.017,),
            "clip-02": (5.108,),
            "clip-03": (3.773,),
            "clip-04": (4.969,),
            "clip-05": (3.889,),
        },
    )

    assert [clip.duration_sec for clip in retimed.clips] == [
        4.517,
        5.608,
        4.273,
        5.469,
        4.389,
    ]
    assert [clip.request["duration_sec"] for clip in retimed.clips] == [
        clip.duration_sec for clip in retimed.clips
    ]
    assert retimed.total_duration_sec == 24.256
    assert retimed.measured_speech_sec == 21.756
    assert retimed.to_dict()["measured_speech_sec"] == 21.756
    assert all(
        any("retimed to measured speech" in warning for warning in clip.warnings)
        for clip in retimed.clips
    )


def test_mixed_script_exposes_narration_without_duplicating_dialogue() -> None:
    plan = plan_auto_sequence(
        "Title: The Global Conflict\n"
        "World War II was the deadliest conflict in human history.\n"
        "Bilal says: 'We must hold the line at all costs!'"
    )

    assert [clip.template for clip in plan.clips] == ["title", "title", "quote"]
    assert plan.clips[0].request["title_lines"] == ["The Global", "Conflict"]
    assert plan.clips[0].narration_text == "The Global Conflict"
    assert plan.clips[0].estimated_narration_sec == 1.091
    assert (
        plan.clips[1].narration_text
        == "World War II was the deadliest conflict in human history."
    )
    assert plan.clips[1].estimated_narration_sec == 3.856
    # Dialogue is already spoken by Bilal; do not also narrate the raw
    # ``Bilal says: ...`` sentence.
    assert plan.clips[2].narration_text == ""
    assert plan.clips[2].estimated_speech_sec == 3.129
    assert plan.estimated_narration_sec == 4.947
    assert plan.estimated_total_speech_sec == 8.076

    retimed = retimed_auto_sequence(
        plan,
        {"clip-01": (1.25,), "clip-02": (3.75,), "clip-03": (2.25,)},
    )
    assert retimed.clips[0].duration_sec == 3.0  # Title template floor.
    assert retimed.clips[1].duration_sec == 4.25
    assert retimed.clips[2].duration_sec == 2.75
    assert retimed.measured_narration_sec == 5.0
    assert retimed.measured_speech_sec == 7.25
    assert retimed.to_dict()["estimated_narration_sec"] == 4.947


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
