"""Structured JSON & console logging with in-memory ring buffer."""

from __future__ import annotations

import json
import logging
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import get_settings

_RECENT_LOGS: deque[dict[str, Any]] = deque(maxlen=500)
_INITIALIZED = False


class RingBufferStructuredHandler(logging.Handler):
    """Captures structured log records in memory and optionally writes JSONL to disk."""

    def __init__(self, jsonl_path: Path | None = None) -> None:
        super().__init__()
        self.jsonl_path = jsonl_path

    def emit(self, record: logging.LogRecord) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for extra_key in ("job_id", "project_id", "stage", "scene_id", "model_id"):
            val = getattr(record, extra_key, None)
            if val is not None:
                entry[extra_key] = val
        if record.exc_info:
            entry["exception"] = "".join(traceback.format_exception(*record.exc_info))

        _RECENT_LOGS.append(entry)
        if self.jsonl_path is not None:
            try:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                with self.jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass


def setup_logging() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    settings = get_settings()
    root = logging.getLogger("sidd_studio")
    root.setLevel(logging.INFO)
    root.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)

    structured = RingBufferStructuredHandler(settings.log_dir / "studio_events.jsonl")
    root.addHandler(structured)
    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    if name.startswith("sidd_studio"):
        return logging.getLogger(name)
    return logging.getLogger(f"sidd_studio.{name}")


def get_recent_logs(limit: int = 100, project_id: str | None = None, job_id: str | None = None) -> list[dict[str, Any]]:
    items = list(_RECENT_LOGS)
    if project_id:
        items = [x for x in items if x.get("project_id") == project_id]
    if job_id:
        items = [x for x in items if x.get("job_id") == job_id]
    return items[-max(1, min(limit, 500)) :]
