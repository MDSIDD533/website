"""Hardware inspection, dependency verification, and realistic workload warnings."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
from typing import Any

import psutil

from backend.core.config import PerformanceMode, get_settings


def _detect_cpu_model() -> str:
    if Path_cpuinfo := "/proc/cpuinfo":
        try:
            with open(Path_cpuinfo, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _detect_gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.check_output(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=4,
            )
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append(
                        {
                            "vendor": "NVIDIA",
                            "name": parts[0],
                            "vram_total_mb": int(float(parts[1])),
                            "vram_free_mb": int(float(parts[2])),
                            "driver": parts[3] if len(parts) > 3 else "",
                        }
                    )
        except Exception:
            pass
    return gpus


def _detect_dependencies() -> dict[str, dict[str, Any]]:
    deps: dict[str, dict[str, Any]] = {}

    # Blender bpy is probed in an isolated subprocess.  The backend venv may
    # deliberately exclude the large bpy wheel, so use the same separate
    # local Blender runtime discovery as the Blender 3D Jobs service.
    from backend.services.blender_3d_service import blender_runtime_info

    bpy_probe = blender_runtime_info(probe=True)
    if bpy_probe.get("available"):
        deps["blender_bpy"] = {
            "installed": True,
            "version": str(bpy_probe.get("blender_version", "")),
            "details": "Headless Cycles CPU path-tracing & 3D animation rig engine",
            "python": bpy_probe.get("python"),
            "runtime": bpy_probe,
        }
    else:
        deps["blender_bpy"] = {
            "installed": False,
            "version": "",
            "details": str(bpy_probe.get("error") or bpy_probe.get("output_tail") or "Not installed"),
            "python": bpy_probe.get("python"),
            "runtime": bpy_probe,
        }

    # FFmpeg via imageio-ffmpeg or system PATH
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_ver = ""
    if not ffmpeg_path:
        try:
            import imageio_ffmpeg  # type: ignore

            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        ffmpeg_ver = os.path.basename(ffmpeg_path)
        deps["ffmpeg"] = {"installed": True, "version": ffmpeg_ver, "path": ffmpeg_path}
    else:
        deps["ffmpeg"] = {"installed": False, "version": "", "path": ""}

    # PyAV
    try:
        import av  # type: ignore

        deps["pyav"] = {"installed": True, "version": av.__version__}
    except Exception:
        deps["pyav"] = {"installed": False, "version": ""}

    # Piper + eSpeak-NG local TTS
    try:
        import piper  # type: ignore

        piper_dir = os.path.dirname(piper.__file__)
        has_espeak = os.path.exists(os.path.join(piper_dir, "espeakbridge.so"))
        has_urdu = os.path.exists(os.path.join(piper_dir, "espeak-ng-data", "ur_dict"))
        deps["local_tts"] = {
            "installed": True,
            "version": "piper-tts + espeak-ng",
            "espeak_bridge": has_espeak,
            "urdu_dictionary": has_urdu,
        }
    except Exception:
        deps["local_tts"] = {"installed": False, "version": ""}

    # ONNX Runtime
    try:
        import onnxruntime as ort  # type: ignore

        deps["onnxruntime"] = {
            "installed": True,
            "version": ort.__version__,
            "providers": ort.get_available_providers(),
        }
    except Exception:
        deps["onnxruntime"] = {"installed": False, "version": "", "providers": []}

    # SciPy procedural audio DSP
    try:
        import scipy  # type: ignore

        deps["scipy_dsp"] = {"installed": True, "version": scipy.__version__}
    except Exception:
        deps["scipy_dsp"] = {"installed": False, "version": ""}

    return deps


def inspect_hardware() -> dict[str, Any]:
    settings = get_settings()
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage(settings.workspace_dir)
    logical_cores = psutil.cpu_count(logical=True) or 1
    physical_cores = psutil.cpu_count(logical=False) or logical_cores
    cpu_percent = psutil.cpu_percent(interval=0.05)
    gpus = _detect_gpus()
    total_vram_mb = sum(g.get("vram_total_mb", 0) for g in gpus)
    free_vram_mb = sum(g.get("vram_free_mb", 0) for g in gpus)
    deps = _detect_dependencies()

    rendering_devices = ["CPU (Blender Cycles Intel Embree)"]
    if gpus:
        for g in gpus:
            rendering_devices.append(f"GPU ({g['name']} — {g['vram_total_mb']} MB VRAM)")

    # Determine recommended mode honestly based on detected hardware
    ram_gb = vm.total / (1024**3)
    if total_vram_mb >= 8192 and ram_gb >= 16 and logical_cores >= 8:
        recommended_mode: PerformanceMode = "high_quality"
    elif (total_vram_mb >= 4096 or logical_cores >= 6) and ram_gb >= 8:
        recommended_mode = "balanced"
    else:
        recommended_mode = "low_resource"

    limitations: list[str] = []
    if not gpus:
        limitations.append(
            "No discrete NVIDIA/AMD GPU detected (0 MB VRAM). All 3D raytracing runs on CPU; heavy diffusion video models (SVD/Wan2.1) are disabled by hardware guard."
        )
    if logical_cores <= 4:
        limitations.append(
            f"CPU has {logical_cores} logical threads. Low-Resource mode (50% internal raytrace scale + Lanczos upscale to 720p, 3–4 Cycles samples) is strongly recommended for fast scene turnaround."
        )
    if ram_gb < 6.0:
        limitations.append(
            f"System RAM is {ram_gb:.1f} GB. Large local LLMs (>1.5B parameters) and 4K multi-layer renders may exhaust memory."
        )
    if disk.free / (1024**3) < 5.0:
        limitations.append("Less than 5 GB free disk space remaining. Clean temporary render files regularly.")

    profiles = {
        "low_resource": {
            "id": "low_resource",
            "label": "Low-Resource Mode",
            "description": "Optimized for 2–4 core CPUs without GPU. Uses Cycles CPU persistent data, 3 spp, 50% internal raytrace scale upscaled cleanly to 720p H.264.",
            "recommended_max_resolution": "720p",
            "recommended_fps": 24,
            "cycles_samples": 3,
            "internal_scale_pct": 50,
            "use_denoiser": False,
        },
        "balanced": {
            "id": "balanced",
            "label": "Balanced Mode",
            "description": "Native 720p/1080p Cycles rendering at 6 spp with 2 light bounces. Suitable for 6+ CPU cores or entry-level GPU.",
            "recommended_max_resolution": "1080p",
            "recommended_fps": 24,
            "cycles_samples": 6,
            "internal_scale_pct": 85,
            "use_denoiser": False,
        },
        "high_quality": {
            "id": "high_quality",
            "label": "High-Quality Mode",
            "description": "Full 100% native resolution at 16 spp + Intel OpenImageDenoise & volumetric lighting. Slow on CPU-only machines; best with discrete GPU.",
            "recommended_max_resolution": "1080p" if not gpus else "4k",
            "recommended_fps": 30,
            "cycles_samples": 16,
            "internal_scale_pct": 100,
            "use_denoiser": True,
        },
    }

    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "platform": platform.platform(),
            "arch": platform.machine(),
            "python_version": platform.python_version(),
        },
        "cpu": {
            "model": _detect_cpu_model(),
            "physical_cores": physical_cores,
            "logical_cores": logical_cores,
            "usage_percent": cpu_percent,
        },
        "memory": {
            "total_gb": round(ram_gb, 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "used_gb": round((vm.total - vm.available) / (1024**3), 2),
            "usage_percent": vm.percent,
        },
        "gpu": {
            "detected": len(gpus) > 0,
            "devices": gpus,
            "total_vram_mb": total_vram_mb,
            "free_vram_mb": free_vram_mb,
        },
        "storage": {
            "workspace_dir": str(settings.workspace_dir),
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "used_percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0.0,
        },
        "rendering_devices": rendering_devices,
        "dependencies": deps,
        "active_mode": settings.performance_mode,
        "recommended_mode": recommended_mode,
        "profiles": profiles,
        "limitations": limitations,
    }


def evaluate_workload_warnings(
    *,
    resolution: str = "720p",
    fps: int = 24,
    duration_sec: float = 10.0,
    quality_profile: str = "low_resource",
    hw: dict[str, Any] | None = None,
) -> list[str]:
    info = hw or inspect_hardware()
    warnings: list[str] = []
    has_gpu = bool(info["gpu"]["detected"])
    cores = int(info["cpu"]["logical_cores"])
    ram_gb = float(info["memory"]["total_gb"])
    free_gb = float(info["storage"]["free_gb"])

    if resolution in {"1440p", "4k", "2160p"} and not has_gpu:
        warnings.append(
            f"Requested resolution '{resolution}' exceeds CPU-only recommended ceiling (720p/1080p). Expect very slow CPU frame times or memory pressure."
        )
    elif resolution == "1080p" and not has_gpu and cores <= 2:
        warnings.append(
            "1080p rendering on a 2-thread CPU without GPU will be significantly slower than 720p. Consider 720p + Low-Resource mode."
        )

    if fps >= 60 and not has_gpu:
        warnings.append(
            f"{fps} FPS doubles frame count vs 30 FPS on CPU-only hardware. 24 FPS cinematic cadence is recommended."
        )

    if quality_profile == "high_quality" and not has_gpu:
        warnings.append(
            "High-Quality mode enables 16 spp + OpenImageDenoise on CPU without GPU acceleration; rendering may take several minutes per scene."
        )

    if duration_sec > 30 and not has_gpu and cores <= 2:
        warnings.append(
            f"Total target duration ({duration_sec:.0f}s) on a 2-thread CPU will require rendering {int(duration_sec * fps)} frames sequentially."
        )

    if ram_gb < 4.5 and quality_profile == "high_quality":
        warnings.append("Available system RAM (<4.5 GB) is tight for Intel OpenImageDenoise buffers at full HD.")

    if free_gb < 2.0:
        warnings.append("Critical disk space warning (<2 GB free): export may fail if intermediate frames fill disk.")

    return warnings
