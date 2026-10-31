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

PIPER_VOICE_SLOT_DIRNAME = "piper-onnx-custom-voice"
PIPER_EN_MALE_MODEL = "en_US-joe-medium.onnx"
PIPER_EN_FEMALE_MODEL = "en_US-amy-medium.onnx"

_PIPER_LOCK = threading.RLock()
_PIPER_VOICE_CACHE: dict[tuple[str, str, int, int], Any] = {}

# Canonical English Piper filenames used when a catalog voice does not name an
# explicit model.  The first entry in each tuple is the model installed in
# ``models_data/piper-onnx-custom-voice`` for this project; the remaining
# names let operators drop in another compatible licensed English voice.
_PIPER_MODEL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "male": (
        PIPER_EN_MALE_MODEL,
        "en_US-hfc_male-medium.onnx",
        "en_US-ryan-medium.onnx",
        "en_US-john-medium.onnx",
        "en_US-bryce-medium.onnx",
        "en_GB-alan-medium.onnx",
        "en_GB-northern_english_male-medium.onnx",
    ),
    "female": (
        PIPER_EN_FEMALE_MODEL,
        "en_US-hfc_female-medium.onnx",
        "en_GB-cori-medium.onnx",
        "en_GB-alba-medium.onnx",
        "en_US-kristin-medium.onnx",
        "en_US-ljspeech-medium.onnx",
        "en_GB-jenny_dioco-medium.onnx",
    ),
}

VOICE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "en_narrator_deep",
        "name": "Atlas (Narrator — Deep Cinematic)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en-us+m3",
        "base_rate": 155,
        "base_pitch": 36,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_MALE_MODEL,
        "license": "CC0-1.0 (Piper Joe dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_male_heroic",
        "name": "Tariq EN (Protagonist — Neural Male)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en+m1",
        "base_rate": 165,
        "base_pitch": 44,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_MALE_MODEL,
        "license": "CC0-1.0 (Piper Joe dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_male_deep",
        "name": "Kael EN (Antagonist — Neural Male, Slower)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en+m4",
        "base_rate": 152,
        "base_pitch": 30,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_MALE_MODEL,
        "license": "CC0-1.0 (Piper Joe dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_male_calm",
        "name": "Idris EN (Advisor — Neural Male, Measured)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en-gb+m2",
        "base_rate": 158,
        "base_pitch": 48,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_MALE_MODEL,
        "license": "CC0-1.0 (Piper Joe dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_female_warm",
        "name": "Zara EN (Heroine — Neural Female)",
        "language": "en",
        "gender": "female",
        "espeak_voice": "en-us+f3",
        "base_rate": 164,
        "base_pitch": 66,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_FEMALE_MODEL,
        "license": "CC-BY-SA-4.0 (Piper Amy dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_female_bright",
        "name": "Noor EN (Scout — Neural Female, Brisk)",
        "language": "en",
        "gender": "female",
        "espeak_voice": "en+f2",
        "base_rate": 170,
        "base_pitch": 72,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_FEMALE_MODEL,
        "license": "CC-BY-SA-4.0 (Piper Amy dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_male_neural",
        "name": "Bilal / Joe EN (Piper Neural — Natural Male)",
        "language": "en",
        "gender": "male",
        "espeak_voice": "en+m1",
        "base_rate": 165,
        "base_pitch": 44,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_MALE_MODEL,
        "license": "CC0-1.0 (Piper Joe dataset); GPL-3.0-or-later eSpeak fallback",
    },
    {
        "id": "en_female_neural",
        "name": "Zara / Amy EN (Piper Neural — Natural Female)",
        "language": "en",
        "gender": "female",
        "espeak_voice": "en-us+f3",
        "base_rate": 164,
        "base_pitch": 66,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "piper_model": PIPER_EN_FEMALE_MODEL,
        "license": "CC-BY-SA-4.0 (Piper Amy dataset); GPL-3.0-or-later eSpeak fallback",
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
        "name": "Piper Local Neural Voice (Auto .onnx Slot)",
        "language": "en",
        "gender": "neutral",
        "espeak_voice": "en-us+f3",
        "base_rate": 162,
        "base_pitch": 55,
        "engine": "piper-onnx-local",
        "fallback_engine": "espeak-ng-local",
        "license": "Depends on user-installed ONNX voice checkpoint",
    },
]

