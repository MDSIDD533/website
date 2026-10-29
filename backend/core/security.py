"""Security utilities: path traversal protection, file validation, and safe input handling."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_ASSET_EXTENSIONS: dict[str, set[str]] = {
    "image": {".png", ".jpg", ".jpeg", ".webp"},
    "audio": {".wav", ".ogg", ".flac", ".mp3", ".m4a"},
    "mesh": {".obj", ".glb", ".gltf", ".stl"},
    "subtitle": {".srt", ".vtt"},
    "script": {".txt", ".md", ".fountain"},
    "model": {".onnx", ".json", ".gguf"},
}

FORBIDDEN_EXTENSIONS: set[str] = {
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".js",
    ".mjs",
    ".php",
    ".rb",
    ".pl",
    ".elf",
}

MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".wav": (b"RIFF",),
    ".ogg": (b"OggS",),
    ".flac": (b"fLaC",),
    ".glb": (b"glTF",),
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,79}$")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


class SecurityViolationError(ValueError):
    """Raised when an input violates path safety, upload constraints, or local-only policy."""


def validate_identifier(identifier: str, label: str = "identifier") -> str:
    cleaned = (identifier or "").strip()
    if not _SAFE_ID_RE.match(cleaned):
        raise SecurityViolationError(f"Invalid {label}: must contain only alphanumeric, '-' or '_' characters.")
    return cleaned


def sanitize_filename(filename: str) -> str:
    """Strip directory components and dangerous characters from a user-supplied filename."""
    raw = (filename or "").strip().replace("\\", "/")
    if raw in {"", ".", ".."} or "/" in raw or "\x00" in raw:
        # Reject traversal attempts if caller passed path components directly, or extract basename safely
        base = os.path.basename(raw)
    else:
        base = raw

    if not base or base in {".", ".."} or ".." in base:
        raise SecurityViolationError("Invalid or unsafe filename.")

    stem, ext = os.path.splitext(base)
    ext_lower = ext.lower()
    if ext_lower in FORBIDDEN_EXTENSIONS:
        raise SecurityViolationError(f"Executable or script extension '{ext_lower}' is forbidden.")

    safe_stem = _SAFE_FILENAME_RE.sub("_", stem).strip("._-") or "asset"
    safe_ext = re.sub(r"[^.a-z0-9]", "", ext_lower)
    return f"{safe_stem[:80]}{safe_ext}"


def resolve_safe_path(base_dir: Path, relative_target: str | Path) -> Path:
    """Resolve `relative_target` strictly within `base_dir`, preventing path traversal & symlink escape."""
    base_resolved = base_dir.resolve()
    rel_str = str(relative_target).strip()
    if not rel_str or "\x00" in rel_str:
        raise SecurityViolationError("Empty or null-byte path is forbidden.")

    candidate_input = Path(rel_str)
    if candidate_input.is_absolute():
        resolved = candidate_input.resolve()
    else:
        resolved = (base_resolved / candidate_input).resolve()

    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise SecurityViolationError(
            f"Path traversal blocked: '{relative_target}' escapes allowed root '{base_resolved}'."
        ) from exc

    return resolved


def validate_uploaded_file(
    filename: str,
    content: bytes,
    category: str | None = None,
    max_mb: int = 50,
) -> str:
    """Validate uploaded file extension, size, magic header, and non-executable content."""
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()

    allowed_all = set().union(*ALLOWED_ASSET_EXTENSIONS.values())
    allowed_set = ALLOWED_ASSET_EXTENSIONS.get(category, allowed_all) if category else allowed_all
    if ext not in allowed_set:
        raise SecurityViolationError(
            f"File extension '{ext}' is not permitted for category '{category or 'general'}'."
        )

    max_bytes = max(1, max_mb) * 1024 * 1024
    if len(content) == 0:
        raise SecurityViolationError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise SecurityViolationError(f"Uploaded file exceeds maximum allowed size ({max_mb} MB).")

    # Reject ELF / PE / shebang binaries disguised as assets
    if content.startswith((b"\x7fELF", b"MZ\x90\x00", b"#!/")):
        raise SecurityViolationError("Executable binary or script disguised as media asset blocked.")

    expected_sigs = MAGIC_SIGNATURES.get(ext)
    if expected_sigs and not any(content.startswith(sig) for sig in expected_sigs):
        raise SecurityViolationError(f"File header does not match expected '{ext}' format signature.")

    return safe_name


def sanitize_story_text(text: str, max_chars: int = 200_000) -> str:
    """Normalize story text as inert data (never executed as code or shell commands)."""
    if not isinstance(text, str):
        raise SecurityViolationError("Script text must be a string.")
    cleaned = text.replace("\x00", "")
    if len(cleaned) > max_chars:
        raise SecurityViolationError(f"Script exceeds maximum length of {max_chars} characters.")
    return cleaned


def validate_local_endpoint_url(url: str) -> str:
    """Verify optional local LLM endpoint points strictly to loopback (127.0.0.1 / localhost / ::1)."""
    cleaned = url.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise SecurityViolationError("Local endpoint URL must use http or https.")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SecurityViolationError(
            f"Privacy policy blocked external LLM host '{host}'. Only local loopback (127.0.0.1 / localhost) is allowed without explicit external opt-in."
        )
    return cleaned


def verify_destructive_confirmation(confirm_token: str | None, expected: str = "DELETE") -> None:
    if (confirm_token or "").strip() != expected:
        raise SecurityViolationError(
            f"Destructive action requires explicit confirmation token '{expected}'."
        )
