# Free deployment guide — Vercel frontend + Docker backend

This guide deploys the current split architecture:

```text
Browser
  │
  ├── React/Vite UI ............ Vercel (frontend/)
  │
  └── HTTPS + WSS .............. FastAPI Docker backend
                                   ├─ HyperFrames 0.8.220
                                   ├─ Chromium + FFmpeg/FFprobe
                                   ├─ Piper Joe  (male, 63,201,294 bytes)
                                   └─ Piper Amy  (female, 63,201,294 bytes)
```

No paid inference/TTS API is used at runtime. Speech synthesis remains local
inside the backend container.

## Read this first: what “free” really means in 2026

### Koyeb does not currently satisfy a strict no-card rule

Koyeb still documents one Free Instance (0.1 vCPU, 512 MB RAM, 2 GB SSD,
Frankfurt or Washington, scale-to-zero after one idle hour). However, Koyeb's
current pricing FAQ says a credit card is required, verified with a **US$29
pre-authorization hold**, and a newly selected plan can be charged pro-rata.
Their organization docs also say Starter requires a valid payment method.
Therefore:

- **If a card is absolutely not allowed, do not start the Koyeb signup.**
- The backend files below are Koyeb-ready if that policy changes or if the
  account owner personally accepts Koyeb's verification step.
- Never select a non-Free instance unless you understand that it is billable.

Official references are linked at the bottom of this document.

### No-card backend options exist, but they are very small

The same `Dockerfile.backend` can be tried on other Docker hosts:

| Host | Card to start | Published free size | Main limitation for this app |
|---|---:|---:|---|
| Back4App Containers | No | 0.25 CPU / 256 MB RAM | Very likely too little RAM for Piper + HyperFrames renders; treat as an API smoke test |
| SnapDeploy Free | No | 0.25 vCPU / 512 MB, 100 running hours/month | Sleeps after 15 idle minutes; free plan says WebSocket apps need Always-On |
| Koyeb Free Instance | **Yes** | 0.1 vCPU / 512 MB / 2 GB SSD | Card rule fails; slow/OOM risk for 1080p renders |

A public URL that wakes on demand is not the same as a powerful always-on
render server. On any 256–512 MB free tier, expect health checks, browsing and
small voice previews to be more realistic than guaranteed 1080p HyperFrames
exports. Generated files and SQLite data are on ephemeral storage unless the
host offers a persistent volume.

### Vercel Hobby limits

Vercel's Hobby plan is free, but Vercel restricts it to **non-commercial,
personal use**. It currently includes (among other limits) the first 100 GB of
Fast Data Transfer and 1,000,000 CDN requests per month. If this becomes a
commercial product, use a plan/host whose terms allow that use.

## Files prepared in this repository

| File | Purpose |
|---|---|
| `frontend/vercel.json` | Vite framework, install/build/output and SPA rewrite |
| `frontend/.env.example` | Frontend backend URL example |
| `deploy/frontend.env.example` | Copy-ready Vercel environment variable list |
| `frontend/src/api.ts` | Uses `VITE_API_BASE_URL`; derives `wss://.../ws/jobs` |
| `Dockerfile.backend` | Backend-only image with Chromium, FFmpeg, HyperFrames and verified Piper models |
| `requirements.backend.txt` | Pinned API/Piper dependencies; excludes Blender `bpy` |
| `deploy/backend.env.example` | Copy-ready backend environment variables |
| `.dockerignore` | Keeps local models, renders, videos and virtualenvs out of the Docker context |

## How the 63 MB Piper models are handled

Do **not** commit the ONNX files to Git and do not use Git LFS for this setup.

`Dockerfile.backend` contains a `piper-models` build stage that:

1. downloads `en_US-joe-medium.onnx`, its JSON config and model card;
2. downloads `en_US-amy-medium.onnx`, its JSON config and model card;
3. verifies these exact model SHA-256 values before the build can continue:
   - Joe: `58afce0321b8d9c46d7cdf9c16500cc55a793b4220212dba6b70fb788b3baf06`
   - Amy: `b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18`
4. copies the verified directory to
   `/opt/sidd-models/piper-onnx-custom-voice` in the runtime image;
5. sets `SIDD_MODELS_DIR=/opt/sidd-models`.

The two models add about **126 MB** before Python, Chromium, Node,
HyperFrames and system libraries. The final image will be much larger than
126 MB. A host with a small disk/image limit can reject it even if the source
repository is small.

Joe's model-card dataset is CC0. Amy comes from the MycroftAI Mimic3 voice
route documented as CC-BY-SA-4.0, so preserve attribution/model-card evidence
and review share-alike duties before redistributing a built image publicly.

If a host's builder cannot reach Hugging Face, build the same image where the
download works, push it to a container registry you control (for example
GHCR), and deploy the prebuilt image. Do not replace the hash check with an
unverified mirror.

