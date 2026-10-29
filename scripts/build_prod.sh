#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  npm install
fi
npm run build
echo "[SIDD STUDIO] Production frontend built into frontend/dist (served directly by FastAPI on port 8000)."
