#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "[SIDD STUDIO] Creating Python virtual environment (.venv)..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/python scripts/setup_headless_bpy.py

echo "[SIDD STUDIO] Starting FastAPI backend on 0.0.0.0:8000..."
PYTHONPATH="$ROOT_DIR" .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  npm install
fi

echo "[SIDD STUDIO] Starting Vite dev server on 0.0.0.0:5173..."
npm run dev
