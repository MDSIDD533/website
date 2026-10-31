"""Auto sequence build/render orchestration tests."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from typing import Any

from backend.services import motion_graphics_service as service


E2E_SCRIPT = """Bilal qile mein aata hai. Zara mash'al jalati hai. Dono baat karte hain:

Bilal kehta hai: 'Guard your left flank!' Zara kehti hai: 'Ready!'"""


def test_auto_sequence_build_only_creates_four_projects(tmp_path: Path) -> None:
    output_root = tmp_path / "auto"

    result = service.execute_auto_motion_graphics_sequence(
        script_text=E2E_SCRIPT,
        output_root=output_root,
        mode="build_only",
        fps=30,
        quality="standard",
    )

    assert result["status"] == "built"
    assert result["combined_video"] is None
    assert [clip["template"] for clip in result["clips"]] == [
        "title",
        "title",
        "title",
        "quote",
    ]
    assert result["plan"]["total_duration_sec"] == 12.009
    assert result["plan"]["estimated_speech_sec"] == 2.259

    plan = json.loads(Path(result["auto_plan_json"]).read_text(encoding="utf-8"))
    assert plan["clip_count"] == 4
    assert plan["scene_count"] == 4

    scenes = json.loads(
        Path(result["parsed_scenes_json"]).read_text(encoding="utf-8")
    )
    assert scenes[0]["actions"] == ["walk"]
    assert scenes[2]["characters"] == ["Bilal", "Zara"]

    for clip in result["clips"]:
        assert Path(clip["index_html"]).is_file()
        assert Path(clip["variables_json"]).is_file()
        assert Path(clip["build_manifest"]).is_file()


def test_dialogue_audio_timeline_places_parser_dialogue(tmp_path: Path) -> None:
    assert service._speaker_voice_id("Bilal", "Guard your left flank!") == "en_male_heroic"
    assert service._speaker_voice_id("Zara", "Ready!") == "en_female_warm"
    assert service._speaker_voice_id("Narrator", "World War II began.") == "en_narrator_deep"

    plan = service.plan_auto_sequence(E2E_SCRIPT)

    def fake_synth(
        text: str,
        *,
        speaker: str,
        output_path: str | Path,
        video_fps: int = 30,
    ) -> dict[str, Any]:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-line-wav")
        return {
            "samples": np.full(4410, 0.25, dtype=np.float32),
            "sample_rate": 44100,
            "duration_sec": 0.1,
            "engine_used": "fake-local-tts",
            "voice_id": f"fake-{speaker.lower()}",
            "voice_model": f"fake-{speaker.lower()}.onnx",
            "model_path": f"/fake/{speaker.lower()}.onnx",
            "normalized_text": text,
            "wav_path": str(path),
        }

    metadata = service.build_dialogue_audio_timeline(
        plan,
        tmp_path / "with-audio",
        video_fps=30,
        synth_line=fake_synth,
    )

    assert metadata is not None
    assert metadata["duration_sec"] == 12.009
    assert metadata["speech_duration_sec"] == 0.2
    assert metadata["first_speech_start_sec"] == 9.15
    assert metadata["last_speech_end_sec"] == 9.6
    assert metadata["trimmed_line_count"] == 0
    assert metadata["line_count"] == 2
    assert metadata["engines"] == ["fake-local-tts"]
    assert metadata["voice_models"] == ["fake-bilal.onnx", "fake-zara.onnx"]
    assert [line["speaker"] for line in metadata["lines"]] == ["Bilal", "Zara"]
    assert [line["voice_model"] for line in metadata["lines"]] == [
        "fake-bilal.onnx",
        "fake-zara.onnx",
    ]
    assert [line["text"] for line in metadata["lines"]] == [
        "Guard your left flank!",
        "Ready!",
    ]
    assert metadata["clips"]["clip-04"][0]["start_sec"] == 9.15
    assert Path(metadata["audio_json"]).is_file()

    with wave.open(metadata["audio_wav"], "rb") as wav:
        assert wav.getframerate() == 44100
        assert wav.getnchannels() == 2
        assert wav.getnframes() == round(44100 * metadata["duration_sec"])


def test_measure_dialogue_durations_uses_actual_synth_results(
    tmp_path: Path,
) -> None:
    plan = service.plan_auto_sequence(
        "Bilal says: 'Hold the torch beside the eastern wall tonight.'\n"
        "Zara says: 'I am ready and watching the road below.'"
    )
    durations_by_speaker = {"Bilal": 4.25, "Zara": 3.5}

    def fake_synth(
        text: str,
        *,
        speaker: str,
        output_path: str | Path,
        video_fps: int = 30,
    ) -> dict[str, Any]:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-preflight-wav")
        return {
            "duration_sec": durations_by_speaker[speaker],
            "engine_used": "fake-local-tts",
            "voice_model": f"fake-{speaker.lower()}.onnx",
            "wav_path": str(path),
        }

    measured = service._measure_dialogue_durations(
        plan,
        tmp_path / "preflight",
        video_fps=30,
        synth_line=fake_synth,
    )

    assert measured == {"clip-01": (4.25,), "clip-02": (3.5,)}
    assert (
        tmp_path / "preflight" / "audio-preflight" / "clip-01-line-01.wav"
    ).is_file()


MIXED_NARRATION_SCRIPT = """Title: The Global Conflict
World War II was the deadliest conflict in human history.
Bilal says: 'We must hold the line at all costs!'"""


def test_measure_speech_durations_includes_narration_and_dialogue(
    tmp_path: Path,
) -> None:
    plan = service.plan_auto_sequence(MIXED_NARRATION_SCRIPT)
    durations_by_text = {
        "The Global Conflict": 1.2,
        "World War II was the deadliest conflict in human history.": 3.4,
        "We must hold the line at all costs!": 2.2,
    }

    def fake_synth(
        text: str,
        *,
        speaker: str,
        output_path: str | Path,
        video_fps: int = 30,
    ) -> dict[str, Any]:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-preflight-wav")
        return {
            "duration_sec": durations_by_text[text],
            "engine_used": "fake-local-tts",
            "voice_id": f"fake-{speaker.lower()}",
            "voice_model": f"fake-{speaker.lower()}.onnx",
            "wav_path": str(path),
        }

    measured = service._measure_speech_durations(
        plan,
        tmp_path / "mixed-preflight",
        video_fps=30,
        synth_line=fake_synth,
        include_dialogue_audio=True,
        include_narration_audio=True,
    )

    assert measured == {
        "clip-01": (1.2,),
        "clip-02": (3.4,),
        "clip-03": (2.2,),
    }
    assert (
        tmp_path
        / "mixed-preflight"
        / "audio-preflight"
        / "clip-01-narration-01.wav"
    ).is_file()


def test_speech_timeline_narrates_non_dialogue_scenes_from_the_start(
    tmp_path: Path,
) -> None:
    plan = service.plan_auto_sequence(MIXED_NARRATION_SCRIPT)

    def fake_synth(
        text: str,
        *,
        speaker: str,
        output_path: str | Path,
        video_fps: int = 30,
    ) -> dict[str, Any]:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-line-wav")
        return {
            "samples": np.full(4410, 0.25, dtype=np.float32),
            "sample_rate": 44100,
            "duration_sec": 0.1,
            "engine_used": "fake-local-tts",
            "voice_id": f"fake-{speaker.lower()}",
            "voice_model": f"fake-{speaker.lower()}.onnx",
            "normalized_text": text,
            "wav_path": str(path),
        }

    metadata = service.build_dialogue_audio_timeline(
        plan,
        tmp_path / "mixed-audio",
        video_fps=30,
        synth_line=fake_synth,
        include_dialogue_audio=True,
        include_narration_audio=True,
    )

    assert metadata is not None
    assert metadata["line_count"] == 3
    assert metadata["narration_line_count"] == 2
    assert metadata["dialogue_line_count"] == 1
    assert metadata["first_speech_start_sec"] == 0.15
    assert [line["speech_kind"] for line in metadata["lines"]] == [
        "narration",
        "narration",
        "dialogue",
    ]
    assert [line["speaker"] for line in metadata["lines"]] == [
        "Narrator",
        "Narrator",
        "Bilal",
    ]
    assert [line["text"] for line in metadata["lines"]] == [
        "The Global Conflict",
        "World War II was the deadliest conflict in human history.",
        "We must hold the line at all costs!",
    ]
    assert [line["start_sec"] for line in metadata["lines"]] == [0.15, 3.15, 6.15]


def test_auto_sequence_render_branch_with_fake_renderer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: dict[str, Any] = {"render": [], "concat": []}

    def fake_render(**kwargs: Any) -> dict[str, Any]:
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake clip mp4")
        calls["render"].append(output)
        if kwargs.get("on_progress"):
            kwargs["on_progress"](100.0, "HyperFrames rendering (100%)")
        return {
            "output_path": str(output),
            "command_program": "fake-hyperframes",
            "elapsed_sec": 0.01,
            "log_tail": ["fake render complete"],
        }

    def fake_verify(path: str | Path) -> dict[str, Any]:
        candidate = Path(path)
        return {
            "verified": candidate.is_file() and candidate.stat().st_size > 0,
            "path": str(candidate),
            "file_size_bytes": candidate.stat().st_size if candidate.is_file() else 0,
            "method": "fake_verify",
            "video_codec": "h264",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "duration_sec": 3.0,
            "decoded_frames": 90,
        }

    def fake_concat(inputs: Any, output: str | Path, **_: Any) -> dict[str, Any]:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake combined mp4")
        calls["concat"].append((list(inputs), output_path))
        return {
            "output_path": str(output_path),
            "method": "fake_concat",
            "verification": fake_verify(output_path),
            "attempts": [],
        }

    monkeypatch.setattr(service, "render_motion_graphics_project", fake_render)
    monkeypatch.setattr(service, "verify_mp4", fake_verify)
    monkeypatch.setattr(service, "concat_mp4_files", fake_concat)

    result = service.execute_auto_motion_graphics_sequence(
        script_text="Bilal qile mein aata hai.",
        output_root=tmp_path / "auto-render",
        mode="render",
        fps=30,
        quality="standard",
    )

    assert result["status"] == "completed"
    assert len(calls["render"]) == 1
    assert len(calls["concat"]) == 1
    assert Path(result["combined_video"]).is_file()
    assert result["verification"]["verified"] is True
    assert Path(result["clips"][0]["verification_json"]).is_file()
    assert Path(result["sequence_result_json"]).is_file()


def test_concat_mp4_files_with_real_ffmpeg(tmp_path: Path) -> None:
    ffmpeg = service.ffmpeg_command()
    inputs: list[Path] = []
    for index, color in enumerate(("black", "blue"), start=1):
        clip = tmp_path / f"clip-{index}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=30:d=0.2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        inputs.append(clip)

    combined = tmp_path / "combined.mp4"
    result = service.concat_mp4_files(inputs, combined, fps=30)

    assert combined.is_file()
    assert result["verification"]["verified"] is True
    assert result["verification"]["decoded_frames"] >= 10
    assert Path(result["concat_list_path"]).is_file()
