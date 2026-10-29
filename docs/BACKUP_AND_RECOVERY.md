# Backup, Storage Cleanup & Crash Recovery

## Local Data Layout
By default, all user data lives inside `workspace_data/` (configurable via `SIDD_WORKSPACE_DIR` in `.env` or Project Settings):

```text
workspace_data/
├── sidd_studio.db          # SQLite WAL database (projects, characters, scenes, jobs, licenses)
└── projects/
    └── <project_id>/
        ├── project_manifest.json
        ├── audio/          # Scene TTS speech & procedural audio mix WAV stems
        ├── subtitles/      # Per-scene .srt & .vtt (+ _ur.srt / _ur.vtt for Roman Urdu)
        ├── renders/        # Verified per-scene H.264 MP4 clips
        ├── thumbnails/     # Raytraced 3D scene thumbnails
        ├── exports/        # Final assembled project H.264 MP4s & master subtitles
        ├── reports/        # Post-render PyAV verification JSON reports
        └── uploads/        # Validated user-uploaded reference assets
```

## Backing Up Your Work
1. Stop active renders in the **Render Queue**.
2. Copy `workspace_data/sidd_studio.db` and `workspace_data/projects/` to your backup drive.
3. Because each project folder also writes `project_manifest.json`, project metadata remains human-readable alongside exported MP4s and subtitles.

## Restart & Crash Recovery
- On backend startup, `JobManager._recover_interrupted_jobs()` scans SQLite for any jobs left in `running` or `paused` state from an unexpected shutdown or power loss and marks them `interrupted` with clear recovery instructions so they can be retried cleanly with one click in **Render Queue**.
- Use **Project Settings -> Clean Temp Files** (`POST /api/projects/{id}/clean-temp`) to reclaim intermediate frame buffers while preserving final verified MP4 exports.
