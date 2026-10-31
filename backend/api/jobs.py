"""Render Queue & Background Job Control API routes."""

from __future__ import annotations

import mimetypes
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.config import get_settings
from backend.core.logging_config import get_recent_logs
from backend.services.job_manager import get_job_manager
from backend.services.motion_graphics_service import (
    list_templates,
    plan_auto_motion_graphics,
    prepare_request,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class RenderSceneRequest(BaseModel):
    project_id: str
    scene_id: str


class RenderSelectedRequest(BaseModel):
    project_id: str
    scene_ids: list[str]


class RenderProjectRequest(BaseModel):
    project_id: str
    force_rerender: bool = False


class MotionGraphicsJobRequest(BaseModel):
    template: Literal["title", "data", "shape", "quote", "outro"]
    request: dict[str, Any] = Field(default_factory=dict)
    script_text: str = Field(default="", max_length=20000)
    mode: Literal["build_only", "render"] = "render"
    fps: Literal[24, 30, 60] = 60
    quality: Literal["draft", "standard", "high"] = "standard"
    project_id: str | None = None


class AutoMotionGraphicsJobRequest(BaseModel):
    script_text: str = Field(min_length=1, max_length=20000)
    mode: Literal["build_only", "render"] = "render"
    fps: Literal[24, 30, 60] = 30
    quality: Literal["draft", "standard", "high"] = "standard"
    brand_label: str = Field(default="SIDD STUDIO", max_length=36)
    include_dialogue_audio: bool = False
    include_narration_audio: bool = False
    project_id: str | None = None


def _motion_preview_payload(req: MotionGraphicsJobRequest) -> dict[str, Any]:
    try:
        request_obj, scenes = prepare_request(
            req.template, req.request, script_text=req.script_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "template": req.template,
        "scenes": scenes,
        "scene_count": len(scenes),
        "request": jsonable_encoder(asdict(request_obj)),
        "variables": jsonable_encoder(request_obj.variables()),
    }


def _auto_motion_preview_payload(
    req: AutoMotionGraphicsJobRequest,
) -> dict[str, Any]:
    try:
        plan = plan_auto_motion_graphics(
            req.script_text,
            brand_label=req.brand_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    plan_payload = jsonable_encoder(plan.to_dict())
    return {
        "template": "auto",
        "mode": req.mode,
        "fps": req.fps,
        "quality": req.quality,
        "include_dialogue_audio": req.include_dialogue_audio,
        "include_narration_audio": req.include_narration_audio,
        "scenes": plan_payload["scenes"],
        "scene_count": plan_payload["scene_count"],
        "clips": plan_payload["clips"],
        "clip_count": plan_payload["clip_count"],
        "total_duration_sec": plan_payload["total_duration_sec"],
        "plan": plan_payload,
    }


@router.get("")
def api_list_jobs(project_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"jobs": get_job_manager().list_jobs(project_id=project_id, limit=limit)}


@router.get("/logs")
def api_get_logs(project_id: str | None = None, job_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"logs": get_recent_logs(limit=limit, project_id=project_id, job_id=job_id)}


@router.get("/motion-graphics/templates")
def api_list_motion_graphics_templates() -> dict[str, Any]:
    return {"templates": list_templates()}


@router.post("/motion-graphics/preview")
def api_preview_motion_graphics(req: MotionGraphicsJobRequest) -> dict[str, Any]:
    return _motion_preview_payload(req)


@router.post("/motion-graphics")
def api_enqueue_motion_graphics(req: MotionGraphicsJobRequest) -> dict[str, Any]:
    preview = _motion_preview_payload(req)
    job = get_job_manager().enqueue_job(
        "motion_graphics",
        project_id=req.project_id,
        payload={
            "template": req.template,
            "request": req.request,
            "prepared_request": preview["request"],
            "script_text": req.script_text,
            "parsed_scene_count": preview["scene_count"],
            "mode": req.mode,
            "fps": req.fps,
            "quality": req.quality,
            "project_id": req.project_id,
        },
    )
    return {"job": job, "preview": preview}


@router.post("/motion-graphics/auto/preview")
def api_preview_auto_motion_graphics(
    req: AutoMotionGraphicsJobRequest,
) -> dict[str, Any]:
    return _auto_motion_preview_payload(req)


@router.post("/motion-graphics/auto")
def api_enqueue_auto_motion_graphics(
    req: AutoMotionGraphicsJobRequest,
) -> dict[str, Any]:
    preview = _auto_motion_preview_payload(req)
    job = get_job_manager().enqueue_job(
        "motion_graphics",
        project_id=req.project_id,
        payload={
            "template": "auto",
            "script_text": req.script_text,
            "auto_plan": preview["plan"],
            "parsed_scene_count": preview["scene_count"],
            "planned_clip_count": preview["clip_count"],
            "planned_duration_sec": preview["total_duration_sec"],
            "mode": req.mode,
            "fps": req.fps,
            "quality": req.quality,
            "brand_label": req.brand_label,
            "include_dialogue_audio": req.include_dialogue_audio,
            "include_narration_audio": req.include_narration_audio,
            "project_id": req.project_id,
        },
    )
    return {"job": job, "preview": preview}


@router.get("/{job_id}")
def api_get_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/artifacts/{artifact_key}")
def api_get_job_artifact(job_id: str, artifact_key: str) -> FileResponse:
    try:
        job = get_job_manager().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    raw_path = (job.get("output_paths") or {}).get(artifact_key)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_key}' not found.")

    workspace = get_settings().workspace_dir.resolve()
    candidate = Path(raw_path).expanduser().resolve()
    if not candidate.is_relative_to(workspace):
        raise HTTPException(status_code=403, detail="Artifact is outside the workspace.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact file not found: {candidate.name}")

    media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return FileResponse(
        candidate,
        media_type=media_type,
        filename=candidate.name,
        content_disposition_type="inline",
    )


@router.post("/render-scene")
def api_enqueue_render_scene(req: RenderSceneRequest) -> dict[str, Any]:
    job = get_job_manager().enqueue_job(
        "render_scene",
        project_id=req.project_id,
        payload={"project_id": req.project_id, "scene_id": req.scene_id},
    )
    return {"job": job}


@router.post("/render-selected")
def api_enqueue_render_selected(req: RenderSelectedRequest) -> dict[str, Any]:
    job = get_job_manager().enqueue_job(
        "render_selected_scenes",
        project_id=req.project_id,
        payload={"project_id": req.project_id, "scene_ids": req.scene_ids},
    )
    return {"job": job}


@router.post("/render-project")
def api_enqueue_render_project(req: RenderProjectRequest) -> dict[str, Any]:
    job = get_job_manager().enqueue_job(
        "render_full_project",
        project_id=req.project_id,
        payload={"project_id": req.project_id, "force_rerender": req.force_rerender},
    )
    return {"job": job}


@router.post("/{job_id}/pause")
def api_pause_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().pause_job(job_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{job_id}/resume")
def api_resume_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().resume_job(job_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{job_id}/cancel")
def api_cancel_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{job_id}/retry")
def api_retry_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().retry_job(job_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
