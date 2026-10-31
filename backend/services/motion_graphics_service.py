"""HyperFrames motion-graphics job execution service.

This module is the bridge between the persistent studio job queue and the
pure project builder in :mod:`app.motion_graphics.builder`.  The builder only
writes a self-contained HyperFrames project; this service owns the optional
local render subprocess, progress extraction, and post-render verification.

No network or paid service is used.  The renderer is whatever local
HyperFrames executable the operator has installed/configured:

* ``SIDD_HYPERFRAMES_BIN`` / ``HYPERFRAMES_BIN``: explicit CLI path;
* otherwise ``hyperframes`` from ``PATH``;
* otherwise ``npx -y hyperframes@0.8.220``.

Browser/FFmpeg discovery stays with the operator's local environment.  The
service forwards ``HYPERFRAMES_BROWSER_PATH`` and can prepend local tool
directories from ``SIDD_HF_BIN_DIR``, ``SIDD_FFMPEG_PATH`` and
``SIDD_FFPROBE_PATH``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.motion_graphics.builder import (
    HYPERFRAMES_VERSION,
    BuiltProject,
    DataBuildRequest,
    OutroBuildRequest,
    QuoteBuildRequest,
    ShapeBuildRequest,
    TitleBuildRequest,
    build_data_project,
    build_outro_project,
    build_quote_project,
    build_shape_project,
    build_title_project,
    quote_request_from_scene,
    title_request_from_scene,
)
from app.motion_graphics.auto_mapper import (
    AutoSequencePlan,
    plan_auto_sequence,
    retimed_auto_sequence,
)
from app.script_parser import DIALOGUE_LEAD_SEC, DIALOGUE_TURN_GAP_SEC, parse_script
from backend.core.config import REPO_ROOT

ProgressCallback = Callable[[float, str], None]
LogCallback = Callable[[str], None]
ProcessCallback = Callable[[subprocess.Popen[str] | None], None]
CancelCheck = Callable[[], bool]
SpeechLineSynthesizer = Callable[..., dict[str, Any]]

_PCT_JSON_RE = re.compile(r'"pct"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
_PCT_TEXT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")

_FEMALE_DIALOGUE_SPEAKERS = {
    name.lower()
    for name in ("Amina", "Amara", "Layla", "Noor", "Sara", "Zara", "Zara")
}


@dataclass(frozen=True)
class MotionTemplateSpec:
    """Registry entry for one reusable HyperFrames template."""

    template_id: str
    label: str
    description: str
    request_type: type[Any]
    build_function: Callable[..., BuiltProject]


TEMPLATE_SPECS: dict[str, MotionTemplateSpec] = {
    "title": MotionTemplateSpec(
        template_id="title",
        label="Title",
        description="Cinematic opening title with a 3D coin/glyph stage.",
        request_type=TitleBuildRequest,
        build_function=build_title_project,
    ),
    "data": MotionTemplateSpec(
        template_id="data",
        label="Data visualization",
        description="Animated bars, hero value, comparison and closing line.",
        request_type=DataBuildRequest,
        build_function=build_data_project,
    ),
    "shape": MotionTemplateSpec(
        template_id="shape",
        label="3D shape stage",
        description="Orb, cube, pyramid or ring hero with orbiting labels.",
        request_type=ShapeBuildRequest,
        build_function=build_shape_project,
    ),
    "quote": MotionTemplateSpec(
        template_id="quote",
        label="Quote / Dialogue",
        description="Centered quote with speaker attribution and optional response.",
        request_type=QuoteBuildRequest,
        build_function=build_quote_project,
    ),
    "outro": MotionTemplateSpec(
        template_id="outro",
        label="Outro",
        description="Closing card with portal corridor, credits and CTA.",
        request_type=OutroBuildRequest,
        build_function=build_outro_project,
    ),
}

TEMPLATE_IDS = tuple(TEMPLATE_SPECS)


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def template_spec(template_id: str) -> MotionTemplateSpec:
    try:
        return TEMPLATE_SPECS[template_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown motion-graphics template '{template_id}'; "
            f"expected one of {', '.join(TEMPLATE_IDS)}"
        ) from exc


def list_templates() -> list[dict[str, Any]]:
    """Return the template catalog used by the Jobs API and Studio UI."""

    catalog: list[dict[str, Any]] = []
    for spec in TEMPLATE_SPECS.values():
        default_request = spec.request_type()
        catalog.append(
            {
                "id": spec.template_id,
                "label": spec.label,
                "description": spec.description,
                "hyperframes_version": HYPERFRAMES_VERSION,
                "request_fields": [field.name for field in fields(spec.request_type)],
                "default_request": _json_safe(default_request),
                "default_variables": _json_safe(default_request.variables()),
                "variable_schema": _json_safe(default_request.variable_schema()),
            }
        )
    return catalog


def _pop_present(payload: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: payload.pop(name) for name in names if name in payload}


def _first_dialogue_scene(scenes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for scene in scenes:
        if scene.get("dialogue"):
            return scene
    return None


def prepare_request(
    template_id: str,
    request_payload: Mapping[str, Any] | None = None,
    *,
    script_text: str = "",
) -> tuple[Any, list[dict[str, Any]]]:
    """Validate a template request and optionally derive copy from a script.

    The rule-based parser is reused exactly as-is.  Only templates with an
    existing scene adapter (Title and Quote) derive copy from parser output;
    the others keep their explicit request values/defaults and merely return
    the parsed scenes for preview/audit.  That avoids inventing chart data or
    marketing copy that the parser never claimed to extract.
    """

    spec = template_spec(template_id)
    payload: dict[str, Any] = dict(request_payload or {})
    scenes = parse_script(script_text) if str(script_text or "").strip() else []

    try:
        if scenes and template_id == "title":
            default_lines = TitleBuildRequest().title_lines
            title_lines = payload.pop("title_lines", default_lines)
            adapter_values = _pop_present(
                payload,
                ("sublines", "accent_line", "kicker", "glyph", "coin_label"),
            )
            request = title_request_from_scene(
                scenes[0], title_lines=title_lines, **adapter_values
            )
            if payload:
                request = replace(request, **payload)
            return request, scenes

        if scenes and template_id == "quote":
            scene = _first_dialogue_scene(scenes)
            if scene is None:
                raise ValueError(
                    "Quote template needs at least one dialogue line in script_text, "
                    "or explicit quote_lines/speaker_name in request"
                )
            adapter_values = _pop_present(
                payload,
                (
                    "quote_lines",
                    "speaker_name",
                    "speaker_role",
                    "response_speaker",
                    "response_line",
                    "include_response",
                    "accent_line",
                    "kicker",
                    "context_line",
                ),
            )
            request = quote_request_from_scene(scene, **adapter_values)
            if payload:
                request = replace(request, **payload)
            return request, scenes

        return spec.request_type(**payload), scenes
    except (TypeError, ValueError) as exc:
        # Re-raise as ValueError so API layers can map every bad template
        # payload to one predictable client-error response.
        raise ValueError(str(exc)) from exc


def build_motion_graphics_project(
    template_id: str,
    request_payload: Mapping[str, Any] | None,
    *,
    script_text: str,
    output_dir: str | Path,
) -> tuple[BuiltProject, Any, list[dict[str, Any]]]:
    """Prepare and write one self-contained HyperFrames project."""

    spec = template_spec(template_id)
    request, scenes = prepare_request(
        template_id, request_payload, script_text=script_text
    )
    result = spec.build_function(request, output_dir, overwrite=True)
    return result, request, scenes


def plan_auto_motion_graphics(
    script_text: str,
    *,
    brand_label: str = "SIDD STUDIO",
) -> AutoSequencePlan:
    """Plan a deterministic multi-clip sequence from a complete script."""

    return plan_auto_sequence(script_text, brand_label=brand_label)


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def hyperframes_command() -> list[str]:
    """Resolve the local HyperFrames CLI command."""

    explicit = (
        os.getenv("SIDD_HYPERFRAMES_BIN", "").strip()
        or os.getenv("HYPERFRAMES_BIN", "").strip()
    )
    if explicit:
        return [explicit]

    discovered = shutil.which("hyperframes")
    if discovered:
        return [discovered]

    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", f"hyperframes@{HYPERFRAMES_VERSION}"]

    raise RuntimeError(
        "HyperFrames CLI not found. Install hyperframes@"
        f"{HYPERFRAMES_VERSION} locally or set SIDD_HYPERFRAMES_BIN."
    )


def hyperframes_environment() -> dict[str, str]:
    """Build the subprocess environment for a local HyperFrames render."""

    env = os.environ.copy()
    env.setdefault("HYPERFRAMES_TELEMETRY_DISABLED", "1")

    browser = (
        os.getenv("SIDD_HYPERFRAMES_BROWSER_PATH", "").strip()
        or os.getenv("HYPERFRAMES_BROWSER_PATH", "").strip()
    )
    if browser:
        if not Path(browser).expanduser().is_file():
            raise RuntimeError(f"Configured Chromium executable not found: {browser}")
        env["HYPERFRAMES_BROWSER_PATH"] = browser

    path_prefixes: list[str] = []
    hf_bin_dir = os.getenv("SIDD_HF_BIN_DIR", "").strip()
    if hf_bin_dir:
        path_prefixes.append(hf_bin_dir)
    for env_name in ("SIDD_FFMPEG_PATH", "SIDD_FFPROBE_PATH"):
        candidate = os.getenv(env_name, "").strip()
        if candidate:
            path_prefixes.append(str(Path(candidate).expanduser().parent))
    if path_prefixes:
        existing = env.get("PATH", "")
        env["PATH"] = os.pathsep.join([*path_prefixes, existing] if existing else path_prefixes)

    ld_library_path = (
        os.getenv("SIDD_CHROMIUM_LD_LIBRARY_PATH", "").strip()
        or os.getenv("SIDD_LD_LIBRARY_PATH", "").strip()
    )
    if ld_library_path:
        env["LD_LIBRARY_PATH"] = ld_library_path

    fontconfig_path = (
        os.getenv("SIDD_FONTCONFIG_PATH", "").strip()
        or os.getenv("FONTCONFIG_PATH", "").strip()
    )
    if fontconfig_path:
        env["FONTCONFIG_PATH"] = fontconfig_path

    return env


def _extract_progress(line: str) -> float | None:
    match = _PCT_JSON_RE.search(line) or _PCT_TEXT_RE.search(line)
    if not match:
        return None
    try:
        return max(0.0, min(100.0, float(match.group(1))))
    except ValueError:
        return None


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def render_motion_graphics_project(
    *,
    project_dir: str | Path,
    variables: Mapping[str, Any],
    output_path: str | Path,
    fps: int = 60,
    quality: str = "standard",
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Render a generated project with the pinned/local HyperFrames CLI."""

    project_root = Path(project_dir).resolve()
    output = Path(output_path).resolve()
    if not (project_root / "index.html").is_file():
        raise FileNotFoundError(f"HyperFrames project index not found: {project_root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    command = [
        *hyperframes_command(),
        "render",
        ".",
        "--output",
        str(output),
        "--fps",
        str(int(fps)),
        "--quality",
        str(quality),
        "--variables",
        json.dumps(dict(variables), ensure_ascii=False, separators=(",", ":")),
        "--strict-variables",
    ]
    env = hyperframes_environment()
    started = time.time()
    if on_log:
        on_log("HyperFrames render command resolved: " + " ".join(command[:2]))

    proc = subprocess.Popen(
        command,
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    if on_process:
        on_process(proc)

    tail: list[str] = []
    last_reported = -10.0
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            if is_cancelled and is_cancelled():
                _terminate_process(proc)
                raise InterruptedError("Motion-graphics render cancelled by user.")

            line = raw_line.strip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-80:]

            pct = _extract_progress(line)
            if pct is not None and on_progress and pct >= last_reported + 2.0:
                last_reported = pct
                on_progress(pct, f"HyperFrames rendering ({pct:.0f}%)")
            elif on_log and (
                "Render complete" in line
                or "rendered in" in line
                or line.startswith("◇")
                or "ERROR" in line
                or "Error" in line
            ):
                on_log(line[:500])

        return_code = proc.wait(timeout=30)
    finally:
        if on_process:
            on_process(None)

    if is_cancelled and is_cancelled():
        raise InterruptedError("Motion-graphics render cancelled by user.")
    if return_code != 0:
        details = "\n".join(tail[-20:])
        raise RuntimeError(
            f"HyperFrames render exited with code {return_code}: {details}"
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"HyperFrames reported success but MP4 was not created: {output}")

    return {
        "output_path": str(output),
        "command_program": command[0],
        "elapsed_sec": round(time.time() - started, 3),
        "log_tail": tail[-30:],
    }


