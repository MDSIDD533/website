"""Hardware Monitor, Storage Breakdown, and Studio Privacy/Path Settings API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import PerformanceMode, get_settings, reconfigure_settings
from backend.core.security import SecurityViolationError, validate_local_endpoint_url
from backend.services.hardware_service import (
    evaluate_workload_warnings,
    inspect_hardware,
)
from project_storage.manager import cleanup_temp_files, get_storage_usage

router = APIRouter(prefix="/api/system", tags=["system_and_hardware"])


class UpdateSettingsRequest(BaseModel):
    workspace_dir: str | None = None
    models_dir: str | None = None
    local_only_default: bool | None = None
    allow_model_downloads: bool | None = None
    performance_mode: PerformanceMode | None = None
    local_llm_url: str | None = None
    local_llm_model: str | None = None


@router.get("/hardware")
def api_get_hardware() -> dict[str, Any]:
    return inspect_hardware()


@router.get("/storage")
def api_get_storage() -> dict[str, Any]:
    return get_storage_usage()


@router.post("/cleanup-temp")
def api_cleanup_temp() -> dict[str, Any]:
    return cleanup_temp_files()


@router.post("/workload-check")
def api_workload_check(payload: dict[str, Any]) -> dict[str, Any]:
    warnings = evaluate_workload_warnings(
        resolution=payload.get("resolution", "720p"),
        fps=int(payload.get("fps", 24)),
        duration_sec=float(payload.get("duration_sec", 10.0)),
        quality_profile=payload.get("quality_profile", "low_resource"),
    )
    return {"warnings": warnings}


@router.get("/settings")
def api_get_settings() -> dict[str, Any]:
    s = get_settings()
    return {
        "app_name": s.app_name,
        "version": s.version,
        "workspace_dir": str(s.workspace_dir),
        "models_dir": str(s.models_dir),
        "database_path": str(s.db_file),
        "local_only_default": s.local_only_default,
        "allow_model_downloads": s.allow_model_downloads,
        "performance_mode": s.performance_mode,
        "local_llm_url": s.local_llm_url,
        "local_llm_model": s.local_llm_model,
        "max_upload_mb": s.max_upload_mb,
    }


@router.patch("/settings")
def api_update_settings(req: UpdateSettingsRequest) -> dict[str, Any]:
    try:
        if req.local_llm_url is not None:
            validate_local_endpoint_url(req.local_llm_url)
        reconfigure_settings(
            workspace_dir=req.workspace_dir,
            models_dir=req.models_dir,
            local_only_default=req.local_only_default,
            allow_model_downloads=req.allow_model_downloads,
            performance_mode=req.performance_mode,
            local_llm_url=req.local_llm_url,
            local_llm_model=req.local_llm_model,
        )
        return api_get_settings()
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
