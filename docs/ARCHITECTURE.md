# Architecture Overview — SIDD AI VIDEO STUDIO

## 1. End-to-End Data Flow

```text
[User Script (EN / UR / Roman UR)]
        │
        ▼
[story_engine.normalizer + parser]
  • Detects language & normalizes Roman Urdu phonetics for TTS
  • Deterministic screenplay/prose parser (+ optional loopback local LLM)
  • Extracts characters, dialogue, emotions, actions, combat, eras, historical warnings
        │
        ▼
[story_engine.storyboard + backend.services.project_service]
  • Persists Project, Persistent Characters, Scenes, and Asset Provenance in SQLite (WAL)
  • Creates local project workspace under workspace_data/projects/<project_id>/
        │
        ▼
[backend.services.job_manager]
  • Enqueues background render job (scene_render or full_video_render)
  • Broadcasts real stage & frame events over WebSocket (/ws/jobs)
  • Supports SIGSTOP/SIGCONT pause/resume, SIGTERM cancel, retry, and restart recovery
        │
        ├──► [voice_engine.tts + sound_design + subtitles]
        │      • Generates offline 44.1 kHz stereo dialogue WAV + word timings
        │      • Computes normalized jaw viseme envelope per frame
        │      • Synthesizes procedural foley/combat SFX + pentatonic underscore with dialogue ducking
        │      • Writes .srt and .vtt subtitle files
        │
        ├──► [render_engine.blender_worker (isolated subprocess)]
        │      • Builds 3D environment, lighting, weather, and props (scene_engine)
        │      • Builds articulated 3D characters with locked identity + active outfit (character_engine)
        │      • Applies locomotion, combat choreography, expressions, and jaw lip-sync (animation_engine)
        │      • Animates cinematic camera rig (scene_engine.cameras)
        │      • Renders Cycles PNG sequence while emitting SIDD_STAGE and SIDD_FRAME telemetry
        │
        ├──► [render_engine.video_assembler]
        │      • Optional burned-in lower-third caption overlay via Pillow
        │      • FFmpeg Lanczos scaling, temporal frame interpolation (on low_resource/balanced), H.264 + AAC + mov_text muxing
        │      • Concatenates verified scene MP4s into final project export
        │
        └──► [render_engine.validator (PyAV)]
               • Verifies non-empty MP4, container integrity, H.264 video stream, expected resolution,
                 non-zero duration, decodable start/middle/end frames, and AAC audio stream
```

## 2. Database Schema (`workspace_data/sidd_studio.db`)
- `projects`: Studio project configuration, script text, parsed summary JSON, render settings, latest output path, validation report.
- `characters`: Persistent reusable 3D characters across projects (appearance, outfit presets, props, default voice, style).
- `scenes`: Ordered storyboard/timeline scenes with environment, camera, lighting, weather, dialogue, voice, animation, choreography, and render status/metrics.
- `jobs`: Persistent background render queue with measurable progress, stage label, pause/cancel state, logs, and result verification payload.
- `model_states`: Local AI Model Manager consent, installation status, local file path, and SHA256 checksums.
- `asset_licenses`: Per-project provenance log for generated 3D scenes, characters, TTS audio, procedural music/SFX, and user uploads.
