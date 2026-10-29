"""Video Library search/sort and strictly validated local media streaming routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.core.config import get_settings
from backend.core.security import (
    SecurityViolationError,
    resolve_safe_path,
    validate_identifier,
)
from backend.services.project_service import get_project, list_projects
from project_storage.manager import get_project_dir

router = APIRouter(tags=["library_and_media"])

SAFE_MEDIA_EXTENSIONS = {".mp4", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".srt", ".vtt", ".json"}

_FALSY_DOWNLOAD_VALUES = {"0", "false", "no", "off", "n", "f"}


def _wants_download(value: str | None) -> bool:
    """Interpret the ``download`` query parameter tolerantly.

    The parameter was historically declared as ``int``, so common boolean
    spellings such as ``?download=true`` — and even a bare ``?download``
    flag — were rejected with HTTP 422 instead of downloading the MP4.
    Accept every common spelling: ``1/true/yes/on`` (and a present-but-empty
    flag) mean "download"; ``0/false/no/off`` or an absent parameter mean
    "stream inline" (used by the in-page <video> player).
    """
    if value is None:
        return False
    return value.strip().lower() not in _FALSY_DOWNLOAD_VALUES


@router.get("/api/library")
def api_list_videos(search: str = "", sort_by: str = "newest") -> dict[str, Any]:
    projects = list_projects()
    videos: list[dict[str, Any]] = []
    q = search.strip().lower()

    for p in projects:
        export_path = p.get("latest_export_path") or ""
        if not export_path:
            continue
        mp4 = Path(export_path)
        if not mp4.is_file():
            continue
        if q and q not in p["title"].lower() and q not in p["description"].lower() and q not in p["genre"].lower():
            continue

        report = p.get("render_report") or {}
        thumb_rel = ""
        if p.get("cover_thumbnail_path"):
            t_name = Path(p["cover_thumbnail_path"]).name
            thumb_rel = f"/api/media/project/{p['id']}/thumbnails/{t_name}"

        exports_dir = get_project_dir(p["id"], create=False) / "exports"
        vtt_url = ""
        vtt_candidate = exports_dir / f"{p['id']}_subtitles.vtt"
        if vtt_candidate.is_file():
            vtt_url = f"/api/media/project/{p['id']}/exports/{vtt_candidate.name}"

        srt_url = ""
        srt_candidate = exports_dir / f"{p['id']}_subtitles.srt"
        if srt_candidate.is_file():
            srt_url = f"/api/media/project/{p['id']}/exports/{srt_candidate.name}?download=1"

        ur_vtt_url = ""
        ur_vtt_candidate = exports_dir / f"{p['id']}_subtitles_ur.vtt"
        if ur_vtt_candidate.is_file():
            ur_vtt_url = f"/api/media/project/{p['id']}/exports/{ur_vtt_candidate.name}"

        ur_srt_url = ""
        ur_srt_candidate = exports_dir / f"{p['id']}_subtitles_ur.srt"
        if ur_srt_candidate.is_file():
            ur_srt_url = f"/api/media/project/{p['id']}/exports/{ur_srt_candidate.name}?download=1"

        videos.append(
            {
                "project_id": p["id"],
                "title": p["title"],
                "description": p["description"],
                "language": p["language"],
                "genre": p["genre"],
                "resolution": report.get("resolution") or p["resolution"],
                "fps": report.get("fps") or p["fps"],
                "aspect_ratio": p["aspect_ratio"],
                "duration_sec": float(report.get("duration_sec") or 0.0),
                "file_size_mb": float(report.get("file_size_mb") or round(mp4.stat().st_size / (1024 * 1024), 2)),
                "video_url": f"/api/media/project/{p['id']}/exports/{mp4.name}",
                "download_url": f"/api/media/project/{p['id']}/exports/{mp4.name}?download=1",
                "subtitle_vtt_url": vtt_url,
                "subtitle_srt_url": srt_url,
                "subtitle_ur_vtt_url": ur_vtt_url,
                "subtitle_ur_srt_url": ur_srt_url,
                "thumbnail_url": thumb_rel,
                "render_report": report,
                "updated_at": p["updated_at"],
            }
        )

    if sort_by == "duration":
        videos.sort(key=lambda x: x["duration_sec"], reverse=True)
    elif sort_by == "size":
        videos.sort(key=lambda x: x["file_size_mb"], reverse=True)
    elif sort_by == "title":
        videos.sort(key=lambda x: x["title"].lower())
    else:
        videos.sort(key=lambda x: x["updated_at"], reverse=True)

    return {"videos": videos}


@router.api_route("/api/media/project/{project_id}/{subpath:path}", methods=["GET", "HEAD"])
def api_serve_project_media(project_id: str, subpath: str, download: str | None = None) -> FileResponse:
    try:
        validate_identifier(project_id, "project_id")
        get_project(project_id, include_details=False)
        proj_dir = get_project_dir(project_id, create=False)
        target = resolve_safe_path(proj_dir, subpath)
        if target.suffix.lower() not in SAFE_MEDIA_EXTENSIONS:
            raise SecurityViolationError("Access to non-media file type denied.")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Media file not found.")
        as_attachment = _wants_download(download)
        disposition = "attachment" if as_attachment else "inline"
        return FileResponse(
            target,
            filename=target.name if as_attachment else None,
            content_disposition_type=disposition,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/api/media/preview/{bucket}/{filename}")
def api_serve_preview_media(bucket: str, filename: str) -> FileResponse:
    settings = get_settings()
    if bucket == "characters":
        base = settings.characters_dir
    elif bucket == "previews":
        base = settings.previews_dir
    else:
        raise HTTPException(status_code=400, detail="Invalid preview bucket.")

    try:
        target = resolve_safe_path(base, filename)
        if target.suffix.lower() not in SAFE_MEDIA_EXTENSIONS:
            raise SecurityViolationError("Forbidden preview file extension.")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Preview file not found.")
        return FileResponse(target)
    except SecurityViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
