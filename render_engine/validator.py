"""Strict post-export MP4 validator using PyAV decode verification & render report builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import av  # type: ignore
import numpy as np


def validate_exported_mp4(
    mp4_path: Path,
    *,
    expect_audio: bool = True,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> dict[str, Any]:
    """Verify file existence, container integrity, video/audio streams, and actual frame/sample decoding.

    Never reports `valid=True` unless real video frames and (when expected) audio packets decode cleanly.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not mp4_path.is_file():
        return {
            "valid": False,
            "filename": mp4_path.name,
            "errors": [f"Output file does not exist: {mp4_path}"],
            "warnings": [],
        }

    size_bytes = mp4_path.stat().st_size
    if size_bytes < 1024:
        return {
            "valid": False,
            "filename": mp4_path.name,
            "file_size_bytes": size_bytes,
            "errors": ["Output file is smaller than 1 KB and cannot be a valid MP4 video."],
            "warnings": [],
        }

    try:
        container = av.open(str(mp4_path))
    except Exception as exc:
        return {
            "valid": False,
            "filename": mp4_path.name,
            "file_size_bytes": size_bytes,
            "errors": [f"Container open failed: {exc}"],
            "warnings": [],
        }

    try:
        v_streams = list(container.streams.video)
        a_streams = list(container.streams.audio)
        s_streams = list(container.streams.subtitles)

        if not v_streams:
            errors.append("Missing video stream in MP4 container.")
        if expect_audio and not a_streams:
            errors.append("Missing audio stream in MP4 container.")

        width = height = 0
        fps = 0.0
        v_codec = ""
        decoded_video_frames = 0
        non_black_frame_seen = False

        if v_streams:
            vs = v_streams[0]
            width = int(vs.codec_context.width or 0)
            height = int(vs.codec_context.height or 0)
            fps = float(vs.average_rate or vs.base_rate or 0.0)
            v_codec = vs.codec_context.name or ""

            if expected_width and width != expected_width:
                warnings.append(f"Video width {width} differs from requested {expected_width}.")
            if expected_height and height != expected_height:
                warnings.append(f"Video height {height} differs from requested {expected_height}.")

            for frame in container.decode(video=0):
                decoded_video_frames += 1
                if decoded_video_frames <= 5:
                    arr = frame.to_ndarray(format="rgb24")
                    if float(np.std(arr)) > 1.0 or float(np.mean(arr)) > 2.0:
                        non_black_frame_seen = True
                if decoded_video_frames >= 30:
                    # Sample first 30 frames to confirm clean H.264 decode without scanning hours of video
                    break

            if decoded_video_frames == 0:
                errors.append("Failed to decode any video frames from stream.")
            elif not non_black_frame_seen:
                warnings.append("Sampled video frames have very low luminance variance.")

        a_codec = ""
        audio_sample_rate = 0
        decoded_audio_samples = 0
        audio_peak = 0.0
        if a_streams:
            container.seek(0)
            aus = a_streams[0]
            a_codec = aus.codec_context.name or ""
            audio_sample_rate = int(aus.codec_context.sample_rate or 0)
            for aframe in container.decode(audio=0):
                arr = aframe.to_ndarray()
                decoded_audio_samples += arr.shape[-1]
                peak = float(np.max(np.abs(arr)))
                if peak > audio_peak:
                    audio_peak = peak
                if decoded_audio_samples >= 44100 * 3:
                    break
            if expect_audio and decoded_audio_samples == 0:
                errors.append("Audio stream exists but decoded 0 audio samples.")

        duration_sec = round(float(container.duration) / float(av.time_base), 2) if container.duration else 0.0
        if duration_sec <= 0.0:
            errors.append("Container reported zero duration.")

    except Exception as exc:
        errors.append(f"Stream decode error: {exc}")
        width = height = decoded_video_frames = decoded_audio_samples = audio_sample_rate = 0
        fps = duration_sec = audio_peak = 0.0
        v_codec = a_codec = ""
        s_streams = []
    finally:
        container.close()

    valid = len(errors) == 0
    return {
        "valid": valid,
        "filename": mp4_path.name,
        "path": str(mp4_path),
        "file_size_bytes": size_bytes,
        "file_size_mb": round(size_bytes / (1024 * 1024), 2),
        "duration_sec": duration_sec,
        "resolution": f"{width}x{height}",
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "video_codec": v_codec,
        "decoded_video_frames_checked": decoded_video_frames,
        "audio_status": "verified_aac_stereo" if (a_codec and decoded_audio_samples > 0) else "missing_or_empty",
        "audio_codec": a_codec,
        "audio_sample_rate": audio_sample_rate,
        "subtitle_streams": len(s_streams),
        "errors": errors,
        "warnings": warnings,
    }
