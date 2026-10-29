"""Character Studio API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.core.security import SecurityViolationError
from backend.services.job_manager import get_job_manager
from character_engine.profiles import (
    DEFAULT_EXPRESSIONS,
    OUTFIT_PRESETS,
    create_character,
    delete_character,
    get_character,
    list_characters,
    update_character,
)

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("/presets")
def api_character_presets() -> dict[str, Any]:
    return {
        "outfits": list(OUTFIT_PRESETS.values()),
        "expressions": DEFAULT_EXPRESSIONS,
        "hair_styles": ["short_dark", "long_wavy", "braided_warrior", "turban_crown", "scholar_sweep"],
    }


@router.get("")
def api_list_characters(project_id: str | None = None) -> dict[str, Any]:
    return {"characters": list_characters(project_id=project_id)}


@router.post("")
def api_create_character(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return create_character(payload)
    except (ValueError, SecurityViolationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{character_id}")
def api_get_character(character_id: str) -> dict[str, Any]:
    try:
        return get_character(character_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{character_id}")
def api_update_character(character_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        return update_character(character_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{character_id}/preview-render")
def api_render_character_preview(character_id: str) -> dict[str, Any]:
    try:
        ch = get_character(character_id)
        job = get_job_manager().enqueue_job(
            "character_preview",
            project_id=ch.get("project_id"),
            payload={"character_id": character_id},
        )
        return {"job": job}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{character_id}")
def api_delete_character(character_id: str) -> dict[str, Any]:
    try:
        return delete_character(character_id)
    except SecurityViolationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