def verify_mp4(path: str | Path) -> dict[str, Any]:
    """Verify an MP4 from disk, preferring a full PyAV decode.

    A successful verification means the file exists, has a video stream, has a
    positive duration, and decodes at least one frame.  When PyAV is present
    (the project requirement), every video frame is decoded and counted.
    """

    mp4 = Path(path).resolve()
    result: dict[str, Any] = {
        "verified": False,
        "path": str(mp4),
        "file_size_bytes": mp4.stat().st_size if mp4.is_file() else 0,
        "method": None,
    }
    if not mp4.is_file() or result["file_size_bytes"] == 0:
        result["error"] = "MP4 file is missing or empty"
        return result

    try:
        import av  # type: ignore
    except Exception:
        av = None  # type: ignore[assignment]

    if av is not None:
        try:
            container = av.open(str(mp4))
            try:
                streams = [
                    {"type": stream.type, "codec": stream.codec_context.name}
                    for stream in container.streams
                ]
                video = container.streams.video[0]
                frame_count = sum(1 for _ in container.decode(video=0))
                duration = (
                    float(video.duration * video.time_base)
                    if video.duration
                    else (container.duration / 1_000_000 if container.duration else None)
                )
                result.update(
                    {
                        "verified": frame_count > 0 and bool(duration and duration > 0),
                        "method": "pyav_full_decode",
                        "streams": streams,
                        "video_codec": video.codec_context.name,
                        "width": int(video.codec_context.width),
                        "height": int(video.codec_context.height),
                        "fps": float(video.average_rate) if video.average_rate else None,
                        "duration_sec": duration,
                        "decoded_frames": frame_count,
                    }
                )
                return result
            finally:
                container.close()
        except Exception as exc:
            result["method"] = "pyav_full_decode"
            result["error"] = str(exc)
            return result

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-count_frames",
                    "-show_entries",
                    "stream=codec_name,width,height,avg_frame_rate,duration,nb_read_frames",
                    "-show_entries",
                    "format=duration,size",
                    "-of",
                    "json",
                    str(mp4),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            data = json.loads(proc.stdout or "{}")
            stream = (data.get("streams") or [{}])[0]
            frames = int(stream.get("nb_read_frames") or 0)
            result.update(
                {
                    "verified": proc.returncode == 0 and frames > 0,
                    "method": "ffprobe_count_frames",
                    "video_codec": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "fps": stream.get("avg_frame_rate"),
                    "duration_sec": stream.get("duration")
                    or (data.get("format") or {}).get("duration"),
                    "decoded_frames": frames,
                }
            )
            return result
        except Exception as exc:
            result["method"] = "ffprobe_count_frames"
            result["error"] = str(exc)
            return result

    result["error"] = "Neither PyAV nor ffprobe is available for MP4 verification"
    return result


