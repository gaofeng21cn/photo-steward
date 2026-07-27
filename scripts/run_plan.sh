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

if ! wait_for_nas_mount; then
  record_job_failure plan "NAS mount preflight failed" 75
  notify_sync "NAS mount unavailable; scheduled plan skipped"
  exit 75
fi

if "$PYTHON_BIN" -m tools.icloud_photo_sync.cli plan-job "$@"; then
  :
else
  exit_code=$?
  notify_sync "scheduled plan failed"
  exit "$exit_code"
fi

PLAN_MESSAGE="$("$PYTHON_BIN" - "$STATUS_DIR/latest_plan.json" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)
payload = json.loads(path.read_text())
summary = payload.get('summary', {})
mirror = int(summary.get('mirror_count', 0))
delete = int(summary.get('delete_count', 0))
unresolved = int(summary.get('unresolved_count', 0))
if mirror or delete or unresolved:
    print(f'plan ready: mirror={mirror} delete={delete} unresolved={unresolved}')
PY
)"

if [[ -n "$PLAN_MESSAGE" ]]; then
  notify_sync "$PLAN_MESSAGE"
fi

exit 0
