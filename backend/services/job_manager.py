"""Background job queue with SQLite persistence, real subprocess control (pause/resume/cancel/retry), and WebSockets."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from backend.core.config import REPO_ROOT, get_settings
from backend.core.database import dumps_json, get_db, loads_json, utc_now_iso
from backend.core.logging_config import get_logger
from backend.services.hardware_service import evaluate_workload_warnings
from backend.services.motion_graphics_service import (
    build_motion_graphics_project,
    execute_auto_motion_graphics_sequence,
    render_motion_graphics_project,
    verify_mp4,
)
from backend.services.project_service import (
    get_project,
    get_scene,
    list_project_scenes,
    sync_project_manifest,
    update_project,
    update_scene,
)
from character_engine.profiles import get_character, update_character
from project_storage.manager import get_project_dir
from render_engine.blender_worker import compute_dimensions
from render_engine.validator import validate_exported_mp4
from render_engine.video_assembler import (
    assemble_project_mp4,
    encode_scene_mp4,
    overlay_burned_captions_on_frames,
)
from voice_engine.sound_design import build_scene_audio_mix
from voice_engine.subtitles import build_urdu_script_segments, write_srt_file, write_vtt_file

logger = get_logger("job_manager")


def _row_to_job(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "current_stage": row["current_stage"],
        "progress_pct": float(row["progress_pct"]) if row["progress_pct"] is not None else None,
        "progress_measurable": bool(row["progress_measurable"]),
        "payload": loads_json(row["payload_json"], {}),
        "output_paths": loads_json(row["output_paths_json"], {}),
        "logs": loads_json(row["logs_json"], []),
        "error_details": row["error_details"],
        "retry_count": int(row["retry_count"]),
        "worker_pid": row["worker_pid"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class JobManager:
    """Thread-safe persistent background job queue with real POSIX process control and WebSocket pub/sub."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()
        self._active_procs: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_ids: set[str] = set()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = set()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._recovered = False

    def start(self) -> None:
        with self._lock:
            if not self._recovered:
                self.recover_orphaned_jobs()
                self._recovered = True
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._stop_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    name="sidd-job-worker",
                    daemon=True,
                )
                self._worker_thread.start()

    def recover_orphaned_jobs(self) -> int:
        """Mark jobs left in `running`/`paused` from an unclean shutdown as recoverable."""
        now = utc_now_iso()
        with get_db() as conn:
            cur = conn.execute(
                """
                UPDATE jobs
                SET status='interrupted',
                    current_stage='interrupted_by_restart (retry available)',
                    worker_pid=NULL,
                    updated_at=?
                WHERE status IN ('running', 'paused')
                """,
                (now,),
            )
            queued_rows = conn.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at ASC"
            ).fetchall()
        for r in queued_rows:
            self._queue.put(r["id"])
        return cur.rowcount

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers = {pair for pair in self._subscribers if pair[1] is not q}

    def _broadcast(self, job_dict: dict[str, Any]) -> None:
        event = {"type": "job_update", "job": job_dict}
        with self._lock:
            subs = list(self._subscribers)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(self._safe_put, q, event)
            except RuntimeError:
                continue

    @staticmethod
    def _safe_put(q: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def enqueue_job(
        self,
        job_type: str,
        *,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.start()
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        now = utc_now_iso()
        initial_logs = [f"[{now}] Job queued: {job_type}"]
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, project_id, job_type, status, current_stage,
                    progress_pct, progress_measurable, payload_json,
                    output_paths_json, logs_json, error_details,
                    retry_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', 'queued', NULL, 0, ?, '{}', ?, '', 0, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    job_type,
                    dumps_json(payload or {}),
                    dumps_json(initial_logs),
                    now,
                    now,
                ),
            )
        job = self.get_job(job_id)
        self._queue.put(job_id)
        self._broadcast(job)
        return job

    def get_job(self, job_id: str) -> dict[str, Any]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise KeyError(f"Job '{job_id}' not found.")
        return _row_to_job(row)

    def list_jobs(self, project_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with get_db() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [_row_to_job(r) for r in rows]

    def _update_job_state(
        self,
        job_id: str,
        *,
        status: str | None = None,
        current_stage: str | None = None,
        progress_pct: float | None = -1.0,
        progress_measurable: bool | None = None,
        log_line: str | None = None,
        output_paths: dict[str, Any] | None = None,
        error_details: str | None = None,
        worker_pid: int | None = -1,
        started: bool = False,
        completed: bool = False,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with get_db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            cur = _row_to_job(row)
            logs = list(cur["logs"])
            if log_line:
                logs.append(f"[{now[11:19]}] {log_line}")
                logs = logs[-200:]

            new_status = status if status is not None else cur["status"]
            new_stage = current_stage if current_stage is not None else cur["current_stage"]
            new_meas = progress_measurable if progress_measurable is not None else cur["progress_measurable"]
            if progress_pct == -1.0:
                new_pct = cur["progress_pct"]
            else:
                new_pct = round(progress_pct, 1) if progress_pct is not None else None

            new_outputs = {**cur["output_paths"], **(output_paths or {})}
            new_err = error_details if error_details is not None else cur["error_details"]
            new_pid = cur["worker_pid"] if worker_pid == -1 else worker_pid
            started_at = now if started and not cur["started_at"] else cur["started_at"]
            completed_at = now if completed else cur["completed_at"]

            conn.execute(
                """
                UPDATE jobs SET
                    status=?, current_stage=?, progress_pct=?, progress_measurable=?,
                    output_paths_json=?, logs_json=?, error_details=?, worker_pid=?,
                    started_at=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    new_status,
                    new_stage,
                    new_pct,
                    int(bool(new_meas)),
                    dumps_json(new_outputs),
                    dumps_json(logs),
                    new_err,
                    new_pid,
                    started_at,
                    completed_at,
                    now,
                    job_id,
                ),
            )
            updated_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        job_dict = _row_to_job(updated_row)
        self._broadcast(job_dict)
        return job_dict

    def pause_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] != "running":
            raise RuntimeError(f"Only running jobs can be paused (current status: {job['status']}).")
        with self._lock:
            proc = self._active_procs.get(job_id)
        if proc and proc.poll() is None and hasattr(signal, "SIGSTOP"):
            os.killpg(os.getpgid(proc.pid), signal.SIGSTOP)
            return self._update_job_state(
                job_id,
                status="paused",
                current_stage=f"paused ({job['current_stage']})",
                log_line="Worker subprocess paused via SIGSTOP.",
            )
        raise RuntimeError("Job is currently between subprocess stages and cannot be mid-step paused right now.")

    def resume_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] != "paused":
            raise RuntimeError(f"Only paused jobs can be resumed (current status: {job['status']}).")
        with self._lock:
            proc = self._active_procs.get(job_id)
        if proc and proc.poll() is None and hasattr(signal, "SIGCONT"):
            os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
            return self._update_job_state(
                job_id,
                status="running",
                current_stage="resumed_rendering",
                log_line="Worker subprocess resumed via SIGCONT.",
            )
        raise RuntimeError("Paused subprocess is no longer active; retry the job instead.")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        with self._lock:
            self._cancelled_ids.add(job_id)
            proc = self._active_procs.get(job_id)
        if proc and proc.poll() is None:
            try:
                if hasattr(signal, "SIGCONT"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        return self._update_job_state(
            job_id,
            status="cancelled",
            current_stage="cancelled",
            progress_pct=None,
            progress_measurable=False,
            worker_pid=None,
            completed=True,
            log_line="Job cancelled by user.",
        )

    def retry_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] not in {"failed", "cancelled", "interrupted"}:
            raise RuntimeError(f"Cannot retry job in status '{job['status']}'.")
        now = utc_now_iso()
        with self._lock:
            self._cancelled_ids.discard(job_id)
        with get_db() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status='queued', current_stage='queued_for_retry',
                    progress_pct=NULL, progress_measurable=0,
                    error_details='', worker_pid=NULL,
                    started_at=NULL, completed_at=NULL,
                    retry_count=retry_count + 1, updated_at=?
                WHERE id=?
                """,
                (now, job_id),
            )
        updated = self.get_job(job_id)
        self._update_job_state(job_id, log_line=f"Retry #{updated['retry_count']} queued.")
        self.start()
        self._queue.put(job_id)
        return self.get_job(job_id)

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._cancelled_ids:
                return True
        return self.get_job(job_id)["status"] == "cancelled"

    def _run_blender_subprocess(
        self,
        job_id: str,
        spec: dict[str, Any],
        *,
        on_frame: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        tmp_dir = settings.temp_dir / f"worker_{job_id}_{uuid.uuid4().hex[:6]}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        spec_file = tmp_dir / "spec.json"
        res_file = tmp_dir / "result.json"
        spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)

        proc = subprocess.Popen(
            [sys.executable, "-m", "render_engine.blender_worker", str(spec_file), str(res_file)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        with self._lock:
            self._active_procs[job_id] = proc
        self._update_job_state(job_id, worker_pid=proc.pid)

        tail_lines: list[str] = []
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                tail_lines.append(line)
                tail_lines = tail_lines[-40:]
                if line.startswith("SIDD_STAGE:"):
                    stage_label = line.split(":", 1)[1].strip()
                    self._update_job_state(job_id, current_stage=stage_label, log_line=f"Blender stage: {stage_label}")
                elif line.startswith("SIDD_FRAME:"):
                    parts = line.split(":", 1)[1].split("/")
                    if len(parts) == 2 and on_frame:
                        done_f, total_f = int(parts[0]), int(parts[1])
                        on_frame(done_f, total_f)

            rc = proc.wait(timeout=30)
            if self._is_cancelled(job_id):
                raise InterruptedError("Render cancelled by user.")
            if rc != 0 or not res_file.is_file():
                err_tail = "\n".join(tail_lines[-12:])
                raise RuntimeError(f"Blender worker exited with code {rc}: {err_tail}")
            return json.loads(res_file.read_text(encoding="utf-8"))
        finally:
            with self._lock:
                self._active_procs.pop(job_id, None)
            self._update_job_state(job_id, worker_pid=None)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _execute_single_scene_pipeline(
        self,
        job_id: str,
        project: dict[str, Any],
        scene: dict[str, Any],
        *,
        scene_offset_pct: float = 0.0,
        scene_span_pct: float = 100.0,
    ) -> dict[str, Any]:
        proj_id = project["id"]
        scene_id = scene["id"]
        proj_dir = get_project_dir(proj_id, create=True)
        update_scene(scene_id, {"generation_status": "rendering", "error_message": ""})

        # 1. Local Speech Synthesis + Visemes + Foley + Music
        self._update_job_state(
            job_id,
            current_stage=f"Scene {scene['scene_index'] + 1}: Synthesizing voices, visemes & sound design",
            progress_pct=scene_offset_pct + scene_span_pct * 0.08,
            progress_measurable=True,
            log_line=f"Synthesizing speech & procedural sound design for '{scene['title']}'",
        )
        audio_res = build_scene_audio_mix(
            scene,
            output_dir=proj_dir / "audio",
            video_fps=int(project["fps"]),
            language_fallback=project["language"],
            narration_enabled=bool(project["narration_prefs"].get("enabled", True)),
            music_enabled=bool(project["music_prefs"].get("enabled", True)),
        )

        # 2. Write scene subtitles (SRT + VTT, plus Urdu script track when Roman Urdu)
        srt_path = proj_dir / "subtitles" / f"{scene_id}.srt"
        vtt_path = proj_dir / "subtitles" / f"{scene_id}.vtt"
        write_srt_file(audio_res["subtitle_segments"], srt_path)
        write_vtt_file(audio_res["subtitle_segments"], vtt_path)
        if project.get("language") == "roman_ur":
            ur_segs = build_urdu_script_segments(audio_res["subtitle_segments"])
            write_srt_file(ur_segs, proj_dir / "subtitles" / f"{scene_id}_ur.srt")
            write_vtt_file(ur_segs, proj_dir / "subtitles" / f"{scene_id}_ur.vtt")

        if self._is_cancelled(job_id):
            raise InterruptedError("Cancelled before 3D rendering.")

        # 3. Real Blender 3D Raytraced Animation
        frames_dir = get_settings().temp_dir / f"frames_{proj_id}_{scene_id}"
        thumb_path = proj_dir / "thumbnails" / f"{scene_id}.png"

        def _on_frame(done_f: int, total_f: int) -> None:
            frac = done_f / float(max(1, total_f))
            pct = scene_offset_pct + scene_span_pct * (0.12 + 0.72 * frac)
            self._update_job_state(
                job_id,
                current_stage=f"Scene {scene['scene_index'] + 1}: Rendering 3D frame {done_f}/{total_f}",
                progress_pct=pct,
                progress_measurable=True,
            )

        blender_spec = {
            "mode": "scene",
            "scene": scene,
            "characters": project.get("characters", []),
            "character_visemes": audio_res["character_visemes"],
            "duration_sec": audio_res["actual_duration_sec"],
            "fps": int(project["fps"]),
            "resolution": project["resolution"],
            "aspect_ratio": project["aspect_ratio"],
            "quality_profile": project["quality_profile"],
            "frames_dir": str(frames_dir),
            "thumbnail_path": str(thumb_path),
        }

        try:
            b_res = self._run_blender_subprocess(job_id, blender_spec, on_frame=_on_frame)

            # Optional burned-in lower-third captions
            if project.get("dialogue_prefs", {}).get("burn_in_captions", True):
                overlay_burned_captions_on_frames(
                    frames_dir,
                    audio_res["subtitle_segments"],
                    int(b_res["render_fps"]),
                )

            # 4. FFmpeg H.264 + AAC Scene Encoding
            self._update_job_state(
                job_id,
                current_stage=f"Scene {scene['scene_index'] + 1}: Encoding H.264/AAC MP4 & verifying stream",
                progress_pct=scene_offset_pct + scene_span_pct * 0.90,
                progress_measurable=True,
                log_line=f"Muxing {b_res['frame_count']} raytraced 3D frames + stereo audio into MP4.",
            )
            scene_mp4 = proj_dir / "renders" / f"scene_{scene['scene_index']:03d}_{scene_id}.mp4"
            encode_scene_mp4(
                frames_dir=frames_dir,
                audio_wav_path=Path(audio_res["mix_wav_path"]),
                output_mp4_path=scene_mp4,
                render_fps=int(b_res["render_fps"]),
                target_fps=int(project["fps"]),
                width=int(b_res["target_width"]),
                height=int(b_res["target_height"]),
                transition_type=scene.get("transition_type", "crossfade"),
                duration_sec=float(audio_res["actual_duration_sec"]),
                subtitle_srt_path=srt_path if project.get("dialogue_prefs", {}).get("subtitles", True) else None,
            )
        finally:
            # Clean temporary uncompressed PNG sequence immediately to save disk space
            shutil.rmtree(frames_dir, ignore_errors=True)

        # 5. Strict Scene MP4 Validation
        val = validate_exported_mp4(
            scene_mp4,
            expect_audio=True,
            expected_width=int(b_res["target_width"]),
            expected_height=int(b_res["target_height"]),
        )
        if not val["valid"]:
            err = "; ".join(val["errors"])
            update_scene(scene_id, {"generation_status": "failed", "error_message": err})
            raise RuntimeError(f"Scene MP4 validation failed: {err}")

        updated_scene = update_scene(
            scene_id,
            {
                "duration_sec": audio_res["actual_duration_sec"],
                "generation_status": "completed",
                "thumbnail_path": str(thumb_path),
                "rendered_video_path": str(scene_mp4),
                "audio_mix_path": audio_res["mix_wav_path"],
                "subtitle_path": str(vtt_path),
                "error_message": "",
                "render_metrics": {
                    "render_time_sec": b_res["elapsed_sec"],
                    "frames_rendered": b_res["frame_count"],
                    "file_size_mb": val["file_size_mb"],
                    "verified_duration_sec": val["duration_sec"],
                    "subtitle_segments": audio_res["subtitle_segments"],
                },
            },
        )
        return updated_scene

    def _execute_auto_motion_graphics_job(
        self, job_id: str, payload: dict[str, Any], t_start: float
    ) -> None:
        """Plan, build/render, concatenate, and verify an auto sequence."""

        mode = str(payload.get("mode") or "render")
        script_text = str(payload.get("script_text") or "")
        include_dialogue_audio = bool(payload.get("include_dialogue_audio"))
        include_narration_audio = bool(payload.get("include_narration_audio"))
        if not script_text.strip():
            raise ValueError("auto motion-graphics script_text must not be empty")

        settings = get_settings()
        job_root = (settings.workspace_dir / "motion_graphics" / job_id).resolve()
        output_root = job_root / "auto_sequence"
        job_root.mkdir(parents=True, exist_ok=True)

        requested_speech = []
        if include_dialogue_audio:
            requested_speech.append("dialogue")
        if include_narration_audio:
            requested_speech.append("narration")
        speech_suffix = (
            f" with local {' and '.join(requested_speech)} audio"
            if requested_speech
            else ""
        )
        self._update_job_state(
            job_id,
            current_stage="Planning auto motion-graphics sequence",
            progress_pct=2.0,
            progress_measurable=True,
            log_line=(
                f"Preparing auto-mapper sequence in {mode} mode"
                f"{speech_suffix}."
            ),
        )

        def _on_progress(pct: float, stage: str) -> None:
            self._update_job_state(
                job_id,
                current_stage=stage,
                progress_pct=max(0.0, min(100.0, float(pct))),
                progress_measurable=True,
            )

        def _on_log(line: str) -> None:
            self._update_job_state(job_id, log_line=line)

        def _on_process(proc: subprocess.Popen[str] | None) -> None:
            with self._lock:
                if proc is None:
                    self._active_procs.pop(job_id, None)
                else:
                    self._active_procs[job_id] = proc
            self._update_job_state(job_id, worker_pid=proc.pid if proc else None)

        result = execute_auto_motion_graphics_sequence(
            script_text=script_text,
            output_root=output_root,
            mode=mode,
            fps=int(payload.get("fps") or 60),
            quality=str(payload.get("quality") or "standard"),
            brand_label=str(payload.get("brand_label") or "SIDD STUDIO"),
            include_dialogue_audio=include_dialogue_audio,
            include_narration_audio=include_narration_audio,
            on_progress=_on_progress,
            on_log=_on_log,
            on_process=_on_process,
            is_cancelled=lambda: self._is_cancelled(job_id),
        )

        plan = result.get("plan") or {}
        clips = result.get("clips") or []
        outputs: dict[str, Any] = {
            "project_dir": str(output_root),
            "auto_plan_json": result.get("auto_plan_json"),
            "parsed_scenes": result.get("parsed_scenes_json"),
            "sequence_result_json": result.get("sequence_result_json"),
            "template": "auto",
            "mode": mode,
            "include_dialogue_audio": include_dialogue_audio,
            "include_narration_audio": include_narration_audio,
            "scene_count": int(plan.get("scene_count") or len(plan.get("scenes") or [])),
            "clip_count": int(plan.get("clip_count") or len(clips)),
            "auto_plan": plan,
            "clips": clips,
            "render_elapsed_sec": result.get("elapsed_sec"),
        }

        for clip in clips:
            if not isinstance(clip, dict):
                continue
            prefix = str(clip.get("clip_id") or "clip").replace("-", "_")
            for artifact_name in (
                "index_html",
                "variables_json",
                "build_manifest",
                "video",
                "render_log",
                "verification_json",
            ):
                value = clip.get(artifact_name)
                if isinstance(value, str) and value:
                    outputs[f"{prefix}_{artifact_name}"] = value

            for line_index, line in enumerate(
                clip.get("speech_audio_lines")
                or clip.get("dialogue_audio_lines")
                or [],
                start=1,
            ):
                if not isinstance(line, dict):
                    continue
                wav_path = line.get("wav_path")
                if isinstance(wav_path, str) and wav_path:
                    outputs[f"{prefix}_line_{line_index:02d}_wav"] = wav_path

        if mode == "build_only":
            if result.get("status") != "built":
                raise RuntimeError(f"Auto sequence build did not complete: {result}")
            self._update_job_state(
                job_id,
                status="completed",
                current_stage="completed",
                progress_pct=100.0,
                progress_measurable=True,
                output_paths=outputs,
                completed=True,
                log_line=(
                    f"Build-only auto sequence completed with {len(clips)} "
                    f"clip project(s) in {round(time.time() - t_start, 2)}s."
                ),
            )
            return

        if result.get("status") != "completed" or not result.get("combined_video"):
            raise RuntimeError(f"Auto sequence render did not complete: {result}")

        silent_verification = result.get("verification") or {}
        verification_with_audio = result.get("verification_with_audio") or {}
        verification = verification_with_audio or silent_verification
        speech_audio = result.get("speech_audio")
        if not isinstance(speech_audio, dict):
            speech_audio = result.get("dialogue_audio")
        if not isinstance(speech_audio, dict):
            speech_audio = None
        # Keep the historical output key working for existing consumers.
        dialogue_audio = speech_audio
        concat = result.get("concat") or {}
        outputs.update(
            {
                "video": result.get("combined_video"),
                "combined_video": result.get("combined_video"),
                "combined_video_silent": result.get("combined_video_silent"),
                "verification": verification,
                "verification_json": result.get("verification_json"),
                "verification_with_audio": verification_with_audio or None,
                "verification_with_audio_json": result.get(
                    "verification_with_audio_json"
                ),
                "speech_audio": speech_audio,
                "speech_audio_wav": result.get("speech_audio_wav")
                or result.get("dialogue_audio_wav"),
                "speech_audio_json": result.get("speech_audio_json")
                or result.get("dialogue_audio_json"),
                "has_speech_audio": bool(speech_audio),
                "dialogue_audio": dialogue_audio,
                "dialogue_audio_wav": result.get("dialogue_audio_wav"),
                "dialogue_audio_json": result.get("dialogue_audio_json"),
                "has_dialogue_audio": bool(dialogue_audio),
                "concat_method": concat.get("method"),
            }
        )
        audio_note = ""
        if speech_audio:
            audio_note = (
                f", {int(speech_audio.get('line_count') or 0)} local speech "
                "line(s) muxed as AAC audio"
            )
        self._update_job_state(
            job_id,
            status="completed",
            current_stage="completed",
            progress_pct=100.0,
            progress_measurable=True,
            output_paths=outputs,
            completed=True,
            log_line=(
                f"Auto sequence MP4 verified: {Path(str(result['combined_video'])).name} "
                f"({outputs['clip_count']} clips, {verification.get('width')}×"
                f"{verification.get('height')} @ {verification.get('fps')}fps, "
                f"{verification.get('duration_sec')}s, "
                f"{verification.get('decoded_frames')} decoded frames{audio_note}) in "
                f"{round(time.time() - t_start, 2)}s."
            ),
        )

    def _execute_motion_graphics_job(
        self, job_id: str, payload: dict[str, Any], t_start: float
    ) -> None:
        """Build and optionally render one HyperFrames motion-graphics job."""

        template_id = str(payload.get("template") or "")
        if template_id == "auto":
            self._execute_auto_motion_graphics_job(job_id, payload, t_start)
            return

        mode = str(payload.get("mode") or "render")
        request_payload = payload.get("request") or {}
        script_text = str(payload.get("script_text") or "")
        if not isinstance(request_payload, dict):
            raise ValueError("motion-graphics request payload must be a JSON object")

        settings = get_settings()
        job_root = (settings.workspace_dir / "motion_graphics" / job_id).resolve()
        project_dir = job_root / "project"
        job_root.mkdir(parents=True, exist_ok=True)

        self._update_job_state(
            job_id,
            current_stage="Parsing script and validating template request",
            progress_pct=5.0,
            progress_measurable=True,
            log_line=f"Preparing HyperFrames template '{template_id}' in {mode} mode.",
        )
        built, _request, scenes = build_motion_graphics_project(
            template_id,
            request_payload,
            script_text=script_text,
            output_dir=project_dir,
        )
        if self._is_cancelled(job_id):
            raise InterruptedError("Motion-graphics job cancelled by user.")

        parsed_scenes_path = job_root / "parsed-scenes.json"
        parsed_scenes_path.write_text(
            json.dumps(scenes, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        outputs: dict[str, Any] = {
            "project_dir": str(built.output_dir),
            "index_html": str(built.index_path),
            "variables_json": str(built.variables_path),
            "build_manifest": str(built.output_dir / "motion-graphics-build.json"),
            "parsed_scenes": str(parsed_scenes_path),
            "template": template_id,
            "mode": mode,
            "scene_count": len(scenes),
        }
        self._update_job_state(
            job_id,
            current_stage="HyperFrames project built",
            progress_pct=25.0,
            progress_measurable=True,
            output_paths=outputs,
            log_line=(
                f"Built self-contained HyperFrames project with {len(built.files)} files "
                f"at {built.output_dir}"
            ),
        )

        if mode == "build_only":
            self._update_job_state(
                job_id,
                status="completed",
                current_stage="completed",
                progress_pct=100.0,
                progress_measurable=True,
                output_paths=outputs,
                completed=True,
                log_line=(
                    f"Build-only motion-graphics job completed in "
                    f"{round(time.time() - t_start, 2)}s."
                ),
            )
            return

        if mode != "render":
            raise ValueError("motion-graphics mode must be 'build_only' or 'render'")

        output_mp4 = built.output_dir / "renders" / f"{template_id}-{job_id}.mp4"

        def _on_render_progress(hf_pct: float, stage: str) -> None:
            mapped = 25.0 + (max(0.0, min(100.0, hf_pct)) / 100.0) * 69.0
            self._update_job_state(
                job_id,
                current_stage=stage,
                progress_pct=mapped,
                progress_measurable=True,
            )

        def _on_render_log(line: str) -> None:
            self._update_job_state(job_id, log_line=line)

        def _on_render_process(proc: subprocess.Popen[str] | None) -> None:
            with self._lock:
                if proc is None:
                    self._active_procs.pop(job_id, None)
                else:
                    self._active_procs[job_id] = proc
            self._update_job_state(job_id, worker_pid=proc.pid if proc else None)

        render_result = render_motion_graphics_project(
            project_dir=built.output_dir,
            variables=built.variables,
            output_path=output_mp4,
            fps=int(payload.get("fps") or 60),
            quality=str(payload.get("quality") or "standard"),
            on_progress=_on_render_progress,
            on_log=_on_render_log,
            on_process=_on_render_process,
            is_cancelled=lambda: self._is_cancelled(job_id),
        )
        render_log_path = job_root / "render-log.txt"
        render_log_path.write_text(
            "\n".join(str(line) for line in render_result.get("log_tail", [])),
            encoding="utf-8",
        )
        outputs.update(
            {
                "video": str(output_mp4),
                "render_log": str(render_log_path),
                "render_elapsed_sec": render_result.get("elapsed_sec"),
            }
        )

        self._update_job_state(
            job_id,
            current_stage="Verifying rendered MP4 from disk",
            progress_pct=96.0,
            progress_measurable=True,
            output_paths=outputs,
            log_line="HyperFrames render finished; starting MP4 verification.",
        )
        verification = verify_mp4(output_mp4)
        verification_path = job_root / "verification.json"
        verification_path.write_text(
            json.dumps(verification, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        outputs["verification"] = verification
        outputs["verification_json"] = str(verification_path)
        if not verification.get("verified"):
            raise RuntimeError(
                "Rendered MP4 failed verification: "
                + str(verification.get("error") or verification)
            )

        self._update_job_state(
            job_id,
            status="completed",
            current_stage="completed",
            progress_pct=100.0,
            progress_measurable=True,
            output_paths=outputs,
            completed=True,
            log_line=(
                f"Motion-graphics MP4 verified: {output_mp4.name} "
                f"({verification.get('width')}×{verification.get('height')} @ "
                f"{verification.get('fps')}fps, {verification.get('duration_sec')}s, "
                f"{verification.get('decoded_frames')} decoded frames) in "
                f"{round(time.time() - t_start, 2)}s."
            ),
        )

    def _execute_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job["status"] == "cancelled":
            return

        t_start = time.time()
        payload = job["payload"]
        jtype = job["job_type"]

        self._update_job_state(
            job_id,
            status="running",
            current_stage="initializing",
            started=True,
            log_line=f"Starting job '{jtype}'",
        )

        try:
            if jtype == "character_preview":
                char_id = payload["character_id"]
                profile = get_character(char_id)
                out_png = get_settings().characters_dir / f"{char_id}_preview.png"
                self._update_job_state(
                    job_id,
                    current_stage="Rendering 3D character portrait in Blender",
                    progress_pct=None,
                    progress_measurable=False,
                )
                res = self._run_blender_subprocess(
                    job_id,
                    {"mode": "character_preview", "character": profile, "output_png": str(out_png)},
                )
                if not res.get("exists"):
                    raise RuntimeError("Character preview PNG was not created.")
                update_character(char_id, {"preview_image_path": str(out_png)})
                self._update_job_state(
                    job_id,
                    status="completed",
                    current_stage="completed",
                    progress_pct=100.0,
                    progress_measurable=True,
                    output_paths={"preview_png": str(out_png)},
                    completed=True,
                    log_line=f"Character 3D preview saved to {out_png.name}",
                )
                return

            if jtype == "environment_preview":
                env_id = payload.get("environment_preset", "fortress")
                tod = payload.get("time_of_day", "sunset")
                weather = payload.get("weather", "clear")
                out_png = get_settings().previews_dir / f"env_{env_id}_{tod}_{weather}.png"
                self._update_job_state(
                    job_id,
                    current_stage=f"Rendering 3D environment '{env_id}' ({tod}, {weather})",
                    progress_pct=None,
                    progress_measurable=False,
                )
                res = self._run_blender_subprocess(
                    job_id,
                    {
                        "mode": "environment_preview",
                        "environment_preset": env_id,
                        "time_of_day": tod,
                        "weather": weather,
                        "location_key": f"{env_id}_{tod}_{weather}",
                        "output_png": str(out_png),
                    },
                )
                if not res.get("exists"):
                    raise RuntimeError("Environment preview PNG was not created.")
                self._update_job_state(
                    job_id,
                    status="completed",
                    current_stage="completed",
                    progress_pct=100.0,
                    progress_measurable=True,
                    output_paths={"preview_png": str(out_png)},
                    completed=True,
                    log_line=f"Environment preview saved to {out_png.name}",
                )
                return

            if jtype == "motion_graphics":
                self._execute_motion_graphics_job(job_id, payload, t_start)
                return

            project_id = job["project_id"] or payload["project_id"]
            project = get_project(project_id, include_details=True)

            if jtype == "render_scene":
                scene = get_scene(payload["scene_id"])
                rendered = self._execute_single_scene_pipeline(job_id, project, scene, 0.0, 100.0)
                self._update_job_state(
                    job_id,
                    status="completed",
                    current_stage="completed",
                    progress_pct=100.0,
                    progress_measurable=True,
                    output_paths={
                        "scene_video": rendered["rendered_video_path"],
                        "thumbnail": rendered["thumbnail_path"],
                    },
                    completed=True,
                    log_line=f"Scene '{rendered['title']}' rendered & verified.",
                )
                return

            if jtype == "render_selected_scenes":
                target_ids = list(payload.get("scene_ids") or [])
                scenes = [s for s in list_project_scenes(project_id) if s["id"] in target_ids]
                if not scenes:
                    raise ValueError("No valid scenes selected for rendering.")
                span = 100.0 / len(scenes)
                outputs: dict[str, Any] = {"scenes": []}
                for idx, sc in enumerate(scenes):
                    done_sc = self._execute_single_scene_pipeline(job_id, project, sc, idx * span, span)
                    outputs["scenes"].append(done_sc["rendered_video_path"])
                self._update_job_state(
                    job_id,
                    status="completed",
                    current_stage="completed",
                    progress_pct=100.0,
                    progress_measurable=True,
                    output_paths=outputs,
                    completed=True,
                    log_line=f"Rendered and verified {len(scenes)} selected scene(s).",
                )
                return

            if jtype == "render_full_project":
                all_scenes = list_project_scenes(project_id)
                if not all_scenes:
                    raise ValueError("Project has no storyboard scenes to render.")

                force_rerender = bool(payload.get("force_rerender", False))
                update_project(project_id, {"export_status": "rendering"})

                failed_scenes: list[dict[str, str]] = []
                skipped_scenes: list[str] = []
                ready_clips: list[Path] = []
                full_subtitles: list[dict[str, Any]] = []
                timeline_cursor = 0.0

                scene_budget_pct = 86.0 / len(all_scenes)
                for idx, sc in enumerate(all_scenes):
                    already_valid = (
                        not force_rerender
                        and sc["generation_status"] == "completed"
                        and sc["rendered_video_path"]
                        and Path(sc["rendered_video_path"]).is_file()
                    )
                    if already_valid:
                        clip_path = Path(sc["rendered_video_path"])
                        ready_clips.append(clip_path)
                        skipped_scenes.append(f"{sc['title']} (reused cached verified scene)")
                        for seg in sc.get("render_metrics", {}).get("subtitle_segments", []):
                            full_subtitles.append(
                                {
                                    "speaker": seg["speaker"],
                                    "text": seg["text"],
                                    "start_sec": round(timeline_cursor + float(seg["start_sec"]), 3),
                                    "end_sec": round(timeline_cursor + float(seg["end_sec"]), 3),
                                }
                            )
                        timeline_cursor += float(sc["duration_sec"])
                        self._update_job_state(
                            job_id,
                            current_stage=f"Reusing already-rendered Scene {idx + 1}/{len(all_scenes)}",
                            progress_pct=(idx + 1) * scene_budget_pct,
                            progress_measurable=True,
                        )
                        continue

                    try:
                        done_sc = self._execute_single_scene_pipeline(
                            job_id,
                            project,
                            sc,
                            scene_offset_pct=idx * scene_budget_pct,
                            scene_span_pct=scene_budget_pct,
                        )
                        ready_clips.append(Path(done_sc["rendered_video_path"]))
                        for seg in done_sc.get("render_metrics", {}).get("subtitle_segments", []):
                            full_subtitles.append(
                                {
                                    "speaker": seg["speaker"],
                                    "text": seg["text"],
                                    "start_sec": round(timeline_cursor + float(seg["start_sec"]), 3),
                                    "end_sec": round(timeline_cursor + float(seg["end_sec"]), 3),
                                }
                            )
                        timeline_cursor += float(done_sc["duration_sec"])
                    except InterruptedError:
                        raise
                    except Exception as sc_err:
                        failed_scenes.append({"scene_id": sc["id"], "title": sc["title"], "error": str(sc_err)})
                        update_scene(sc["id"], {"generation_status": "failed", "error_message": str(sc_err)})
                        self._update_job_state(
                            job_id,
                            log_line=f"Scene '{sc['title']}' failed: {sc_err}",
                        )

                if not ready_clips:
                    update_project(project_id, {"export_status": "failed"})
                    raise RuntimeError(
                        "All scenes failed to render; aborting final export. Details: "
                        + json.dumps(failed_scenes)
                    )

                # Assemble final chronological MP4 + unified subtitles
                self._update_job_state(
                    job_id,
                    current_stage="Assembling chronological MP4 & synchronizing audio/subtitles",
                    progress_pct=None,
                    progress_measurable=False,
                    log_line=f"Concatenating {len(ready_clips)} scene(s) into final MP4...",
                )
                proj_dir = get_project_dir(project_id, create=True)
                full_srt = proj_dir / "exports" / f"{project_id}_subtitles.srt"
                full_vtt = proj_dir / "exports" / f"{project_id}_subtitles.vtt"
                write_srt_file(full_subtitles, full_srt)
                write_vtt_file(full_subtitles, full_vtt)

                full_ur_srt: Path | None = None
                full_ur_vtt: Path | None = None
                if project.get("language") == "roman_ur" and full_subtitles:
                    ur_full_segs = build_urdu_script_segments(full_subtitles)
                    full_ur_srt = proj_dir / "exports" / f"{project_id}_subtitles_ur.srt"
                    full_ur_vtt = proj_dir / "exports" / f"{project_id}_subtitles_ur.vtt"
                    write_srt_file(ur_full_segs, full_ur_srt)
                    write_vtt_file(ur_full_segs, full_ur_vtt)

                export_mp4 = proj_dir / "exports" / f"{project_id}_final.mp4"
                assemble_project_mp4(
                    scene_mp4_paths=ready_clips,
                    output_mp4_path=export_mp4,
                    resolution=project["resolution"],
                    aspect_ratio=project["aspect_ratio"],
                    fps=int(project["fps"]),
                    full_srt_path=full_srt if full_subtitles else None,
                )

                # Mandatory Post-Export Decode Verification
                self._update_job_state(
                    job_id,
                    current_stage="Verifying exported MP4 streams & decoding frames",
                    progress_pct=96.0,
                    progress_measurable=True,
                )
                exp_w, exp_h = compute_dimensions(project["resolution"], project["aspect_ratio"])
                validation = validate_exported_mp4(
                    export_mp4,
                    expect_audio=True,
                    expected_width=exp_w,
                    expected_height=exp_h,
                )
                if not validation["valid"]:
                    update_project(project_id, {"export_status": "failed"})
                    raise RuntimeError(
                        "Final MP4 failed post-export stream verification: " + "; ".join(validation["errors"])
                    )

                total_render_time = round(time.time() - t_start, 2)
                hw_warnings = evaluate_workload_warnings(
                    resolution=project["resolution"],
                    fps=int(project["fps"]),
                    duration_sec=validation["duration_sec"],
                    quality_profile=project["quality_profile"],
                )
                report = {
                    "output_filename": export_mp4.name,
                    "output_path": str(export_mp4),
                    "subtitle_vtt_path": str(full_vtt),
                    "subtitle_srt_path": str(full_srt),
                    "subtitle_ur_vtt_path": str(full_ur_vtt) if full_ur_vtt else "",
                    "subtitle_ur_srt_path": str(full_ur_srt) if full_ur_srt else "",
                    "duration_sec": validation["duration_sec"],
                    "resolution": validation["resolution"],
                    "fps": validation["fps"],
                    "video_codec": validation["video_codec"],
                    "audio_status": validation["audio_status"],
                    "audio_codec": validation["audio_codec"],
                    "file_size_bytes": validation["file_size_bytes"],
                    "file_size_mb": validation["file_size_mb"],
                    "render_time_sec": total_render_time,
                    "warnings": list(validation["warnings"]) + hw_warnings,
                    "failed_scenes": failed_scenes,
                    "skipped_or_cached_scenes": skipped_scenes,
                    "scenes_included": len(ready_clips),
                    "scenes_total": len(all_scenes),
                    "verified_at": utc_now_iso(),
                }
                report_file = proj_dir / "reports" / "latest_render_report.json"
                report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

                export_state = "completed_with_warnings" if failed_scenes else "completed"
                update_project(
                    project_id,
                    {
                        "export_status": export_state,
                        "latest_export_path": str(export_mp4),
                        "render_report": report,
                    },
                )
                sync_project_manifest(project_id)

                out_paths_dict: dict[str, Any] = {
                    "final_mp4": str(export_mp4),
                    "subtitles_vtt": str(full_vtt),
                    "subtitles_srt": str(full_srt),
                    "render_report": str(report_file),
                }
                if full_ur_vtt and full_ur_srt:
                    out_paths_dict["subtitles_ur_vtt"] = str(full_ur_vtt)
                    out_paths_dict["subtitles_ur_srt"] = str(full_ur_srt)

                self._update_job_state(
                    job_id,
                    status="completed",
                    current_stage="completed",
                    progress_pct=100.0,
                    progress_measurable=True,
                    output_paths=out_paths_dict,
                    completed=True,
                    log_line=(
                        f"Export verified: {export_mp4.name} ({validation['resolution']} @ {validation['fps']}fps, "
                        f"{validation['duration_sec']}s, {validation['file_size_mb']} MB in {total_render_time}s)"
                    ),
                )
                return

            raise ValueError(f"Unsupported job_type '{jtype}'")

        except InterruptedError as cancel_exc:
            logger.info("Job cancelled: %s (%s)", job_id, cancel_exc)
            self._update_job_state(
                job_id,
                status="cancelled",
                current_stage="cancelled",
                progress_pct=None,
                progress_measurable=False,
                completed=True,
                log_line=str(cancel_exc),
            )
        except Exception as exc:
            logger.exception("Job failed: %s", job_id)
            self._update_job_state(
                job_id,
                status="failed",
                current_stage="failed",
                progress_pct=None,
                progress_measurable=False,
                error_details=str(exc),
                completed=True,
                log_line=f"ERROR: {exc}",
            )

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._execute_job(job_id)
            finally:
                self._queue.task_done()


_JOB_MANAGER = JobManager()


def get_job_manager() -> JobManager:
    return _JOB_MANAGER
