# syntax=docker/dockerfile:1

# --- Frontend production bundle -------------------------------------------
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Pinned HyperFrames CLI ------------------------------------------------
FROM node:22-bookworm-slim AS hyperframes-runtime
WORKDIR /opt/hyperframes-runtime
RUN npm init -y >/dev/null 2>&1 \
    && npm install --omit=dev --no-audit --no-fund hyperframes@0.8.220

# --- Runtime ---------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    SIDD_HOST=0.0.0.0 \
    SIDD_WORKSPACE_DIR=/tmp/sidd-workspace \
    SIDD_MODELS_DIR=/tmp/sidd-models \
    SIDD_DATABASE_PATH=/tmp/sidd-workspace/sidd_studio.db \
    SIDD_LOG_DIR=/tmp/sidd-logs \
    SIDD_LOCAL_ONLY_DEFAULT=false \
    SIDD_ALLOW_MODEL_DOWNLOADS=false \
    SIDD_MAX_CONCURRENT_JOBS=1 \
    SIDD_HYPERFRAMES_BIN=/opt/hyperframes-runtime/node_modules/.bin/hyperframes \
    SIDD_HYPERFRAMES_BROWSER_PATH=/usr/local/bin/chromium-render \
    HYPERFRAMES_BROWSER_PATH=/usr/local/bin/chromium-render \
    HYPERFRAMES_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        ffmpeg \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# Node is needed only to execute the pinned HyperFrames CLI. Copying the
# interpreter and the preinstalled CLI avoids a full Node/npm runtime layer.
COPY --from=hyperframes-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=hyperframes-runtime /opt/hyperframes-runtime /opt/hyperframes-runtime

RUN printf '#!/bin/sh\nexec /usr/bin/chromium --no-sandbox --disable-dev-shm-usage "$@"\n' \
        > /usr/local/bin/chromium-render \
    && chmod +x /usr/local/bin/chromium-render \
    && mkdir -p /tmp/sidd-workspace /tmp/sidd-models /tmp/sidd-logs

WORKDIR /app

COPY requirements.render.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.render.txt

COPY . .
COPY --from=frontend-build /src/frontend/dist ./frontend/dist

EXPOSE 7860

# Hugging Face Spaces expects the app on port 7860 by default; PORT can override it.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
