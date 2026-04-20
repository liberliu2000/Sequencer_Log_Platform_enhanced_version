#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${1:-online-version}"
REMOTE="${REMOTE_NAME:-origin}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}"

cd "$ROOT_DIR"

echo "[1/5] Fetch latest branch and tags"
git fetch "$REMOTE" "$BRANCH" --tags

echo "[2/5] Checkout branch: $BRANCH"
git checkout "$BRANCH"

echo "[3/5] Fast-forward pull from $REMOTE/$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"

echo "[4/5] Restart application containers"
if docker compose version >/dev/null 2>&1; then
  docker compose -f "$COMPOSE_FILE" up -d --build
  docker compose -f "$COMPOSE_FILE" ps
else
  PYTHONNOUSERSITE=1 docker-compose -f "$COMPOSE_FILE" up -d --build
  PYTHONNOUSERSITE=1 docker-compose -f "$COMPOSE_FILE" ps
fi

echo "[5/5] Verify current commit and API health"
git rev-parse HEAD
if command -v curl >/dev/null 2>&1; then
  curl --fail --silent --show-error "$API_HEALTH_URL"
  echo
else
  echo "curl not found; skip API health check."
fi

echo "Server deployment finished."
