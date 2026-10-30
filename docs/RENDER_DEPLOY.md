# Deploy /studio on Render (Free)

This repository is prepared for a single Docker web service on Render. The
FastAPI process serves both `/api/*` and the built React app, including the
`/studio` route.

> Arena cannot create a service inside a user's Render account. The files in
> this repo make the repo deployable; the account owner still needs to connect
> the GitHub repo in the Render Dashboard once.

## Option A — Manual Web Service (works from a non-default branch)

1. Open the Render Dashboard and choose **New + → Web Service**.
2. Connect GitHub and select `MDSIDD533/website`.
3. Select branch `arena/49e70a96-website` (or `main` after this branch is
   merged).
4. Set **Language/Runtime** to **Docker**.
5. Set **Region** to **Singapore**.
6. Set **Instance Type / Plan** to **Free**.
7. Confirm **Dockerfile Path** is `./Dockerfile`.
8. Set **Health Check Path** to `/api/health`.
9. Deploy. When Render gives the service URL, open `<service-url>/studio`.

The Dockerfile is self-contained: it builds `frontend/dist`, installs the
slim Python runtime from `requirements.render.txt`, installs Chromium and
FFmpeg/FFprobe, and pins `hyperframes@0.8.220`.

## Option B — Blueprint

After these files are available on the branch/repo Render reads for
Blueprints, choose **New + → Blueprint**, select the same repository, and
apply `render.yaml`. The Blueprint requests:

- service name `sidd-ai-video-studio` (Render may add a suffix if taken);
- `runtime: docker`;
- `plan: free`;
- `region: singapore`;
- `branch: arena/49e70a96-website`;
- health check `/api/health`.

## Important free-tier limits

- Free web services are small (0.1 CPU / 512 MB RAM in the Blueprint plan
  table). A 1080p Chromium/HyperFrames render can be very slow or run out of
  memory; the UI/API can deploy successfully even when a long render is not
  practical on the free instance.
- Free services spin down after inactivity and take time to wake.
- The filesystem is ephemeral. Jobs, the SQLite database and generated MP4s
  under `/tmp/sidd-workspace` can disappear on restart, redeploy or spin-down.
  Download a finished MP4 immediately.
- This deployment has no login/auth layer. Anyone who has the public URL can
  open the studio and queue jobs, so keep the URL private or add auth/another
  access control before sharing it widely.
- Blender (`bpy`), Piper/ONNX and SciPy are intentionally excluded from the
  slim Render image. The Motion Studio HyperFrames path is the supported
  target for this deployment.

For reliable public rendering, keep the same Dockerfile but move to a larger
paid instance and attach persistent storage or external object storage for
outputs.
