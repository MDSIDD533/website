"""Animation & Combat Choreography Studio API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from animation_engine.choreography import (
    SUPPORTED_ANIMATION_CLIPS,
    SUPPORTED_EXPRESSIONS,
    plan_scene_choreography,
    resolve_collision_free_positions,
)

router = APIRouter(prefix="/api/animations", tags=["animations"])


@router.get("")
def api_list_animations() -> dict[str, Any]:
    return {
        "clips": SUPPORTED_ANIMATION_CLIPS,
        "expressions": SUPPORTED_EXPRESSIONS,
        "attack_directions": ["right_slash", "left_slash", "overhead_strike", "jab_cross", "front_kick"],
        "defense_reactions": ["block", "dodge", "parry_counter", "fall", "get_up"],
    }


@router.post("/solve-choreography")
def api_solve_choreography(payload: dict[str, Any]) -> dict[str, Any]:
    if "positions" in payload and isinstance(payload["positions"], list):
        return {"character_positions": resolve_collision_free_positions(payload["positions"])}
    return plan_scene_choreography(
        characters_present=payload.get("characters_present") or ["Hero", "Rival"],
        actions=payload.get("actions") or ["cinematic_combat"],
        is_combat=bool(payload.get("is_combat", True)),
    )
