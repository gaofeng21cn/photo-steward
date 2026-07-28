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

if photo_cli todo-plan-job "$@"; then
  :
else
  exit_code=$?
  notify_sync "scheduled todo plan failed"
  exit "$exit_code"
fi

PLAN_MESSAGE="$(photo_cli status --scope todo --format json | "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
summary = payload.get("jobs", {}).get("todo_plan", {}).get("summary", {})
copy_count = int(summary.get('copy_count', 0))
move_count = int(summary.get('move_count', 0))
unresolved = int(summary.get('unresolved_count', 0))
if copy_count or move_count or unresolved:
    print(f'todo plan ready: copy={copy_count} move={move_count} unresolved={unresolved}')
')"

if [[ -n "$PLAN_MESSAGE" ]]; then
  notify_sync "$PLAN_MESSAGE"
fi

exit 0
