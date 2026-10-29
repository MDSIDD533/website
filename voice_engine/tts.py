"""Local multi-voice text-to-speech engine (eSpeak-NG C bridge + Piper ONNX runtime) and viseme extractor."""

from __future__ import annotations

import ctypes
import math
import os
import threading
import wave
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from backend.core.config import get_settings
from story_engine.normalizer import detect_script_language, normalize_roman_urdu_for_tts

TARGET_SAMPLE_RATE = 44100
_ESPEAK_LOCK = threading.Lock()
_ESPEAK_LIB: Any = None
_ESPEAK_SR: int = 22050

VOICE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "en_narrator_deep",
        "name": "Atlas (Narrator — Deep Cinematic)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en-us+m3",
        "base_rate": 155,
        "base_pitch": 36,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "en_male_heroic",
        "name": "Tariq EN (Protagonist — Resolute Baritone)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en+m1",
        "base_rate": 165,
        "base_pitch": 44,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "en_male_deep",
        "name": "Kael EN (Antagonist — Commanding Low)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en+m4",
        "base_rate": 152,
        "base_pitch": 30,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "en_male_calm",
        "name": "Idris EN (Advisor — Measured Tenor)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en-gb+m2",
        "base_rate": 158,
        "base_pitch": 48,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "en_female_warm",
        "name": "Zara EN (Heroine — Warm Expressive)",
        "language": "en",
        "gender": "female",
        "espeak_voice": "en-us+f3",
        "base_rate": 164,
        "base_pitch": 66,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "en_female_bright",
        "name": "Noor EN (Scout — Clear Bright)",
        "language": "en",
        "gender": "female",
        "espeak_voice": "en+f2",
        "base_rate": 170,
        "base_pitch": 72,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "ur_narrator_deep",
        "name": "Dastan-Go (Urdu / Roman-Urdu Narrator)",
        "language": "ur",
        "gender": "male",
        "espeak_voice": "ur+m3",
        "base_rate": 148,
        "base_pitch": 36,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "ur_male_heroic",
        "name": "Sardar Tariq (Urdu / Roman-Urdu Male)",
        "language": "ur",
        "gender": "male",
        "espeak_voice": "ur+m1",
        "base_rate": 156,
        "base_pitch": 44,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "ur_male_deep",
        "name": "Zafar (Urdu / Roman-Urdu Deep Male)",
        "language": "ur",
        "gender": "male",
        "espeak_voice": "ur+m4",
        "base_rate": 146,
        "base_pitch": 30,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "ur_female_warm",
        "name": "Zara UR (Urdu / Roman-Urdu Female)",
        "language": "ur",
        "gender": "female",
        "espeak_voice": "ur+f3",
        "base_rate": 154,
        "base_pitch": 68,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "ur_female_bright",
        "name": "Amina UR (Urdu / Roman-Urdu Bright Female)",
        "language": "ur",
        "gender": "female",
        "espeak_voice": "ur+f2",
        "base_rate": 160,
        "base_pitch": 74,
        "engine": "espeak-ng-local",
        "license": "GPL-3.0-or-later (Synthetic Voice)",
    },
    {
        "id": "piper_neural_local",
        "name": "Piper Local Neural Voice (Custom .onnx Slot)",
        "language": "en",
        "gender": "neutral",
        "espeak_voice": "en-us+f3",
        "base_rate": 162,
        "base_pitch": 55,
        "engine": "piper-onnx-local",
        "license": "Depends on user-installed ONNX voice checkpoint",
    },
]

