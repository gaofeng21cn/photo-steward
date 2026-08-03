#!/bin/sh
set -eu

NAS_HOST="${PHOTO_STEWARD_NAS_HOST:-}"
REMOTE_HOME="${PHOTO_STEWARD_NAS_HOME:-}"

if [ -z "$NAS_HOST" ]; then
  echo "Set PHOTO_STEWARD_NAS_HOST to an SSH destination, for example user@nas.local." >&2
  exit 2
fi

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
if [ -z "$REMOTE_HOME" ]; then
  REMOTE_HOME="$(ssh "$NAS_HOST" 'printf %s "$HOME"')"
fi
REMOTE_DIR="$REMOTE_HOME/.local/share/photo-steward"

ssh "$NAS_HOST" "mkdir -p '$REMOTE_DIR'"
rsync -a "$ROOT_DIR/scripts/nas/photo_steward_nas_worker.py" "$NAS_HOST:$REMOTE_DIR/photo_steward_nas_worker.py"
DRY_RUN_RECEIPT="$(ssh "$NAS_HOST" "chmod 755 '$REMOTE_DIR/photo_steward_nas_worker.py'; '$REMOTE_DIR/photo_steward_nas_worker.py' --nas-home '$REMOTE_HOME' --dry-run")"
printf '%s\n' "$DRY_RUN_RECEIPT"

ssh "$NAS_HOST" "python3 - '$REMOTE_DIR' '$DRY_RUN_RECEIPT'" <<'PY'
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

remote_dir = Path(sys.argv[1])
worker_receipt = Path(sys.argv[2])
worker = remote_dir / "photo_steward_nas_worker.py"
payload = {
    "schema_version": 1,
    "status": "worker_ready",
    "installed_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "worker_path": str(worker),
    "worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(),
    "dry_run_receipt": str(worker_receipt),
    "scheduler": "synology_dsm_task_scheduler",
    "scheduler_status": "not_installed",
    "cloud_sync_status": "not_verified",
}
(remote_dir / "deployment.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

cat <<EOF
NAS worker installed and dry-run receipt verified.

Create one DSM Task Scheduler entry as this NAS user:
  Schedule: weekly, Sunday, 04:00
  Command: $REMOTE_DIR/photo_steward_nas_worker.py --nas-home $REMOTE_HOME

Retention remains audit-only. Add --apply-retention only after reviewing the
candidate_roots in the latest NAS receipt and explicitly approving deletion.

Do not disable the Mac fallback jobs until DSM Task Scheduler and Cloud Sync
have been verified and recorded in the local nas-jobs-external receipt.
EOF
