#!/usr/bin/env bash
# Dev entry point for podman-compose 1.0.6, which does not recreate existing
# containers on a plain `up -d --build`: it errors on the already-taken names,
# falls back to `podman start`, and keeps serving the stale image. Tearing down
# first and force-recreating guarantees rebuilt code is what actually runs.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> podman-compose down --remove-orphans"
# Tolerated: a fresh checkout has nothing to remove yet.
podman-compose down --remove-orphans || echo "down failed (nothing running yet) - continuing"

echo "==> podman-compose up -d --build --force-recreate"
podman-compose up -d --build --force-recreate

echo "==> podman-compose ps"
podman-compose ps