LIPSYNC_CAPABILITY_MATRIX: list[dict[str, Any]] = [
    {
        "language": "English (en)",
        "tts_status": "implemented_offline",
        "tts_engine": "eSpeak-NG + Optional Piper Neural ONNX",
        "lipsync_mode": "Frame-accurate 3D jaw viseme envelope + head/brow emphasis",
        "naturalness_note": "Built-in offline voice uses formant synthesis with DSP warmth filter; install a Piper .onnx voice in Model Manager for neural prosody.",
    },
    {
        "language": "Urdu Script (اردو / ur)",
        "tts_status": "implemented_offline",
        "tts_engine": "eSpeak-NG Native Urdu Dictionary (ur_dict)",
        "lipsync_mode": "Frame-accurate 3D jaw viseme envelope",
        "naturalness_note": "Full offline Urdu script synthesis included out of the box; formant acoustic quality.",
    },
    {
        "language": "Roman Urdu (roman_ur)",
        "tts_status": "implemented_offline",
        "tts_engine": "Roman-Urdu Lexicon Normalizer -> eSpeak-NG Urdu/Phonetic",
        "lipsync_mode": "Frame-accurate 3D jaw viseme envelope",
        "naturalness_note": "Deterministic Roman-Urdu-to-Urdu normalizer maps common vocabulary accurately; uncommon proper nouns use phonetic fallback.",
    },
]

EMOTION_MODIFIERS: dict[str, tuple[float, float, float]] = {
    # (rate_mult, pitch_mult, range_val)
    "neutral": (1.0, 1.0, 52),
    "calm": (0.93, 0.96, 44),
    "determined": (1.02, 0.98, 62),
    "angry": (1.10, 0.92, 76),
    "joyful": (1.07, 1.12, 72),
    "sad": (0.86, 0.90, 34),
    "fearful": (1.14, 1.16, 70),
    "surprised": (1.08, 1.18, 78),
}


class _EspeakEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("unique_identifier", ctypes.c_uint),
        ("text_position", ctypes.c_int),
        ("length", ctypes.c_int),
        ("audio_position", ctypes.c_int),
        ("sample", ctypes.c_int),
        ("user_data", ctypes.c_void_p),
        ("id", ctypes.c_long),
    ]


_SYNTH_CB_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.POINTER(_EspeakEvent)
)


def _get_espeak_lib() -> tuple[Any, int] | None:
    global _ESPEAK_LIB, _ESPEAK_SR
    if _ESPEAK_LIB is not None:
        return (_ESPEAK_LIB, _ESPEAK_SR)
    try:
        import piper  # type: ignore

        piper_dir = os.path.dirname(piper.__file__)
        so_path = os.path.join(piper_dir, "espeakbridge.so")
        data_dir = os.path.join(piper_dir, "espeak-ng-data")
        if not os.path.exists(so_path):
            return None
        lib = ctypes.CDLL(so_path)
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        lib.espeak_Initialize.restype = ctypes.c_int
        lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        lib.espeak_SetVoiceByName.restype = ctypes.c_int
        lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.espeak_SetParameter.restype = ctypes.c_int
        sr = lib.espeak_Initialize(0x02, 0, data_dir.encode("utf-8"), 0)
        if sr <= 0:
            sr = 22050
        _ESPEAK_LIB = lib
        _ESPEAK_SR = int(sr)
        return (_ESPEAK_LIB, _ESPEAK_SR)
    except Exception:
        return None


