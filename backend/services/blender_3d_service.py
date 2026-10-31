"""Local Blender 3D service used by the persistent Jobs API.

Blender runs in its own Python subprocess (`render_engine.blender_worker`).
The backend process itself deliberately never imports ``bpy``: a local Blender
runtime can therefore be pointed to a project virtualenv, Blender's bundled
Python, or a separate environment installed from ``requirements.txt``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.blender_3d.planner import Blender3DRequest, plan_blender_3d, quality_profile, theme_infos

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_RUNTIME = Path("/tmp/blender-runtime/bin/python")
DEFAULT_BLENDER_STUBS = Path("/tmp/blender-stubs")
BLENDER_JOB_TYPE = "blender_3d"

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[float, str], None]
ProcessCallback = Callable[[subprocess.Popen[str] | None], None]
CancelCheck = Callable[[], bool]
_runtime_probe_cache: dict[tuple[str, str], dict[str, Any]] = {}


class BlenderRuntimeError(RuntimeError):
    """Raised when no usable local Blender Python runtime is configured."""


@dataclass(frozen=True)
class BuiltBlender3DProject:
    root_dir: Path
    plan_path: Path
    parsed_scenes_path: Path
    spec_template_path: Path
    captions_path: Path | None
    manifest_path: Path
    plan: dict[str, Any]

    def output_paths(self) -> dict[str, str]:
        outputs = {
            "project_dir": str(self.root_dir),
            "blender_plan_json": str(self.plan_path),
            "parsed_scenes_json": str(self.parsed_scenes_path),
            "blender_spec_json": str(self.spec_template_path),
            "build_manifest_json": str(self.manifest_path),
        }
        if self.captions_path is not None:
            outputs["captions_ass"] = str(self.captions_path)
        return outputs


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def blender_themes() -> list[dict[str, Any]]:
    return theme_infos()


def prepare_blender_3d_preview(
    script_text: str = "",
    request_payload: dict[str, Any] | None = None,
    *,
    mode: str = "render",
    fps: int | None = None,
    quality: str | None = None,
    duration_sec: float | None = None,
    theme: str | None = None,
    include_captions: bool | None = None,
) -> dict[str, Any]:
    if mode not in {"build_only", "render"}:
        raise ValueError("Blender mode must be 'build_only' or 'render'")
    payload = dict(request_payload or {})
    if fps is not None:
        payload["fps"] = fps
    if quality is not None:
        payload["quality"] = quality
    if duration_sec is not None:
        payload["duration_sec"] = duration_sec
    if theme is not None:
        payload["theme"] = theme
    if include_captions is not None:
        payload["include_captions"] = include_captions
    # Validate explicitly before planning so API callers receive the same
    # bounded errors as direct planner users.
    Blender3DRequest.from_dict(payload)
    plan = plan_blender_3d(script_text or "", payload)
    plan_dict = plan.to_dict()
    return {
        "engine": "blender",
        "template": BLENDER_JOB_TYPE,
        "job_type": BLENDER_JOB_TYPE,
        "mode": mode,
        "scenes": plan_dict["scenes"],
        "scene_count": plan_dict["scene_count"],
        "request": plan_dict["request"],
        "topic": plan_dict["topic"],
        "plan": plan_dict,
        "total_duration_sec": plan_dict["total_duration_sec"],
        "total_frames": plan_dict["total_frames"],
        "runtime": blender_runtime_info(probe=False),
    }


def _ass_timestamp(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def write_captions_ass(plan: dict[str, Any], output_path: Path) -> Path | None:
    segments = plan.get("caption_segments") or []
    if not segments:
        return None
    request = plan.get("request") or {}
    width = int(request.get("width") or 1280)
    height = int(request.get("height") or 720)
    font_size = max(24, round(height * 0.041))
    lines = [
        "[Script Info]",
        "Title: SIDD Blender 3D captions",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Lower,DejaVu Sans,{font_size},&H00FFFFFF,&H000000FF,&HAA000000,&H64000000,-1,0,0,0,100,100,0.4,0,1,3,1,2,54,54,42,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for segment in segments:
        text = str(segment.get("text") or "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()
        if not text:
            continue
        lines.append(
            "Dialogue: 0,{}, {},Lower,,0,0,0,,{}".format(
                _ass_timestamp(float(segment.get("start_sec") or 0)),
                _ass_timestamp(float(segment.get("end_sec") or 0)),
                text,
            )
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def build_blender_3d_project(
    *,
    script_text: str,
    request_payload: dict[str, Any] | None,
    output_dir: str | Path,
    mode: str = "render",
    fps: int | None = None,
    quality: str | None = None,
    duration_sec: float | None = None,
    theme: str | None = None,
    include_captions: bool | None = None,
) -> BuiltBlender3DProject:
    preview = prepare_blender_3d_preview(
        script_text,
        request_payload,
        mode=mode,
        fps=fps,
        quality=quality,
        duration_sec=duration_sec,
        theme=theme,
        include_captions=include_captions,
    )
    plan = preview["plan"]
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root / "blender-plan.json"
    scenes_path = root / "parsed-scenes.json"
    spec_path = root / "blender-spec-template.json"
    manifest_path = root / "blender-build.json"
    captions_path = write_captions_ass(plan, root / "captions.ass") if (plan.get("request") or {}).get("include_captions", True) else None

    _write_json(plan_path, plan)
    _write_json(scenes_path, plan.get("scenes") or [])
    _write_json(
        spec_path,
        {
            "mode": "dynamic_3d",
            "operation": "set_at_execution",
            "plan": plan,
            "thumbnail_fraction": 0.58,
        },
    )
    manifest = {
        "engine": "blender",
        "job_type": BLENDER_JOB_TYPE,
        "mode": mode,
        "planner_version": plan.get("planner_version"),
        "topic": plan.get("topic"),
        "request": plan.get("request"),
        "scene_count": plan.get("scene_count"),
        "files": {
            "plan": str(plan_path),
            "parsed_scenes": str(scenes_path),
            "spec_template": str(spec_path),
            "captions_ass": str(captions_path) if captions_path else None,
        },
        "runtime": blender_runtime_info(probe=False),
    }
    _write_json(manifest_path, manifest)
    return BuiltBlender3DProject(
        root_dir=root,
        plan_path=plan_path,
        parsed_scenes_path=scenes_path,
        spec_template_path=spec_path,
        captions_path=captions_path,
        manifest_path=manifest_path,
        plan=plan,
    )


def _candidate_blender_pythons() -> list[Path]:
    candidates: list[Path] = []
    runtime_dir = os.getenv("SIDD_BLENDER_RUNTIME_DIR", "").strip()
    if runtime_dir:
        base = Path(runtime_dir).expanduser()
        candidates.extend([base / "bin" / "python", base / "Scripts" / "python.exe", base])
    candidates.extend(
        [
            REPO_ROOT / ".venv" / "bin" / "python",
            REPO_ROOT / ".venv-blender" / "bin" / "python",
            DEFAULT_BLENDER_RUNTIME,
            Path.home() / ".local" / "share" / "sidd-blender" / "bin" / "python",
            Path(sys.executable),
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def blender_python_command() -> str:
    explicit = os.getenv("SIDD_BLENDER_PYTHON", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        discovered = shutil.which(explicit)
        if discovered:
            return discovered
        raise BlenderRuntimeError(f"Configured SIDD_BLENDER_PYTHON was not found: {explicit}")
    for candidate in _candidate_blender_pythons():
        if candidate.is_file():
            return str(candidate)
    raise BlenderRuntimeError(
        "No local Blender Python runtime found. Install the project requirements "
        "(which include bpy==4.2.15) or set SIDD_BLENDER_PYTHON/SIDD_BLENDER_RUNTIME_DIR."
    )


def blender_environment(python_command: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(REPO_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env.setdefault("BLENDER_USER_CONFIG", str(Path.home() / ".config" / "blender"))
    library_dirs: list[str] = []
    configured = os.getenv("SIDD_BLENDER_LIBRARY_PATH", "").strip() or os.getenv("SIDD_BLENDER_STUBS_DIR", "").strip()
    if configured:
        library_dirs.extend(part for part in configured.split(os.pathsep) if part)
    elif DEFAULT_BLENDER_STUBS.is_dir():
        # The headless sandbox build used loader-only X/GL stubs with Cycles
        # CPU.  Normal desktops do not need this path, so it is only added
        # when the known local stub directory actually exists.
        library_dirs.append(str(DEFAULT_BLENDER_STUBS))
    if library_dirs:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = os.pathsep.join([*library_dirs, existing] if existing else library_dirs)
    return env


def blender_runtime_info(*, probe: bool = False, python_command: str | None = None) -> dict[str, Any]:
    try:
        command = python_command or blender_python_command()
    except Exception as exc:
        return {
            "available": False,
            "python": None,
            "error": str(exc),
            "candidates": [str(path) for path in _candidate_blender_pythons()],
            "configuration": "Set SIDD_BLENDER_PYTHON or SIDD_BLENDER_RUNTIME_DIR to a local Python with bpy installed.",
        }
    env = blender_environment(command)
    info: dict[str, Any] = {
        "available": Path(command).is_file(),
        "python": command,
        "configured_python_env": bool(os.getenv("SIDD_BLENDER_PYTHON")),
        "configured_runtime_dir_env": bool(os.getenv("SIDD_BLENDER_RUNTIME_DIR")),
        "library_path": env.get("LD_LIBRARY_PATH"),
        "probed": False,
    }
    if not probe:
        return info
    if python_command is None and not os.getenv("SIDD_BLENDER_PYTHON", "").strip():
        # A normal backend .venv may intentionally exclude bpy (the small
        # deployment requirements do), while a separate local Blender venv
        # contains it.  Probe existing candidates in order and use the first
        # interpreter that can really import bpy.
        attempts: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        for candidate in _candidate_blender_pythons():
            if not candidate.is_file():
                continue
            result = blender_runtime_info(probe=True, python_command=str(candidate))
            attempts.append(
                {
                    "python": str(candidate),
                    "available": bool(result.get("available")),
                    "blender_version": result.get("blender_version"),
                    "error": str(result.get("error") or "")[-300:] or None,
                }
            )
            if result.get("available"):
                result["attempts"] = attempts
                return result
            last_result = result
        if last_result is not None:
            last_result["attempts"] = attempts
            return last_result
    cache_key = (command, env.get("LD_LIBRARY_PATH", ""))
    if cache_key in _runtime_probe_cache:
        return {**info, **_runtime_probe_cache[cache_key], "probed": True, "cached": True}
    started = time.time()
    try:
        proc = subprocess.run(
            [
                command,
                "-c",
                "import bpy; print(f'BPY_OK {bpy.app.version_string} background={bpy.app.background}')",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        match = re.search(r"BPY_OK\s+([^\s]+)", output)
        probe_result = {
            "available": proc.returncode == 0 and bool(match),
            "blender_version": match.group(1) if match else None,
            "return_code": proc.returncode,
            "elapsed_sec": round(time.time() - started, 3),
            "output_tail": output[-1000:],
        }
        if proc.returncode != 0 or not match:
            probe_result["error"] = output[-1000:] or f"Blender probe exited with code {proc.returncode}"
    except Exception as exc:
        probe_result = {
            "available": False,
            "blender_version": None,
            "elapsed_sec": round(time.time() - started, 3),
            "error": str(exc),
        }
    _runtime_probe_cache[cache_key] = probe_result
    return {**info, **probe_result, "probed": True, "cached": False}


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


_FRAME_RE = re.compile(r"SIDD_FRAME:(\d+)/(\d+)")
_SAVED_FRAME_RE = re.compile(r"Saved: '.*?[\\/]frame_(\d+)\.png'")
_STAGE_RE = re.compile(r"SIDD_STAGE:(.+)")


def run_blender_3d_worker(
    *,
    plan: dict[str, Any],
    operation: str,
    blend_path: str | Path,
    thumbnail_path: str | Path,
    frames_dir: str | Path | None,
    work_dir: str | Path,
    on_log: LogCallback | None = None,
    on_progress: ProgressCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    output_png: str | Path | None = None,
    still_frame: int | None = None,
) -> dict[str, Any]:
    if operation not in {"build_only", "render", "still"}:
        raise ValueError(f"Unsupported Blender operation: {operation}")
    runtime = blender_runtime_info(probe=True)
    if not runtime.get("available"):
        raise BlenderRuntimeError(
            "Local Blender runtime is unavailable: "
            + str(runtime.get("error") or runtime.get("output_tail") or runtime)
        )
    command = str(runtime["python"])
    work = Path(work_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    spec_path = work / f"blender-{operation}-spec.json"
    result_path = work / f"blender-{operation}-result.json"
    log_path = work / f"blender-{operation}.log"
    spec: dict[str, Any] = {
        "mode": "dynamic_3d",
        "operation": operation,
        "plan": plan,
        "blend_path": str(Path(blend_path).expanduser().resolve()),
        "thumbnail_path": str(Path(thumbnail_path).expanduser().resolve()),
        "thumbnail_fraction": 0.58,
    }
    if frames_dir is not None:
        spec["frames_dir"] = str(Path(frames_dir).expanduser().resolve())
    if output_png is not None:
        spec["output_png"] = str(Path(output_png).expanduser().resolve())
    if still_frame is not None:
        spec["still_frame"] = int(still_frame)
    _write_json(spec_path, spec)
    if result_path.exists():
        result_path.unlink()

    total_frames = max(1, int(plan.get("total_frames") or (plan.get("request") or {}).get("frame_count") or 1))
    started = time.time()
    proc = subprocess.Popen(
        [command, "-m", "render_engine.blender_worker", str(spec_path), str(result_path)],
        cwd=str(REPO_ROOT),
        env=blender_environment(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    if on_process:
        on_process(proc)
    tail: list[str] = []
    last_logged_frame = -1
    try:
        assert proc.stdout is not None
        with log_path.open("w", encoding="utf-8") as log_file:
            for raw_line in proc.stdout:
                if is_cancelled and is_cancelled():
                    _terminate_process(proc)
                    raise InterruptedError("Blender 3D render cancelled.")
                log_file.write(raw_line)
                log_file.flush()
                line = raw_line.strip()
                if not line:
                    continue
                tail.append(line)
                tail = tail[-120:]
                stage_match = _STAGE_RE.search(line)
                if stage_match:
                    message = f"Blender: {stage_match.group(1)[:180]}"
                    if on_log:
                        on_log(message)
                    if on_progress:
                        on_progress(0.02, message)
                    continue
                frame_match = _FRAME_RE.search(line)
                saved_match = _SAVED_FRAME_RE.search(line)
                done: int | None = None
                total = total_frames
                if frame_match:
                    done, total = int(frame_match.group(1)), max(1, int(frame_match.group(2)))
                elif saved_match:
                    done = int(saved_match.group(1))
                if done is not None:
                    ratio = max(0.0, min(1.0, done / max(1, total)))
                    if on_progress:
                        on_progress(ratio, f"Blender frames {done}/{total}")
                    if on_log and (done == total or done - last_logged_frame >= 25):
                        on_log(f"Blender frames {done}/{total}")
                        last_logged_frame = done
                elif any(marker in line for marker in ("Error", "Traceback", "Warning", "Saved:")) and on_log:
                    on_log(line[:500])
        return_code = proc.wait(timeout=30)
    finally:
        if on_process:
            on_process(None)

    if is_cancelled and is_cancelled():
        raise InterruptedError("Blender 3D render cancelled.")
    if return_code != 0:
        raise RuntimeError(
            "Blender worker failed with exit code "
            f"{return_code}. Log: {log_path}. Tail: " + " | ".join(tail[-12:])
        )
    if not result_path.is_file():
        raise RuntimeError(f"Blender worker exited without a result file: {result_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(
        {
            "runtime": runtime,
            "spec_path": str(spec_path),
            "result_path": str(result_path),
            "log_path": str(log_path),
            "log_tail": tail[-30:],
            "service_elapsed_sec": round(time.time() - started, 3),
        }
    )
    return result


def encode_blender_frames(
    *,
    frames_dir: str | Path,
    output_path: str | Path,
    fps: int,
    quality: str = "turbo",
    captions_path: str | Path | None = None,
    on_log: LogCallback | None = None,
    on_process: ProcessCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    from backend.services.motion_graphics_service import ffmpeg_command

    frames = Path(frames_dir).expanduser().resolve()
    frame_files = sorted(frames.glob("frame_*.png"))
    if not frame_files:
        raise RuntimeError(f"No Blender PNG frames found in {frames}")
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        profile = quality_profile(quality)
    except KeyError:
        profile = quality_profile("turbo")
    encode_crf = int(profile.get("encode_crf") or 23)
    encode_preset = str(profile.get("encode_preset") or "veryfast")
    filters: list[str] = []
    captions_burned = False
    if captions_path is not None:
        captions = Path(captions_path).expanduser().resolve()
        if captions.is_file():
            # Run FFmpeg from the frames directory and reference a local copy
            # by a simple filename; this avoids fragile filtergraph escaping
            # for absolute paths while keeping the source ASS untouched.
            local_captions = frames / "captions.ass"
            if captions != local_captions:
                shutil.copy2(captions, local_captions)
            filters.append("ass=filename=captions.ass:fontsdir=/usr/share/fonts/truetype/dejavu")
            captions_burned = True
    filters.append("format=yuv420p")
    command = [
        ffmpeg_command(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "1",
        "-i",
        "frame_%04d.png",
        "-vf",
        ",".join(filters),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        encode_preset,
        "-crf",
        str(encode_crf),
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        str(output),
    ]
    started = time.time()
    proc = subprocess.Popen(
        command,
        cwd=str(frames),
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
                raise InterruptedError("Blender frame encoding cancelled.")
            line = raw_line.strip()
            if line:
                tail.append(line)
                tail = tail[-80:]
        return_code = proc.wait(timeout=30)
    finally:
        if on_process:
            on_process(None)
    if is_cancelled and is_cancelled():
        raise InterruptedError("Blender frame encoding cancelled.")
    if return_code != 0 or not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError(
            f"FFmpeg failed to encode Blender frames (exit {return_code}): " + " | ".join(tail[-12:])
        )
    if on_log:
        on_log(f"Encoded {len(frame_files)} Blender frames -> {output}")
    return {
        "output_path": str(output),
        "frame_count": len(frame_files),
        "fps": fps,
        "crf": encode_crf,
        "preset": encode_preset,
        "quality": quality,
        "captions_burned": captions_burned,
        "elapsed_sec": round(time.time() - started, 3),
        "log_tail": tail[-20:],
        "command": command,
    }
