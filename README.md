# SIDD AI VIDEO STUDIO

**SIDD AI VIDEO STUDIO** is a self-hosted, offline-first, local 3D AI video production application that transforms written scripts (English, Urdu `اردو`, Roman Urdu, and mixed dialogue) into verified **H.264 MP4** animated videos with persistent 3D rigged characters, reusable 3D environments, skeletal animation & combat choreography, lip-synced local TTS voice acting, procedural sound effects & original music, subtitles, and cinematic camera movements.

> **100% Local & Free Workflow:** Zero mandatory paid APIs, cloud accounts, or API keys. After dependencies are installed, the entire script-to-video pipeline executes locally and offline.

---

## Core Capabilities (Implemented vs. Experimental / Planned)

### Implemented & Verified End-to-End
- **7-Step Script-to-Video Pipeline:**
  1. **Script Input & Project Setup:** Paste or upload scripts (`.txt`, `.md`, `.fountain`, `.srt`), select language (`auto`, `en`, `ur`, `roman_ur`, `mixed`), visual style (`cinematic_3d`, `stylized_animation`, `historical_drama`, `action_cinematic`, `educational`, `documentary`, `kids_cartoon`, `sci_fi`), aspect ratio (`16:9`, `9:16`, `1:1`), resolution (`720p`, `1080p`), FPS (`24`, `30`, `60`), subtitles, music, SFX, and render profile (`low_resource`, `balanced`, `high_quality`).
  2. **Deterministic + Optional Local LLM Script Analysis:** Extracts characters, outfits, props, locations, dialogue, narration, emotional states, physical actions, combat beats, transitions, historical eras, and historical accuracy review warnings without executing story text as code.
  3. **Editable Storyboard & Scene Planner:** Reorder, add, duplicate, delete, regenerate, or customize every scene's duration, environment, weather, time of day, camera shot/movement, animation clip, combat choreography, voice/emotion, SFX, and music.
  4. **Persistent 3D Character Studio:** Reusable humanoid 3D characters stored in SQLite with locked facial geometry, skin/eye/hair pigmentation, height, physique, default voice, prop inventory (`sword`, `shield`, `spear`, `lantern`, `scroll`, `staff`), and switchable outfit presets without identity drift across scenes.
  5. **Real 3D Scene & Skeletal Animation Engine (Blender 4.2 LTS `bpy`):**
     - **12 procedural 3D environments:** Palace Throne Hall, Ancient Marketplace, Desert Dunes, Medieval Fort Courtyard, Battlefield Plain, Forest Clearing, Mountain Pass, Village Square, Modern Room, Futuristic Sci-Fi Hall, Classroom, Masjid / Historic Courtyard.
     - **20 procedural 3D skeletal motions + facial/jaw rigging:** Idle breathing, walk/run locomotion, talking gestures, sit/stand, bow, point, carry, horse-riding stride, sword draw, attack slash, overhead strike, shield block, dodge sidestep, hit stagger, victory salute, kneel, dramatic turn.
     - **Collision-free multi-character blocking & combat choreography:** Deterministic attacker/defender beat timelines with alternating strikes, blocks, dodges, sparks, and camera shakes.
     - **7 camera shot presets & animated camera rigs:** Wide Establishing, Medium Two-Shot, Close-Up Portrait, Over-the-Shoulder, Tracking Follow, Orbit 360, Action Combat Dynamic, plus animated lighting, torches, banners, dust/rain/fog/sandstorm atmosphere.
  6. **Local Multilingual Voice Acting, Viseme Lip-Sync & Audio Mixing:**
     - **Offline TTS (`piper` / `espeakbridge` + optional Piper ONNX models):** Distinct male, female, elder, youth, and narrator voices supporting English, Urdu (`اردو`), and normalized Roman Urdu (`Assalam o Alaikum`, `dushman`, `qila`, etc.).
     - **3D Lip-Sync:** Extracts normalized per-frame speech amplitude envelopes to drive 3D jaw and mouth keyframes synchronized with dialogue audio.
     - **Procedural Sound Design & Original Music:** Synthesizes royalty-free footsteps, sword clashes, shield impacts, battle horns, wind, crowd murmur, desert breeze, and pentatonic/cinematic underscore with automatic `-9.5 dB` dialogue ducking.
  7. **FFmpeg H.264/AAC Muxing & Strict PyAV Output Verification:**
     - Encodes `libx264` (`yuv420p`) + `aac` stereo (`44.1 kHz`) + optional soft `mov_text` track + burned lower-third captions + `.srt`/`.vtt` files.
     - Every scene and full-project export is verified via **PyAV** (non-empty file, container openable, video stream present, expected resolution, non-zero duration, decodable start/middle/end frames, audio stream present) before a render job can succeed.
- **14-Section Dark Cinematic Web UI:** Dashboard, Create New Video, Script Editor, Storyboard, Character Studio, Voice Studio, Environment Studio, Animation Studio, Scene Timeline, Render Queue (live WebSocket progress + pause/resume/cancel/retry), Video Library, AI Model Manager, Hardware Monitor, and Project Settings.
- **Governance, Copyright & Security:** Per-project license provenance report (`GET /api/projects/{id}/license-report`), consent-gated AI Model Manager with SHA256 verification, strict path traversal protection, file type/size validation, loopback-only local LLM support by default, and confirmation tokens for destructive deletions.

