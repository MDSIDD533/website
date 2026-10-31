"""Gender-matched local Piper ONNX routing tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from backend.core.config import get_settings
from voice_engine import tts


def _write_fake_piper_pair(slot: Path, filename: str) -> Path:
    model = slot / filename
    # Keep this above the production minimum-size guard so the test exercises
    # the same LFS-pointer rejection path as a real 63 MB checkpoint.
    model.write_bytes(b"ONNX" + (b"\0" * 1_000_001))
    Path(f"{model}.json").write_text("{}", encoding="utf-8")
    return model


def _install_fake_models(isolated_workspace: Path) -> Path:
    slot = get_settings().models_dir / tts.PIPER_VOICE_SLOT_DIRNAME
    slot.mkdir(parents=True, exist_ok=True)
    _write_fake_piper_pair(slot, tts.PIPER_EN_MALE_MODEL)
    _write_fake_piper_pair(slot, tts.PIPER_EN_FEMALE_MODEL)
    return slot


def test_piper_resolver_keeps_male_and_female_models_distinct(
    isolated_workspace: Path,
) -> None:
    slot = _install_fake_models(isolated_workspace)

    male = tts._resolve_piper_voice_model(
        tts.get_voice_meta("en_male_heroic"),
        voice_id="en_male_heroic",
    )
    female = tts._resolve_piper_voice_model(
        tts.get_voice_meta("en_female_warm"),
        voice_id="en_female_warm",
    )

    assert male is not None
    assert female is not None
    assert male[0] == (slot / tts.PIPER_EN_MALE_MODEL).resolve()
    assert female[0] == (slot / tts.PIPER_EN_FEMALE_MODEL).resolve()

    status = tts.get_piper_voice_status()
    assert status["voices"]["male"]["model"] == tts.PIPER_EN_MALE_MODEL
    assert status["voices"]["female"]["model"] == tts.PIPER_EN_FEMALE_MODEL


def test_english_synthesis_reports_gender_matched_piper_model(
    isolated_workspace: Path,
    monkeypatch: Any,
) -> None:
    _install_fake_models(isolated_workspace)

    def fake_load(model_path: Path, cfg_path: Path) -> Any:
        class FakeVoice:
            def synthesize(self, text: str, *, syn_config: Any):
                samples = np.full(2205, 4000, dtype=np.int16)
                yield SimpleNamespace(
                    sample_rate=22050,
                    audio_int16_bytes=samples.tobytes(),
                )

        return FakeVoice()

    monkeypatch.setattr(tts, "_load_piper_voice", fake_load)

    male = tts.synthesize_speech_segment(
        "Guard your left flank!",
        voice_id="en_male_heroic",
        output_wav_path=isolated_workspace / "male-neural.wav",
    )
    female = tts.synthesize_speech_segment(
        "Ready!",
        voice_id="en_female_warm",
        output_wav_path=isolated_workspace / "female-neural.wav",
    )

    assert male["engine_used"] == "piper-onnx-local"
    assert male["voice_model"] == tts.PIPER_EN_MALE_MODEL
    assert female["engine_used"] == "piper-onnx-local"
    assert female["voice_model"] == tts.PIPER_EN_FEMALE_MODEL
