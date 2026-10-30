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
from typing import Any, Callable, Mapping

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
from app.script_parser import parse_script
from backend.core.config import REPO_ROOT

ProgressCallback = Callable[[float, str], None]
LogCallback = Callable[[str], None]
ProcessCallback = Callable[[subprocess.Popen[str] | None], None]
CancelCheck = Callable[[], bool]

_PCT_JSON_RE = re.compile(r'"pct"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
_PCT_TEXT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


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
