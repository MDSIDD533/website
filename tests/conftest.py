"""Shared test fixtures isolating SQLite database and workspace per test."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.core.config import reconfigure_settings
from backend.core.database import init_database
from backend.main import app


@pytest.fixture()
def isolated_workspace(tmp_path: Path) -> Iterator[Path]:
    ws = tmp_path / "ws"
    md = tmp_path / "models"
    db = ws / "test_studio.db"
    reconfigure_settings(
        workspace_dir=ws,
        models_dir=md,
        database_path=db,
        local_only_default=True,
        allow_model_downloads=False,
        performance_mode="low_resource",
        local_llm_url="",
    )
    init_database(db)
    yield ws


@pytest.fixture()
def api_client(isolated_workspace: Path) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
