"""Provenance tracking and project-level copyright & license report generation."""

from __future__ import annotations

import uuid
from typing import Any

from backend.core.database import get_db, utc_now_iso

CORE_STACK_LICENSES: list[dict[str, Any]] = [
    {
        "component": "Blender Python Module (bpy)",
        "version": "4.2.15 LTS",
        "purpose": "3D scene generation, armature rigging, keyframe animation, lighting, cameras, Cycles CPU path tracing",
        "license": "GPL-3.0-or-later",
        "commercial_use": True,
        "attribution_required": True,
        "redistribution_notes": "Blender binary/module is GPL-3.0; rendered image/video outputs created by your scenes are owned by you (subject to input asset licenses).",
    },
    {
        "component": "FFmpeg (via imageio-ffmpeg) & PyAV",
        "version": "7.0.2 / 18.1.0",
        "purpose": "H.264/AAC MP4 muxing, audio mixing, subtitle burn-in, and stream decode verification",
        "license": "GPL-2.0-or-later / LGPL-2.1-or-later / BSD-3-Clause (PyAV wrapper)",
        "commercial_use": True,
        "attribution_required": True,
        "redistribution_notes": "Includes libx264 (GPL-2.0+); redistributing the bundled FFmpeg binary requires GPL compliance.",
    },
    {
        "component": "eSpeak-NG Speech Synthesizer & Language Dictionaries",
        "version": "1.52 (via piper-tts wheel)",
        "purpose": "Offline English, Urdu, and Roman-Urdu speech synthesis and phoneme/viseme timing",
        "license": "GPL-3.0-or-later",
        "commercial_use": True,
        "attribution_required": False,
        "redistribution_notes": "Synthetic audio output generated from user text has no eSpeak copyright restriction; engine binary is GPL-3.0.",
    },
    {
        "component": "Piper TTS Runtime & ONNX Runtime",
        "version": "1.8.0 / 1.31.1",
        "purpose": "Local neural text-to-speech inference engine",
        "license": "MIT",
        "commercial_use": True,
        "attribution_required": True,
        "redistribution_notes": "Individual downloaded voice checkpoints have per-dataset licenses; check AI Model Manager before commercial use.",
    },
    {
        "component": "SIDD Procedural 3D Assets, Humanoid Rig, Environments & Foley DSP",
        "version": "1.0.0",
        "purpose": "Procedurally generated 3D character meshes/rigs, historical environments, weather, sound effects, and background music",
        "license": "MIT (Original Studio Procedural Code)",
        "commercial_use": True,
        "attribution_required": False,
        "redistribution_notes": "100% mathematically/procedurally synthesized locally; contains zero third-party copyrighted meshes, motion capture, or film soundtracks.",
    },
]

LEGAL_DISCLAIMER = (
    "IMPORTANT LEGAL NOTICE: SIDD AI VIDEO STUDIO does not guarantee that any generated video is automatically "
    "free of all copyright, trademark, personality/publicity, or moral-rights claims. Rights in the final output "
    "depend on applicable law in your jurisdiction, the originality of your script, the provenance of any user-uploaded "
    "assets, and the specific license terms of any optional third-party AI model weights you choose to install. "
    "Never imitate a real living person's voice or likeness without explicit authorization."
)


def record_asset_provenance(
    *,
    project_id: str | None,
    asset_name: str,
    asset_type: str,
    source_kind: str,
    license_spdx: str,
    version: str = "1.0",
    attribution_required: bool = False,
    commercial_allowed: bool = True,
    redistribution_allowed: bool = True,
    uncertain_rights: bool = False,
    notes: str = "",
    local_path: str = "",
) -> dict[str, Any]:
    rec_id = f"prov_{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO asset_provenance (
                id, project_id, asset_name, asset_type, source_kind, version,
                license_spdx, attribution_required, commercial_allowed,
                redistribution_allowed, uncertain_rights, notes, local_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_id,
                project_id,
                asset_name,
                asset_type,
                source_kind,
                version,
                license_spdx,
                int(attribution_required),
                int(commercial_allowed),
                int(redistribution_allowed),
                int(uncertain_rights),
                notes,
                local_path,
                now,
            ),
        )
    return {
        "id": rec_id,
        "project_id": project_id,
        "asset_name": asset_name,
        "asset_type": asset_type,
        "source_kind": source_kind,
        "version": version,
        "license_spdx": license_spdx,
        "attribution_required": attribution_required,
        "commercial_allowed": commercial_allowed,
        "redistribution_allowed": redistribution_allowed,
        "uncertain_rights": uncertain_rights,
        "notes": notes,
        "local_path": local_path,
        "created_at": now,
    }


def generate_project_license_report(project_id: str, installed_models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    with get_db() as conn:
        proj_row = conn.execute("SELECT id, title, language, historical_accuracy_mode FROM projects WHERE id = ?", (project_id,)).fetchone()
        prov_rows = conn.execute(
            "SELECT * FROM asset_provenance WHERE project_id = ? OR project_id IS NULL ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()

    assets = [
        {
            "id": r["id"],
            "asset_name": r["asset_name"],
            "asset_type": r["asset_type"],
            "source_kind": r["source_kind"],
            "version": r["version"],
            "license_spdx": r["license_spdx"],
            "attribution_required": bool(r["attribution_required"]),
            "commercial_allowed": bool(r["commercial_allowed"]),
            "redistribution_allowed": bool(r["redistribution_allowed"]),
            "uncertain_rights": bool(r["uncertain_rights"]),
            "notes": r["notes"],
        }
        for r in prov_rows
    ]

    flags: list[str] = []
    if any(a["uncertain_rights"] for a in assets):
        flags.append("UNCERTAIN_RIGHTS: One or more user-uploaded assets have unverified license metadata. Verify ownership before public distribution.")
    if any(not a["commercial_allowed"] for a in assets):
        flags.append("NON_COMMERCIAL_RESTRICTION: At least one asset or model carries a non-commercial license condition.")
    if any(a["attribution_required"] for a in assets):
        flags.append("ATTRIBUTION_REQUIRED: One or more assets require creator/model attribution in video credits.")

    for m in installed_models or []:
        if m.get("installed") and not m.get("commercial_use", True):
            flags.append(
                f"MODEL_NON_COMMERCIAL: Installed model '{m['name']}' ({m['license']}) restricts commercial output use."
            )

    return {
        "project_id": project_id,
        "project_title": proj_row["title"] if proj_row else project_id,
        "generated_at": utc_now_iso(),
        "user_script_notice": "User-submitted story script — rights depend on the user's original authorship or permission from rights holders.",
        "core_software_stack": CORE_STACK_LICENSES,
        "active_and_installed_models": [
            {
                "id": m["id"],
                "name": m["name"],
                "version": m["version"],
                "license": m["license"],
                "commercial_use": m.get("commercial_use", True),
                "attribution_required": m.get("attribution_required", False),
            }
            for m in (installed_models or [])
            if m.get("installed")
        ],
        "project_assets_provenance": assets,
        "compliance_flags": flags,
        "legal_disclaimer": LEGAL_DISCLAIMER,
    }
