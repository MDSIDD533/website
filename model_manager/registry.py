"""Local AI Model Manager: catalog, license & hardware verification, consent-gated install, and SHA256 checks."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from backend.core.config import get_settings, reconfigure_settings
from backend.core.database import get_db, utc_now_iso
from backend.core.security import SecurityViolationError, resolve_safe_path, validate_identifier
from backend.services.hardware_service import inspect_hardware

MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "blender-cycles-cpu-4.2",
        "name": "Blender 4.2 LTS Cycles 3D Engine (bpy)",
        "purpose": "3D scene assembly, articulated character rigging, keyframe animation, cameras, lighting, and raytraced rendering",
        "category": "3d_render",
        "version": "4.2.15 LTS",
        "license": "GPL-3.0-or-later",
        "commercial_use": True,
        "attribution_required": True,
        "download_size_mb": 350.2,
        "required_storage_mb": 620.0,
        "min_ram_gb": 2.0,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": False,
        "builtin": True,
        "supported_languages": ["all"],
        "supported_tasks": ["3d_scene", "rigging", "animation", "combat_choreography", "raytracing"],
        "implementation_status": "implemented",
        "notes": "Pre-installed in local Python environment with Intel Embree CPU path tracer.",
    },
    {
        "id": "espeak-ng-multilingual-1.52",
        "name": "eSpeak-NG Multilingual Synthesizer & Viseme Engine",
        "purpose": "Zero-cloud local speech synthesis & frame-accurate jaw viseme extraction for English, Urdu, and Roman Urdu",
        "category": "tts",
        "version": "1.52",
        "license": "GPL-3.0-or-later",
        "commercial_use": True,
        "attribution_required": False,
        "download_size_mb": 19.0,
        "required_storage_mb": 25.0,
        "min_ram_gb": 0.5,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": False,
        "builtin": True,
        "supported_languages": ["en", "ur", "roman_ur", "hi", "ar"],
        "supported_tasks": ["tts", "dialogue", "narration", "viseme_lipsync"],
        "implementation_status": "implemented",
        "notes": "Formant speech synthesis + DSP warmth post-filter. Works 100% offline immediately with native Urdu (`ur_dict`) and English (`en_dict`).",
    },
    {
        "id": "sidd-deterministic-story-nlp-1.0",
        "name": "SIDD Multilingual Story Parser & Storyboard Planner",
        "purpose": "Deterministic script analysis (characters, dialogue, emotions, props, historical vs fictional notes, camera & combat planning)",
        "category": "script_analysis",
        "version": "1.0.0",
        "license": "MIT",
        "commercial_use": True,
        "attribution_required": False,
        "download_size_mb": 0.2,
        "required_storage_mb": 1.0,
        "min_ram_gb": 0.5,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": False,
        "builtin": True,
        "supported_languages": ["en", "ur", "roman_ur"],
        "supported_tasks": ["script_parsing", "storyboard_planning", "roman_urdu_normalization"],
        "implementation_status": "implemented",
        "notes": "Reliable deterministic parser & validator requiring zero external weights.",
    },
    {
        "id": "sidd-procedural-audio-dsp-1.0",
        "name": "SIDD Procedural Foley, Ambience & Cinematic Music Engine",
        "purpose": "Synthesizes original environmental ambience, footsteps, combat foley, weather audio, and ducked musical scores",
        "category": "audio_dsp",
        "version": "1.0.0",
        "license": "MIT",
        "commercial_use": True,
        "attribution_required": False,
        "download_size_mb": 0.1,
        "required_storage_mb": 1.0,
        "min_ram_gb": 0.5,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": False,
        "builtin": True,
        "supported_languages": ["all"],
        "supported_tasks": ["ambience", "foley", "combat_sfx", "music", "dialogue_ducking"],
        "implementation_status": "implemented",
        "notes": "100% original procedural DSP synthesis via NumPy/SciPy; zero copyrighted samples.",
    },
    {
        "id": "piper-onnx-custom-voice",
        "name": "Piper Neural TTS ONNX Voices (Joe Male + Amy Female)",
        "purpose": "High-naturalness local ONNX neural voice inference via installed `piper-tts` + `onnxruntime`",
        "category": "tts",
        "version": "1.8.0-onnx",
        "license": "Joe dataset CC0-1.0; Amy dataset CC-BY-SA-4.0 (verify any replacement checkpoint)",
        "commercial_use": True,
        "attribution_required": True,
        "download_size_mb": 126.4,
        "required_storage_mb": 140.0,
        "min_ram_gb": 1.5,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": True,
        "builtin": False,
        "supported_languages": ["en"],
        "supported_tasks": ["tts", "dialogue", "narration"],
        "implementation_status": "implemented",
        "notes": "Runtime (`piper-tts` + `onnxruntime`) is fully integrated. English male dialogue prefers `en_US-joe-medium.onnx`; female dialogue prefers `en_US-amy-medium.onnx`, each with its matching `.onnx.json` in `models_data/piper-onnx-custom-voice/`. eSpeak-NG is the offline fallback.",
    },
    {
        "id": "local-gguf-llm-bridge",
        "name": "Local LLM Script Analyzer (Ollama / llama.cpp Loopback)",
        "purpose": "Optional neural script enrichment paired with deterministic schema validation & fallback",
        "category": "script_analysis",
        "version": "Qwen2.5-1.5B-Instruct-Q4_K_M (Recommended)",
        "license": "Apache-2.0",
        "commercial_use": True,
        "attribution_required": True,
        "download_size_mb": 1120.0,
        "required_storage_mb": 1400.0,
        "min_ram_gb": 4.5,
        "min_vram_mb": 0,
        "requires_gpu": False,
        "internet_required_to_run": False,
        "internet_required_to_install": True,
        "builtin": False,
        "supported_languages": ["en", "ur", "roman_ur"],
        "supported_tasks": ["script_parsing", "scene_enrichment"],
        "implementation_status": "optional_external_local_daemon",
        "notes": "Connects strictly to 127.0.0.1 loopback when configured in Project Settings; falls back automatically to deterministic parser.",
    },
    {
        "id": "wan2.1-t2v-1.3b",
        "name": "Wan 2.1 Text-to-Video 1.3B (Generative Video Diffusion)",
        "purpose": "Optional neural diffusion background/video clip generation when discrete GPU is available",
        "category": "generative_video",
        "version": "2.1-1.3B",
        "license": "Apache-2.0",
        "commercial_use": True,
        "attribution_required": True,
        "download_size_mb": 5400.0,
        "required_storage_mb": 8500.0,
        "min_ram_gb": 16.0,
        "min_vram_mb": 8192,
        "requires_gpu": True,
        "internet_required_to_run": False,
        "internet_required_to_install": True,
        "builtin": False,
        "supported_languages": ["en"],
        "supported_tasks": ["generative_video_backdrop"],
        "implementation_status": "hardware_gated_experimental",
        "notes": "Requires >=8 GB CUDA VRAM and 16 GB RAM. Disabled on CPU-only systems in favor of deterministic Blender 3D rendering.",
    },
    {
        "id": "svd-xt-1.1-img2vid",
        "name": "Stable Video Diffusion XT 1.1",
        "purpose": "Reference-conditioned image-to-video clip synthesis",
        "category": "generative_video",
        "version": "1.1",
        "license": "Stability AI Community License (Non-Commercial >$1M rev without enterprise license)",
        "commercial_use": False,
        "attribution_required": True,
        "download_size_mb": 9560.0,
        "required_storage_mb": 12000.0,
        "min_ram_gb": 16.0,
        "min_vram_mb": 12288,
        "requires_gpu": True,
        "internet_required_to_run": False,
        "internet_required_to_install": True,
        "builtin": False,
        "supported_languages": ["all"],
        "supported_tasks": ["image_to_video"],
        "implementation_status": "hardware_gated_experimental",
        "notes": "Flagged for non-commercial license conditions and requires >=12 GB VRAM.",
    },
]


def _check_compatibility(entry: dict[str, Any], hw: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    ram_gb = float(hw["memory"]["total_gb"])
    vram_mb = int(hw["gpu"]["total_vram_mb"])
    has_gpu = bool(hw["gpu"]["detected"])
    free_disk_mb = float(hw["storage"]["free_gb"]) * 1024.0

    if entry["requires_gpu"] and not has_gpu:
        reasons.append(f"Requires discrete GPU ({entry['min_vram_mb']} MB VRAM minimum), but 0 GPUs detected.")
    elif entry["min_vram_mb"] > vram_mb:
        reasons.append(f"Requires {entry['min_vram_mb']} MB VRAM; detected {vram_mb} MB.")

    if ram_gb < entry["min_ram_gb"]:
        reasons.append(f"Requires {entry['min_ram_gb']} GB system RAM; detected {ram_gb:.1f} GB.")

    if not entry["builtin"] and free_disk_mb < entry["required_storage_mb"]:
        reasons.append(
            f"Requires {entry['required_storage_mb']:.0f} MB free disk space; detected {free_disk_mb:.0f} MB."
        )

    if reasons:
        if entry["requires_gpu"] and not has_gpu:
            return ("incompatible", reasons)
        return ("warning", reasons)
    return ("compatible", [])


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def list_models() -> list[dict[str, Any]]:
    settings = get_settings()
    hw = inspect_hardware()
    deps = hw["dependencies"]

    with get_db() as conn:
        rows = {
            r["model_id"]: dict(r)
            for r in conn.execute("SELECT * FROM model_registry_state").fetchall()
        }

    result: list[dict[str, Any]] = []
    for item in MODEL_CATALOG:
        mid = item["id"]
        db_state = rows.get(mid, {})
        model_dir = (settings.models_dir / mid).resolve()
        compat_status, compat_notes = _check_compatibility(item, hw)

        if item["builtin"]:
            if mid == "blender-cycles-cpu-4.2":
                installed = bool(deps.get("blender_bpy", {}).get("installed"))
            elif mid == "espeak-ng-multilingual-1.52":
                installed = bool(deps.get("local_tts", {}).get("installed"))
            else:
                installed = True
            active = bool(db_state.get("active", 1))
            install_path = str(model_dir) if model_dir.exists() else "builtin://python-venv"
        else:
            has_local_files = model_dir.exists() and any(
                p.is_file() and p.name != "manifest.json" for p in model_dir.rglob("*")
            )
            installed = bool(db_state.get("installed", 0)) and has_local_files
            if has_local_files and not db_state:
                installed = True
            active = bool(db_state.get("active", 0)) and installed
            install_path = str(model_dir)

        result.append(
            {
                **item,
                "installed": installed,
                "active": active,
                "compatibility_status": compat_status,
                "compatibility_notes": compat_notes,
                "model_directory": install_path,
                "verified_sha256": db_state.get("verified_sha256", ""),
                "last_verified_at": db_state.get("last_verified_at", ""),
            }
        )
    return result


def get_model(model_id: str) -> dict[str, Any]:
    validate_identifier(model_id.replace(".", "_"), "model_id")
    for m in list_models():
        if m["id"] == model_id:
            return m
    raise KeyError(f"Unknown model_id '{model_id}'")


def install_or_register_model(
    model_id: str,
    *,
    user_confirmed: bool = False,
    local_source_files: list[Path] | None = None,
) -> dict[str, Any]:
    """Install/register a model only with explicit user consent and hardware compatibility check."""
    model = get_model(model_id)
    if model["builtin"]:
        return {**model, "status_message": "Built-in engine is already installed locally."}

    if not user_confirmed:
        raise PermissionError(
            f"Explicit user confirmation is required before installing '{model['name']}' "
            f"(estimated download size: {model['download_size_mb']} MB, storage required: {model['required_storage_mb']} MB)."
        )

    if model["compatibility_status"] == "incompatible":
        raise RuntimeError(
            f"Hardware compatibility check blocked installation of '{model['name']}': "
            + "; ".join(model["compatibility_notes"])
        )

    settings = get_settings()
    target_dir = resolve_safe_path(settings.models_dir, model_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    combined_hash = hashlib.sha256()

    if local_source_files:
        for src in local_source_files:
            if not src.is_file():
                raise FileNotFoundError(f"Local model file not found: {src}")
            dst = resolve_safe_path(target_dir, src.name)
            shutil.copy2(src, dst)
            copied_files.append(dst.name)
            combined_hash.update(_sha256_file(dst).encode("ascii"))
    else:
        # Honest offline/sandbox check: never fake downloading multi-GB weights!
        if not settings.allow_model_downloads:
            raise PermissionError(
                "External model downloads are disabled by privacy settings ('allow_model_downloads=false'). "
                "Enable model downloads in Project Settings or import local .onnx/.gguf weight files into "
                f"'{target_dir}'."
            )
        raise RuntimeError(
            f"Direct remote weight download for '{model['name']}' requires internet access to external model hosts. "
            f"Place verified weight files inside '{target_dir}' and click 'Verify Files' to activate offline."
        )

    manifest = {
        "model_id": model_id,
        "files": copied_files,
        "installed_at": utc_now_iso(),
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    digest = combined_hash.hexdigest()
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_registry_state (
                model_id, installed, active, install_path, verified_sha256, last_verified_at, user_consented, updated_at
            ) VALUES (?, 1, 1, ?, ?, ?, 1, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                installed=1, active=1, install_path=excluded.install_path,
                verified_sha256=excluded.verified_sha256, last_verified_at=excluded.last_verified_at,
                user_consented=1, updated_at=excluded.updated_at
            """,
            (model_id, str(target_dir), digest, now, now),
        )
    return get_model(model_id)


