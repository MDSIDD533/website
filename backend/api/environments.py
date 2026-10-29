"""Environment & Camera Studio API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.job_manager import get_job_manager
from scene_engine.cameras import CAMERA_MOVEMENTS, CAMERA_SHOT_CATALOG
from scene_engine.environments import ENVIRONMENT_CATALOG, TIME_OPTIONS, WEATHER_OPTIONS

router = APIRouter(prefix="/api/environments", tags=["environments"])


class EnvironmentPreviewRequest(BaseModel):
    environment_preset: str = "fortress"
    time_of_day: str = "sunset"
    weather: str = "clear"
    project_id: str | None = None


@router.get("")
def api_list_environments() -> dict[str, Any]:
    return {
        "environments": ENVIRONMENT_CATALOG,
        "times_of_day": TIME_OPTIONS,
        "weather_options": WEATHER_OPTIONS,
        "camera_shots": CAMERA_SHOT_CATALOG,
        "camera_movements": CAMERA_MOVEMENTS,
    }


@router.post("/preview-render")
def api_render_environment_preview(req: EnvironmentPreviewRequest) -> dict[str, Any]:
    job = get_job_manager().enqueue_job(
        "environment_preview",
        project_id=req.project_id,
        payload=req.model_dump(),
    )
    return {
        "job": job,
        "expected_preview_url": f"/api/media/preview/previews/env_{req.environment_preset}_{req.time_of_day}_{req.weather}.png",
    }
