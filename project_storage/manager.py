"""Safe local project directory management, manifest export/reopen, and disk usage inspection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.security import (
    resolve_safe_path,
    validate_identifier,
    verify_destructive_confirmation,
)

PROJECT_SUBDIRS = (
    "scenes",
    "audio",
    "renders",
    "thumbnails",
    "subtitles",
    "exports",
    "reports",
    "uploads",
)


def get_project_dir(project_id: str, create: bool = True) -> Path:
    safe_id = validate_identifier(project_id, "project_id")
    settings = get_settings()
    proj_dir = resolve_safe_path(settings.projects_dir, safe_id)
    if create:
        proj_dir.mkdir(parents=True, exist_ok=True)
        for sub in PROJECT_SUBDIRS:
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)
    return proj_dir


def write_project_manifest(project_id: str, payload: dict[str, Any]) -> Path:
    proj_dir = get_project_dir(project_id, create=True)
    manifest_path = proj_dir / "project_manifest.json"
    tmp_path = proj_dir / "project_manifest.json.tmp"
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(manifest_path)
    return manifest_path


def read_project_manifest(project_id: str) -> dict[str, Any] | None:
    proj_dir = get_project_dir(project_id, create=False)
    manifest_path = proj_dir / "project_manifest.json"
    if not manifest_path.is_file():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def get_storage_usage() -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_directories()
    disk = shutil.disk_usage(settings.workspace_dir)

    projects_bytes = directory_size_bytes(settings.projects_dir)
    models_bytes = directory_size_bytes(settings.models_dir)
    previews_bytes = directory_size_bytes(settings.previews_dir) + directory_size_bytes(settings.characters_dir)
    temp_bytes = directory_size_bytes(settings.temp_dir)
    db_bytes = settings.db_file.stat().st_size if settings.db_file.exists() else 0

    per_project: list[dict[str, Any]] = []
    if settings.projects_dir.exists():
        for entry in sorted(settings.projects_dir.iterdir()):
            if entry.is_dir():
                sz = directory_size_bytes(entry)
                per_project.append(
                    {
                        "project_id": entry.name,
                        "bytes": sz,
                        "mb": round(sz / (1024 * 1024), 2),
                    }
                )

    total_studio_bytes = projects_bytes + models_bytes + previews_bytes + temp_bytes + db_bytes
    return {
        "workspace_dir": str(settings.workspace_dir),
        "models_dir": str(settings.models_dir),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "studio_total_mb": round(total_studio_bytes / (1024 * 1024), 2),
        "breakdown_mb": {
            "projects": round(projects_bytes / (1024 * 1024), 2),
            "models": round(models_bytes / (1024 * 1024), 2),
            "previews_and_characters": round(previews_bytes / (1024 * 1024), 2),
            "temp": round(temp_bytes / (1024 * 1024), 2),
            "database": round(db_bytes / (1024 * 1024), 2),
        },
        "projects": per_project,
    }


def cleanup_temp_files() -> dict[str, Any]:
    settings = get_settings()
    freed = directory_size_bytes(settings.temp_dir)
    if settings.temp_dir.exists():
        shutil.rmtree(settings.temp_dir, ignore_errors=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    return {"cleaned": True, "freed_mb": round(freed / (1024 * 1024), 2)}


def delete_project_files(project_id: str, confirm_token: str) -> dict[str, Any]:
    verify_destructive_confirmation(confirm_token, expected="DELETE")
    proj_dir = get_project_dir(project_id, create=False)
    freed = directory_size_bytes(proj_dir)
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    return {
        "deleted": True,
        "project_id": project_id,
        "freed_mb": round(freed / (1024 * 1024), 2),
    }
