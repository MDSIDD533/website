"""Regression tests for the MP4 media ``download`` query parameter.

The parameter used to be declared as ``int``, so boolean spellings such as
``?download=true`` (and a bare ``?download`` flag) were rejected with
HTTP 422 instead of returning the MP4 as an attachment. These tests pin the
tolerant parsing: ``1/true/yes/on``/empty-flag -> attachment download,
absent/``0/false`` -> inline streaming for the in-page <video> player,
and HEAD support for download clients that probe before fetching.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from project_storage.manager import get_project_dir


def _project_with_export(api_client: TestClient) -> tuple[str, str]:
    samples = api_client.get("/api/projects/samples").json()["samples"]
    created = api_client.post(
        "/api/projects",
        json={
            "title": "Download Parameter Regression",
            "language": "en",
            "script_text": samples["roman_ur_adventure"]["script"],
            "auto_generate_storyboard": True,
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    exports = get_project_dir(project_id, create=True) / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    filename = f"{project_id}_final.mp4"
    # The media endpoint only streams bytes; a valid container is not needed here.
    Path(exports / filename).write_bytes(b"\x00\x00\x00\x18ftypisom" + b"X" * 4096)
    return project_id, filename


def test_mp4_download_parameter_accepts_boolean_spellings(api_client: TestClient) -> None:
    project_id, filename = _project_with_export(api_client)
    base = f"/api/media/project/{project_id}/exports/{filename}"

    # Every common "truthy" spelling must download as an attachment, never 422.
    for suffix in ("?download=1", "?download=true", "?download=yes", "?download=on", "?download=", "?download"):
        resp = api_client.get(base + suffix)
        assert resp.status_code == 200, suffix
        assert resp.headers.get("content-disposition", "").startswith("attachment"), suffix
        assert filename in resp.headers.get("content-disposition", ""), suffix
        assert len(resp.content) > 4096, suffix

    # Inline playback (used by <video>) must not force an attachment.
    for suffix in ("", "?download=0", "?download=false", "?download=no", "?download=off"):
        resp = api_client.get(base + suffix)
        assert resp.status_code == 200, suffix
        assert not resp.headers.get("content-disposition", "").startswith("attachment"), suffix

    # Range streaming for the video player still works inline.
    ranged = api_client.get(base, headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 100

    # Download clients that probe with HEAD must not get 405.
    head = api_client.head(base + "?download=1")
    assert head.status_code == 200
    assert head.headers.get("content-disposition", "").startswith("attachment")
