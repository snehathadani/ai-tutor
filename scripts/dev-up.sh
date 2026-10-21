#!/usr/bin/env bash
# Dev entry point for podman-compose 1.0.6: `down --remove-orphans` first
# guarantees a clean slate (no containers, no taken names), so a plain
# `up -d --build` recreates every container from the freshly built images.
# `--force-recreate` is deliberately not used: its stop pass logs one
# "exit code: 125" complaint per container `down` already removed.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> podman-compose down --remove-orphans"
# Tolerated: a fresh checkout has nothing to remove yet.
podman-compose down --remove-orphans || echo "down failed (nothing running yet) - continuing"

echo "==> podman-compose up -d --build"
podman-compose up -d --build

echo "==> podman-compose ps"
podman-compose ps