### Optional / Hardware-Dependent / Planned Capabilities
- **Local Neural LLM Script Refinement (Optional):** Supports local `Ollama` / `llama.cpp` OpenAI-compatible loopback servers (`SIDD_LOCAL_LLM_URL`) when installed by the user; falls back automatically to the built-in deterministic screenplay/prose parser.
- **Custom Neural Piper ONNX Voice Weights (Optional):** Users can import local licensed `.onnx` + `.onnx.json` Piper voice packs in the AI Model Manager; built-in offline eSpeak-NG Studio DSP voices work out-of-the-box with zero extra downloads.
- **Photorealistic AAA Crowd Simulations / High-Poly Mocap Retargeting (Hardware-Limited / Planned):** Current 3D characters use clean stylized-cinematic articulated humanoid meshes optimized to render reliably on both CPU-only machines and GPU workstations. Photorealistic skin subsurface scattering, cloth physics, and large battle crowds require dedicated NVIDIA RTX GPUs (12 GB+ VRAM) and external `.fbx`/`.glb` asset imports.

---

## Hardware Profiles & Honest Expectations

| Profile | Target Hardware | Strategy | Typical Speed (per 4s scene) |
| :--- | :--- | :--- | :--- |
| **`low_resource`** | CPU-only (2–4 cores, 4–8 GB RAM, 0 VRAM) | Keyframe step rendering (`8 fps` -> temporal interpolation to target FPS, `50%` internal scale -> Lanczos upscale, `3 spp` Cycles CPU) | ~12–25 sec on 2-vCPU Xeon |
| **`balanced`** | 6–8 core CPU or 4–8 GB VRAM GPU, 16 GB RAM | `12 fps` internal render, `80%` internal scale, `6 spp` | ~8–20 sec on modern desktop |
| **`high_quality`** | 8+ core CPU + 8–16 GB+ VRAM GPU, 32 GB RAM | Full native FPS (`24/30/60`), `100%` native 1080p scale, `14 spp` + OpenImageDenoise | Best with CUDA/OptiX GPU |

---

## Quick Start (Local Installation & Run)

### Prerequisites
- **Linux** (Debian/Ubuntu x86_64 recommended) or macOS/WSL2
- **Python 3.11** (required for the `bpy==4.2.15` wheel)
- **Node.js 20+** and **npm 10+**
- `gcc` (used once on headless Linux servers without X11/OpenGL libraries by `scripts/setup_headless_bpy.py`)

### 1. Clone & Set Up Python Environment
```bash
git clone <your-repo-url>
cd website

python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# On headless Linux without X11/GL system packages, verify/build lightweight headless shims for bpy:
.venv/bin/python scripts/setup_headless_bpy.py
```

### 2. Build Frontend & Start Studio (Local-Only Binding on `:8000`)
```bash
./scripts/build_prod.sh
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser. *(Bind to `127.0.0.1` on personal machines for local-only security; use `--host 0.0.0.0` only inside isolated container preview environments.)*

### 3. Development Mode (Hot-Reload Frontend `:5173` + API `:8000`)
```bash
./scripts/dev.sh
```
Open **`http://localhost:5173`** in your browser (Vite proxies `/api` and `/ws` cleanly to `:8000`).

---

## Running Automated Tests

```bash
# Fast unit, security, offline privacy, model manager, license, and API tests (~1.5s):
.venv/bin/pytest -m "not e2e" -v

# Full test suite INCLUDING real Blender 3D multi-scene rendering, local TTS, FFmpeg muxing, and PyAV MP4 decode verification:
.venv/bin/pytest -v
```

---

## Project Directory Structure

```text
website/
├── backend/
│   ├── api/                # FastAPI routers (projects, characters, voices, environments, animations, jobs, library, models, hardware)
│   ├── core/               # Config, SQLite WAL schema, path/upload security guards, structured ring-buffer logging
│   ├── services/           # Project workflow service, persistent subprocess JobManager + WebSocket hub, hardware & license services
│   └── main.py             # FastAPI app entrypoint, /ws/jobs WebSocket, SPA static serving
├── story_engine/           # English/Urdu/Roman-Urdu normalizer, deterministic + local-LLM script parser, storyboard builder
├── character_engine/       # Persistent Character Studio CRUD, outfit presets, articulated 3D humanoid + prop rig builder (bpy)
├── scene_engine/           # 12 procedural 3D environments, weather/lighting, 7 cinematic camera rigs (bpy)
├── animation_engine/       # 20 skeletal animation clips, collision-free XY blocking, combat choreography, viseme jaw keyframes
├── voice_engine/           # Offline multilingual TTS (eSpeak-NG / Piper ONNX), viseme extractor, procedural SFX & music mixer, SRT/VTT
├── render_engine/          # Headless Blender subprocess worker, Pillow caption overlay + FFmpeg H.264/AAC muxer, PyAV MP4 validator
├── model_manager/          # Local AI Model catalog, license & hardware checks, consent-gated local model import & SHA256 check
├── project_storage/        # Local project directory layout, manifest read/write, disk usage inspection, temp file cleanup
├── frontend/               # React 18 + TypeScript + Vite + Tailwind CSS dark cinematic studio interface (14 views)
├── scripts/                # Headless bpy shim builder, dev launcher, production frontend builder
├── tests/                  # Unit, API, security, offline-mode, and real end-to-end 3D MP4 verification tests
└── docs/                   # Architecture, hardware limitations, copyright/licensing, and backup/recovery guides
```

---

## Documentation Index
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Modular pipeline architecture, data flow, and database schema
- [`docs/HARDWARE_AND_LIMITATIONS.md`](docs/HARDWARE_AND_LIMITATIONS.md) — Hardware tiers, CPU fallback behavior, and known limitations
- [`docs/LICENSES_AND_COPYRIGHT.md`](docs/LICENSES_AND_COPYRIGHT.md) — Open-source component licenses, asset provenance, and ethical guardrails
- [`docs/BACKUP_AND_RECOVERY.md`](docs/BACKUP_AND_RECOVERY.md) — Backing up projects, SQLite state, crash recovery, and storage cleanup
