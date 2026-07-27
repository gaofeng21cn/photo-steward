#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATUS_DIR="$ROOT_DIR/state/status"
source "$ROOT_DIR/scripts/lib/automation_common.sh"

if ! resolve_python; then
  notify_sync "Python runtime unavailable"
  exit 127
fi

mkdir -p "$ROOT_DIR/tmp/automation"
cd "$ROOT_DIR"

if "$PYTHON_BIN" -m tools.icloud_photo_sync.cli todo-plan-job "$@"; then
  :
else
  exit_code=$?
  notify_sync "scheduled todo plan failed"
  exit "$exit_code"
fi

PLAN_MESSAGE="$("$PYTHON_BIN" - "$STATUS_DIR/latest_todo_plan.json" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)
payload = json.loads(path.read_text())
summary = payload.get('summary', {})
copy_count = int(summary.get('copy_count', 0))
move_count = int(summary.get('move_count', 0))
unresolved = int(summary.get('unresolved_count', 0))
if copy_count or move_count or unresolved:
    print(f'todo plan ready: copy={copy_count} move={move_count} unresolved={unresolved}')
PY
)"

if [[ -n "$PLAN_MESSAGE" ]]; then
  notify_sync "$PLAN_MESSAGE"
fi

exit 0
