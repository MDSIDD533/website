"""Tests for security guards, offline privacy policy, AI Model Manager compatibility/consent, and license reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.security import (
    SecurityViolationError,
    resolve_safe_path,
    sanitize_filename,
    validate_local_endpoint_url,
    validate_uploaded_file,
    verify_destructive_confirmation,
)
from backend.services.license_service import (
    generate_project_license_report,
    record_asset_provenance,
)
from backend.services.project_service import create_project
from model_manager.registry import (
    install_or_register_model,
    list_models,
    verify_model_files,
)


def test_path_traversal_and_upload_validation(isolated_workspace: Path) -> None:
    with pytest.raises(SecurityViolationError):
        resolve_safe_path(isolated_workspace, "../../etc/passwd")

    with pytest.raises(SecurityViolationError):
        sanitize_filename("exploit.sh")

    # Reject ELF binary disguised as PNG
    with pytest.raises(SecurityViolationError):
        validate_uploaded_file("avatar.png", b"\x7fELF\x02\x01\x01\x00" + b"0" * 64, category="image")

    # Accept genuine PNG header
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    assert validate_uploaded_file("face ref.png", valid_png, category="image") == "face_ref.png"

    # Reject destructive deletion without exact token
    with pytest.raises(SecurityViolationError):
        verify_destructive_confirmation("wrong_token")


def test_privacy_loopback_enforcement() -> None:
    assert validate_local_endpoint_url("http://127.0.0.1:11434/api/chat") == "http://127.0.0.1:11434/api/chat"
    with pytest.raises(SecurityViolationError):
        validate_local_endpoint_url("https://api.external-cloud-llm.example.com/v1/chat")


def test_shell_injection_in_story_prompt_is_inert(isolated_workspace: Path) -> None:
    marker = isolated_workspace / "pwned.txt"
    malicious_script = (
        f"SCENE 1: FORTRESS\n"
        f"TARIQ: $(touch {marker}) `touch {marker}` ; rm -rf /nonexistent\n"
    )
    proj = create_project({"title": "Prompt Safety", "script_text": malicious_script, "auto_generate_storyboard": True})
    assert not marker.exists()
    assert len(proj["scenes"]) >= 1


def test_model_compatibility_consent_and_license_report(isolated_workspace: Path) -> None:
    models = {m["id"]: m for m in list_models()}
    assert models["blender-cycles-cpu-4.2"]["installed"] is True
    assert models["espeak-ng-multilingual-1.52"]["installed"] is True

    # GPU diffusion model must be flagged incompatible on CPU-only sandbox
    if models["wan2.1-t2v-1.3b"]["compatibility_status"] == "incompatible":
        with pytest.raises(RuntimeError):
            install_or_register_model("wan2.1-t2v-1.3b", user_confirmed=True)

    # Consent must be enforced before installing optional models
    with pytest.raises(PermissionError):
        install_or_register_model("piper-onnx-custom-voice", user_confirmed=False)

    # Importing local model weights with consent works offline & passes SHA256 verification
    dummy_onnx = isolated_workspace / "test_voice.onnx"
    dummy_cfg = isolated_workspace / "test_voice.onnx.json"
    dummy_onnx.write_bytes(b"ONNX_WEIGHTS_FIXTURE")
    dummy_cfg.write_text('{"audio": {"sample_rate": 22050}}', encoding="utf-8")

    installed = install_or_register_model(
        "piper-onnx-custom-voice",
        user_confirmed=True,
        local_source_files=[dummy_onnx, dummy_cfg],
    )
    assert installed["installed"] is True
    verified = verify_model_files("piper-onnx-custom-voice")
    assert verified["verified"] is True
    assert len(verified["sha256"]) == 64

    # License & provenance report flags uncertain user uploads
    proj = create_project({"title": "License Audit Project", "script_text": "TARIQ: Ready!"})
    record_asset_provenance(
        project_id=proj["id"],
        asset_name="mystery_clip.wav",
        asset_type="audio",
        source_kind="user_upload",
        license_spdx="Unknown",
        uncertain_rights=True,
    )
    report = generate_project_license_report(proj["id"], installed_models=list_models())
    assert any("UNCERTAIN_RIGHTS" in f for f in report["compliance_flags"])
    assert "does not guarantee" in report["legal_disclaimer"]
