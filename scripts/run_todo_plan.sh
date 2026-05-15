#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/Users/gaofeng/.py-global/bin/python3}"

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"icloud-photo-sync\"" >/dev/null 2>&1 || true
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python runtime missing: $PYTHON_BIN" >&2
  exit 127
fi

mkdir -p "$ROOT_DIR/tmp/automation"
cd "$ROOT_DIR"

"$PYTHON_BIN" -m tools.icloud_photo_sync.cli todo-plan-job "$@"
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  notify "scheduled todo plan failed"
  exit $exit_code
fi

PLAN_MESSAGE="$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
import json

path = Path('/Users/gaofeng/workspace/app/icloud-photo-sync/state/status/latest_todo_plan.json')
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
  notify "$PLAN_MESSAGE"
fi

exit 0
