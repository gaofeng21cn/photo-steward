#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/Users/gaofeng/.py-global/bin/python3}"
cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python runtime missing: $PYTHON_BIN" >&2
  exit 127
fi

if [[ "${1:-}" == "--plan-dir" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "missing value for --plan-dir" >&2
    exit 2
  fi
  exec "$PYTHON_BIN" -m tools.icloud_photo_sync.cli apply-job --plan-dir "$1"
fi

if [[ "${1:-}" == "--latest" ]]; then
  PLAN_DIR="$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
import json

logs_root = Path("/Volumes/home/Photos_SyncLogs")
candidates = []
for summary in logs_root.glob("*/**/plan_summary.json"):
    try:
        data = json.loads(summary.read_text())
    except Exception:
        continue
    candidates.append((summary.stat().st_mtime_ns, str(summary.parent), data.get("plan_id", "")))

if not candidates:
    raise SystemExit(1)

candidates.sort()
print(candidates[-1][1])
PY
)"
if [[ -z "$PLAN_DIR" ]]; then
    echo "no plan found" >&2
    exit 1
  fi
  exec "$PYTHON_BIN" -m tools.icloud_photo_sync.cli apply-job --plan-dir "$PLAN_DIR"
fi

echo "usage: $0 --plan-dir <plan_dir> | --latest" >&2
exit 2