def _try_piper_onnx_synth(text: str, speed: float) -> tuple[np.ndarray, int] | None:
    """Use PiperVoice ONNX neural model if the user installed one in models_data/piper-onnx-custom-voice."""
    settings = get_settings()
    slot_dir = settings.models_dir / "piper-onnx-custom-voice"
    if not slot_dir.is_dir():
        return None
    onnx_files = sorted(slot_dir.glob("*.onnx"))
    if not onnx_files:
        return None
    model_path = onnx_files[0]
    cfg_path = Path(f"{model_path}.json")
    if not cfg_path.is_file():
        alt = slot_dir / "config.json"
        if alt.is_file():
            cfg_path = alt
        else:
            return None
    try:
        from piper import PiperVoice, SynthesisConfig  # type: ignore

        voice = PiperVoice.load(str(model_path), config_path=str(cfg_path))
        syn_cfg = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, speed)))
        chunks: list[np.ndarray] = []
        sr = 22050
        for audio_chunk in voice.synthesize(text, syn_config=syn_cfg):
            sr = audio_chunk.sample_rate
            arr = np.frombuffer(audio_chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            chunks.append(arr)
        if chunks:
            return (np.concatenate(chunks), sr)
    except Exception:
        return None
    return None


def _apply_voice_warmth_dsp(samples: np.ndarray, sr: int) -> np.ndarray:
    """Apply gentle low-pass smoothing and subtle early reflection so formant speech sounds warm & cinematic."""
    if samples.size < 64:
        return samples
    nyq = 0.5 * sr
    cutoff = min(0.92, 5800.0 / nyq)
    b, a = signal.butter(2, cutoff, btype="low")
    filtered = signal.lfilter(b, a, samples).astype(np.float32)

    # Subtle 18ms studio room reflection
    delay = int(0.018 * sr)
    if filtered.size > delay + 10:
        reflected = np.zeros_like(filtered)
        reflected[delay:] = filtered[:-delay] * 0.11
        filtered = filtered + reflected

    peak = float(np.max(np.abs(filtered)))
    if peak > 1e-4:
        filtered = filtered / peak * 0.86
    return filtered


def compute_viseme_envelope(samples: np.ndarray, sr: int, video_fps: int = 24) -> list[float]:
    """Compute normalized [0.0..1.0] per-video-frame mouth/jaw openness curve from speech waveform."""
    if samples.size == 0:
        return []
    spf = max(1, int(round(sr / float(max(1, video_fps)))))
    n_frames = max(1, math.ceil(samples.size / spf))
    env: list[float] = []
    for i in range(n_frames):
        seg = samples[i * spf : (i + 1) * spf]
        if seg.size == 0:
            env.append(0.0)
        else:
            rms = float(np.sqrt(np.mean(np.square(seg))))
            env.append(rms)

    max_rms = max(env) if env else 0.0
    if max_rms < 1e-4:
        return [0.0 for _ in env]

    smoothed: list[float] = []
    prev = 0.0
    for val in env:
        norm = min(1.0, (val / max_rms) * 1.15)
        if norm < 0.08:
            norm = 0.0
        cur = 0.55 * norm + 0.45 * prev
        smoothed.append(round(cur, 3))
        prev = cur
    return smoothed


def get_voice_meta(voice_id: str) -> dict[str, Any]:
    for v in VOICE_CATALOG:
        if v["id"] == voice_id:
            return v
    return VOICE_CATALOG[0]


def synthesize_speech_segment(
    text: str,
    *,
    voice_id: str = "en_male_heroic",
    language: str | None = None,
    speed: float = 1.0,
    pitch: float = 1.0,
    emotion: str = "determined",
    video_fps: int = 24,
    output_wav_path: Path | None = None,
) -> dict[str, Any]:
    """Synthesize speech locally to 44.1 kHz float32/WAV and extract 3D jaw lip-sync viseme envelope."""
    clean_text = (text or "").strip()
    if not clean_text:
        empty = np.zeros(int(TARGET_SAMPLE_RATE * 0.2), dtype=np.float32)
        return {
            "samples": empty,
            "sample_rate": TARGET_SAMPLE_RATE,
            "duration_sec": 0.2,
            "visemes": [0.0] * max(1, int(0.2 * video_fps)),
            "engine_used": "silence",
            "normalized_text": "",
        }

    voice_meta = get_voice_meta(voice_id)
    detected_lang = language or detect_script_language(clean_text)
    normalized_text = clean_text

    if detected_lang == "roman_ur":
        urdu_mapped, _ = normalize_roman_urdu_for_tts(clean_text)
        normalized_text = urdu_mapped
        espeak_voice = voice_meta["espeak_voice"] if voice_meta["language"] == "ur" else "ur+m1"
    elif detected_lang == "ur":
        espeak_voice = voice_meta["espeak_voice"] if voice_meta["language"] == "ur" else "ur+m1"
    else:
        espeak_voice = voice_meta["espeak_voice"]

    raw_samples: np.ndarray | None = None
    raw_sr = TARGET_SAMPLE_RATE
    engine_used = "espeak-ng-local"

    if voice_id == "piper_neural_local":
        piper_res = _try_piper_onnx_synth(clean_text, speed)
        if piper_res is not None:
            raw_samples, raw_sr = piper_res
            engine_used = "piper-onnx-local"

    if raw_samples is None:
        espeak_pair = _get_espeak_lib()
        if espeak_pair is not None:
            lib, sr = espeak_pair
            emo_rate, emo_pitch, emo_range = EMOTION_MODIFIERS.get(emotion, EMOTION_MODIFIERS["neutral"])
            rate_wpm = int(max(85, min(340, voice_meta["base_rate"] * float(speed) * emo_rate)))
            pitch_val = int(max(5, min(95, voice_meta["base_pitch"] * float(pitch) * emo_pitch)))

            pcm_buffers: list[bytes] = []

            @_SYNTH_CB_TYPE
            def _cb(wav_ptr: Any, numsamples: int, events: Any) -> int:
                if wav_ptr and numsamples > 0:
                    pcm_buffers.append(ctypes.string_at(wav_ptr, numsamples * 2))
                return 0

            with _ESPEAK_LOCK:
                lib.espeak_SetSynthCallback(_cb)
                rc = lib.espeak_SetVoiceByName(espeak_voice.encode("utf-8"))
                if rc != 0:
                    fallback_v = b"ur" if detected_lang in {"ur", "roman_ur"} else b"en"
                    lib.espeak_SetVoiceByName(fallback_v)
                lib.espeak_SetParameter(1, rate_wpm, 0)  # espeakRATE
                lib.espeak_SetParameter(2, 100, 0)       # espeakVOLUME
                lib.espeak_SetParameter(3, pitch_val, 0) # espeakPITCH
                lib.espeak_SetParameter(4, emo_range, 0) # espeakRANGE
                utf8_bytes = normalized_text.encode("utf-8")
                # flags=1 -> espeakCHARS_UTF8
                lib.espeak_Synth(utf8_bytes, len(utf8_bytes) + 1, 0, 0, 0, 1, None, None)

            pcm_all = b"".join(pcm_buffers)
            if pcm_all:
                raw_samples = np.frombuffer(pcm_all, dtype=np.int16).astype(np.float32) / 32768.0
                raw_sr = sr

    if raw_samples is None or raw_samples.size == 0:
        # Pure DSP fallback vowel cadence if C library unavailable
        engine_used = "procedural-formant-fallback"
        dur = max(0.8, min(8.0, len(clean_text.split()) * 0.36 / max(0.5, speed)))
        t = np.linspace(0, dur, int(TARGET_SAMPLE_RATE * dur), endpoint=False)
        f0 = (125.0 if voice_meta["gender"] == "male" else 210.0) * float(pitch)
        syllable_env = np.clip(np.sin(2 * np.pi * 3.4 * t) * 0.6 + 0.4, 0.0, 1.0)
        carrier = 0.55 * np.sin(2 * np.pi * f0 * t) + 0.28 * np.sin(2 * np.pi * 2 * f0 * t) + 0.14 * np.sin(2 * np.pi * 3 * f0 * t)
        raw_samples = (carrier * syllable_env * 0.65).astype(np.float32)
        raw_sr = TARGET_SAMPLE_RATE

    # Resample to 44100 Hz
    if raw_sr != TARGET_SAMPLE_RATE and raw_samples.size > 8:
        target_len = int(round(raw_samples.size * TARGET_SAMPLE_RATE / float(raw_sr)))
        resampled = signal.resample(raw_samples, max(1, target_len)).astype(np.float32)
    else:
        resampled = raw_samples.astype(np.float32)

    warmed = _apply_voice_warmth_dsp(resampled, TARGET_SAMPLE_RATE)
    visemes = compute_viseme_envelope(warmed, TARGET_SAMPLE_RATE, video_fps=video_fps)

    if output_wav_path is not None:
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        write_stereo_wav(output_wav_path, warmed, TARGET_SAMPLE_RATE)

    return {
        "samples": warmed,
        "sample_rate": TARGET_SAMPLE_RATE,
        "duration_sec": round(warmed.size / float(TARGET_SAMPLE_RATE), 3),
        "visemes": visemes,
        "engine_used": engine_used,
        "voice_id": voice_id,
        "language": detected_lang,
        "normalized_text": normalized_text,
        "wav_path": str(output_wav_path) if output_wav_path else "",
    }


def write_stereo_wav(path: Path, mono_or_stereo: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(mono_or_stereo, dtype=np.float32)
    if arr.ndim == 1:
        stereo = np.stack([arr, arr], axis=1)
    else:
        stereo = arr
    clipped = np.clip(stereo, -0.99, 0.99)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return path
