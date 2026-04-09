#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == "--plan-dir" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "missing value for --plan-dir" >&2
    exit 2
  fi
  exec /usr/bin/python3 -m tools.icloud_photo_sync.cli apply --plan-dir "$1"
fi

if [[ "${1:-}" == "--latest" ]]; then
  PLAN_DIR="$(/usr/bin/python3 - <<'PY'
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
  exec /usr/bin/python3 -m tools.icloud_photo_sync.cli apply --plan-dir "$PLAN_DIR"
fi

echo "usage: $0 --plan-dir <plan_dir> | --latest" >&2
exit 2

