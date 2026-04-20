#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/.migration_bundles}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
HOST_TAG="${HOSTNAME:-$(hostname 2>/dev/null || echo server)}"
ARCHIVE_NAME="sequencer-log-platform_migration_${HOST_TAG}_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"
CHECKSUM_PATH="$ARCHIVE_PATH.sha256"

mkdir -p "$OUTPUT_DIR"

tar \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./venv' \
  --exclude='./__pycache__' \
  --exclude='./.pytest_cache' \
  --exclude='./.pytest_tmp_run' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/.next' \
  --exclude='./.deploy_backups' \
  --exclude='./.migration_bundles' \
  --exclude='./.codex_deploy_bundle' \
  --exclude='./.tmp_real_logs' \
  -czf "$ARCHIVE_PATH" \
  -C "$ROOT_DIR" \
  .

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARCHIVE_PATH" > "$CHECKSUM_PATH"
fi

echo "Migration bundle created:"
echo "  archive:  $ARCHIVE_PATH"
if [[ -f "$CHECKSUM_PATH" ]]; then
  echo "  checksum: $CHECKSUM_PATH"
fi
du -h "$ARCHIVE_PATH"
