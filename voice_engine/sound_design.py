"""Original procedural sound design, ambience, foley, combat SFX, background music, and ducked audio mixing."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from voice_engine.tts import TARGET_SAMPLE_RATE, synthesize_speech_segment, write_stereo_wav

MUSIC_MOODS: list[dict[str, str]] = [
    {"id": "epic_historical", "label": "Epic Historical Strings & Frame Drum", "license": "MIT Original Procedural Score"},
    {"id": "tense_combat", "label": "Tense Action Percussion & Low Brass", "license": "MIT Original Procedural Score"},
    {"id": "mystical_ambient", "label": "Mystical Atmospheric Pads", "license": "MIT Original Procedural Score"},
    {"id": "hopeful_sunrise", "label": "Hopeful Dawn Orchestral Pad", "license": "MIT Original Procedural Score"},
    {"id": "none", "label": "No Background Music", "license": "N/A"},
]


def _generate_ambience(env_preset: str, weather: str, n_samples: int, sr: int) -> np.ndarray:
    rng = np.random.default_rng(abs(hash(f"{env_preset}:{weather}")) % (2**31))
    white = rng.standard_normal(n_samples).astype(np.float32)

    # Wind / room base filter
    cutoff = 380.0 if env_preset in {"room", "temple"} else 680.0
    b, a = signal.butter(2, cutoff / (0.5 * sr), btype="low")
    wind = signal.lfilter(b, a, white).astype(np.float32)
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    swell = (0.65 + 0.35 * np.sin(2 * np.pi * 0.19 * t)).astype(np.float32)
    amb = wind * swell * 0.22

    if weather == "rain":
        b_r, a_r = signal.butter(2, [1200.0 / (0.5 * sr), 5500.0 / (0.5 * sr)], btype="band")
        rain_tex = signal.lfilter(b_r, a_r, rng.standard_normal(n_samples).astype(np.float32)).astype(np.float32)
        amb += rain_tex * 0.26
    elif weather == "fire":
        # Crackle impulses
        impulses = (rng.random(n_samples) > 0.9985).astype(np.float32) * rng.uniform(0.2, 0.6, n_samples).astype(np.float32)
        b_f, a_f = signal.butter(2, 2400.0 / (0.5 * sr), btype="high")
        amb += signal.lfilter(b_f, a_f, impulses).astype(np.float32) * 0.55

    return amb


def _generate_footsteps(n_samples: int, sr: int, is_running: bool = False) -> np.ndarray:
    out = np.zeros(n_samples, dtype=np.float32)
    interval = 0.32 if is_running else 0.54
    step_len = int(0.085 * sr)
    rng = np.random.default_rng(707)
    b, a = signal.butter(2, 420.0 / (0.5 * sr), btype="low")

    pos = int(0.12 * sr)
    while pos + step_len < n_samples:
        env = np.exp(-np.linspace(0, 7.0, step_len)).astype(np.float32)
        thud = signal.lfilter(b, a, rng.standard_normal(step_len).astype(np.float32)).astype(np.float32)
        out[pos : pos + step_len] += thud * env * 0.45
        pos += int(interval * sr)
    return out


def _generate_combat_sfx(n_samples: int, sr: int, contact_pcts: tuple[float, ...] = (0.45, 0.76)) -> np.ndarray:
    out = np.zeros(n_samples, dtype=np.float32)
    rng = np.random.default_rng(1337)

    for idx, pct in enumerate(contact_pcts):
        center = int(n_samples * pct)
        # Pre-impact blade whoosh
        whoosh_len = int(0.16 * sr)
        w_start = max(0, center - whoosh_len)
        w_actual = center - w_start
        if w_actual > 32:
            w_env = np.sin(np.linspace(0, math.pi, w_actual)).astype(np.float32)
            b_w, a_w = signal.butter(2, [700.0 / (0.5 * sr), 3200.0 / (0.5 * sr)], btype="band")
            whoosh = signal.lfilter(b_w, a_w, rng.standard_normal(w_actual).astype(np.float32)).astype(np.float32)
            out[w_start:center] += whoosh * w_env * 0.42

        # Metallic sword/shield ring + low impact punch
        hit_len = min(int(0.38 * sr), n_samples - center)
        if hit_len > 32:
            t_h = np.arange(hit_len, dtype=np.float32) / float(sr)
            decay_metal = np.exp(-t_h * 9.5).astype(np.float32)
            decay_thud = np.exp(-t_h * 24.0).astype(np.float32)
            f_base = 1180.0 if idx % 2 == 0 else 1420.0
            clang = (
                0.45 * np.sin(2 * np.pi * f_base * t_h)
                + 0.30 * np.sin(2 * np.pi * (f_base * 1.51) * t_h)
                + 0.22 * np.sin(2 * np.pi * (f_base * 2.37) * t_h)
            ).astype(np.float32) * decay_metal
            thud = np.sin(2 * np.pi * 92.0 * t_h).astype(np.float32) * decay_thud
            out[center : center + hit_len] += (clang * 0.48 + thud * 0.55)
    return out


def _generate_procedural_music(mood: str, n_samples: int, sr: int) -> np.ndarray:
    if mood == "none" or n_samples <= 0:
        return np.zeros(n_samples, dtype=np.float32)

    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    chord_freqs = {
        "epic_historical": (110.0, 164.81, 220.0, 261.63),   # A minor cinematic fifth/octave
        "tense_combat": (98.0, 146.83, 207.65, 293.66),      # G Phrygian tension
        "mystical_ambient": (130.81, 196.0, 246.94, 293.66), # Cmaj9 ethereal
        "hopeful_sunrise": (146.83, 220.0, 277.18, 329.63),  # D major warm dawn
    }.get(mood, (110.0, 164.81, 220.0, 261.63))

    pad = np.zeros(n_samples, dtype=np.float32)
    for k, f in enumerate(chord_freqs):
        lfo = 0.82 + 0.18 * np.sin(2 * np.pi * (0.18 + 0.05 * k) * t)
        voice = (0.65 * np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2.0 * f * t)).astype(np.float32)
        pad += voice * lfo * (0.28 / (1.0 + 0.25 * k))

    # Add cinematic frame-drum pulse for historical & combat moods
    if mood in {"epic_historical", "tense_combat"}:
        beat_sec = 0.50 if mood == "tense_combat" else 0.85
        drum_len = int(0.18 * sr)
        pos = 0
        while pos + drum_len < n_samples:
            td = np.arange(drum_len, dtype=np.float32) / float(sr)
            pitch_drop = 72.0 * np.exp(-td * 6.0) + 46.0
            hit = np.sin(2 * np.pi * pitch_drop * td) * np.exp(-td * 14.0)
            pad[pos : pos + drum_len] += hit.astype(np.float32) * 0.34
            pos += int(beat_sec * sr)

    b, a = signal.butter(2, 1900.0 / (0.5 * sr), btype="low")
    smoothed = signal.lfilter(b, a, pad).astype(np.float32)
    peak = float(np.max(np.abs(smoothed)))
    if peak > 1e-4:
        smoothed = smoothed / peak * 0.72
    return smoothed


def build_scene_audio_mix(
    scene: dict[str, Any],
    *,
    output_dir: Path,
    video_fps: int = 24,
    language_fallback: str = "en",
    narration_enabled: bool = True,
    music_enabled: bool = True,
) -> dict[str, Any]:
    """Synthesize narration, multi-character dialogue, foley, ambience, and ducked music for a scene."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sr = TARGET_SAMPLE_RATE

    speech_events: list[dict[str, Any]] = []
    cursor_sec = 0.22

    # 1. Optional Narration lead-in (always spoken when no explicit screenplay dialogue exists,
    #    or when narrative prose also auto-synthesized a character mukalma exchange)
    narration_text = (scene.get("narration_text") or "").strip()
    dialogue_list = scene.get("dialogue") or []
    include_narration = narration_enabled and bool(narration_text) and (
        not dialogue_list or all(bool(d.get("auto_synthesized")) for d in dialogue_list)
    )
    if include_narration:
        narr_wav = output_dir / f"{scene['id']}_narration.wav"
        res = synthesize_speech_segment(
            narration_text,
            voice_id=scene.get("narration_voice_id") or "en_narrator_deep",
            language=language_fallback,
            speed=1.0,
            pitch=1.0,
            emotion="calm",
            video_fps=video_fps,
            output_wav_path=narr_wav,
        )
        speech_events.append(
            {
                "kind": "narration",
                "speaker": "Narrator",
                "text": narration_text,
                "start_sec": round(cursor_sec, 3),
                "end_sec": round(cursor_sec + res["duration_sec"], 3),
                "samples": res["samples"],
                "visemes": res["visemes"],
                "wav_path": str(narr_wav),
            }
        )
        cursor_sec += res["duration_sec"] + 0.30

    # 2. Character Dialogue lines
    for idx, dlg in enumerate(dialogue_list):
        txt = (dlg.get("text") or "").strip()
        if not txt:
            continue
        line_wav = output_dir / f"{scene['id']}_dlg_{idx:02d}.wav"
        res = synthesize_speech_segment(
            txt,
            voice_id=dlg.get("voice_id") or "en_male_heroic",
            language=language_fallback,
            speed=float(dlg.get("speed", 1.0)),
            pitch=float(dlg.get("pitch", 1.0)),
            emotion=dlg.get("emotion", "determined"),
            video_fps=video_fps,
            output_wav_path=line_wav,
        )
        speech_events.append(
            {
                "kind": "dialogue",
                "speaker": dlg.get("speaker", "Character"),
                "text": txt,
                "start_sec": round(cursor_sec, 3),
                "end_sec": round(cursor_sec + res["duration_sec"], 3),
                "samples": res["samples"],
                "visemes": res["visemes"],
                "wav_path": str(line_wav),
            }
        )
        cursor_sec += res["duration_sec"] + float(dlg.get("pause_after_sec", 0.30))

    # Scene duration adapts upward if spoken dialogue exceeds initial duration estimate
    target_dur = max(float(scene.get("duration_sec", 3.5)), round(cursor_sec + 0.35, 2))
    n_samples = max(int(sr * 1.0), int(round(target_dur * sr)))
    total_video_frames = max(1, int(round(target_dur * video_fps)))

    speech_track = np.zeros(n_samples, dtype=np.float32)
    speech_activity = np.zeros(n_samples, dtype=np.float32)
    character_visemes: dict[str, list[float]] = {}

    for ev in speech_events:
        s_idx = int(round(ev["start_sec"] * sr))
        seg = ev["samples"]
        end_idx = min(n_samples, s_idx + seg.size)
        if end_idx > s_idx:
            speech_track[s_idx:end_idx] += seg[: end_idx - s_idx]
            speech_activity[s_idx:end_idx] = 1.0

        if ev["kind"] == "dialogue":
            spk = ev["speaker"]
            track_vis = character_visemes.setdefault(spk, [0.0] * total_video_frames)
            f_offset = int(round(ev["start_sec"] * video_fps))
            for k, v_val in enumerate(ev["visemes"]):
                if 0 <= f_offset + k < total_video_frames:
                    track_vis[f_offset + k] = max(track_vis[f_offset + k], v_val)

    # Smooth ducking envelope (1.0 when silent, ~0.34 when someone speaks)
    cues = scene.get("audio_cues") or {}
    if cues.get("dialogue_ducking", True) and np.any(speech_activity > 0):
        win = max(1, int(0.12 * sr))
        kernel = np.ones(win, dtype=np.float32) / float(win)
        smooth_act = np.convolve(speech_activity, kernel, mode="same")
        duck_gain = 1.0 - 0.65 * np.clip(smooth_act * 1.4, 0.0, 1.0)
    else:
        duck_gain = np.ones(n_samples, dtype=np.float32)

    # 3. Ambience + Weather + Foley + Combat SFX + Music
    sfx_vol = float(cues.get("sfx_volume", 0.42))
    music_vol = float(cues.get("music_volume", 0.24)) if music_enabled else 0.0

    bg_bed = _generate_ambience(
        scene.get("environment_preset", "fortress"),
        scene.get("weather", "clear"),
        n_samples,
        sr,
    ) * sfx_vol

    actions = scene.get("actions") or []
    if cues.get("footsteps", False) or any(a in actions for a in ("walk", "run", "chase")):
        bg_bed += _generate_footsteps(n_samples, sr, is_running=("run" in actions or "chase" in actions)) * sfx_vol

    combat_cfg = scene.get("combat_choreography") or {}
    if cues.get("combat_sfx", False) or combat_cfg.get("enabled"):
        c1 = float(combat_cfg.get("contact_frame_pct", 0.45))
        c2 = float(combat_cfg.get("secondary_exchange_pct", 0.76))
        bg_bed += _generate_combat_sfx(n_samples, sr, (c1, c2)) * (sfx_vol * 1.15)

    music_mood = cues.get("music_mood", "epic_historical") if music_enabled else "none"
    music_bed = _generate_procedural_music(music_mood, n_samples, sr) * music_vol

    mixed = speech_track * 0.92 + (bg_bed * (0.55 + 0.45 * duck_gain)) + (music_bed * duck_gain)

    # Smooth fade-in (120ms) and fade-out (220ms)
    fade_in = min(int(0.12 * sr), n_samples // 4)
    fade_out = min(int(0.22 * sr), n_samples // 4)
    if fade_in > 1:
        mixed[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out > 1:
        mixed[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)

    # Soft master limiter
    peak = float(np.max(np.abs(mixed)))
    if peak > 0.96:
        mixed = mixed / peak * 0.94

    mix_wav_path = output_dir / f"{scene['id']}_mix.wav"
    write_stereo_wav(mix_wav_path, mixed, sr)

    subtitle_segments = [
        {
            "speaker": ev["speaker"],
            "text": ev["text"],
            "start_sec": ev["start_sec"],
            "end_sec": ev["end_sec"],
        }
        for ev in speech_events
    ]

    return {
        "mix_wav_path": str(mix_wav_path),
        "actual_duration_sec": round(n_samples / float(sr), 3),
        "total_video_frames": total_video_frames,
        "character_visemes": character_visemes,
        "subtitle_segments": subtitle_segments,
    }