def ffmpeg_command() -> str:
    """Resolve a local FFmpeg executable for sequence concatenation."""

    explicit = os.getenv("SIDD_FFMPEG_PATH", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        discovered = shutil.which(explicit)
        if discovered:
            return discovered
        raise RuntimeError(f"Configured FFmpeg executable not found: {explicit}")

    hf_bin_dir = os.getenv("SIDD_HF_BIN_DIR", "").strip()
    if hf_bin_dir:
        candidate = Path(hf_bin_dir).expanduser() / "ffmpeg"
        if candidate.is_file():
            return str(candidate)

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    try:
        import imageio_ffmpeg  # type: ignore

        candidate = Path(imageio_ffmpeg.get_ffmpeg_exe()).expanduser()
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass

    raise RuntimeError(
        "FFmpeg not found. Install it locally or set SIDD_FFMPEG_PATH / "
        "SIDD_HF_BIN_DIR."
    )


def _run_ffmpeg_once(
    command: list[str],
    *,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=hyperframes_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    if on_process:
        on_process(proc)

    tail: list[str] = []
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            if is_cancelled and is_cancelled():
                _terminate_process(proc)
                raise InterruptedError("FFmpeg sequence concatenation cancelled.")
            line = raw_line.strip()
            if line:
                tail.append(line)
                tail = tail[-80:]
        return_code = proc.wait(timeout=30)
    finally:
        if on_process:
            on_process(None)

    if is_cancelled and is_cancelled():
        raise InterruptedError("FFmpeg sequence concatenation cancelled.")
    if on_log and tail:
        on_log(tail[-1][:500])
    return {
        "return_code": return_code,
        "elapsed_sec": round(time.time() - started, 3),
        "log_tail": tail[-30:],
    }


def _speaker_voice_id(speaker: str, text: str) -> str:
    """Choose a local catalog voice for one parsed dialogue speaker."""

    try:
        from story_engine.normalizer import detect_script_language

        language = detect_script_language(text)
    except Exception:
        language = "en"

    normalized_speaker = str(speaker or "").strip().lower()
    if normalized_speaker in {"narrator", "narration", "voiceover", "voice-over"}:
        return (
            "ur_narrator_deep"
            if language in {"ur", "roman_ur"}
            else "en_narrator_deep"
        )

    is_female = normalized_speaker in _FEMALE_DIALOGUE_SPEAKERS
    if language in {"ur", "roman_ur"}:
        return "ur_female_warm" if is_female else "ur_male_heroic"
    return "en_female_warm" if is_female else "en_male_heroic"


def _synthesize_speech_line(
    text: str,
    *,
    speaker: str,
    output_path: str | Path,
    video_fps: int = 30,
) -> dict[str, Any]:
    """Synthesize one dialogue line with the existing fully local TTS stack.

    English dialogue prefers the gender-matched local Piper ONNX models
    (Joe for male speakers such as Bilal, Amy for female speakers such as
    Zara).  eSpeak-NG remains an honest offline fallback when a model pair
    is unavailable.  No network or hosted speech API is involved.
    """

    from voice_engine.tts import synthesize_speech_segment

    return synthesize_speech_segment(
        text,
        voice_id=_speaker_voice_id(speaker, text),
        video_fps=int(video_fps),
        output_wav_path=Path(output_path),
    )


def _clip_speech_entries(
    clip: Any,
    scene: Mapping[str, Any],
    *,
    include_dialogue_audio: bool = True,
    include_narration_audio: bool = False,
) -> tuple[dict[str, str], ...]:
    """Return the spoken entries owned by one clip, in script order.

    Extracted dialogue is preferred.  Only when a scene has no dialogue can
    its exact source sentence be used as narration; this prevents reading a
    line such as ``Bilal says: '...'`` aloud in addition to Bilal's own
    dialogue.  The narration text normally comes from the auto-plan so the
    same deterministic copy is used for preflight measurement and final
    timeline placement.
    """

    entries: list[dict[str, str]] = []
    dialogue = scene.get("dialogue") or []
    if include_dialogue_audio:
        for entry in dialogue:
            if not isinstance(entry, Mapping):
                continue
            speaker = str(entry.get("speaker") or "Speaker").strip() or "Speaker"
            text = str(entry.get("line") or "").strip()
            if text:
                entries.append(
                    {
                        "speaker": speaker,
                        "line": text,
                        "speech_kind": "dialogue",
                    }
                )
    if entries:
        return tuple(entries)

    if include_narration_audio and not dialogue:
        narration_text = str(getattr(clip, "narration_text", "") or "").strip()
        if not narration_text:
            sentence_text = str(getattr(clip, "sentence_text", "") or "").strip()
            narration_text = re.sub(
                r"^title\s*:\s*", "", sentence_text, flags=re.IGNORECASE
            ).strip()
        if narration_text:
            entries.append(
                {
                    "speaker": "Narrator",
                    "line": narration_text,
                    "speech_kind": "narration",
                }
            )
    return tuple(entries)


def _measure_speech_durations(
    plan: AutoSequencePlan,
    output_dir: str | Path,
    *,
    video_fps: int = 30,
    synth_line: SpeechLineSynthesizer | None = None,
    on_log: LogCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    include_dialogue_audio: bool = True,
    include_narration_audio: bool = False,
) -> dict[str, tuple[float, ...]]:
    """Synthesize planned speech once to measure real local-TTS durations.

    The preflight files are kept under ``audio-preflight`` as auditable
    evidence.  Returning one duration per line lets the auto-mapper size
    each video clip to the actual Joe/Amy (or truthful fallback) speech
    before HyperFrames renders it, instead of relying only on a word-rate
    estimate and leaving long silent tails.
    """

    synthesize = synth_line or _synthesize_speech_line
    scenes_by_id: dict[int, Mapping[str, Any]] = {}
    for scene in plan.scenes:
        try:
            scenes_by_id[int(scene.get("scene_id") or 0)] = scene
        except Exception:
            continue

    measured: dict[str, tuple[float, ...]] = {}
    preflight_dir = Path(output_dir).resolve() / "audio-preflight"

    for clip in plan.clips:
        scene = scenes_by_id.get(int(clip.scene_id), {})
        speech_entries = _clip_speech_entries(
            clip,
            scene,
            include_dialogue_audio=include_dialogue_audio,
            include_narration_audio=include_narration_audio,
        )
        durations: list[float] = []

        for line_index, entry in enumerate(speech_entries, start=1):
            if is_cancelled and is_cancelled():
                raise InterruptedError(
                    "Auto sequence cancelled during speech preflight."
                )
            speaker = str(entry.get("speaker") or "Speaker").strip() or "Speaker"
            text = str(entry.get("line") or "").strip()
            speech_kind = str(entry.get("speech_kind") or "dialogue")
            if not text:
                continue

            preflight_dir.mkdir(parents=True, exist_ok=True)
            file_kind = "line" if speech_kind == "dialogue" else speech_kind
            line_wav = (
                preflight_dir / f"{clip.clip_id}-{file_kind}-{line_index:02d}.wav"
            )
            result = synthesize(
                text,
                speaker=speaker,
                output_path=line_wav,
                video_fps=int(video_fps),
            )

            duration = 0.0
            try:
                duration = float(result.get("duration_sec") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            if duration <= 0:
                raw_samples = result.get("samples")
                if raw_samples is not None:
                    try:
                        import numpy as np

                        samples = np.asarray(raw_samples)
                        frame_count = (
                            int(samples.shape[0])
                            if samples.ndim > 1
                            else int(samples.size)
                        )
                        sample_rate = int(result.get("sample_rate") or 44100)
                        duration = frame_count / float(sample_rate)
                    except Exception:
                        duration = 0.0
            if duration <= 0:
                raise RuntimeError(
                    "Speech preflight produced no measurable audio for "
                    f"{clip.clip_id} line {line_index} ({speaker})."
                )

            measured_duration = round(float(duration), 3)
            durations.append(measured_duration)
            if on_log:
                engine_used = str(result.get("engine_used") or "local-tts")
                voice_model = str(result.get("voice_model") or "")
                model_suffix = f" ({voice_model})" if voice_model else ""
                on_log(
                    f"Measured {speech_kind} for retiming "
                    f"{clip.clip_id}: {speaker} via {engine_used}{model_suffix} "
                    f"= {measured_duration:.3f}s"
                )

        if durations:
            measured[clip.clip_id] = tuple(durations)

    return measured


def _measure_dialogue_durations(
    plan: AutoSequencePlan,
    output_dir: str | Path,
    *,
    video_fps: int = 30,
    synth_line: SpeechLineSynthesizer | None = None,
    on_log: LogCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, tuple[float, ...]]:
    """Backward-compatible dialogue-only preflight measurement."""

    return _measure_speech_durations(
        plan,
        output_dir,
        video_fps=video_fps,
        synth_line=synth_line,
        on_log=on_log,
        is_cancelled=is_cancelled,
        include_dialogue_audio=True,
        include_narration_audio=False,
    )


def build_dialogue_audio_timeline(
    plan: AutoSequencePlan,
    output_dir: str | Path,
    *,
    video_fps: int = 30,
    synth_line: SpeechLineSynthesizer | None = None,
    on_log: LogCallback | None = None,
    include_dialogue_audio: bool = True,
    include_narration_audio: bool = False,
) -> dict[str, Any] | None:
    """Create one WAV timeline from planned dialogue/narration speech.

    Speech is placed inside the clip that owns its parsed scene, preserving
    parser order.  Dialogue is preferred; narration is used only for scenes
    without extracted dialogue when explicitly enabled.  Other clips remain
    silent so the WAV duration matches the planned combined-video duration
    and can be muxed without re-timing video.  Lines that do not fit inside
    their clip are trimmed and marked as such in the returned metadata
    rather than silently shifting later scenes.
    """

    import numpy as np

    from voice_engine.tts import TARGET_SAMPLE_RATE, write_stereo_wav

    synthesize = synth_line or _synthesize_speech_line
    sample_rate = int(TARGET_SAMPLE_RATE)
    total_duration = float(
        plan.total_duration_sec
        or sum(float(clip.duration_sec) for clip in plan.clips)
    )
    timeline = np.zeros(int(round(total_duration * sample_rate)), dtype=np.float32)

    scenes_by_id: dict[int, Mapping[str, Any]] = {}
    for scene in plan.scenes:
        try:
            scenes_by_id[int(scene.get("scene_id") or 0)] = scene
        except Exception:
            continue

    audio_dir = Path(output_dir).resolve() / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    all_lines: list[dict[str, Any]] = []
    lines_by_clip: dict[str, list[dict[str, Any]]] = {}
    engines: set[str] = set()
    voice_models: set[str] = set()
    timeline_offset_sec = 0.0

    for clip in plan.clips:
        scene = scenes_by_id.get(int(clip.scene_id), {})
        speech_entries = _clip_speech_entries(
            clip,
            scene,
            include_dialogue_audio=include_dialogue_audio,
            include_narration_audio=include_narration_audio,
        )
        cursor_sec = DIALOGUE_LEAD_SEC
        clip_lines: list[dict[str, Any]] = []

        for line_index, entry in enumerate(speech_entries, start=1):
            speaker = str(entry.get("speaker") or "Speaker").strip() or "Speaker"
            text = str(entry.get("line") or "").strip()
            speech_kind = str(entry.get("speech_kind") or "dialogue")
            if not text:
                continue

            file_kind = "line" if speech_kind == "dialogue" else speech_kind
            line_wav = audio_dir / f"{clip.clip_id}-{file_kind}-{line_index:02d}.wav"
            result = synthesize(
                text,
                speaker=speaker,
                output_path=line_wav,
                video_fps=int(video_fps),
            )

            raw_samples_value = result.get("samples")
            if raw_samples_value is None:
                samples = np.asarray([], dtype=np.float32)
            else:
                samples = np.asarray(raw_samples_value, dtype=np.float32)
            if samples.ndim > 1:
                samples = np.mean(samples, axis=1).astype(np.float32)
            samples = samples.reshape(-1)

            source_rate = int(result.get("sample_rate") or sample_rate)
            if source_rate != sample_rate and samples.size > 1:
                target_len = int(round(samples.size * sample_rate / source_rate))
                source_x = np.linspace(0.0, 1.0, samples.size, endpoint=False)
                target_x = np.linspace(0.0, 1.0, max(1, target_len), endpoint=False)
                samples = np.interp(target_x, source_x, samples).astype(np.float32)

            start_sec = timeline_offset_sec + cursor_sec
            start_idx = int(round(start_sec * sample_rate))
            clip_end_idx = int(
                round((timeline_offset_sec + float(clip.duration_sec)) * sample_rate)
            )
            available = max(0, min(clip_end_idx, timeline.size) - start_idx)
            placed = int(min(int(samples.size), available))
            if placed > 0:
                timeline[start_idx : start_idx + placed] += samples[:placed]

            engine_used = str(result.get("engine_used") or "local-tts")
            engines.add(engine_used)
            voice_model = str(result.get("voice_model") or "")
            if voice_model:
                voice_models.add(voice_model)
            line_meta: dict[str, Any] = {
                "clip_id": clip.clip_id,
                "scene_id": int(clip.scene_id),
                "speaker": speaker,
                "speech_kind": speech_kind,
                "text": text,
                "normalized_text": str(result.get("normalized_text") or text),
                "voice_id": str(result.get("voice_id") or _speaker_voice_id(speaker, text)),
                "engine_used": engine_used,
                "voice_model": voice_model,
                "model_path": str(result.get("model_path") or ""),
                "model_config_path": str(result.get("model_config_path") or ""),
                "wav_path": str(line_wav),
                "start_sec": round(float(start_sec), 3),
                "duration_sec": round(float(samples.size / sample_rate), 3)
                if sample_rate
                else 0.0,
                "placed_duration_sec": round(float(placed / sample_rate), 3)
                if sample_rate
                else 0.0,
                "trimmed": bool(samples.size > placed),
            }
            clip_lines.append(line_meta)
            all_lines.append(line_meta)
            cursor_sec += (
                placed / float(sample_rate) if sample_rate else 0.0
            ) + DIALOGUE_TURN_GAP_SEC

            if on_log:
                model_suffix = f" ({voice_model})" if voice_model else ""
                on_log(
                    f"Generated local {speech_kind} audio for {clip.clip_id}: "
                    f"{speaker} via {engine_used}{model_suffix} "
                    f"({line_meta['placed_duration_sec']}s at {line_meta['start_sec']}s)"
                )

        if clip_lines:
            lines_by_clip[clip.clip_id] = clip_lines
        timeline_offset_sec += float(clip.duration_sec)

    if not all_lines:
        return None

    peak = float(np.max(np.abs(timeline))) if timeline.size else 0.0
    if peak > 0.99:
        timeline = (timeline * (0.89 / peak)).astype(np.float32)

    timeline_wav = audio_dir / "dialogue-audio.wav"
    write_stereo_wav(timeline_wav, timeline, sample_rate)

    first_speech_start_sec = min(
        (float(line["start_sec"]) for line in all_lines), default=0.0
    )
    last_speech_end_sec = max(
        (
            float(line["start_sec"]) + float(line["placed_duration_sec"])
            for line in all_lines
        ),
        default=0.0,
    )
    placed_speech_sec = round(
        sum(float(line["placed_duration_sec"]) for line in all_lines), 3
    )

    metadata: dict[str, Any] = {
        "audio_wav": str(timeline_wav),
        "sample_rate": sample_rate,
        "duration_sec": round(float(total_duration), 3),
        "line_count": len(all_lines),
        "dialogue_line_count": int(
            sum(1 for line in all_lines if line.get("speech_kind") == "dialogue")
        ),
        "narration_line_count": int(
            sum(1 for line in all_lines if line.get("speech_kind") == "narration")
        ),
        "include_dialogue_audio": bool(include_dialogue_audio),
        "include_narration_audio": bool(include_narration_audio),
        "engines": sorted(engines),
        "voice_models": sorted(voice_models),
        "speech_duration_sec": placed_speech_sec,
        "speech_coverage_pct": round(
            (placed_speech_sec / float(total_duration) * 100.0)
            if total_duration > 0
            else 0.0,
            3,
        ),
        "first_speech_start_sec": round(first_speech_start_sec, 3),
        "last_speech_end_sec": round(last_speech_end_sec, 3),
        "trimmed_line_count": int(
            sum(1 for line in all_lines if bool(line.get("trimmed")))
        ),
        "lines": all_lines,
        "clips": lines_by_clip,
    }
    metadata_path = audio_dir / "dialogue-audio.json"
    metadata["audio_json"] = str(metadata_path)
    _write_json(metadata_path, metadata)
    return _json_safe(metadata)


def mux_audio_into_mp4(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Mux a WAV timeline into a rendered MP4 without re-encoding video."""

    video = Path(video_path).resolve()
    audio = Path(audio_path).resolve()
    output = Path(output_path).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Video MP4 missing for audio mux: {video}")
    if not audio.is_file():
        raise FileNotFoundError(f"Audio file missing for audio mux: {audio}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    command = [
        ffmpeg_command(),
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]
    run = _run_ffmpeg_once(
        command,
        on_log=on_log,
        on_process=on_process,
        is_cancelled=is_cancelled,
    )
    if run["return_code"] != 0 or not output.is_file():
        raise RuntimeError(f"FFmpeg audio mux failed: {run}")

    verification = verify_mp4(output)
    streams = verification.get("streams") or []
    has_audio = any(
        isinstance(stream, Mapping) and stream.get("type") == "audio"
        for stream in streams
    )
    if not verification.get("verified") or (streams and not has_audio):
        raise RuntimeError(
            "Muxed MP4 failed verification or has no audio stream: "
            + str(verification.get("error") or verification)
        )

    return {
        "output_path": str(output),
        "video_path": str(video),
        "audio_path": str(audio),
        "run": run,
        "verification": verification,
    }


def concat_mp4_files(
    input_paths: Sequence[str | Path],
    output_path: str | Path,
    *,
    fps: int = 30,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Concatenate same-format MP4 clips and verify the combined result.

    Stream copy is attempted first.  If that output cannot be verified, a
    deterministic H.264 re-encode at the requested FPS is used instead.
    """

    inputs = [Path(path).resolve() for path in input_paths]
    if not inputs:
        raise ValueError("at least one MP4 is required for concatenation")
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"MP4 clip(s) missing for concatenation: {missing}")

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    list_path = output.with_suffix(".concat.txt")
    list_path.write_text(
        "\n".join(
            "file '" + str(path).replace("'", "'\\''") + "'" for path in inputs
        )
        + "\n",
        encoding="utf-8",
    )

    ffmpeg = ffmpeg_command()
    attempts: list[dict[str, Any]] = []
    candidates: list[tuple[str, Path, list[str]]] = [
        (
            "stream_copy",
            output.with_name(f"{output.stem}.copy.mp4"),
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
            ],
        ),
        (
            "reencode_h264",
            output.with_name(f"{output.stem}.reencode.mp4"),
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-vf",
                f"fps={int(fps)},format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-an",
                "-movflags",
                "+faststart",
            ],
        ),
    ]

    for method, candidate, base_command in candidates:
        if candidate.exists():
            candidate.unlink()
        command = [*base_command, str(candidate)]
        run = _run_ffmpeg_once(
            command,
            on_log=on_log,
            on_process=on_process,
            is_cancelled=is_cancelled,
        )
        attempt: dict[str, Any] = {"method": method, **run}
        verification: dict[str, Any] | None = None
        if run["return_code"] == 0 and candidate.is_file():
            verification = verify_mp4(candidate)
            attempt["verification"] = verification
        attempts.append(attempt)

        if verification and verification.get("verified"):
            candidate.replace(output)
            return {
                "output_path": str(output),
                "concat_list_path": str(list_path),
                "method": method,
                "verification": verification,
                "attempts": attempts,
            }

        if candidate.exists():
            candidate.unlink()
        if on_log:
            on_log(
                f"FFmpeg {method} concat did not produce a verified MP4; "
                "trying the next deterministic method."
            )

    details = json.dumps(_json_safe(attempts), ensure_ascii=False)[-3000:]
    raise RuntimeError(f"Unable to create a verified combined MP4: {details}")


def execute_auto_motion_graphics_sequence(
    *,
    script_text: str,
    output_root: str | Path,
    mode: str = "render",
    fps: int = 30,
    quality: str = "standard",
    brand_label: str = "SIDD STUDIO",
    include_dialogue_audio: bool = False,
    include_narration_audio: bool = False,
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Plan, build, render, verify, and concatenate an automatic sequence."""

    if mode not in {"build_only", "render"}:
        raise ValueError("auto sequence mode must be 'build_only' or 'render'")

    started = time.time()
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    plan = plan_auto_sequence(script_text, brand_label=brand_label)
    speech_retiming: dict[str, Any] | None = None
    include_speech_audio = include_dialogue_audio or include_narration_audio
    if include_speech_audio and mode == "render":
        measured_speech = _measure_speech_durations(
            plan,
            root,
            video_fps=int(fps),
            on_log=on_log,
            is_cancelled=is_cancelled,
            include_dialogue_audio=include_dialogue_audio,
            include_narration_audio=include_narration_audio,
        )
        if measured_speech:
            estimated_total = plan.total_duration_sec
            measured_speech_total = round(
                sum(sum(values) for values in measured_speech.values()), 3
            )
            plan = retimed_auto_sequence(plan, measured_speech)
            speech_retiming = {
                "method": "measured_local_tts_preflight",
                "include_dialogue_audio": bool(include_dialogue_audio),
                "include_narration_audio": bool(include_narration_audio),
                "estimated_total_duration_sec": estimated_total,
                "retimed_total_duration_sec": plan.total_duration_sec,
                "measured_speech_total_sec": measured_speech_total,
                "measured_narration_total_sec": plan.measured_narration_sec,
                "measured_speech_sec_by_clip": {
                    clip_id: list(values)
                    for clip_id, values in measured_speech.items()
                },
            }
            if on_log:
                on_log(
                    "Speech retiming: estimated total "
                    f"{estimated_total:.3f}s -> measured plan "
                    f"{plan.total_duration_sec:.3f}s "
                    f"({measured_speech_total:.3f}s of speech)."
                )

    plan_path = _write_json(root / "auto-plan.json", plan.to_dict())
    parsed_scenes_path = _write_json(
        root / "parsed-scenes.json", list(plan.scenes)
    )
    if on_progress:
        on_progress(
            2.0,
            f"Auto-mapper planned {len(plan.clips)} clip(s) "
            f"({plan.total_duration_sec:.1f}s planned)",
        )
    if on_log:
        on_log(
            "Auto-mapper plan: "
            + ", ".join(
                f"{clip.clip_id}={clip.template}" for clip in plan.clips
            )
        )

    built_items: list[tuple[Any, BuiltProject, dict[str, Any], Path]] = []
    clip_results: list[dict[str, Any]] = []

    for index, clip in enumerate(plan.clips):
        if is_cancelled and is_cancelled():
            raise InterruptedError("Auto sequence cancelled during project build.")
        clip_root = root / "clips" / f"{clip.clip_id}-{clip.template}"
        project_dir = clip_root / "project"
        if on_progress:
            on_progress(
                5.0 + (index / max(1, len(plan.clips))) * 10.0,
                f"Building {clip.clip_id} ({clip.template})",
            )
        built, _request_obj, _scenes = build_motion_graphics_project(
            clip.template,
            clip.request,
            script_text="",
            output_dir=project_dir,
        )
        result: dict[str, Any] = {
            **clip.to_dict(),
            "project_dir": str(built.output_dir),
            "index_html": str(built.index_path),
            "variables_json": str(built.variables_path),
            "build_manifest": str(
                built.output_dir / "motion-graphics-build.json"
            ),
            "built_files": list(built.files),
        }
        built_items.append((clip, built, result, clip_root))
        clip_results.append(result)
        if on_log:
            on_log(
                f"Built {clip.clip_id} ({clip.template}) with "
                f"{len(built.files)} files at {built.output_dir}"
            )

    result_payload: dict[str, Any] = {
        "status": "built" if mode == "build_only" else "rendering",
        "mode": mode,
        "fps": int(fps),
        "quality": quality,
        "output_root": str(root),
        "auto_plan_json": str(plan_path),
        "parsed_scenes_json": str(parsed_scenes_path),
        "plan": plan.to_dict(),
        "speech_retiming": speech_retiming,
        "dialogue_retiming": speech_retiming,
        "clips": clip_results,
        "combined_video": None,
        "combined_video_silent": None,
        "speech_audio": None,
        "dialogue_audio": None,
        "verification": None,
    }

    if mode == "build_only":
        result_payload["elapsed_sec"] = round(time.time() - started, 3)
        sequence_result_path = _write_json(
            root / "sequence-result.json", result_payload
        )
        result_payload["sequence_result_json"] = str(sequence_result_path)
        _write_json(sequence_result_path, result_payload)
        if on_progress:
            on_progress(100.0, "Auto sequence projects built")
        return _json_safe(result_payload)

    rendered_paths: list[Path] = []
    render_span_start = 15.0
    render_span = 73.0
    per_clip_span = render_span / max(1, len(built_items))

    for index, (clip, built, result, clip_root) in enumerate(built_items):
        if is_cancelled and is_cancelled():
            raise InterruptedError("Auto sequence cancelled before clip render.")
        output_mp4 = (
            built.output_dir
            / "renders"
            / f"{clip.clip_id}-{clip.template}.mp4"
        )
        clip_base = render_span_start + index * per_clip_span

        def _clip_progress(
            hf_pct: float,
            stage: str,
            *,
            base: float = clip_base,
            current_clip: Any = clip,
        ) -> None:
            if on_progress:
                mapped = base + (max(0.0, min(100.0, hf_pct)) / 100.0) * per_clip_span
                on_progress(mapped, f"{current_clip.clip_id}: {stage}")

        def _clip_log(line: str, *, current_clip: Any = clip) -> None:
            if on_log:
                on_log(f"{current_clip.clip_id}: {line}")

        render_result = render_motion_graphics_project(
            project_dir=built.output_dir,
            variables=built.variables,
            output_path=output_mp4,
            fps=int(fps),
            quality=str(quality),
            on_progress=_clip_progress,
            on_log=_clip_log,
            on_process=on_process,
            is_cancelled=is_cancelled,
        )
        render_log_path = clip_root / "render-log.txt"
        render_log_path.parent.mkdir(parents=True, exist_ok=True)
        render_log_path.write_text(
            "\n".join(
                str(line) for line in render_result.get("log_tail", [])
            ),
            encoding="utf-8",
        )

        if on_progress:
            on_progress(
                min(90.0, clip_base + per_clip_span),
                f"Verifying {clip.clip_id} MP4",
            )
        verification = verify_mp4(output_mp4)
        verification_path = _write_json(
            clip_root / "verification.json", verification
        )
        result.update(
            {
                "video": str(output_mp4),
                "render_log": str(render_log_path),
                "render_elapsed_sec": render_result.get("elapsed_sec"),
                "verification": verification,
                "verification_json": str(verification_path),
            }
        )
        if not verification.get("verified"):
            raise RuntimeError(
                f"{clip.clip_id} MP4 failed verification: "
                + str(verification.get("error") or verification)
            )
        rendered_paths.append(output_mp4)
        if on_log:
            on_log(
                f"Verified {clip.clip_id}: {verification.get('width')}x"
                f"{verification.get('height')} @ {verification.get('fps')}fps, "
                f"{verification.get('duration_sec')}s, "
                f"{verification.get('decoded_frames')} frames"
            )

    if on_progress:
        on_progress(92.0, "Concatenating verified clips")
    combined_path = root / "combined.mp4"
    concat_result = concat_mp4_files(
        rendered_paths,
        combined_path,
        fps=int(fps),
        on_log=on_log,
        on_process=on_process,
        is_cancelled=is_cancelled,
    )

    if on_progress:
        on_progress(96.0, "Verifying combined MP4")
    combined_verification = verify_mp4(combined_path)
    combined_verification_path = _write_json(
        root / "verification.json", combined_verification
    )
    if not combined_verification.get("verified"):
        raise RuntimeError(
            "Combined MP4 failed final verification: "
            + str(
                combined_verification.get("error") or combined_verification
            )
        )

    final_video_path = combined_path
    final_verification = combined_verification

    result_payload.update(
        {
            "status": "completed",
            "combined_video": str(combined_path),
            "combined_video_silent": str(combined_path),
            "concat": concat_result,
            "verification": combined_verification,
            "verification_json": str(combined_verification_path),
        }
    )

    if include_speech_audio:
        if on_progress:
            on_progress(97.0, "Generating local speech audio")
        speech_audio = build_dialogue_audio_timeline(
            plan,
            root,
            video_fps=int(fps),
            on_log=on_log,
            include_dialogue_audio=include_dialogue_audio,
            include_narration_audio=include_narration_audio,
        )
        if speech_audio:
            for clip_result in clip_results:
                clip_lines = speech_audio.get("clips", {}).get(
                    str(clip_result.get("clip_id"))
                )
                if clip_lines:
                    clip_result["speech_audio_lines"] = clip_lines
                    # Preserve the established result key used by existing
                    # Motion Studio consumers.
                    clip_result["dialogue_audio_lines"] = clip_lines

            if on_progress:
                on_progress(98.5, "Muxing speech audio into combined MP4")
            muxed_path = root / "combined_with_audio.mp4"
            mux_result = mux_audio_into_mp4(
                combined_path,
                str(speech_audio["audio_wav"]),
                muxed_path,
                on_log=on_log,
                on_process=on_process,
                is_cancelled=is_cancelled,
            )
            final_video_path = muxed_path
            final_verification = mux_result["verification"]
            verification_with_audio_path = _write_json(
                root / "verification_with_audio.json", final_verification
            )
            result_payload.update(
                {
                    "combined_video": str(muxed_path),
                    "combined_video_silent": str(combined_path),
                    "speech_audio": speech_audio,
                    "speech_audio_wav": speech_audio["audio_wav"],
                    "speech_audio_json": speech_audio["audio_json"],
                    "dialogue_audio": speech_audio,
                    "dialogue_audio_wav": speech_audio["audio_wav"],
                    "dialogue_audio_json": speech_audio["audio_json"],
                    "audio_mux": mux_result,
                    "verification_with_audio": final_verification,
                    "verification_with_audio_json": str(
                        verification_with_audio_path
                    ),
                }
            )
        elif on_log:
            on_log(
                "Speech audio requested, but the parser found no dialogue "
                "or narration lines to synthesize."
            )

    result_payload["elapsed_sec"] = round(time.time() - started, 3)
    sequence_result_path = _write_json(
        root / "sequence-result.json", result_payload
    )
    result_payload["sequence_result_json"] = str(sequence_result_path)
    _write_json(sequence_result_path, result_payload)

    if on_progress:
        on_progress(100.0, "Auto sequence completed")
    if on_log:
        on_log(
            "Combined MP4 verified: "
            f"{final_video_path} ({final_verification.get('duration_sec')}s, "
            f"{final_verification.get('decoded_frames')} frames)"
        )
    return _json_safe(result_payload)