LIPSYNC_CAPABILITY_MATRIX: list[dict[str, Any]] = [
    {
        "language": "English (en)",
        "tts_status": "implemented_offline",
        "tts_engine": "Piper Neural ONNX (Joe male / Amy female) + eSpeak-NG fallback",
        "lipsync_mode": "Frame-accurate 3D jaw viseme envelope + head/brow emphasis",
        "naturalness_note": "English prefers the local Joe/Amy Piper ONNX voices in models_data/piper-onnx-custom-voice; eSpeak-NG remains an offline fallback if a model pair is missing.",
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


def _piper_slot_dir() -> Path:
    """Return the local directory containing Piper ``.onnx``/config pairs."""

    override = (
        os.getenv("SIDD_PIPER_VOICES_DIR", "").strip()
        or os.getenv("SIDD_PIPER_MODEL_DIR", "").strip()
    )
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[1] / candidate
        return candidate.resolve()
    return (get_settings().models_dir / PIPER_VOICE_SLOT_DIRNAME).resolve()


def _piper_config_for(model_path: Path) -> Path | None:
    candidates = (
        Path(f"{model_path}.json"),
        model_path.with_suffix(".json"),
        model_path.parent / "config.json",
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def _is_usable_piper_model(model_path: Path) -> bool:
    """Reject missing files and Git-LFS pointer stubs masquerading as models."""

    try:
        if not model_path.is_file() or model_path.stat().st_size < 1_000_000:
            return False
        with model_path.open("rb") as fh:
            prefix = fh.read(64)
        return not prefix.startswith(b"version https://git-lfs.github.com/spec/v1")
    except OSError:
        return False


def _resolve_piper_model_value(value: str, slot_dir: Path) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = slot_dir / candidate
    candidate = candidate.resolve()
    if _is_usable_piper_model(candidate) and _piper_config_for(candidate):
        return candidate
    return None


def _resolve_piper_voice_model(
    voice_meta: dict[str, Any] | None = None,
    *,
    voice_id: str = "piper_neural_local",
) -> tuple[Path, Path] | None:
    """Resolve a usable local Piper model/config pair for a catalog voice.

    English male voices prefer Joe and English female voices prefer Amy.
    Explicit environment overrides win, followed by a catalog ``piper_model``
    filename, ``male``/``female`` subdirectories, canonical Piper filenames,
    and finally (for the generic slot voice) any usable model in the slot.
    """

    meta = dict(voice_meta or get_voice_meta(voice_id))
    slot_dir = _piper_slot_dir()
    if not slot_dir.is_dir():
        return None

    gender = str(meta.get("gender") or "neutral").lower()
    ordered_values: list[str] = []

    generic_override = os.getenv("SIDD_PIPER_MODEL_PATH", "").strip()
    if generic_override:
        ordered_values.append(generic_override)
    if gender == "male":
        ordered_values.append(os.getenv("SIDD_PIPER_EN_MALE_MODEL", "").strip())
    elif gender == "female":
        ordered_values.append(os.getenv("SIDD_PIPER_EN_FEMALE_MODEL", "").strip())

    ordered_values.append(str(meta.get("piper_model") or ""))

    for value in ordered_values:
        resolved = _resolve_piper_model_value(value, slot_dir)
        if resolved is not None:
            cfg = _piper_config_for(resolved)
            if cfg is not None:
                return resolved, cfg

    candidate_paths: list[Path] = []
    if gender in {"male", "female"}:
        gender_dir = slot_dir / gender
        if gender_dir.is_dir():
            candidate_paths.extend(sorted(gender_dir.glob("*.onnx")))
        candidate_paths.extend(slot_dir / name for name in _PIPER_MODEL_CANDIDATES[gender])
    else:
        # The historical generic slot defaults to the male model, then any
        # other usable pair.  Dedicated male/female catalog voices do not
        # silently cross genders just because the other model is present.
        candidate_paths.extend(slot_dir / name for name in _PIPER_MODEL_CANDIDATES["male"])
        candidate_paths.extend(slot_dir / name for name in _PIPER_MODEL_CANDIDATES["female"])
        candidate_paths.extend(sorted(slot_dir.glob("*.onnx")))
        candidate_paths.extend(sorted(slot_dir.glob("*/*.onnx")))

    seen: set[Path] = set()
    for candidate in candidate_paths:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if not _is_usable_piper_model(candidate):
            continue
        cfg = _piper_config_for(candidate)
        if cfg is not None:
            return candidate, cfg
    return None


def get_piper_voice_status() -> dict[str, Any]:
    """Describe the local English Piper voices currently usable by the API."""

    slot_dir = _piper_slot_dir()
    status: dict[str, Any] = {
        "slot_dir": str(slot_dir),
        "slot_exists": slot_dir.is_dir(),
        "voices": {},
    }
    for label, voice_id in (
        ("male", "en_male_neural"),
        ("female", "en_female_neural"),
    ):
        resolved = _resolve_piper_voice_model(get_voice_meta(voice_id), voice_id=voice_id)
        if resolved is None:
            status["voices"][label] = {"available": False, "voice_id": voice_id}
            continue
        model_path, cfg_path = resolved
        status["voices"][label] = {
            "available": True,
            "voice_id": voice_id,
            "model": model_path.name,
            "model_path": str(model_path),
            "config_path": str(cfg_path),
            "size_bytes": model_path.stat().st_size,
        }
    return status


def _load_piper_voice(model_path: Path, cfg_path: Path) -> Any:
    stat = model_path.stat()
    key = (str(model_path), str(cfg_path), int(stat.st_size), int(stat.st_mtime_ns))
    with _PIPER_LOCK:
        cached = _PIPER_VOICE_CACHE.get(key)
        if cached is not None:
            return cached
        from piper import PiperVoice  # type: ignore

        voice = PiperVoice.load(str(model_path), config_path=str(cfg_path))
        # Keep the cache intentionally tiny: the studio uses one male and
        # one female English model in normal operation.
        if len(_PIPER_VOICE_CACHE) >= 4:
            _PIPER_VOICE_CACHE.clear()
        _PIPER_VOICE_CACHE[key] = voice
        return voice


def _try_piper_onnx_synth(
    text: str,
    speed: float,
    *,
    voice_id: str = "piper_neural_local",
    voice_meta: dict[str, Any] | None = None,
    detected_lang: str = "en",
) -> tuple[np.ndarray, int, dict[str, str]] | None:
    """Synthesize English text with a local Piper ONNX voice, if installed."""

    if detected_lang != "en":
        return None

    meta = dict(voice_meta or get_voice_meta(voice_id))
    if str(meta.get("language") or "en") != "en":
        return None

    resolved = _resolve_piper_voice_model(meta, voice_id=voice_id)
    if resolved is None:
        return None
    model_path, cfg_path = resolved

    try:
        from piper import SynthesisConfig  # type: ignore

        # Catalog variants retain a little of their intended pacing even
        # though the installed release has one base model per gender.
        base_rate = float(meta.get("base_rate") or 165)
        effective_speed = max(0.5, min(2.0, float(speed) * (base_rate / 165.0)))
        syn_cfg = SynthesisConfig(length_scale=1.0 / effective_speed)
        chunks: list[np.ndarray] = []
        sr = 22050
        with _PIPER_LOCK:
            voice = _load_piper_voice(model_path, cfg_path)
            for audio_chunk in voice.synthesize(text, syn_config=syn_cfg):
                sr = int(audio_chunk.sample_rate)
                arr = (
                    np.frombuffer(audio_chunk.audio_int16_bytes, dtype=np.int16)
                    .astype(np.float32)
                    / 32768.0
                )
                if arr.size:
                    chunks.append(arr)
        if chunks:
            return (
                np.concatenate(chunks),
                sr,
                {
                    "voice_model": model_path.name,
                    "model_path": str(model_path),
                    "model_config_path": str(cfg_path),
                },
            )
    except Exception:
        return None
    return None


def _apply_voice_warmth_dsp(
    samples: np.ndarray,
    sr: int,
    *,
    preserve_neural: bool = False,
) -> np.ndarray:
    """Warm formant speech while preserving the natural detail of Piper audio."""
    if samples.size < 64:
        return samples
    if preserve_neural:
        out = samples.astype(np.float32, copy=True)
        out -= float(np.mean(out))
        peak = float(np.max(np.abs(out))) or 1.0
        if peak > 0.92:
            out *= 0.92 / peak
        return out.astype(np.float32)
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
    piper_meta: dict[str, str] = {}

    # English catalog voices now prefer the local gender-matched Piper ONNX
    # model.  Urdu/Roman-Urdu remains on eSpeak because the installed Piper
    # checkpoints are English (en_US) voices.
    should_try_piper = (
        detected_lang == "en"
        and str(voice_meta.get("language") or "en") == "en"
        and (
            voice_id == "piper_neural_local"
            or bool(voice_meta.get("piper_model"))
            or str(voice_meta.get("engine") or "") == "piper-onnx-local"
        )
    )
    if should_try_piper:
        piper_res = _try_piper_onnx_synth(
            clean_text,
            speed,
            voice_id=voice_id,
            voice_meta=voice_meta,
            detected_lang=detected_lang,
        )
        if piper_res is not None:
            raw_samples, raw_sr, piper_meta = piper_res
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
        piper_meta = {}
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

    warmed = _apply_voice_warmth_dsp(
        resampled,
        TARGET_SAMPLE_RATE,
        preserve_neural=engine_used == "piper-onnx-local",
    )
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
        "voice_model": piper_meta.get("voice_model", ""),
        "model_path": piper_meta.get("model_path", ""),
        "model_config_path": piper_meta.get("model_config_path", ""),
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
