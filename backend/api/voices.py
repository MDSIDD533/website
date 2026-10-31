"""Voice Studio & Sound Design API routes."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import get_settings
from story_engine.normalizer import detect_script_language, normalize_roman_urdu_for_tts
from voice_engine.sound_design import MUSIC_MOODS
from voice_engine.tts import (
    LIPSYNC_CAPABILITY_MATRIX,
    VOICE_CATALOG,
    get_piper_voice_status,
    synthesize_speech_segment,
)

router = APIRouter(prefix="/api/voices", tags=["voices"])


class VoicePreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1200)
    voice_id: str = "en_male_heroic"
    language: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=1.8)
    emotion: str = "determined"


@router.get("")
def api_list_voices() -> dict[str, Any]:
    return {
        "voices": VOICE_CATALOG,
        "piper_voices": get_piper_voice_status(),
        "lipsync_capabilities": LIPSYNC_CAPABILITY_MATRIX,
        "music_moods": MUSIC_MOODS,
    }


@router.post("/normalize-roman-urdu")
def api_normalize_roman_urdu(payload: dict[str, str]) -> dict[str, Any]:
    txt = payload.get("text", "")
    urdu_script, phonetic = normalize_roman_urdu_for_tts(txt)
    return {
        "detected_language": detect_script_language(txt),
        "urdu_script": urdu_script,
        "phonetic": phonetic,
    }


@router.post("/preview")
def api_synthesize_voice_preview(req: VoicePreviewRequest) -> dict[str, Any]:
    try:
        digest = hashlib.sha256(
            f"{req.voice_id}:{req.language}:{req.speed}:{req.pitch}:{req.emotion}:{req.text}".encode("utf-8")
        ).hexdigest()[:14]
        filename = f"voice_preview_{digest}.wav"
        out_path = get_settings().previews_dir / filename
        res = synthesize_speech_segment(
            req.text,
            voice_id=req.voice_id,
            language=req.language,
            speed=req.speed,
            pitch=req.pitch,
            emotion=req.emotion,
            output_wav_path=out_path,
        )
        return {
            "audio_url": f"/api/media/preview/previews/{filename}",
            "duration_sec": res["duration_sec"],
            "engine_used": res["engine_used"],
            "voice_id": res.get("voice_id", req.voice_id),
            "voice_model": res.get("voice_model", ""),
            "model_path": res.get("model_path", ""),
            "model_config_path": res.get("model_config_path", ""),
            "language": res["language"],
            "normalized_text": res["normalized_text"],
            "viseme_frame_count": len(res["visemes"]),
            "viseme_sample": res["visemes"][:36],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
