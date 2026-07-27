#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/automation_common.sh"

if ! resolve_python; then
  notify_sync "Python runtime unavailable"
  exit 127
fi

mkdir -p "$ROOT_DIR/tmp/automation"
cd "$ROOT_DIR"

if "$PYTHON_BIN" -m tools.icloud_photo_sync.cli prune-deleted-pool "$@"; then
  exit 0
else
  exit_code=$?
  notify_sync "deleted pool retention failed"
  exit "$exit_code"
fi