---

# Step 1 — Deploy the backend before the frontend

The frontend needs the backend's final HTTPS domain.

## Option A: Koyeb-ready path (card warning above)

1. Create/log in to the Koyeb account yourself. Stop if it asks for a card and
   that violates your rule.
2. In Koyeb, choose **Create Web Service**.
3. Choose **GitHub**, repository `MDSIDD533/website`, and branch
   `arena/49e70a96-website` (use `main` only after this branch is reviewed and
   merged).
4. Builder: **Dockerfile**.
5. Dockerfile location/path: `Dockerfile.backend`.
6. Service type: **Web Service**.
7. Region for the Free Instance: **Frankfurt** or **Washington, D.C.**
8. Instance: **Free** only. Do not select Eco/Standard if you require $0.
9. Exposed port: `8000`, protocol HTTP.
10. Route: `/` → port `8000`.
11. Health check path: `/api/health`.
12. Add every value from `deploy/backend.env.example` in **Environment
    variables**. If Koyeb supplies its own `PORT`, keep its supplied value;
    the container command reads `PORT`.
13. Name the app/service, for example `sidd-ai-video-studio-api`.
14. Click **Deploy** and watch the build logs.

During the build you should see both SHA-256 checks report `OK`. The first
build downloads Python wheels, Chromium, HyperFrames and the two models, so it
is expected to take longer than a small FastAPI image.

When Koyeb shows a domain such as `https://...koyeb.app`, test it before
touching Vercel:

```bash
curl -fsS https://YOUR-BACKEND-DOMAIN/api/health
curl -fsS https://YOUR-BACKEND-DOMAIN/api/voices
```

In `/api/voices`, check:

```json
"piper_voices": {
  "voices": {
    "male":   { "available": true, "model": "en_US-joe-medium.onnx" },
    "female": { "available": true, "model": "en_US-amy-medium.onnx" }
  }
}
```

Then test a real synthesis:

```bash
curl -fsS https://YOUR-BACKEND-DOMAIN/api/voices/preview \
  -H 'Content-Type: application/json' \
  -d '{"text":"Guard your left flank!","voice_id":"en_male_heroic"}'
```

The response must contain:

```text
"engine_used": "piper-onnx-local"
"voice_model": "en_US-joe-medium.onnx"
```

## Option B: strict no-card Docker trial (Back4App)

1. Create a Back4App account; its container pricing page says the free tier
   requires no credit card.
2. Open **Web Deployment / Containers** and create a new app from GitHub.
3. Select `MDSIDD533/website` and `arena/49e70a96-website`.
4. If a Dockerfile path field is offered, set `Dockerfile.backend`.
5. Set/confirm port `8000` and health check `/api/health`.
6. Add the variables from `deploy/backend.env.example`.
7. Deploy and test `/api/health` and `/api/voices` as above.

Back4App's free size is only 256 MB RAM. If the process is killed/OOMs, that
is a capacity limit, not proof that the Dockerfile is invalid. Use this option
as a no-card smoke test rather than a guaranteed render server.

## Option C: strict no-card Docker trial (SnapDeploy)

1. Create a SnapDeploy account and choose a GitHub/Docker deployment.
2. Select this repository/branch and set the Dockerfile to
   `Dockerfile.backend` if the UI asks.
3. Expose port `8000`; add `deploy/backend.env.example` values.
4. Deploy, then repeat the same health/voices checks.

SnapDeploy's current pricing says free containers sleep after 15 idle minutes,
share 100 running hours/month, and WebSocket apps require Always-On. The UI
has polling fallback, but live job updates may be limited on the free plan.

---

# Step 2 — Deploy the React frontend on Vercel

1. Log in to Vercel with GitHub.
2. **Add New → Project** and import `MDSIDD533/website`.
3. Production branch: `arena/49e70a96-website` for now, or `main` after merge.
4. **Root Directory:** `frontend`.
5. Framework preset: **Vite**.
6. Install command: `npm ci --no-audit --no-fund`.
7. Build command: `npm run build`.
8. Output directory: `dist`.
9. Before the first deploy, add this Production environment variable:

```text
VITE_API_BASE_URL=https://YOUR-BACKEND-DOMAIN
```

Do not add a trailing slash. `VITE_WS_URL` is optional; if omitted, the app
derives `wss://YOUR-BACKEND-DOMAIN/ws/jobs` from the API URL.

10. Click **Deploy**.
11. Open the Vercel URL and verify:
    - `/` loads the studio;
    - `/studio` loads after a hard refresh (SPA rewrite);
    - projects/jobs/voices data load without CORS errors;
    - browser devtools show requests going to the backend domain;
    - Voice Studio preview returns `piper-onnx-local`;
    - a generated artifact/download URL opens from the backend domain.

Changing a `VITE_*` value requires a **new Vercel deployment** because Vite
embeds it into the browser bundle at build time.

