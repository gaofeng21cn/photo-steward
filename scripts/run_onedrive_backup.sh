#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/automation_common.sh"
cd "$ROOT_DIR"

if ! resolve_python; then
  notify_sync "Python runtime unavailable"
  exit 127
fi
if ! resolve_photo_config; then
  notify_sync "Photo Steward configuration unavailable"
  exit 2
fi

if ! wait_for_nas_mount; then
  record_job_failure onedrive "NAS mount preflight failed" 75
  notify_sync "NAS mount unavailable; backup skipped"
  exit 75
fi

if photo_cli backup-onedrive "$@"; then
  exit 0
else
  exit_code=$?
  notify_sync "OneDrive backup failed"
  exit "$exit_code"
fi
