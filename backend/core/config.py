"""Runtime configuration for SIDD AI VIDEO STUDIO."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
PerformanceMode = Literal["low_resource", "balanced", "high_quality"]


def _resolve_dir(raw: str, default_rel: str) -> Path:
    val = (raw or "").strip() or default_rel
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


@dataclass
class StudioSettings:
    app_name: str = "SIDD AI VIDEO STUDIO"
    version: str = "1.0.0"
    host: str = field(default_factory=lambda: os.getenv("SIDD_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SIDD_PORT", "8000")))
    workspace_dir: Path = field(
        default_factory=lambda: _resolve_dir(os.getenv("SIDD_WORKSPACE_DIR", ""), "workspace_data")
    )
    models_dir: Path = field(
        default_factory=lambda: _resolve_dir(os.getenv("SIDD_MODELS_DIR", ""), "models_data")
    )
    log_dir: Path = field(
        default_factory=lambda: _resolve_dir(os.getenv("SIDD_LOG_DIR", ""), "logs")
    )
    database_path: Path | None = None
    local_only_default: bool = field(
        default_factory=lambda: os.getenv("SIDD_LOCAL_ONLY_DEFAULT", "true").lower() in {"1", "true", "yes"}
    )
    allow_model_downloads: bool = field(
        default_factory=lambda: os.getenv("SIDD_ALLOW_MODEL_DOWNLOADS", "false").lower() in {"1", "true", "yes"}
    )
    local_llm_url: str = field(default_factory=lambda: os.getenv("SIDD_LOCAL_LLM_URL", "").strip())
    local_llm_model: str = field(default_factory=lambda: os.getenv("SIDD_LOCAL_LLM_MODEL", "").strip())
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("SIDD_MAX_UPLOAD_MB", "50")))
    max_concurrent_jobs: int = field(default_factory=lambda: int(os.getenv("SIDD_MAX_CONCURRENT_JOBS", "1")))
    performance_mode: PerformanceMode = "low_resource"

    def __post_init__(self) -> None:
        self.ensure_directories()

    @property
    def db_file(self) -> Path:
        if self.database_path is not None:
            return self.database_path
        raw_db = os.getenv("SIDD_DATABASE_PATH", "").strip()
        if raw_db:
            p = Path(raw_db).expanduser()
            return p.resolve() if p.is_absolute() else (REPO_ROOT / p).resolve()
        return (self.workspace_dir / "sidd_studio.db").resolve()

    @property
    def projects_dir(self) -> Path:
        return (self.workspace_dir / "projects").resolve()

    @property
    def temp_dir(self) -> Path:
        return (self.workspace_dir / "tmp").resolve()

    @property
    def characters_dir(self) -> Path:
        return (self.workspace_dir / "characters").resolve()

    @property
    def previews_dir(self) -> Path:
        return (self.workspace_dir / "previews").resolve()

    def ensure_directories(self) -> None:
        for directory in (
            self.workspace_dir,
            self.projects_dir,
            self.temp_dir,
            self.characters_dir,
            self.previews_dir,
            self.models_dir,
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)


_SETTINGS = StudioSettings()


def get_settings() -> StudioSettings:
    return _SETTINGS


def reconfigure_settings(
    *,
    workspace_dir: str | Path | None = None,
    models_dir: str | Path | None = None,
    database_path: str | Path | None = None,
    local_only_default: bool | None = None,
    allow_model_downloads: bool | None = None,
    performance_mode: PerformanceMode | None = None,
    local_llm_url: str | None = None,
    local_llm_model: str | None = None,
) -> StudioSettings:
    global _SETTINGS
    if workspace_dir is not None:
        _SETTINGS.workspace_dir = _resolve_dir(str(workspace_dir), "workspace_data")
    if models_dir is not None:
        _SETTINGS.models_dir = _resolve_dir(str(models_dir), "models_data")
    if database_path is not None:
        p = Path(database_path).expanduser()
        _SETTINGS.database_path = p.resolve() if p.is_absolute() else (REPO_ROOT / p).resolve()
    if local_only_default is not None:
        _SETTINGS.local_only_default = bool(local_only_default)
    if allow_model_downloads is not None:
        _SETTINGS.allow_model_downloads = bool(allow_model_downloads)
    if performance_mode in {"low_resource", "balanced", "high_quality"}:
        _SETTINGS.performance_mode = performance_mode  # type: ignore[assignment]
    if local_llm_url is not None:
        _SETTINGS.local_llm_url = local_llm_url.strip()
    if local_llm_model is not None:
        _SETTINGS.local_llm_model = local_llm_model.strip()
    _SETTINGS.ensure_directories()
    return _SETTINGS
