import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.services import blender_3d_service as service
from backend.services import job_manager as job_manager_module


WW2_SCRIPT = "World War II began in 1939 when Germany invaded Poland."


def test_build_blender_project_writes_plan_spec_and_captions(tmp_path: Path) -> None:
    built = service.build_blender_3d_project(
        script_text=WW2_SCRIPT,
        request_payload={"duration_sec": 4, "fps": 12, "width": 640, "height": 360},
        output_dir=tmp_path / "project",
    )

    assert built.plan["topic"]["theme"] == "ww2_battlefield"
    assert built.plan_path.is_file()
    assert built.parsed_scenes_path.is_file()
    assert built.spec_template_path.is_file()
    assert built.manifest_path.is_file()
    assert built.captions_path is not None and built.captions_path.is_file()
    assert "1939 · INVASION" in built.captions_path.read_text(encoding="utf-8")
    spec = json.loads(built.spec_template_path.read_text(encoding="utf-8"))
    assert spec["mode"] == "dynamic_3d"
    assert spec["plan"]["request"]["width"] == 640


def test_explicit_missing_blender_python_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIDD_BLENDER_PYTHON", str(tmp_path / "missing-python"))

    with pytest.raises(service.BlenderRuntimeError, match="was not found"):
        service.blender_python_command()


def test_blender_environment_includes_repo_and_configured_library_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIDD_BLENDER_LIBRARY_PATH", str(tmp_path / "libs"))
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)

    env = service.blender_environment("/usr/bin/python3")

    assert env["PYTHONPATH"].split(":")[0] == str(service.REPO_ROOT)
    assert env["LD_LIBRARY_PATH"] == str(tmp_path / "libs")


class _FakeWorkerProcess:
    pid = 4242

    def __init__(self, command, **_kwargs):
        result_path = Path(command[-1])
        result_path.write_text(
            json.dumps({"operation": "still", "frame_count": 0, "render": {"width": 640, "height": 360}}),
            encoding="utf-8",
        )
        self.stdout = iter(
            [
                "SIDD_STAGE:building_dynamic_blender_scene\n",
                "Saved: '/tmp/example/frame_0006.png'\n",
                "SIDD_FRAME:12/12\n",
            ]
        )

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def test_worker_runner_streams_saved_frame_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preview = service.prepare_blender_3d_preview(
        WW2_SCRIPT,
        {"duration_sec": 3, "fps": 12, "width": 640, "height": 360},
    )
    monkeypatch.setattr(
        service,
        "blender_runtime_info",
        lambda probe=False: {"available": True, "python": "/fake/blender-python", "probed": probe},
    )
    monkeypatch.setattr(service.subprocess, "Popen", _FakeWorkerProcess)
    progress: list[tuple[float, str]] = []

    result = service.run_blender_3d_worker(
        plan=preview["plan"],
        operation="still",
        blend_path=tmp_path / "scene.blend",
        thumbnail_path=tmp_path / "thumb.png",
        frames_dir=tmp_path / "frames",
        work_dir=tmp_path / "worker",
        on_progress=lambda ratio, stage: progress.append((ratio, stage)),
    )

    assert result["operation"] == "still"
    assert Path(result["spec_path"]).is_file()
    assert Path(result["log_path"]).is_file()
    assert any(ratio == pytest.approx(6 / 36) for ratio, _stage in progress)
    assert progress[-1][0] == 1.0


def test_encode_blender_frames_with_captions(tmp_path: Path) -> None:
    built = service.build_blender_3d_project(
        script_text=WW2_SCRIPT,
        request_payload={"duration_sec": 3, "fps": 12, "width": 320, "height": 180},
        output_dir=tmp_path / "project",
    )
    frames = tmp_path / "frames"
    frames.mkdir()
    for index in range(1, 7):
        Image.new("RGB", (320, 180), color=(35 + index * 12, 70, 110)).save(frames / f"frame_{index:04d}.png")

    result = service.encode_blender_frames(
        frames_dir=frames,
        output_path=tmp_path / "encoded.mp4",
        fps=12,
        quality="draft",
        captions_path=built.captions_path,
    )

    assert result["frame_count"] == 6
    assert result["captions_burned"] is True
    assert Path(result["output_path"]).stat().st_size > 0


def test_job_manager_blender_render_orchestration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = object.__new__(job_manager_module.JobManager)
    manager._lock = job_manager_module.threading.RLock()
    manager._active_procs = {}
    states: list[dict] = []
    manager._update_job_state = lambda job_id, **kwargs: states.append({"job_id": job_id, **kwargs})  # type: ignore[method-assign]
    manager._is_cancelled = lambda _job_id: False  # type: ignore[method-assign]

    monkeypatch.setattr(
        job_manager_module,
        "get_settings",
        lambda: SimpleNamespace(workspace_dir=tmp_path / "workspace"),
    )

    def fake_worker(**kwargs):
        blend = Path(kwargs["blend_path"])
        thumb = Path(kwargs["thumbnail_path"])
        frames = Path(kwargs["frames_dir"])
        blend.parent.mkdir(parents=True, exist_ok=True)
        frames.mkdir(parents=True, exist_ok=True)
        blend.write_bytes(b"BLENDER test placeholder")
        Image.new("RGB", (640, 360), color=(80, 90, 70)).save(thumb)
        total = int(kwargs["plan"]["total_frames"])
        for index in range(1, total + 1):
            Image.new("RGB", (640, 360), color=(80, 90, 70)).save(frames / f"frame_{index:04d}.png")
        kwargs["on_process"](SimpleNamespace(pid=4321))
        kwargs["on_progress"](0.5, "Blender frames half")
        kwargs["on_process"](None)
        return {
            "operation": "render",
            "frame_count": total,
            "metadata": {"object_count": 123},
            "render": {"width": 640, "height": 360},
            "spec_path": str(Path(kwargs["work_dir"]) / "spec.json"),
            "result_path": str(Path(kwargs["work_dir"]) / "result.json"),
            "log_path": str(Path(kwargs["work_dir"]) / "render.log"),
            "service_elapsed_sec": 1.25,
        }

    def fake_encode(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake encoded mp4")
        return {"output_path": str(output), "frame_count": 36, "elapsed_sec": 0.2}

    monkeypatch.setattr(job_manager_module, "run_blender_3d_worker", fake_worker)
    monkeypatch.setattr(job_manager_module, "encode_blender_frames", fake_encode)
    monkeypatch.setattr(
        job_manager_module,
        "verify_mp4",
        lambda _path: {
            "verified": True,
            "width": 640,
            "height": 360,
            "fps": 12.0,
            "duration_sec": 3.0,
            "decoded_frames": 36,
        },
    )

    manager._execute_blender_3d_job(
        "job_blender_test",
        {
            "script_text": WW2_SCRIPT,
            "request": {"width": 640, "height": 360},
            "mode": "render",
            "fps": 12,
            "quality": "draft",
            "duration_sec": 3,
            "theme": "auto",
            "include_captions": True,
        },
        job_manager_module.time.time(),
    )

    completed = [state for state in states if state.get("status") == "completed"]
    assert completed
    outputs = completed[-1]["output_paths"]
    assert outputs["theme"] == "ww2_battlefield"
    assert Path(outputs["blend_file"]).is_file()
    assert Path(outputs["thumbnail_png"]).is_file()
    assert Path(outputs["video"]).is_file()
    assert outputs["verification"]["decoded_frames"] == 36
    assert any(state.get("current_stage") == "Blender frames half" for state in states)