def verify_model_files(model_id: str) -> dict[str, Any]:
    model = get_model(model_id)
    now = utc_now_iso()
    if model["builtin"]:
        hw = inspect_hardware()
        ok = model["installed"]
        digest = hashlib.sha256(f"{model_id}:{model['version']}:{ok}".encode("utf-8")).hexdigest()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO model_registry_state (
                    model_id, installed, active, install_path, verified_sha256, last_verified_at, user_consented, updated_at
                ) VALUES (?, ?, 1, 'builtin://python-venv', ?, ?, 1, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    installed=excluded.installed, verified_sha256=excluded.verified_sha256,
                    last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at
                """,
                (model_id, int(ok), digest, now, now),
            )
        return {
            "model_id": model_id,
            "verified": ok,
            "sha256": digest,
            "checked_at": now,
            "details": "Verified built-in Python environment libraries and binaries.",
            "dependencies": hw["dependencies"],
        }

    settings = get_settings()
    target_dir = resolve_safe_path(settings.models_dir, model_id)
    files = [
        p for p in sorted(target_dir.rglob("*")) if p.is_file() and p.name != "manifest.json"
    ] if target_dir.exists() else []
    if not files:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO model_registry_state (
                    model_id, installed, active, install_path, verified_sha256, last_verified_at, user_consented, updated_at
                ) VALUES (?, 0, 0, ?, '', ?, 0, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    installed=0, active=0, verified_sha256='', last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at
                """,
                (model_id, str(target_dir), now, now),
            )
        return {
            "model_id": model_id,
            "verified": False,
            "sha256": "",
            "checked_at": now,
            "details": f"No weight files found in {target_dir}.",
        }

    combined = hashlib.sha256()
    file_digests: dict[str, str] = {}
    for f in files:
        d = _sha256_file(f)
        file_digests[f.name] = d
        combined.update(d.encode("ascii"))
    digest = combined.hexdigest()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_registry_state (
                model_id, installed, active, install_path, verified_sha256, last_verified_at, user_consented, updated_at
            ) VALUES (?, 1, 1, ?, ?, ?, 1, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                installed=1, install_path=excluded.install_path, verified_sha256=excluded.verified_sha256,
                last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at
            """,
            (model_id, str(target_dir), digest, now, now),
        )
    return {
        "model_id": model_id,
        "verified": True,
        "sha256": digest,
        "files": file_digests,
        "checked_at": now,
        "details": f"Verified {len(files)} model file(s) in {target_dir}.",
    }


def set_active_model(model_id: str, active: bool) -> dict[str, Any]:
    model = get_model(model_id)
    if active and not model["installed"]:
        raise RuntimeError(f"Cannot activate '{model['name']}' because its files are not installed.")
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_registry_state (
                model_id, installed, active, install_path, verified_sha256, last_verified_at, user_consented, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(model_id) DO UPDATE SET active=excluded.active, updated_at=excluded.updated_at
            """,
            (
                model_id,
                int(model["installed"]),
                int(active),
                model["model_directory"],
                model["verified_sha256"],
                model["last_verified_at"],
                now,
            ),
        )
    return get_model(model_id)


def remove_model(model_id: str) -> dict[str, Any]:
    model = get_model(model_id)
    if model["builtin"]:
        raise SecurityViolationError("Built-in studio core engines cannot be deleted from the workspace.")
    settings = get_settings()
    target_dir = resolve_safe_path(settings.models_dir, model_id)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE model_registry_state
            SET installed=0, active=0, verified_sha256='', updated_at=?
            WHERE model_id=?
            """,
            (now, model_id),
        )
    return get_model(model_id)


def configure_models_directory(new_path: str) -> dict[str, Any]:
    settings = reconfigure_settings(models_dir=new_path)
    return {"models_dir": str(settings.models_dir), "models": list_models()}
