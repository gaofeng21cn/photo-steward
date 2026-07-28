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
  record_job_failure plan "NAS mount preflight failed" 75
  notify_sync "NAS mount unavailable; scheduled plan skipped"
  exit 75
fi

if photo_cli plan-job "$@"; then
  :
else
  exit_code=$?
  notify_sync "scheduled plan failed"
  exit "$exit_code"
fi

PLAN_MESSAGE="$(photo_cli status --scope photo --format json | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
summary = payload.get("jobs", {}).get("plan", {}).get("summary", {})
mirror = int(summary.get("mirror_count", 0))
delete = int(summary.get("delete_count", 0))
unresolved = int(summary.get("unresolved_count", 0))
if mirror or delete or unresolved:
    print(f"plan ready: mirror={mirror} delete={delete} unresolved={unresolved}")
')"

if [[ -n "$PLAN_MESSAGE" ]]; then
  notify_sync "$PLAN_MESSAGE"
fi

exit 0
