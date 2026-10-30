"""Auto sequence build/render orchestration tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from backend.services import motion_graphics_service as service


E2E_SCRIPT = """Bilal qile mein aata hai. Zara mash'al jalati hai. Dono baat karte hain:

Bilal kehta hai: 'Guard your left flank!' Zara kehti hai: 'Ready!'"""


def test_auto_sequence_build_only_creates_four_projects(tmp_path: Path) -> None:
    output_root = tmp_path / "auto"

    result = service.execute_auto_motion_graphics_sequence(
        script_text=E2E_SCRIPT,
        output_root=output_root,
        mode="build_only",
        fps=30,
        quality="standard",
    )

    assert result["status"] == "built"
    assert result["combined_video"] is None
    assert [clip["template"] for clip in result["clips"]] == [
        "title",
        "title",
        "title",
        "quote",
    ]
    assert result["plan"]["total_duration_sec"] == 15.0

    plan = json.loads(Path(result["auto_plan_json"]).read_text(encoding="utf-8"))
    assert plan["clip_count"] == 4
    assert plan["scene_count"] == 4

    scenes = json.loads(
        Path(result["parsed_scenes_json"]).read_text(encoding="utf-8")
    )
    assert scenes[0]["actions"] == ["walk"]
    assert scenes[2]["characters"] == ["Bilal", "Zara"]

    for clip in result["clips"]:
        assert Path(clip["index_html"]).is_file()
        assert Path(clip["variables_json"]).is_file()
        assert Path(clip["build_manifest"]).is_file()


def test_auto_sequence_render_branch_with_fake_renderer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: dict[str, Any] = {"render": [], "concat": []}

    def fake_render(**kwargs: Any) -> dict[str, Any]:
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake clip mp4")
        calls["render"].append(output)
        if kwargs.get("on_progress"):
            kwargs["on_progress"](100.0, "HyperFrames rendering (100%)")
        return {
            "output_path": str(output),
            "command_program": "fake-hyperframes",
            "elapsed_sec": 0.01,
            "log_tail": ["fake render complete"],
        }

    def fake_verify(path: str | Path) -> dict[str, Any]:
        candidate = Path(path)
        return {
            "verified": candidate.is_file() and candidate.stat().st_size > 0,
            "path": str(candidate),
            "file_size_bytes": candidate.stat().st_size if candidate.is_file() else 0,
            "method": "fake_verify",
            "video_codec": "h264",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "duration_sec": 3.0,
            "decoded_frames": 90,
        }

    def fake_concat(inputs: Any, output: str | Path, **_: Any) -> dict[str, Any]:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake combined mp4")
        calls["concat"].append((list(inputs), output_path))
        return {
            "output_path": str(output_path),
            "method": "fake_concat",
            "verification": fake_verify(output_path),
            "attempts": [],
        }

    monkeypatch.setattr(service, "render_motion_graphics_project", fake_render)
    monkeypatch.setattr(service, "verify_mp4", fake_verify)
    monkeypatch.setattr(service, "concat_mp4_files", fake_concat)

    result = service.execute_auto_motion_graphics_sequence(
        script_text="Bilal qile mein aata hai.",
        output_root=tmp_path / "auto-render",
        mode="render",
        fps=30,
        quality="standard",
    )

    assert result["status"] == "completed"
    assert len(calls["render"]) == 1
    assert len(calls["concat"]) == 1
    assert Path(result["combined_video"]).is_file()
    assert result["verification"]["verified"] is True
    assert Path(result["clips"][0]["verification_json"]).is_file()
    assert Path(result["sequence_result_json"]).is_file()


def test_concat_mp4_files_with_real_ffmpeg(tmp_path: Path) -> None:
    ffmpeg = service.ffmpeg_command()
    inputs: list[Path] = []
    for index, color in enumerate(("black", "blue"), start=1):
        clip = tmp_path / f"clip-{index}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=30:d=0.2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        inputs.append(clip)

    combined = tmp_path / "combined.mp4"
    result = service.concat_mp4_files(inputs, combined, fps=30)

    assert combined.is_file()
    assert result["verification"]["verified"] is True
    assert result["verification"]["decoded_frames"] >= 10
    assert Path(result["concat_list_path"]).is_file()
