# Copyright, Licensing & Ethical Media Policy

## Core Principles
1. **No Unauthorized Cloning or Ripping:** SIDD AI VIDEO STUDIO never downloads copyrighted characters, commercial soundtracks, celebrity voice clones, or unlicensed 3D meshes.
2. **Explicit Model Consent:** Every optional model in the AI Model Manager displays its exact license (`MIT`, `GPL-3.0-or-later`, `Apache-2.0`), disk footprint, hardware requirements, and requires explicit user consent (`user_consent=true`) before registration or import.
3. **Project Provenance Report:** Every project maintains an auditable license ledger (`GET /api/projects/{project_id}/license-report`) listing the origin and license of every 3D rig, environment, voice clip, procedural music cue, and user-uploaded file.

## Bundled Open-Source Engines & Licenses
| Component | License | Role in Studio |
| :--- | :--- | :--- |
| **Blender Python API (`bpy` 4.2 LTS)** | `GPL-3.0-or-later` | Headless 3D scene construction, character rigging, animation, lighting, Cycles rendering |
| **Piper TTS & eSpeak-NG (`piper-tts`)** | `MIT` / `GPL-3.0-or-later` | Offline multilingual English, Urdu & Roman Urdu speech + phoneme synthesis |
| **FFmpeg (`imageio-ffmpeg`) & PyAV (`av`)** | `LGPL-2.1+` / `GPL-2.0+` / `BSD-3-Clause` | H.264/AAC encoding, audio mixing, subtitle muxing, and post-render stream decode verification |
| **FastAPI, Pydantic, Uvicorn** | `MIT` / `BSD-3-Clause` | Local REST API & WebSocket server |
| **React, Vite, Tailwind CSS, Lucide** | `MIT` / `ISC` | Dark cinematic frontend studio application |
| **Procedural 3D Rigs, Environments, SFX & Music** | `CC0-1.0 / Studio Original` | Synthesized locally from mathematical geometry and DSP waveforms; safe for user exports |
