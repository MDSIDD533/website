# Hardware Profiles, Fallbacks & Honest Limitations

## Automatic Hardware Detection
On startup and via `GET /api/hardware/status`, SIDD AI VIDEO STUDIO inspects:
- Operating system, kernel, architecture
- Physical/logical CPU cores and model name
- Total and available system RAM
- Free disk space on the project storage volume
- NVIDIA (`nvidia-smi`) and AMD (`rocm-smi`) GPUs and available VRAM
- Installed local engines (`bpy`, `ffmpeg`, `pyav`, `espeakbridge`, `piper`)

## Render Profiles
1. **`low_resource` (Auto-selected when no discrete GPU is found or RAM < 8 GB):**
   - Renders Blender 3D scenes at `50%` internal resolution and `8 keyframes/sec` with `3 Cycles samples`, then applies Lanczos upscaling, `hqdn3d` denoising, and FFmpeg temporal interpolation (`framerate`) to produce smooth 720p/1080p H.264 output in seconds rather than hours on CPU-only hosts.
2. **`balanced` (4–8 GB VRAM or 8+ CPU cores with 16 GB RAM):**
   - Renders at `80%` internal resolution, `12 keyframes/sec`, `6 Cycles samples`.
3. **`high_quality` (8 GB+ VRAM GPU and 16 GB+ RAM):**
   - Renders every target frame natively (`100%` scale, `14 Cycles samples` + OpenImageDenoise). Warning: Running `high_quality` at 1080p/60fps on CPU-only hardware will take several minutes per scene.

## Known Technical Limitations
- **Mesh Style:** Procedural 3D characters and environments are stylized-cinematic articulated 3D geometry built natively via `bpy` (zero external multi-GB asset packs required). They are not photorealistic Metahuman scans.
- **Urdu Typography in Burned Video Frames:** Soft subtitle tracks (`mov_text`, `.srt`, `.vtt`) preserve full UTF-8 Arabic/Urdu (`اردو`) script cleanly for media players and HTML5 `<track>` playback. Burned-in pixel overlays on systems without an Urdu shaping engine (`libraqm`/HarfBuzz) display Latin/Roman-Urdu cleanly while relying on `.vtt`/`.srt` tracks for shaped Nastaliq/Naskh Urdu glyphs.
- **Voice Expressiveness:** Built-in eSpeak-NG + Studio DSP voices synthesize clear offline English, Urdu, and Roman Urdu immediately with zero model downloads, with robotic timbre compared to neural TTS. Importing a local licensed `.onnx` Piper voice pack in the AI Model Manager upgrades neural naturalness offline.
