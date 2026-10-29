"""SRT and WebVTT subtitle generation for individual scenes and full assembled videos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from story_engine.normalizer import transliterate_roman_urdu_to_urdu


def build_urdu_script_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Produce companion Urdu (اردو) script subtitle segments from Roman Urdu segments."""
    urdu_segments: list[dict[str, Any]] = []
    for seg in segments:
        spk = str(seg.get("speaker") or "")
        txt = str(seg.get("text") or "").strip()
        ur_spk = "راوی" if spk == "Narrator" else (transliterate_roman_urdu_to_urdu(spk) if spk else "")
        ur_txt = transliterate_roman_urdu_to_urdu(txt)
        urdu_segments.append(
            {
                **seg,
                "speaker": ur_spk,
                "text": ur_txt,
            }
        )
    return urdu_segments


def _fmt_srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hrs, rem = divmod(ms_total, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    return _fmt_srt_time(seconds).replace(",", ".")


def write_srt_file(segments: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start_s = float(seg.get("start_sec", 0.0))
        end_s = max(start_s + 0.4, float(seg.get("end_sec", start_s + 1.5)))
        speaker = seg.get("speaker", "")
        text = (seg.get("text") or "").strip()
        caption = f"{speaker}: {text}" if speaker and speaker != "Narrator" else text
        lines.append(f"{idx}\n{_fmt_srt_time(start_s)} --> {_fmt_srt_time(end_s)}\n{caption}\n")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_vtt_file(segments: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["WEBVTT\n"]
    for seg in segments:
        start_s = float(seg.get("start_sec", 0.0))
        end_s = max(start_s + 0.4, float(seg.get("end_sec", start_s + 1.5)))
        speaker = seg.get("speaker", "")
        text = (seg.get("text") or "").strip()
        caption = f"{speaker}: {text}" if speaker and speaker != "Narrator" else text
        lines.append(f"{_fmt_vtt_time(start_s)} --> {_fmt_vtt_time(end_s)}\n{caption}\n")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
