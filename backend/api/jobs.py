"""Render Queue & Background Job Control API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.logging_config import get_recent_logs
from backend.services.job_manager import get_job_manager

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


@router.get("")
def api_list_jobs(project_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"jobs": get_job_manager().list_jobs(project_id=project_id, limit=limit)}


@router.get("/logs")
def api_get_logs(project_id: str | None = None, job_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"logs": get_recent_logs(limit=limit, project_id=project_id, job_id=job_id)}


@router.get("/{job_id}")
def api_get_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_manager().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
