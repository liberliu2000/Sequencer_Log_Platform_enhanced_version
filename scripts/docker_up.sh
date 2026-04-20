#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.oneclick.yml}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.docker}"
ENV_EXAMPLE_FILE="${ENV_EXAMPLE_FILE:-$ROOT_DIR/.env.docker.example}"

mkdir -p \
  "$ROOT_DIR/data/uploads" \
  "$ROOT_DIR/data/exports" \
  "$ROOT_DIR/data/runtime_logs" \
  "$ROOT_DIR/data/intermediate_cache" \
  "$ROOT_DIR/data/tmp"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
  echo "Created $ENV_FILE from template. Adjust NEXT_PUBLIC_API_BASE_URL if this server is accessed remotely."
fi

set -a
source "$ENV_FILE"
set +a

if docker compose version >/dev/null 2>&1; then
  docker compose -f "$COMPOSE_FILE" up -d --build
  docker compose -f "$COMPOSE_FILE" ps
elif command -v docker-compose >/dev/null 2>&1; then
  PYTHONNOUSERSITE=1 docker-compose -f "$COMPOSE_FILE" up -d --build
  PYTHONNOUSERSITE=1 docker-compose -f "$COMPOSE_FILE" ps
else
  echo "docker compose is not installed." >&2
  exit 1
fi

echo "API:       http://127.0.0.1:${HOST_API_PORT:-8000}"
echo "Web:       http://127.0.0.1:${HOST_WEB_PORT:-3000}"
echo "Streamlit: http://127.0.0.1:${HOST_STREAMLIT_PORT:-8501}"
