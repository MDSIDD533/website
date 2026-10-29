"""Local AI Model Manager API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.security import (
    SecurityViolationError,
    resolve_safe_path,
    validate_uploaded_file,
)
from model_manager.registry import (
    configure_models_directory,
    get_model,
    install_or_register_model,
    list_models,
    remove_model,
    set_active_model,
    verify_model_files,
)

router = APIRouter(prefix="/api/models", tags=["models"])


class InstallModelRequest(BaseModel):
    user_confirmed: bool = False


class ToggleActiveModelRequest(BaseModel):
    active: bool


class ConfigureModelPathRequest(BaseModel):
    models_dir: str


@router.get("")
def api_list_models() -> dict[str, Any]:
    return {"models": list_models(), "models_dir": str(get_settings().models_dir)}


@router.get("/{model_id}")
def api_get_model(model_id: str) -> dict[str, Any]:
    try:
        return get_model(model_id)
    except (KeyError, SecurityViolationError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{model_id}/install")
def api_install_model(model_id: str, req: InstallModelRequest) -> dict[str, Any]:
    try:
        return install_or_register_model(model_id, user_confirmed=req.user_confirmed)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, RuntimeError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{model_id}/import-local")
async def api_import_local_model_weights(
    model_id: str,
    user_confirmed: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    try:
        if not user_confirmed:
            raise PermissionError("Explicit user confirmation is required before importing model files.")
        settings = get_settings()
        staging = settings.temp_dir / f"model_import_{model_id}"
        staging.mkdir(parents=True, exist_ok=True)
        staged_paths = []
        for f in files:
            data = await f.read()
            safe_name = validate_uploaded_file(f.filename or "weights.onnx", data, category="model", max_mb=500)
            dst = resolve_safe_path(staging, safe_name)
            dst.write_bytes(data)
            staged_paths.append(dst)
        return install_or_register_model(model_id, user_confirmed=True, local_source_files=staged_paths)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, RuntimeError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{model_id}/verify")
def api_verify_model(model_id: str) -> dict[str, Any]:
    try:
        return verify_model_files(model_id)
    except (KeyError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{model_id}/active")
def api_set_active_model(model_id: str, req: ToggleActiveModelRequest) -> dict[str, Any]:
    try:
        return set_active_model(model_id, req.active)
    except (KeyError, RuntimeError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{model_id}")
def api_remove_model(model_id: str) -> dict[str, Any]:
    try:
        return remove_model(model_id)
    except (KeyError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/configure-path")
def api_configure_models_path(req: ConfigureModelPathRequest) -> dict[str, Any]:
    return configure_models_directory(req.models_dir)
