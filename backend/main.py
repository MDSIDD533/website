"""SIDD AI VIDEO STUDIO — FastAPI Application Entrypoint & WebSocket Hub."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import (
    animations,
    characters,
    environments,
    hardware,
    jobs,
    library,
    models,
    projects,
    voices,
)
from backend.core.config import REPO_ROOT, get_settings
from backend.core.database import init_database
from backend.core.logging_config import get_logger, setup_logging
from backend.services.job_manager import get_job_manager
from scripts.setup_headless_bpy import ensure_headless_bpy

logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    settings.ensure_directories()
    init_database()
    bpy_status = ensure_headless_bpy()
    logger.info("SIDD AI VIDEO STUDIO initialized. Blender status: %s", bpy_status)
    get_job_manager().start()
    yield


app = FastAPI(
    title="SIDD AI VIDEO STUDIO",
    description="Local-first Personal AI 3D Video Studio — Script to Animated 3D MP4",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(characters.router)
app.include_router(voices.router)
app.include_router(environments.router)
app.include_router(animations.router)
app.include_router(jobs.router)
app.include_router(library.router)
app.include_router(models.router)
app.include_router(hardware.router)


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "version": s.version,
        "local_only": s.local_only_default,
        "performance_mode": s.performance_mode,
    }


@app.websocket("/ws/jobs")
async def websocket_jobs(ws: WebSocket) -> None:
    await ws.accept()
    jm = get_job_manager()
    loop = asyncio.get_running_loop()
    sub_queue = jm.subscribe(loop)
    try:
        await ws.send_json({"type": "initial_jobs", "jobs": jm.list_jobs(limit=25)})
        while True:
            try:
                event = await asyncio.wait_for(sub_queue.get(), timeout=20.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        jm.unsubscribe(sub_queue)


# Serve production React bundle automatically when `frontend/dist` exists
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").is_file():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/") or full_path == "ws" or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="API endpoint not found.")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
