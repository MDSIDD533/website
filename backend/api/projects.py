"""Projects, Script Analysis, Storyboard, Timeline, Provenance, and Safe Deletion API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.core.config import get_settings
from backend.core.security import (
    SecurityViolationError,
    resolve_safe_path,
    validate_uploaded_file,
)
from backend.services.license_service import (
    generate_project_license_report,
    record_asset_provenance,
)
from backend.services.project_service import (
    create_project,
    delete_project_completely,
    generate_project_storyboard,
    get_project,
    get_scene,
    list_project_scenes,
    list_projects,
    reopen_project_from_manifest,
    reorder_project_scenes,
    update_project,
    update_scene,
)
from model_manager.registry import list_models
from project_storage.manager import get_project_dir, read_project_manifest
from story_engine.normalizer import SAMPLE_SCRIPTS
from story_engine.parser import analyze_script

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str = Field(default="Untitled Cinematic Story", min_length=1, max_length=140)
    description: str = ""
    language: str = "en"
    visual_style: str = "cinematic_3d"
    genre: str = "historical"
    historical_accuracy_mode: bool = False
    target_duration_sec: float = Field(default=10.0, ge=2.5, le=300.0)
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    fps: int = 24
    quality_profile: str = "low_resource"
    num_scenes_target: int = Field(default=3, ge=1, le=24)
    script_text: str = ""
    narration_prefs: dict[str, Any] | None = None
    dialogue_prefs: dict[str, Any] | None = None
    music_prefs: dict[str, Any] | None = None
    auto_generate_storyboard: bool = False


class AnalyzeScriptRequest(BaseModel):
    script_text: str
    language: str = "auto"
    target_scenes: int = Field(default=3, ge=1, le=24)
    genre: str = "historical"
    historical_accuracy_mode: bool = False


class GenerateStoryboardRequest(BaseModel):
    script_text: str | None = None


class ReorderScenesRequest(BaseModel):
    ordered_scene_ids: list[str]


class ReopenManifestRequest(BaseModel):
    manifest_filename: str = "project_manifest.json"
    project_folder_id: str


class DeleteProjectRequest(BaseModel):
    confirm_token: str


@router.get("/samples")
def get_sample_scripts() -> dict[str, Any]:
    return {"samples": SAMPLE_SCRIPTS}


@router.post("/analyze-preview")
def analyze_script_preview(req: AnalyzeScriptRequest) -> dict[str, Any]:
    try:
        return analyze_script(
            req.script_text,
            language=req.language,
            target_scenes=req.target_scenes,
            genre=req.genre,
            historical_accuracy_mode=req.historical_accuracy_mode,
        )
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def api_list_projects() -> dict[str, Any]:
    return {"projects": list_projects()}


@router.post("")
def api_create_project(req: CreateProjectRequest) -> dict[str, Any]:
    try:
        return create_project(req.model_dump())
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}")
def api_get_project(project_id: str) -> dict[str, Any]:
    try:
        return get_project(project_id, include_details=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{project_id}")
def api_update_project(project_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        return update_project(project_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/storyboard")
def api_generate_storyboard(project_id: str, req: GenerateStoryboardRequest) -> dict[str, Any]:
    try:
        return generate_project_storyboard(project_id, script_override=req.script_text)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/scenes")
def api_list_scenes(project_id: str) -> dict[str, Any]:
    try:
        return {"scenes": list_project_scenes(project_id)}
    except (KeyError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{project_id}/scenes/{scene_id}")
def api_update_scene(project_id: str, scene_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        sc = get_scene(scene_id)
        if sc["project_id"] != project_id:
            raise HTTPException(status_code=400, detail="Scene does not belong to specified project.")
        return update_scene(scene_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/scenes/reorder")
def api_reorder_scenes(project_id: str, req: ReorderScenesRequest) -> dict[str, Any]:
    try:
        scenes = reorder_project_scenes(project_id, req.ordered_scene_ids)
        return {"scenes": scenes}
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/manifest")
def api_get_manifest(project_id: str) -> dict[str, Any]:
    try:
        manifest = read_project_manifest(project_id)
        if manifest is None:
            manifest = get_project(project_id, include_details=True)
        return manifest
    except (KeyError, SecurityViolationError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reopen")
def api_reopen_project(req: ReopenManifestRequest) -> dict[str, Any]:
    try:
        settings = get_settings()
        folder = resolve_safe_path(settings.projects_dir, req.project_folder_id)
        manifest_path = resolve_safe_path(folder, req.manifest_filename)
        if not manifest_path.is_file():
            raise HTTPException(status_code=404, detail="Manifest file not found in local project folder.")
        return reopen_project_from_manifest(manifest_path)
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/upload-asset")
async def api_upload_project_asset(
    project_id: str,
    file: UploadFile = File(...),
    category: str = Form("image"),
    license_spdx: str = Form("Unverified-User-Upload"),
    attribution_required: bool = Form(False),
    commercial_allowed: bool = Form(True),
) -> dict[str, Any]:
    try:
        settings = get_settings()
        content = await file.read()
        safe_name = validate_uploaded_file(
            file.filename or "asset.bin",
            content,
            category=category,
            max_mb=settings.max_upload_mb,
        )
        proj_dir = get_project_dir(project_id, create=True)
        dest = resolve_safe_path(proj_dir / "uploads", safe_name)
        dest.write_bytes(content)

        uncertain = license_spdx in {"", "Unverified-User-Upload", "Unknown"}
        prov = record_asset_provenance(
            project_id=project_id,
            asset_name=safe_name,
            asset_type=category,
            source_kind="user_upload",
            license_spdx=license_spdx or "Unverified-User-Upload",
            attribution_required=attribution_required,
            commercial_allowed=commercial_allowed,
            uncertain_rights=uncertain,
            notes="Uploaded locally by user; verify third-party rights before redistribution.",
            local_path=str(dest),
        )
        return {"filename": safe_name, "size_bytes": len(content), "provenance": prov}
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/license-report")
def api_project_license_report(project_id: str) -> dict[str, Any]:
    try:
        get_project(project_id, include_details=False)
        return generate_project_license_report(project_id, installed_models=list_models())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{project_id}")
def api_delete_project(project_id: str, confirm_token: str = "") -> dict[str, Any]:
    try:
        return delete_project_completely(project_id, confirm_token=confirm_token)
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