## Local production-build check

The frontend can be tested before deployment with:

```bash
cd frontend
npm ci --no-audit --no-fund
VITE_API_BASE_URL=https://YOUR-BACKEND-DOMAIN npm run build
```

For local development, leave `VITE_API_BASE_URL` empty; Vite's existing
`/api` and `/ws` proxies continue to target `127.0.0.1:8000`.

---

# Step 3 — Understand storage, jobs and security

## Storage is not permanent on the free container

The backend defaults in Docker are:

```text
SIDD_WORKSPACE_DIR=/tmp/sidd-workspace
SIDD_DATABASE_PATH=/tmp/sidd-workspace/sidd_studio.db
SIDD_MODELS_DIR=/opt/sidd-models
```

Models survive because they are baked into the image. Projects, SQLite rows,
job state and generated MP4s under `/tmp` can vanish on restart/redeploy.
Download finished videos immediately. Real permanence later requires one of:

- a persistent volume for workspace/database; and/or
- object storage for generated MP4s; and/or
- an external database instead of local SQLite.

## Render capacity

`SIDD_MAX_CONCURRENT_JOBS=1` is intentional. A free 512 MB instance can still
run out of memory when Chromium, HyperFrames, FFmpeg and Piper compete. Test
in this order:

1. `/api/health`
2. voice preview
3. build-only motion project
4. one short 720p/30 fps render
5. only then try 1080p

If a render is killed with no Python traceback, check host metrics for OOM.

## Public URL safety

The application currently has no end-user login/auth layer around all studio
operations. Anyone with the backend/frontend URLs may be able to create
projects, queue expensive jobs, upload files or delete data exposed by the API.
Do not advertise the URL as a public production service until authentication,
rate limits and upload/job quotas are added.

The backend CORS policy is currently permissive (`allow_origins=["*"]`) so
the separate Vercel origin works. Tighten it to the final Vercel/custom domain
before a wider launch.

## Custom domains

- Vercel: Project → Settings → Domains.
- Backend host: add the API subdomain in that host, then update
  `VITE_API_BASE_URL` and redeploy Vercel.
- Always use HTTPS/WSS in production; browsers block insecure WebSockets from
  an HTTPS page.

---

# Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Vercel site opens but all data fails | Wrong/missing `VITE_API_BASE_URL`, or frontend was built before setting it | Browser Network tab; redeploy after changing env |
| Backend health works, UI still fails CORS | Wrong backend URL or host redirects HTTP→HTTPS oddly | Test with `curl -i`; current FastAPI CORS is wildcard |
| WebSocket shows disconnected | Host/proxy blocks WS or `wss://` URL is wrong | Test API polling; set `VITE_WS_URL=wss://.../ws/jobs` explicitly |
| `/api/voices` says Piper unavailable | Model stage did not run or wrong Dockerfile/models dir | Build log SHA checks; ensure `Dockerfile.backend`, `SIDD_MODELS_DIR=/opt/sidd-models` |
| Voice response says `espeak-ng-local` | Piper pair/runtime unavailable, so truthful fallback ran | Check `/api/voices` `piper_voices`; do not call that output neural |
| Docker build fails on model download | Builder cannot reach Hugging Face/CDN | Retry; otherwise prebuild image and deploy from a registry, retaining hash checks |
| Container restarts during render | OOM on 256–512 MB | Lower resolution/FPS, one job, shorten script, or use a larger/self-hosted machine |
| Projects disappear after redeploy | Ephemeral `/tmp` workspace/SQLite | Download outputs; add persistent volume/object storage |
| First request is slow | Free service slept/scaled to zero | Wait for cold start; no free always-on guarantee |
| Koyeb asks for card/plan charge | Current Koyeb policy | Stop if no-card is mandatory; use a no-card trial host or self-host |

## Most capable no-card alternative for real renders

Run the same backend on a computer you own and expose only HTTPS/WSS through a
tunnel you control. That keeps the large models, Chromium workload and output
files on real local storage and avoids a 512 MB container. The public site is
then available only while that computer and tunnel are running, so it is
“free” rather than cloud-permanent.

---

# Official references checked 31 October 2026

- Vercel Hobby plan and limits:
  https://vercel.com/docs/plans/hobby
- Koyeb Free Instance size/limitations:
  https://www.koyeb.com/docs/reference/instances#free-instances
- Koyeb pricing FAQ — card and US$29 pre-authorization:
  https://www.koyeb.com/docs/faqs/pricing
- Koyeb FastAPI deployment:
  https://www.koyeb.com/docs/deploy/fastapi
- Back4App Containers pricing/free tier:
  https://www.back4app.com/pricing/container-as-a-service
- SnapDeploy pricing/free limitations:
  https://snapdeploy.dev/pricing
- Piper voices repository:
  https://huggingface.co/rhasspy/piper-voices
