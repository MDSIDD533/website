"""Tests for Character Studio persistence, outfit identity lock, local TTS, visemes, and audio mixing."""

from __future__ import annotations

from pathlib import Path

from character_engine.profiles import create_character, get_character, update_character
from voice_engine.sound_design import build_scene_audio_mix
from voice_engine.subtitles import write_srt_file
from voice_engine.tts import synthesize_speech_segment


def test_character_persistence_and_outfit_identity_lock(isolated_workspace: Path) -> None:
    created = create_character(
        {
            "name": "Commander Tariq",
            "outfit_preset": "historical_armor",
            "default_voice_id": "ur_male_heroic",
            "language": "roman_ur",
            "skin_tone": "#c58c65",
        }
    )
    orig_seed = created["identity_seed"]
    orig_skin = created["skin_tone"]

    updated = update_character(created["id"], {"active_outfit": "royal_tunic", "approved": True})
    reloaded = get_character(created["id"])
    assert reloaded["active_outfit"] == "royal_tunic"
    assert "royal_tunic" in reloaded["outfits"]
    assert reloaded["identity_seed"] == orig_seed
    assert reloaded["skin_tone"] == orig_skin
    assert reloaded["approved"] is True


def test_multilingual_tts_and_viseme_lipsync(isolated_workspace: Path) -> None:
    en_wav = isolated_workspace / "en_test.wav"
    res_en = synthesize_speech_segment(
        "Stand firm on the ramparts!",
        voice_id="en_male_heroic",
        language="en",
        emotion="determined",
        video_fps=24,
        output_wav_path=en_wav,
    )
    assert en_wav.is_file() and en_wav.stat().st_size > 4000
    assert res_en["duration_sec"] > 0.4
    assert len(res_en["visemes"]) >= 8
    assert max(res_en["visemes"]) > 0.05

    ru_wav = isolated_workspace / "roman_ur_test.wav"
    res_ru = synthesize_speech_segment(
        "Hum taiyar hain Sardar, qila mehfooz hai.",
        voice_id="ur_male_heroic",
        language="roman_ur",
        video_fps=24,
        output_wav_path=ru_wav,
    )
    assert ru_wav.is_file() and ru_wav.stat().st_size > 4000
    assert res_ru["duration_sec"] > 0.4


def test_scene_audio_mix_ducking_and_subtitles(isolated_workspace: Path) -> None:
    scene = {
        "id": "scn_audiotest",
        "duration_sec": 3.0,
        "environment_preset": "fortress",
        "weather": "rain",
        "actions": ["walk", "cinematic_combat"],
        "combat_choreography": {"enabled": True, "contact_frame_pct": 0.45, "secondary_exchange_pct": 0.78},
        "narration_text": "",
        "dialogue": [
            {"speaker": "Tariq", "voice_id": "en_male_heroic", "text": "Hold the eastern gate!", "emotion": "determined"},
            {"speaker": "Zara", "voice_id": "en_female_warm", "text": "Archers are ready!", "emotion": "determined"},
        ],
        "audio_cues": {
            "footsteps": True,
            "combat_sfx": True,
            "music_mood": "tense_combat",
            "dialogue_ducking": True,
        },
    }
    mix_res = build_scene_audio_mix(scene, output_dir=isolated_workspace / "audio", video_fps=24)
    mix_path = Path(mix_res["mix_wav_path"])
    assert mix_path.is_file() and mix_path.stat().st_size > 20_000
    assert "Tariq" in mix_res["character_visemes"]
    assert "Zara" in mix_res["character_visemes"]
    assert len(mix_res["subtitle_segments"]) == 2

    srt_file = write_srt_file(mix_res["subtitle_segments"], isolated_workspace / "subs.srt")
    srt_text = srt_file.read_text(encoding="utf-8")
    assert "Tariq: Hold the eastern gate!" in srt_text
    assert "-->" in srt_text
