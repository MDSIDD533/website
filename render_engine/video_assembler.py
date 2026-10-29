"""FFmpeg video encoder, caption renderer, scene muxer, and multi-scene chronological exporter."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from render_engine.blender_worker import compute_dimensions


def get_ffmpeg_binary() -> str:
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    import imageio_ffmpeg  # type: ignore

    return imageio_ffmpeg.get_ffmpeg_exe()


def overlay_burned_captions_on_frames(
    frames_dir: Path,
    subtitle_segments: list[dict[str, Any]],
    render_fps: int,
) -> None:
    """Composite clean lower-third caption bars onto rendered PNG frames for Latin/Roman-Urdu captions."""
    if not subtitle_segments:
        return
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    if not frame_files:
        return

    font = ImageFont.load_default()
    for idx, fpath in enumerate(frame_files):
        t_sec = idx / float(max(1, render_fps))
        active_seg = next(
            (
                s
                for s in subtitle_segments
                if float(s.get("start_sec", 0.0)) <= t_sec <= float(s.get("end_sec", 0.0)) + 0.15
            ),
            None,
        )
        if not active_seg:
            continue
        raw_text = f"{active_seg.get('speaker', '')}: {active_seg.get('text', '')}".strip(": ")
        # Default bitmap font supports ASCII/Latin cleanly; non-ASCII (e.g. Urdu script) is served via UTF-8 VTT/SRT & mov_text
        if not all(ord(c) < 256 for c in raw_text):
            continue

        with Image.open(fpath).convert("RGBA") as img:
            w, h = img.size
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            bar_h = max(28, int(h * 0.10))
            bar_y0 = h - bar_h - int(h * 0.04)
            margin_x = int(w * 0.08)
            draw.rounded_rectangle(
                [(margin_x, bar_y0), (w - margin_x, bar_y0 + bar_h)],
                radius=6,
                fill=(10, 12, 18, 185),
                outline=(212, 175, 55, 130),
                width=1,
            )
            clipped_txt = raw_text[:92] + ("..." if len(raw_text) > 92 else "")
            bbox = draw.textbbox((0, 0), clipped_txt, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = max(margin_x + 10, (w - tw) // 2)
            ty = bar_y0 + max(4, (bar_h - th) // 2)
            draw.text((tx, ty), clipped_txt, fill=(245, 245, 240, 255), font=font)
            combined = Image.alpha_composite(img, overlay).convert("RGB")
            combined.save(fpath, format="PNG")


def encode_scene_mp4(
    *,
    frames_dir: Path,
    audio_wav_path: Path,
    output_mp4_path: Path,
    render_fps: int,
    target_fps: int,
    width: int,
    height: int,
    transition_type: str = "crossfade",
    duration_sec: float = 3.5,
    subtitle_srt_path: Path | None = None,
) -> Path:
    """Encode PNG sequence + mixed WAV audio (+ optional soft SRT track) into H.264/AAC MP4."""
    ffmpeg = get_ffmpeg_binary()
    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)

    vf_parts = [
        f"scale={width}:{height}:flags=lanczos",
        "hqdn3d=1.5:1.5:3:3",
    ]
    if target_fps > render_fps:
        vf_parts.append(f"framerate=fps={target_fps}:interp_start=0:interp_end=255")
    else:
        vf_parts.append(f"fps={target_fps}")

    if transition_type in {"crossfade", "dip_to_black"} and duration_sec >= 1.2:
        fade_out_start = max(0.2, duration_sec - 0.35)
        vf_parts.append("fade=t=in:st=0:d=0.25")
        vf_parts.append(f"fade=t=out:st={fade_out_start:.2f}:d=0.32")

    vf_Parts_str = ",".join(vf_parts)

    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        str(render_fps),
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-i",
        str(audio_wav_path),
    ]
    has_subs = subtitle_srt_path is not None and subtitle_srt_path.is_file() and subtitle_srt_path.stat().st_size > 0
    if has_subs:
        cmd.extend(["-i", str(subtitle_srt_path)])

    cmd.extend(
        [
            "-vf",
            vf_Parts_str,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "44100",
            "-ac",
            "2",
        ]
    )
    if has_subs:
        cmd.extend(["-c:s", "mov_text"])

    cmd.extend(["-movflags", "+faststart", "-shortest", str(output_mp4_path)])

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0 or not output_mp4_path.is_file():
        raise RuntimeError(f"FFmpeg scene encoding failed (exit {proc.returncode}): {proc.stderr[-600:]}")
    return output_mp4_path


def assemble_project_mp4(
    *,
    scene_mp4_paths: list[Path],
    output_mp4_path: Path,
    resolution: str,
    aspect_ratio: str,
    fps: int,
    full_srt_path: Path | None = None,
) -> Path:
    """Concatenate rendered chronological scene MP4s into a single synchronized H.264/AAC MP4."""
    if not scene_mp4_paths:
        raise ValueError("Cannot assemble final video: zero rendered scene clips provided.")

    ffmpeg = get_ffmpeg_binary()
    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = compute_dimensions(resolution, aspect_ratio)

    concat_list_file = output_mp4_path.parent / f"{output_mp4_path.stem}_concat.txt"
    escaped_lines = []
    for p in scene_mp4_paths:
        if not p.is_file():
            raise FileNotFoundError(f"Rendered scene file missing: {p}")
        safe_p = str(p.resolve()).replace("'", "'\\''")
        escaped_lines.append(f"file '{safe_p}'")
    concat_list_file.write_text("\n".join(escaped_lines) + "\n", encoding="utf-8")

    has_subs = full_srt_path is not None and full_srt_path.is_file() and full_srt_path.stat().st_size > 0
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_file),
    ]
    if has_subs:
        cmd.extend(["-i", str(full_srt_path)])

    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
        ]
    )
    if has_subs:
        cmd.extend(["-map", "1:0", "-c:s", "mov_text"])

    cmd.extend(
        [
            "-vf",
            f"scale={width}:{height}:flags=lanczos,fps={fps}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_mp4_path),
        ]
    )

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode != 0 or not output_mp4_path.is_file():
            raise RuntimeError(f"FFmpeg project assembly failed (exit {proc.returncode}): {proc.stderr[-600:]}")
    finally:
        concat_list_file.unlink(missing_ok=True)

    return output_mp4_path
