#!/usr/bin/env bash
# Render build script: installs Python deps, installs Node via
# nodeenv, then builds the React/Vite SPA bundle that Flask serves
# at /app/*. Render's "Native Runtime" Python service ships Python
# only — Node has to be added explicitly. We use `nodeenv` because
# it's a pip-installable Python package that drops Node into the
# active Python prefix's bin/, so node + npm land on PATH for the
# remainder of this buildCommand without sudo / apt / system
# changes.
#
# Run locally:
#   ./scripts/build.sh
#
# render.yaml's buildCommand calls this script.
#
# Idempotent: pip and nodeenv both no-op if already-installed,
# and `npm ci` always replaces node_modules from package-lock so
# repeated runs produce a deterministic dist/.
set -euo pipefail

# Pinned Node major. Bump this in lockstep with frontend's
# `engines.node` so dev + CI + Render all match. Vite 8 requires
# Node 22.12+ (see https://vite.dev/guide/migration); 22.20.0 is
# the latest LTS as of this writing.
NODE_VERSION="22.20.0"

echo "==> Python deps"
pip install -r requirements.txt

echo "==> Install Node ${NODE_VERSION} via nodeenv"
pip install --quiet --upgrade nodeenv
# `-p` installs Node into the currently active Python prefix's
# bin/, which is on PATH for the rest of the build. `--prebuilt`
# downloads a prebuilt binary instead of compiling from source —
# critical on Render where the build step is time-bounded.
nodeenv --prebuilt --node="${NODE_VERSION}" --python-virtualenv -p
echo "node $(node --version), npm $(npm --version)"

echo "==> Frontend build"
cd "$(dirname "$0")/.."
cd frontend
npm ci --no-audit --no-fund --silent
npm run build
echo "==> Frontend bundle:"
ls -lh dist/index.html dist/assets/*.js dist/assets/*.css 2>/dev/null || true
